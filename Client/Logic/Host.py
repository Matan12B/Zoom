import threading
import time
import socket
import cv2
import queue
import numpy as np

from Client.Devices.Camera import CameraControl
from Client.Devices.Microphone import Microphone
from Client.Devices.AudioOutputDevice import AudioOutput
from Client.Comms.videoComm import VideoComm
from Client.Comms.audioComm import AudioServer
from Client.GUI.VideoDisplay import VideoDisplay
from Client.Protocol import clientProtocol
from Client.Comms.ClientServerComm import ClientServer
from Common.Cipher import AESCipher


class Host:
    def __init__(self, port, meeting_key, comm):
        self.open_clients = {}   # ip -> [socket, port]
        self.msgQ = queue.Queue()
        self.display = VideoDisplay()
        self.host_comm = comm
        self.AES = AESCipher(meeting_key)

        self.host_server = ClientServer(port, self.msgQ, self.open_clients, self.AES)
        self.audio_comm = AudioServer(self.AES, self.open_clients)
        self.video_comm = VideoComm(self.AES, self.open_clients)

        hostname = socket.gethostname()
        self.ip = socket.gethostbyname(hostname)

        self.UI_queue = queue.Queue()
        self.remote_video_queue = queue.Queue()
        self.latest_remote_frames = {}

        self.commands = {
            "hj": self.handle_join,
            "hd": self.handle_disconnect
        }

        self.camera = CameraControl(jpeg_quality=5)
        self.mic = Microphone(50)
        self.AudioOutput = AudioOutput()

        # client_ip -> { sync_ts -> {"audio": ..., "video": ...} }
        self.sync_buffer = {}

        self.meeting_start_time = None
        self.running = True

    def start(self):
        print("Starting call...")

        self.camera.start()
        self.mic.start()
        self.mic.unmute()

        threading.Thread(target=self.handle_msgs_from_guests, daemon=True).start()
        threading.Thread(target=self.receive_video_loop, daemon=True).start()
        threading.Thread(target=self.receive_audio_loop, daemon=True).start()

        self.meeting_start_time = time.time()

        threading.Thread(target=self.playback_loop, daemon=True).start()

        try:
            while self.running:
                if self.meeting_start_time is not None:
                    timestamp = time.time() - self.meeting_start_time

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

                    if self.mic.running:
                        audio_chunk = self.mic.record()
                        if audio_chunk:
                            audio_msg = clientProtocol.build_audio_msg(timestamp, audio_chunk, self.ip)
                            self.audio_comm.broadcast_audio(audio_msg, self.ip)

                time.sleep(0.01)

        except KeyboardInterrupt:
            print("Call interrupted.")
        finally:
            self.close()

    def receive_video_loop(self):
        """
        Receive incoming guest video into sync_buffer.
        Works both if frameQ returns:
        - (decoded_frame, timestamp, addr)
        - (frame_bytes, timestamp, addr)
        """
        while self.running:
            while not self.video_comm.frameQ.empty():
                try:
                    video_data, timestamp, addr = self.video_comm.frameQ.get_nowait()
                except queue.Empty:
                    break

                client_ip = addr[0]
                frame = None

                try:
                    if isinstance(video_data, np.ndarray):
                        frame = video_data
                    elif isinstance(video_data, (bytes, bytearray)):
                        frame = cv2.imdecode(
                            np.frombuffer(video_data, np.uint8),
                            cv2.IMREAD_COLOR
                        )
                except Exception as e:
                    print("decode error:", e)
                    frame = None

                if frame is None:
                    continue

                if self.meeting_start_time is None:
                    continue

                rel_timestamp = float(timestamp)
                sync_ts = round(rel_timestamp / 0.05) * 0.05

                if client_ip not in self.sync_buffer:
                    self.sync_buffer[client_ip] = {}

                if sync_ts not in self.sync_buffer[client_ip]:
                    self.sync_buffer[client_ip][sync_ts] = {"audio": None, "video": None}

                self.sync_buffer[client_ip][sync_ts]["video"] = frame
                self._prune_old_frames(client_ip, keep=20)

            time.sleep(0.005)

    def receive_audio_loop(self):
        while self.running:
            while not self.audio_comm.audio_queue.empty():
                try:
                    audio_bytes, timestamp, sender_ip = self.audio_comm.audio_queue.get_nowait()
                except queue.Empty:
                    break

                client_ip = sender_ip

                if self.meeting_start_time is None:
                    continue

                rel_timestamp = float(timestamp)
                sync_ts = round(rel_timestamp / 0.05) * 0.05

                if client_ip not in self.sync_buffer:
                    self.sync_buffer[client_ip] = {}

                if sync_ts not in self.sync_buffer[client_ip]:
                    self.sync_buffer[client_ip][sync_ts] = {"video": None, "audio": None}

                self.sync_buffer[client_ip][sync_ts]["audio"] = audio_bytes
                self._prune_old_frames(client_ip, keep=20)

            time.sleep(0.005)

    def playback_loop(self):
        """
        Playback synced remote audio/video based on host meeting clock.
        Audio is played here.
        Video is pushed to remote_video_queue for the GUI.
        """
        while self.running:
            if self.meeting_start_time is None:
                time.sleep(0.01)
                continue

            current_time = time.time() - self.meeting_start_time

            for client_ip in list(self.sync_buffer.keys()):
                if client_ip not in self.sync_buffer:
                    continue

                timestamps = sorted(self.sync_buffer[client_ip].keys())

                for ts in timestamps:
                    # small delay buffer helps sync
                    if ts > current_time - 0.10:
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
                        self.latest_remote_frames[client_ip] = frame

                        while self.remote_video_queue.qsize() >= 5:
                            try:
                                self.remote_video_queue.get_nowait()
                            except queue.Empty:
                                break

                        self.remote_video_queue.put((client_ip, frame))

                    if ts in self.sync_buffer[client_ip]:
                        del self.sync_buffer[client_ip][ts]

            time.sleep(0.01)

    def _prune_old_frames(self, client_ip, keep=20):
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

    def handle_msgs_from_client_logic(self, opcode, data):
        try:
            if opcode in self.commands:
                self.commands[opcode](data)
        except Exception as e:
            print(f"Error handling message: {e}")

    def handle_msgs_from_guests(self):
        while self.running:
            msg = self.msgQ.get()
            print(f"Received message from guest: {msg}")

            try:
                guest_ip = msg[0]
                raw_msg = msg[1]
                opcode, data = clientProtocol.unpack(raw_msg)
            except Exception as e:
                print("unpack error:", e)
                continue

            if opcode == "hj":
                if isinstance(data, list):
                    if len(data) == 1:
                        data = [guest_ip, data[0]]
                    elif len(data) >= 2:
                        data[0] = guest_ip
                else:
                    data = [guest_ip, data]

            elif opcode == "hd":
                if isinstance(data, list):
                    if len(data) == 0:
                        data = [guest_ip]
                    else:
                        data[0] = guest_ip
                else:
                    data = [guest_ip]

            if opcode in self.commands:
                try:
                    self.commands[opcode](data)
                except Exception as e:
                    print(f"Error in command {opcode}: {e}")

    def handle_video(self, client_ip, username, timestamp, frame):
        sync_ts = round(float(timestamp) / 0.05) * 0.05

        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}

        if sync_ts not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][sync_ts] = {"audio": None, "video": None}

        self.sync_buffer[client_ip][sync_ts]["video"] = frame
        self._prune_old_frames(client_ip, keep=20)

    def handle_disconnect(self, data):
        ip = data[0] if len(data) > 0 else ""
        username = data[1] if len(data) > 1 else ip

        print(username, "left the call")

        try:
            self.display.remove_user(ip, username)
        except Exception:
            pass

        if ip in self.open_clients:
            del self.open_clients[ip]

        if ip in self.sync_buffer:
            del self.sync_buffer[ip]

        if ip in self.latest_remote_frames:
            del self.latest_remote_frames[ip]

        try:
            self.video_comm.remove_user(ip, 0)
        except Exception:
            pass

    def handle_join(self, data):
        ip = data[0]
        port = int(data[1])

        print("adding", ip, "to open clients")

        if ip not in self.open_clients:
            self.open_clients[ip] = [None, port]
        else:
            if isinstance(self.open_clients[ip], list) and len(self.open_clients[ip]) >= 2:
                self.open_clients[ip][1] = port
            else:
                self.open_clients[ip] = [None, port]

        time.sleep(0.1)

        while self.running and ip in self.open_clients and self.open_clients[ip][0] is None:
            time.sleep(0.01)

        if self.running and ip in self.open_clients:
            self.send_meeting_start_time(ip)

    def send_meeting_start_time(self, ip):
        print("sending start time")
        msg = clientProtocol.build_meeting_start_time(self.meeting_start_time)
        self.host_server.send_msg(ip, msg)

    def leave_call(self):
        self.close()

    def close(self):
        if not self.running:
            return

        print("Closing call...")
        self.running = False

        try:
            if hasattr(self, 'camera'):
                self.camera.stop()
        except Exception as e:
            print("camera stop error:", e)

        try:
            if hasattr(self, 'mic'):
                self.mic.stop()
                self.mic.close()
        except Exception as e:
            print("mic stop error:", e)

        try:
            if hasattr(self, 'video_comm'):
                self.video_comm.close()
        except Exception as e:
            print("video close error:", e)

        try:
            if hasattr(self, 'audio_comm') and hasattr(self.audio_comm, 'close'):
                self.audio_comm.close()
        except Exception as e:
            print("audio close error:", e)

        try:
            if hasattr(self, 'host_server') and hasattr(self.host_server, 'close'):
                self.host_server.close()
        except Exception as e:
            print("host server close error:", e)

        time.sleep(0.1)