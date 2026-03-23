import threading
import time
import socket
import queue
from MatMeet.Client.Devices.Camera import CameraControl
from MatMeet.Client.Devices.Microphone import Microphone
from MatMeet.Client.Devices.AudioOutputDevice import AudioOutput
from MatMeet.Client.GUI.VideoDisplay import VideoDisplay
from MatMeet.Client.Comms.videoComm import VideoComm
from MatMeet.Client.Comms.audioComm import AudioClient
from MatMeet.Client.Protocol import clientProtocol

class CallLogic:
    """
    Guest call logic: handles camera/mic, video/audio comm, and sync_buffer.
    Behaves like Host in-meeting, minus host privileges.
    """

    def __init__(self, port, key, comm, audio_server_ip):
        self.open_clients = {}
        self.msgQ = queue.Queue()
        self.display = VideoDisplay()
        self.call_comm = comm
        self.audio_comm = AudioClient(audio_server_ip, port)
        self.video_comm = VideoComm(port, key, self.open_clients)

        # Current user IP
        hostname = socket.gethostname()
        self.ip = socket.gethostbyname(hostname)

        # Command mapping
        self.commands = {
            "hv": self.handle_video,
            "ha": self.handle_audio,
            "hj": self.handle_join,
            "hd": self.handle_disconnect
        }

        # Devices
        self.camera = CameraControl(width=478, height=359)  # Resize in CameraControl
        self.mic = Microphone(50)
        self.AudioOutput = AudioOutput()

        # Buffers for received audio/video
        self.sync_buffer = {}
        self.running = True

    def start(self):
        """Main loop: start devices, handle communication, send audio/video."""
        print("Starting call...")

        # Start devices
        self.camera.start()
        self.mic.start()
        self.mic.unmute()

        # Start message handling thread
        threading.Thread(
            target=self.handle_msgs,
            daemon=True
        ).start()

        # Start playback thread
        # threading.Thread(target=self.playback_loop, daemon=True).start()

        try:
            while self.running:
                # Send latest camera frame
                frame = self.camera.get_frame()
                if frame is not None:
                    self.send_video(self.ip, frame)

                # Send microphone audio
                # audio_chunk = self.mic.record()
                # if audio_chunk:
                #     self.send_audio(self.ip, audio_chunk)

                time.sleep(0.01)  # prevent CPU overuse

        except KeyboardInterrupt:
            print("Call interrupted.")

        finally:
            self.cleanup()

    def cleanup(self):
        """Stop devices and clean resources."""
        print("Closing call...")
        self.camera.stop()
        self.mic.stop()
        self.mic.close()

    # -------------------
    # Communication
    # -------------------

    def handle_msgs(self):
        """Process incoming messages from the server."""
        while True:
            msg = self.msgQ.get()
            opcode, data = clientProtocol.unpack(msg)
            if opcode in self.commands:
                self.commands[opcode](data)

    def send_video(self, username, img):
        """Send a frame to video communication system (CameraControl handles resizing)."""
        if img is not None:
            self.video_comm.send_frame(img)

    def send_audio(self, username, audio):
        """Send audio chunk to all clients."""
        self.audio_comm.send_audio(audio)

    # -------------------
    # Playback
    # -------------------

    # def playback_loop(self):
    #     """Play audio and video from the sync_buffer."""
    #     while True:
    #         for client in list(self.sync_buffer.keys()):
    #             timestamps = list(self.sync_buffer[client].keys())
    #             for timestamp in timestamps:
    #                 data = self.sync_buffer[client][timestamp]
    #                 if data["audio"] and data["video"]:
    #                     # Display video
    #                     self.display.show_frame(client, data["video"])
    #                     # Play audio
    #                     self.AudioOutput.play(data["audio"])
    #                     # Remove after playback
    #                     del self.sync_buffer[client][timestamp]
    #
    #         time.sleep(0.01)

    # -------------------
    # Handlers
    # -------------------

    def handle_video(self, client_ip, username, timestamp, img):
        """Store received video frame in sync_buffer."""
        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}
        if timestamp not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}
        self.sync_buffer[client_ip][timestamp]["video"] = img

    def handle_audio(self, client_ip, username, timestamp, audio):
        """Store received audio chunk in sync_buffer."""
        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}
        if timestamp not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}
        self.sync_buffer[client_ip][timestamp]["audio"] = audio

    def handle_join(self, comm, data, state):
        """Handle a new participant joining (update open_clients)."""
        ip, username = data.get("ip"), data.get("username")
        self.open_clients[ip] = username

    def handle_disconnect(self, comm, data, state):
        """Handle a participant leaving the call."""
        ip, username = data.get("ip"), data.get("username")
        if ip in self.open_clients:
            del self.open_clients[ip]
        self.display.remove_user(ip, username)

    def leave_call(self):
        self.running = False
        self.cleanup()