# Host.py

import threading
import time
import socket
import cv2
import queue

from Client.Devices.Camera import CameraControl
from Client.Devices.Microphone import Microphone
from Client.Devices.AudioOutputDevice import AudioOutput
from Client.Comms.videoComm import VideoComm
from Client.Comms.audioComm import AudioServer
from Client.Protocol import clientProtocol
from Client.Comms.ClientServerComm import ClientServer
from Common.Cipher import AESCipher
from Client.Logic.av_sync import AVSyncManager


class Host:
    def __init__(self, port, meeting_key, comm, meeting_code):
        self.open_clients = {}   # ip -> [socket, port]
        self.msgQ = queue.Queue()
        self.host_comm = comm
        self.AES = AESCipher(meeting_key)
        self.meeting_code = meeting_code

        self.host_server = ClientServer(port, self.msgQ, self.open_clients, self.AES)
        self.audio_comm = AudioServer(AES=self.AES, open_clients=self.open_clients)
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
        self.mic = Microphone(50, rate=16000, channels=1, chunk=160)
        self.av_sync = AVSyncManager(playout_delay=0.04)
        self.AudioOutput = AudioOutput(rate=16000, channels=1)
        self.encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
        self.meeting_start_time = None
        self.running = True

    def start(self):
        print("Starting call...")

        self.camera.start()
        self.mic.start()
        self.mic.unmute()

        self.meeting_start_time = time.time()

        threading.Thread(target=self.handle_msgs_from_guests, daemon=True).start()
        threading.Thread(target=self.receive_video_loop, daemon=True).start()
        threading.Thread(target=self.receive_audio_loop, daemon=True).start()
        threading.Thread(target=self.host_audio_send_loop, daemon=True).start()
        threading.Thread(target=self.playback_loop, daemon=True).start()

        try:
            while self.running:
                timestamp = time.time() - self.meeting_start_time

                frame = self.camera.get_frame()
                if frame is not None:
                    while self.UI_queue.qsize() >= 1:
                        try:
                            self.UI_queue.get_nowait()
                        except queue.Empty:
                            break

                    self.UI_queue.put(frame.copy())

                    ok, encoded = cv2.imencode(".jpg", frame, self.encode_params)
                    if ok:
                        frame_bytes = encoded.tobytes()
                        frame_data = clientProtocol.build_video_msg(timestamp, frame_bytes)
                        self.video_comm.send_frame(frame_data)

                time.sleep(0.002)

        except KeyboardInterrupt:
            print("Call interrupted.")
        finally:
            self.close()

    def receive_video_loop(self):
        while self.running:
            try:
                while not self.video_comm.frameQ.empty():
                    try:
                        video_data, timestamp, addr = self.video_comm.frameQ.get_nowait()
                    except queue.Empty:
                        break

                    client_ip = addr[0]

                    if client_ip not in self.open_clients:
                        self.open_clients[client_ip] = [None, 0]

                    if video_data is None:
                        continue

                    self.av_sync.add_video(client_ip, float(timestamp), video_data)

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

                    self.av_sync.add_audio(sender_ip, float(timestamp), audio_bytes)

                    try:
                        msg = clientProtocol.build_audio_msg(float(timestamp), audio_bytes, sender_ip)
                        self.audio_comm.broadcast_audio(msg, sender_ip)
                    except Exception as e:
                        print("audio relay error:", e)

                    # TEMP DEBUG:
                    # uncomment this line once just to verify host output device works
                    # self.AudioOutput.play_bytes(audio_bytes)

                time.sleep(0.001)

            except Exception as e:
                print("receive_audio_loop error:", e)
                time.sleep(0.01)

    def host_audio_send_loop(self):
        while self.running:
            try:
                if not self.mic.running or self.meeting_start_time is None:
                    time.sleep(0.01)
                    continue

                audio_chunk = self.mic.record()
                if not audio_chunk:
                    continue

                timestamp = time.time() - self.meeting_start_time
                audio_msg = clientProtocol.build_audio_msg(timestamp, audio_chunk, self.ip)
                self.audio_comm.broadcast_audio(audio_msg, self.ip)

            except Exception as e:
                print("host_audio_send_loop error:", e)
                time.sleep(0.02)

    def playback_loop(self):
        while self.running:
            now = time.monotonic()

            for client_ip in list(self.av_sync.states.keys()):
                try:
                    due_audio = self.av_sync.pop_due_audio(client_ip, now)
                    for _, audio_bytes in due_audio:
                        self.AudioOutput.play_bytes(audio_bytes)

                    frame = self.av_sync.pop_latest_due_video(client_ip, now)
                    if frame is not None:
                        self.latest_remote_frames[client_ip] = frame

                        while self.remote_video_queue.qsize() >= 3:
                            try:
                                self.remote_video_queue.get_nowait()
                            except queue.Empty:
                                break

                        self.remote_video_queue.put((client_ip, frame))

                except Exception as e:
                    print("playback_loop error:", e)

            time.sleep(0.001)

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

    def handle_disconnect(self, data):
        ip = data[0] if len(data) > 0 else ""
        username = data[1] if len(data) > 1 else ip

        print(username, "left the call")

        if ip in self.open_clients:
            del self.open_clients[ip]

        if ip in self.latest_remote_frames:
            del self.latest_remote_frames[ip]

        self.av_sync.remove_sender(ip)

        try:
            self.video_comm.remove_user(ip, 0)
        except Exception:
            pass

    def handle_join(self, data):
        ip = data[0]
        port = int(data[1])

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
        msg = clientProtocol.build_meeting_start_time(self.meeting_start_time)
        self.host_server.send_msg(ip, msg)

    def leave_call(self):
        self.close()

    def close(self):
        if not self.running:
            return
        msg2server = clientProtocol.build_leave_meeting(self.meeting_code)
        self.host_comm.send_msg(msg2server)
        print("Closing call...")
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
            if hasattr(self.audio_comm, "close"):
                self.audio_comm.close()
        except Exception as e:
            print("audio close error:", e)

        try:
            if hasattr(self.host_server, "close"):
                self.host_server.close()
        except Exception as e:
            print("host server close error:", e)

        time.sleep(0.1)