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
        self.camera = CameraControl(width=359, height=270, jpeg_quality=5)
        self.mic = Microphone(50)
        self.AudioOutput = AudioOutput()

        # Buffers
        self.sync_buffer = {}
        self.send_queue = queue.Queue()
        self.UI_queue = queue.Queue()
        self.remote_video_queue = queue.Queue()

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

        # sync config
        self.sync_bucket = 0.05      # 50ms buckets
        self.playback_delay = 0.10   # 100ms jitter buffer

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

        threading.Thread(target=self.playback_loop, daemon=True).start()
        threading.Thread(target=self.receive_video_loop, daemon=True).start()
        threading.Thread(target=self.receive_audio_loop, daemon=True).start()

        try:
            while self.running:
                if self.meeting_start_time is not None:
                    timestamp = time.time() - float(self.meeting_start_time)

                    # local camera preview + send
                    frame = self.camera.get_frame()
                    if frame is not None:
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

                    # local audio send
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
            if hasattr(self, "AudioOutput"):
                self.AudioOutput.stop()
        except Exception as e:
            print("audio output stop error:", e)

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
        if opcode in self.commands:
            self.commands[opcode](data)

    def handle_msgs_from_host(self):
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
        try:
            if isinstance(data, list):
                self.meeting_start_time = float(data[0])
            else:
                self.meeting_start_time = float(data)
            print("meeting start time:", self.meeting_start_time)
        except Exception as e:
            print("meeting start time parse error:", e)

    def _get_sync_ts(self, timestamp):
        return round(float(timestamp) / self.sync_bucket) * self.sync_bucket

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

                # incoming media timestamp is already relative to meeting start
                sync_ts = self._get_sync_ts(timestamp)

                if client_ip not in self.sync_buffer:
                    self.sync_buffer[client_ip] = {}

                if sync_ts not in self.sync_buffer[client_ip]:
                    self.sync_buffer[client_ip][sync_ts] = {"audio": None, "video": None}

                self.sync_buffer[client_ip][sync_ts]["video"] = frame
                self._prune_old_frames(client_ip, keep=20)

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

                # incoming media timestamp is already relative to meeting start
                sync_ts = self._get_sync_ts(timestamp)

                if client_ip not in self.sync_buffer:
                    self.sync_buffer[client_ip] = {}

                if sync_ts not in self.sync_buffer[client_ip]:
                    self.sync_buffer[client_ip][sync_ts] = {"video": None, "audio": None}

                self.sync_buffer[client_ip][sync_ts]["audio"] = audio_bytes
                self._prune_old_frames(client_ip, keep=20)

            time.sleep(0.005)

    def _prune_old_frames(self, client_ip, keep=20):
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

    def playback_loop(self):
        """
        Play synced audio and send synced remote video to GUI.
        """
        while self.running:
            if self.meeting_start_time is None:
                time.sleep(0.01)
                continue

            current_time = time.time() - float(self.meeting_start_time)

            for client_ip in list(self.sync_buffer.keys()):
                if client_ip not in self.sync_buffer:
                    continue

                timestamps = sorted(self.sync_buffer[client_ip].keys())

                for ts in timestamps:
                    if ts > current_time - self.playback_delay:
                        break

                    data = self.sync_buffer[client_ip].get(ts, {})
                    frame = data.get("video")
                    audio = data.get("audio")

                    if audio is not None:
                        try:
                            self.AudioOutput.play_bytes(audio)
                        except Exception as e:
                            print("audio play error:", e)

                    if frame is not None:
                        while self.remote_video_queue.qsize() >= 3:
                            try:
                                self.remote_video_queue.get_nowait()
                            except queue.Empty:
                                break
                        self.remote_video_queue.put((client_ip, frame))

                    if ts in self.sync_buffer[client_ip]:
                        del self.sync_buffer[client_ip][ts]

            time.sleep(0.01)

    # =====================
    # Command handlers
    # =====================

    def handle_video(self, client_ip, username, timestamp, frame):
        sync_ts = self._get_sync_ts(timestamp)

        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}

        if sync_ts not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][sync_ts] = {"audio": None, "video": None}

        self.sync_buffer[client_ip][sync_ts]["video"] = frame
        self._prune_old_frames(client_ip, keep=20)

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

        sync_ts = self._get_sync_ts(timestamp)

        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}

        if sync_ts not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][sync_ts] = {"audio": None, "video": None}

        self.sync_buffer[client_ip][sync_ts]["audio"] = audio
        self._prune_old_frames(client_ip, keep=20)

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
        self.running = False
        self.cleanup()