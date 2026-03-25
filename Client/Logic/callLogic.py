import threading
import time
import socket
import queue
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
    Guest call logic (LAN P2P) rewritten in Host-style:
    - Sends video via VideoComm
    - Sends/receives audio via AudioClient
    - Uses sync_buffer for GUI
    """

    def __init__(self, port, meeting_key, comm, host_ip):
        self.open_clients = {}  # {ip: port}
        self.msgQ = queue.Queue()
        self.display = VideoDisplay()
        self.call_comm = comm
        self.AES = AESCipher(meeting_key)  # single AES key for meeting

        # Comm systems
        self.video_comm = VideoComm(self.AES, self.open_clients)
        self.audio_comm = AudioClient(host_ip, self.AES)

        # Local devices
        self.camera = CameraControl(width=478, height=359)
        self.mic = Microphone(50)
        self.AudioOutput = AudioOutput()  # for playback
        self.sync_buffer = {}

        # Guest IP (LAN)
        # self.ip = socket.gethostbyname(socket.gethostname())
        self.ip = "10.0.0.5"
        # Command handlers
        self.commands = {
            "hv": self.handle_video,
            "ha": self.handle_audio,
            "hj": self.handle_join,
            "hd": self.handle_disconnect
        }

        self.running = True

    def start(self):
        """Start devices, threads, and send loops (like Host)"""
        print("Starting guest call...")

        # Start devices
        self.camera.start()
        self.mic.start()
        self.mic.unmute()

        # Start threads
        threading.Thread(target=self.handle_msgs, daemon=True).start()
        threading.Thread(target=self.receive_video_loop, daemon=True).start()

        try:
            while self.running:
                # Capture and send own video
                frame_bytes = self.camera.get_frame()
                if frame_bytes is not None:
                    self.video_comm.send_frame(frame_bytes)

                # Capture and send own audio
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
        """Stop devices and communication"""
        print("Closing guest call...")
        self.running = False
        if hasattr(self, "camera"):
            self.camera.stop()
        if hasattr(self, "mic"):
            self.mic.stop()
            self.mic.close()
        if hasattr(self, "video_comm"):
            self.video_comm.close()

    def handle_msgs(self):
        """Threaded message handler"""
        while self.running:
            msg = self.msgQ.get()
            opcode, data = clientProtocol.unpack(msg)
            if opcode in self.commands:
                self.commands[opcode](*data)

    def receive_video_loop(self):
        """Receive incoming frames from peers into sync_buffer"""
        while self.running:
            while not self.video_comm.frameQ.empty():
                frame, addr = self.video_comm.frameQ.get()
                client_ip = addr[0]
                timestamp = time.time()

                if client_ip not in self.sync_buffer:
                    self.sync_buffer[client_ip] = {}
                if timestamp not in self.sync_buffer[client_ip]:
                    self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}

                self.sync_buffer[client_ip][timestamp]["video"] = frame

            time.sleep(0.005)

    # === Command Handlers ===
    def handle_video(self, client_ip, username, timestamp, frame):
        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}
        if timestamp not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}
        self.sync_buffer[client_ip][timestamp]["video"] = frame

    def handle_audio(self, client_ip, username, timestamp, audio):
        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}
        if timestamp not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}
        self.sync_buffer[client_ip][timestamp]["audio"] = audio

    def handle_join(self, ip, port):
        """New peer joined (store port and add to VideoComm)"""
        print(f"{ip} joined the call")
        self.open_clients[ip] = port
        self.video_comm.add_user(ip, port)

    def handle_disconnect(self, ip, username):
        """Peer left the call"""
        print(f"{username} left the call")
        if ip in self.open_clients:
            del self.open_clients[ip]
        self.video_comm.remove_user(ip, 0)
        if ip in self.sync_buffer:
            del self.sync_buffer[ip]

    def leave_call(self):
        """Stop running and cleanup"""
        self.running = False
        self.cleanup()