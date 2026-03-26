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
from Client.Comms.ClientComm import ClientComm

class CallLogic:
    """
    Guest call logic (LAN P2P) rewritten in Host-style:
    - Sends video via VideoComm
    - Sends/receives audio via AudioClient
    - Uses sync_buffer for GUI
    """

    def __init__(self, port, meeting_key, comm, host_ip):
        self.open_clients = {}  # {ip: port}
        self.msgs_from_host = queue.Queue()
        self.display = VideoDisplay()
        self.comm_with_server = comm
        self.AES = AESCipher(meeting_key)  # single AES key for meeting
        self.comm_with_host = ClientComm(host_ip, port, self.msgs_from_host, self.AES)
        # Comm systems
        self.video_comm = VideoComm(self.AES, self.open_clients)
        self.audio_comm = AudioClient(host_ip, self.AES)
        self.open_clients[host_ip] = port
        # Local devices
        self.camera = CameraControl(width=478, height=359, jpeg_quality=60)
        self.mic = Microphone(50)
        self.AudioOutput = AudioOutput()  # for playback
        self.sync_buffer = {}
        self.meeting_start_time = None
        # self.ip = socket.gethostbyname(socket.gethostname())
        self.ip = "192.168.4.73"
        # Command handlers
        self.commands = {
            "ha": self.handle_audio,
            "hj": self.handle_join,
            "hd": self.handle_disconnect,
            "gmst": self.get_meeting_start_time
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
        threading.Thread(target=self.handle_msgs_from_host, daemon=True).start()
        while self.meeting_start_time is None:
            time.sleep(0.01)
        threading.Thread(target=self.receive_video_loop, daemon=True).start()
        threading.Thread(target=self.receive_audio_loop, daemon=True).start()
        try:
            while self.running:
                # Capture and send own video
                if self.meeting_start_time is not None:
                    timestamp = time.time() - self.meeting_start_time
                    frame_bytes = self.camera.get_frame()
                    if frame_bytes is not None :
                        frame_data = clientProtocol.build_video_msg(timestamp, frame_bytes)
                        self.video_comm.send_frame(frame_data)
                    if self.mic.running:  # make sure mic is started
                        audio_chunk = self.mic.record()
                        if audio_chunk:
                            # Send audio using your updated protocol with sender IP
                            audio_msg = clientProtocol.build_audio_msg(timestamp, audio_chunk, self.ip)
                            self.audio_comm.send_audio(audio_msg)
                    time.sleep(0.001)

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

    # def handle_msgs(self):
    #     """Threaded message handler"""
    #     while self.running:
    #         msg = self.msgs_from_host.get()
    #         opcode, data = clientProtocol.unpack(msg)
    #         if opcode in self.commands:
    #             self.commands[opcode](*data)

    def handle_msgs_from_client_logic(self, opcode, data):
        """
        handle messages from client logic call functions
        :param opcode: function opcode
        :param data: data
        :return:
        """
        if opcode in self.commands:
            self.commands[opcode](data)

    def handle_msgs_from_host(self):
        """
        handle msgs from host server
        """
        print("started listening to host server")
        while self.running:
            msg = self.msgs_from_host.get()
            print(f"Received message: {msg}")
            opcode, data = clientProtocol.unpack(msg)
            if opcode in self.commands:
                self.commands[opcode](data)

    def get_meeting_start_time(self, data):
        """
        get meeting start time from host for time stamps
        """
        self.meeting_start_time = float(data)
        print("meeting start time:", self.meeting_start_time)

    def receive_video_loop(self):
        """Receive incoming frames from peers into sync_buffer"""
        while self.running:
            while not self.video_comm.frameQ.empty():
                frame, timestamp, addr = self.video_comm.frameQ.get()
                print(timestamp, addr)
                client_ip = addr[0]
                if self.meeting_start_time is not None:
                    timestamp = timestamp - self.meeting_start_time
                    if client_ip not in self.sync_buffer:
                        self.sync_buffer[client_ip] = {}
                    if timestamp not in self.sync_buffer[client_ip]:
                        self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}
                    self.sync_buffer[client_ip][timestamp]["video"] = frame
                else:
                    print("didnt recv start time")
            time.sleep(0.005)
    
    def receive_audio_loop(self):
        while self.running:
            while not self.audio_comm.audio_queue.empty():
                audio_bytes, timestamp, sender_ip = self.audio_comm.audio_queue.get()
                print(audio_bytes, timestamp, sender_ip)

                client_ip = sender_ip
                if self.meeting_start_time is not None:
                    timestamp -= self.meeting_start_time
                    if client_ip not in self.sync_buffer:
                        self.sync_buffer[client_ip] = {}
                    if timestamp not in self.sync_buffer[client_ip]:
                        self.sync_buffer[client_ip][timestamp] = {"video": None, "audio": None}
                    self.sync_buffer[client_ip][timestamp]["audio"] = audio_bytes
                else:
                    print("didnt recv start time")

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