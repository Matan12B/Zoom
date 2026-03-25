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

class CallLogic:
    """
    Guest call logic for MatMeet:
    - Sends video P2P to other guests via VideoComm
    - Sends audio through host via AudioClient
    - Receives video and audio, stores in sync_buffer
    """

    def __init__(self, port, key, comm, audio_server_ip):
        self.open_clients = {}  # {ip: [AESCipher, port]}
        self.msgQ = queue.Queue()
        self.display = VideoDisplay()
        self.call_comm = comm
        self.audio_comm = AudioClient(audio_server_ip, port)
        self.video_comm = VideoComm(port, key, self.open_clients)
        hostname = socket.gethostname()
        self.ip = socket.gethostbyname(hostname)
        self.commands = {
            "hv": self.handle_video,
            "ha": self.handle_audio,
            "hj": self.handle_join,
            "hd": self.handle_disconnect
        }
        self.camera = CameraControl(width=478, height=359)
        self.mic = Microphone(50)
        self.AudioOutput = AudioOutput()
        self.sync_buffer = {}
        self.running = True

    def start(self):
        """Start the call: devices, threads, sending loops"""
        print("Starting call...")
        # Start devices
        self.camera.start()
        self.mic.start()
        self.mic.unmute()
        threading.Thread(target=self.handle_msgs, daemon=True).start()
        threading.Thread(target=self.receive_video_loop, daemon=True).start()
        try:
            while self.running:
                # Send own camera frame
                frame_bytes = self.camera.get_frame()
                if frame_bytes is not None:
                    self.video_comm.send_frame(frame_bytes)

                # Send own audio chunk through host
                # audio_chunk = self.mic.record()
                # if audio_chunk:
                #     timestamp = time.time()
                #     self.audio_comm.send_audio(audio_chunk)

                time.sleep(0.01)

        except KeyboardInterrupt:
            print("Call interrupted.")
        finally:
            self.cleanup()

    def cleanup(self):
        """Stop devices and mark call as finished"""
        print("Closing call...")
        self.running = False
        if hasattr(self, 'camera'):
            self.camera.stop()
        if hasattr(self, 'mic'):
            self.mic.stop()
            self.mic.close()
        if hasattr(self, 'video_comm'):
            self.video_comm.close()

    def handle_msgs(self):
        """Process incoming messages from host/peers"""
        while self.running:
            msg = self.msgQ.get()
            opcode, data = clientProtocol.unpack(msg)
            if opcode in self.commands:
                self.commands[opcode](*data)  # Important: unpack data list

    def receive_video_loop(self):
        """Bridge incoming P2P frames into sync_buffer for GUI"""
        while self.running:
            while not self.video_comm.frameQ.empty():
                frame, addr = self.video_comm.frameQ.get()
                client_ip = addr[0]
                timestamp = time.time()

                if client_ip not in self.sync_buffer:
                    self.sync_buffer[client_ip] = {}

                if timestamp not in self.sync_buffer[client_ip]:
                    self.sync_buffer[client_ip][timestamp] = {
                        "audio": None,
                        "video": None
                    }

                self.sync_buffer[client_ip][timestamp]["video"] = frame

            time.sleep(0.005)

    def send_video(self, username, frame_bytes):
        """Send own video frame to peers"""
        if frame_bytes is not None:
            self.video_comm.send_frame(frame_bytes)

    def send_audio(self, username, audio, timestamp):
        """Send audio through host"""
        self.audio_comm.send_audio(audio)

    def handle_video(self, client_ip, username, timestamp, img):
        """Store received video frame in sync_buffer"""
        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}
        if timestamp not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}
        self.sync_buffer[client_ip][timestamp]["video"] = img

    def handle_audio(self, client_ip, username, timestamp, audio):
        """Store received audio chunk in sync_buffer"""
        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}
        if timestamp not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}
        self.sync_buffer[client_ip][timestamp]["audio"] = audio

    def handle_join(self, ip, port, shared_key):
        """A new peer joined the call: store info and connect via VideoComm"""
        print(f"{ip} joined the call")
        self.video_comm.add_user(ip, port)
        self.open_clients[ip] = [AESCipher(shared_key), port]

    def handle_disconnect(self, ip, username):
        """A peer left the call"""
        print(f"{username} left the call")
        if ip in self.open_clients:
            del self.open_clients[ip]
        self.video_comm.remove_user(ip, 0)  # port not needed for dict removal
        if ip in self.sync_buffer:
            del self.sync_buffer[ip]

    def leave_call(self):
        """Stop running and cleanup"""
        self.running = False
        self.cleanup()