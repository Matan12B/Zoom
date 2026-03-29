# callLogic.py

import threading
import time
import cv2
import queue
import socket
from Client.Devices.Camera import CameraControl
from Client.Devices.Microphone import Microphone
from Client.Devices.AudioOutputDevice import AudioOutput
from Client.Comms.videoComm import VideoComm
from Client.Comms.audioComm import AudioClient
from Client.Protocol import clientProtocol
from Common.Cipher import AESCipher
from Client.Comms.ClientComm import ClientComm
from Client.Logic.av_sync import AVSyncManager


class CallLogic:
    def __init__(self, port, meeting_key, comm, host_ip, meeting_code):
        self.open_clients = {}   # ip -> port
        self.msgs_from_host = queue.Queue()
        self.comm_with_server = comm
        self.AES = AESCipher(meeting_key)
        self.meeting_code = meeting_code
        self.comm_with_host = ClientComm(host_ip, port, self.msgs_from_host, self.AES)
        self.video_comm = VideoComm(self.AES, self.open_clients)
        self.audio_comm = AudioClient(host_ip, self.AES)

        self.open_clients[host_ip] = port
        self.host_ip = host_ip

        hostname = socket.gethostname()
        self.ip = socket.gethostbyname(hostname)
        self.UI_queue = queue.Queue()
        self.remote_video_queue = queue.Queue()
        self.latest_remote_frames = {}

        self.commands = {
            "ha": self.handle_audio_msg,
            "hv": self.handle_video_msg,
            "hj": self.handle_join,
            "hd": self.handle_disconnect,
            "gmst": self.get_meeting_start_time,
            "fd": self.force_disconnect
        }

        self.camera = CameraControl(jpeg_quality=5)
        self.encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
        self.mic = Microphone(50, rate=16000, channels=1, chunk=160)
        self.AudioOutput = AudioOutput(rate=16000, channels=1)
        self.av_sync = AVSyncManager(playout_delay=0.04)
        self.meeting_start_time = None
        self.running = True
        self.send_queue = queue.Queue(maxsize=1)

    def start(self):
        print("Starting guest call...")

        self.camera.start()
        self.mic.start()
        self.mic.unmute()

        threading.Thread(target=self.handle_msgs_from_host, daemon=True).start()
        threading.Thread(target=self.receive_video_loop, daemon=True).start()
        threading.Thread(target=self.receive_audio_loop, daemon=True).start()
        threading.Thread(target=self.send_loop, daemon=True).start()
        threading.Thread(target=self.audio_send_loop, daemon=True).start()
        threading.Thread(target=self.playback_loop, daemon=True).start()

        try:
            while self.running:
                frame = self.camera.get_frame()

                if frame is None:
                    time.sleep(0.005)
                    continue

                frame = frame.copy()

                while self.UI_queue.qsize() >= 1:
                    try:
                        self.UI_queue.get_nowait()
                    except queue.Empty:
                        break

                self.UI_queue.put(frame)

                if self.meeting_start_time is not None:
                    timestamp = time.time() - self.meeting_start_time

                    if self.send_queue.full():
                        try:
                            self.send_queue.get_nowait()
                        except queue.Empty:
                            pass

                    try:
                        self.send_queue.put_nowait((frame, timestamp))
                    except queue.Full:
                        pass
                time.sleep(0.002)
        except Exception as e:
            print("guest start loop error:", e)
        finally:
            self.cleanup()

    def send_loop(self):
        while self.running:
            try:
                frame, timestamp = self.send_queue.get(timeout=1)

                ok, encoded = cv2.imencode(".jpg", frame, self.encode_params)
                if not ok:
                    continue

                frame_bytes = encoded.tobytes()
                frame_data = clientProtocol.build_video_msg(timestamp, frame_bytes)
                self.video_comm.send_frame(frame_data)

            except queue.Empty:
                continue
            except Exception as e:
                print("send_loop error:", e)
                time.sleep(0.02)

    def audio_send_loop(self):
        while self.running:
            try:
                if not self.mic.running or self.meeting_start_time is None:
                    time.sleep(0.01)
                    continue

                audio_chunk = self.mic.record()
                if not audio_chunk:
                    continue

                timestamp = time.time() - self.meeting_start_time
                msg = clientProtocol.build_audio_msg(timestamp, audio_chunk, self.ip)
                self.audio_comm.send_audio(msg)

            except Exception as e:
                print("audio_send_loop error:", e)
                time.sleep(0.02)

    def receive_video_loop(self):
        while self.running:
            try:
                while not self.video_comm.frameQ.empty():
                    try:
                        video_data, timestamp, addr = self.video_comm.frameQ.get_nowait()
                    except queue.Empty:
                        break

                    sender_ip = addr[0]

                    if sender_ip not in self.open_clients:
                        self.open_clients[sender_ip] = self.open_clients.get(self.host_ip, 0)

                    if video_data is None:
                        continue

                    self.av_sync.add_video(sender_ip, float(timestamp), video_data)

                time.sleep(0.005)

            except Exception as e:
                print("receive_video_loop error:", e)
                time.sleep(0.05)

    def receive_audio_loop(self):
        while self.running:
            try:
                while not self.audio_comm.audio_queue.empty():
                    try:
                        audio_bytes, timestamp, sender_ip = self.audio_comm.audio_queue.get_nowait()
                    except queue.Empty:
                        break
                    if sender_ip not in self.open_clients:
                        self.open_clients[sender_ip] = self.open_clients.get(self.host_ip, 0)
                    self.av_sync.add_audio(sender_ip, float(timestamp), audio_bytes)
                time.sleep(0.001)
            except Exception as e:
                print("receive_audio_loop error:", e)
                time.sleep(0.01)

    def playback_loop(self):
        while self.running:
            now = time.monotonic()

            for sender_ip in list(self.av_sync.states.keys()):
                try:
                    due_audio = self.av_sync.pop_due_audio(sender_ip, now)
                    for _, audio_bytes in due_audio:
                        self.AudioOutput.play_bytes(audio_bytes)

                    frame = self.av_sync.pop_latest_due_video(sender_ip, now)
                    if frame is not None:
                        self.latest_remote_frames[sender_ip] = frame

                        while self.remote_video_queue.qsize() >= 3:
                            try:
                                self.remote_video_queue.get_nowait()
                            except queue.Empty:
                                break

                        self.remote_video_queue.put((sender_ip, frame))

                except Exception as e:
                    print("guest playback_loop error:", e)

            time.sleep(0.001)

    def handle_msgs_from_client_logic(self, opcode, data):
        try:
            if opcode in self.commands:
                self.commands[opcode](data)
        except Exception as e:
            print(f"Error handling message: {e}")

    def handle_msgs_from_host(self):
        while self.running:
            try:
                msg = self.msgs_from_host.get(timeout=1)
            except queue.Empty:
                continue
            except Exception as e:
                print("host queue error:", e)
                time.sleep(0.05)
                continue

            print(f"Received message from host: {msg}")

            try:
                opcode, data = clientProtocol.unpack(msg)
            except Exception as e:
                print("unpack error:", e)
                continue

            if opcode in self.commands:
                try:
                    self.commands[opcode](data)
                except Exception as e:
                    print(f"Error in command {opcode}: {e}")

    def get_meeting_start_time(self, data):
        try:
            if isinstance(data, list):
                self.meeting_start_time = float(data[0])
            else:
                self.meeting_start_time = float(data)

            print("meeting start time:", self.meeting_start_time)
        except Exception as e:
            print("meeting start time parse error:", e)

    def handle_video_msg(self, data):
        try:
            sender_ip = data[0]
            timestamp = float(data[2])
            frame = data[3]
        except Exception as e:
            print("video msg parse error:", e)
            return

        self.av_sync.add_video(sender_ip, timestamp, frame)

    def handle_audio_msg(self, data):
        try:
            sender_ip = data[0]
            timestamp = float(data[2])
            audio = data[3]
        except Exception as e:
            print("audio msg parse error:", e)
            return

        self.av_sync.add_audio(sender_ip, timestamp, audio)

    def handle_join(self, data):
        try:
            ip = data[0]
            port = int(data[1])
        except Exception as e:
            print("join parse error:", e)
            return

        print(f"{ip} joined the call")
        self.open_clients[ip] = port
    def force_disconnect(self):
        """
        if server says to disconnect, disconnect client
        :return:
        """
        self.leave_call()

    def handle_disconnect(self, data):
        try:
            ip = data[0]
            username = data[1] if len(data) > 1 else ip
        except Exception as e:
            print("disconnect parse error:", e)
            return

        print(f"{username} left the call")

        if ip in self.open_clients:
            del self.open_clients[ip]

        if ip in self.latest_remote_frames:
            del self.latest_remote_frames[ip]

        self.av_sync.remove_sender(ip)

        try:
            self.video_comm.remove_user(ip, 0)
        except Exception:
            pass

    def leave_call(self):
        self.cleanup()

    def cleanup(self):
        if not self.running:
            return

        print("Closing guest call...")
        self.running = False

        try:
            self.camera.stop()
        except Exception as e:
            print("camera stop error:", e)

        try:
            self.mic.stop()
        except Exception as e:
            print("mic stop error:", e)

        try:
            self.AudioOutput.stop()
        except Exception as e:
            print("audio output stop error:", e)

        try:
            self.video_comm.close()
        except Exception as e:
            print("video close error:", e)

        try:
            if hasattr(self.audio_comm, "close_client"):
                self.audio_comm.close_client()
        except Exception as e:
            print("audio close error:", e)

        try:
            if hasattr(self.comm_with_host, "close_client"):
                self.comm_with_host.close_client()
        except Exception as e:
            print("host comm close error:", e)

        time.sleep(0.1)