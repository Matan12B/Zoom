import threading
import time
import socket
import queue
import cv2

from Client.Devices.Camera import CameraControl
from Client.Devices.Microphone import Microphone
from Client.Devices.AudioOutputDevice import AudioOutput
from Client.GUI.VideoDisplay import VideoDisplay
from Client.Comms.videoComm import VideoComm
from Client.Comms.audioComm import AudioClient
from Client.Protocol import clientProtocol
from Common.Cipher import AESCipher
from Client.Comms.ClientComm import ClientComm


class CallLogic:
    """
    Guest call logic (LAN P2P)
    """

    def __init__(self, port, meeting_key, comm, host_ip):
        self.open_clients = {}          # {ip: port}
        self.msgs_from_host = queue.Queue()
        self.display = VideoDisplay()
        self.comm_with_server = comm
        self.AES = AESCipher(meeting_key)

        self.comm_with_host = ClientComm(host_ip, port, self.msgs_from_host, self.AES)

        # Media comm
        self.video_comm = VideoComm(self.AES, self.open_clients)
        self.audio_comm = AudioClient(host_ip, self.AES)

        # Host is always connected
        self.open_clients[host_ip] = port

        # Local devices
        self.camera = CameraControl(width=359, height=270, jpeg_quality=60)
        self.mic = Microphone(50)
        self.AudioOutput = AudioOutput()

        # Buffers
        self.sync_buffer = {}
        self.UI_queue = queue.Queue()
        self.send_queue = queue.Queue()

        # Timing/network identity
        self.meeting_start_time = None
        self.ip = socket.gethostbyname(socket.gethostname())

        self.commands = {
            "ha": self.handle_audio,
            "hj": self.handle_join,
            "hd": self.handle_disconnect,
            "gmst": self.get_meeting_start_time
        }

        self.running = True

    def start(self):
        """
        Start camera/mic, wait for meeting start time,
        then send local video/audio and receive remote media.
        """
        print("Starting guest call...")

        self.camera.start()
        self.mic.start()
        self.mic.unmute()

        threading.Thread(target=self.handle_msgs_from_host, daemon=True).start()

        while self.running and self.meeting_start_time is None:
            time.sleep(0.01)

        if not self.running:
            return

        threading.Thread(target=self.receive_video_loop, daemon=True).start()
        threading.Thread(target=self.receive_audio_loop, daemon=True).start()

        try:
            while self.running:
                if self.meeting_start_time is not None:
                    timestamp = time.time() - float(self.meeting_start_time)

                    # -------- local camera preview + send --------
                    frame = self.camera.get_frame()
                    if frame is not None:
                        # keep only newest self frame for GUI
                        while self.UI_queue.qsize() >= 1:
                            try:
                                self.UI_queue.get_nowait()
                            except queue.Empty:
                                break

                        self.UI_queue.put(frame.copy())

                        ok, encoded = cv2.imencode('.jpg', frame)
                        if ok:
                            frame_bytes = encoded.tobytes()
                            frame_data = clientProtocol.build_video_msg(timestamp, frame_bytes)
                            self.video_comm.send_frame(frame_data)

                    # -------- local audio send --------
                    if self.mic.running:
                        audio_chunk = self.mic.record()
                        if audio_chunk:
                            audio_msg = clientProtocol.build_audio_msg(timestamp, audio_chunk, self.ip)
                            self.audio_comm.send_audio(audio_msg)

                time.sleep(0.01)

        except KeyboardInterrupt:
            print("Call interrupted.")
        finally:
            self.cleanup()

    def cleanup(self):
        """
        Stop devices and communications.
        """
        if not self.running:
            print("Closing guest call...")
        else:
            print("Closing guest call...")

        self.running = False

        try:
            if hasattr(self, "camera"):
                self.camera.stop()
        except Exception as e:
            print("camera stop error:", e)

        try:
            if hasattr(self, "mic"):
                self.mic.stop()
                self.mic.close()
        except Exception as e:
            print("mic stop error:", e)

        try:
            if hasattr(self, "video_comm"):
                self.video_comm.close()
        except Exception as e:
            print("video close error:", e)

        try:
            if hasattr(self, "audio_comm") and hasattr(self.audio_comm, "close"):
                self.audio_comm.close()
        except Exception as e:
            print("audio close error:", e)

        try:
            if hasattr(self, "comm_with_host") and hasattr(self.comm_with_host, "close"):
                self.comm_with_host.close()
        except Exception as e:
            print("host comm close error:", e)

    def handle_msgs_from_client_logic(self, opcode, data):
        """
        Handle messages from outer client logic.
        """
        if opcode in self.commands:
            self.commands[opcode](data)

    def handle_msgs_from_host(self):
        """
        Handle messages from host.
        """
        print("started listening to host server")
        while self.running:
            msg = self.msgs_from_host.get()
            print(f"Received message: {msg}")

            try:
                opcode, data = clientProtocol.unpack(msg)
            except Exception as e:
                print("unpack error:", e)
                continue

            if opcode in self.commands:
                try:
                    self.commands[opcode](data)
                except Exception as e:
                    print(f"command {opcode} error:", e)

    def get_meeting_start_time(self, data):
        """
        Get meeting start time from host for timestamps sync.
        """
        try:
            if isinstance(data, list):
                self.meeting_start_time = float(data[0])
            else:
                self.meeting_start_time = float(data)
            print("meeting start time:", self.meeting_start_time)
        except Exception as e:
            print("meeting start time parse error:", e)

    def receive_video_loop(self):
        """
        Receive incoming frames into sync_buffer.
        Assumes VideoComm.frameQ returns: (frame, timestamp, addr)
        """
        while self.running:
            while not self.video_comm.frameQ.empty():
                try:
                    frame, timestamp, addr = self.video_comm.frameQ.get_nowait()
                except queue.Empty:
                    break

                client_ip = addr[0]

                if frame is None:
                    continue

                if self.meeting_start_time is None:
                    print("didnt recv start time")
                    continue

                rel_timestamp = timestamp - float(self.meeting_start_time)

                if client_ip not in self.sync_buffer:
                    self.sync_buffer[client_ip] = {}

                if rel_timestamp not in self.sync_buffer[client_ip]:
                    self.sync_buffer[client_ip][rel_timestamp] = {"audio": None, "video": None}

                self.sync_buffer[client_ip][rel_timestamp]["video"] = frame
                self._prune_old_frames(client_ip, keep=3)

            time.sleep(0.005)

    def receive_audio_loop(self):
        """
        Receive incoming audio into sync_buffer.
        """
        while self.running:
            while not self.audio_comm.audio_queue.empty():
                try:
                    audio_bytes, timestamp, sender_ip = self.audio_comm.audio_queue.get_nowait()
                except queue.Empty:
                    break

                client_ip = sender_ip

                if self.meeting_start_time is None:
                    print("didnt recv start time")
                    continue

                rel_timestamp = timestamp - float(self.meeting_start_time)

                if client_ip not in self.sync_buffer:
                    self.sync_buffer[client_ip] = {}

                if rel_timestamp not in self.sync_buffer[client_ip]:
                    self.sync_buffer[client_ip][rel_timestamp] = {"video": None, "audio": None}

                self.sync_buffer[client_ip][rel_timestamp]["audio"] = audio_bytes

            time.sleep(0.005)

    def _prune_old_frames(self, client_ip, keep=3):
        """
        Keep only the newest timestamps per remote client.
        """
        if client_ip not in self.sync_buffer:
            return

        timestamps = self.sync_buffer[client_ip]
        if len(timestamps) <= keep:
            return

        latest = sorted(timestamps.keys(), reverse=True)[:keep]
        latest = set(latest)

        for ts in list(timestamps.keys()):
            if ts not in latest:
                del timestamps[ts]

    # =====================
    # Command handlers
    # =====================

    def handle_video(self, client_ip, username, timestamp, frame):
        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}

        if timestamp not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}

        self.sync_buffer[client_ip][timestamp]["video"] = frame
        self._prune_old_frames(client_ip, keep=3)

    def handle_audio(self, data):
        """
        If host sends protocol audio control through commands.
        """
        try:
            client_ip = data[0]
            username = data[1]
            timestamp = data[2]
            audio = data[3]
        except Exception:
            return

        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}

        if timestamp not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}

        self.sync_buffer[client_ip][timestamp]["audio"] = audio

    def handle_join(self, data):
        """
        New peer joined.
        Expected: [ip, port]
        """
        try:
            ip = data[0]
            port = int(data[1])
        except Exception as e:
            print("join parse error:", e)
            return

        print(f"{ip} joined the call")
        self.open_clients[ip] = port

    def handle_disconnect(self, data):
        """
        Peer left the call.
        Expected: [ip, username] or [ip]
        """
        try:
            ip = data[0]
            username = data[1] if len(data) > 1 else ip
        except Exception as e:
            print("disconnect parse error:", e)
            return

        print(f"{username} left the call")

        if ip in self.open_clients:
            del self.open_clients[ip]

        try:
            self.video_comm.remove_user(ip, 0)
        except Exception:
            pass

        if ip in self.sync_buffer:
            del self.sync_buffer[ip]

    def leave_call(self):
        """
        Stop running and cleanup.
        """
        self.running = False
        self.cleanup()