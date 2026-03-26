import threading
import time
import socket
import sys
import os
import cv2
import queue
from Client.Devices.Camera      import CameraControl
from Client.Devices.Microphone  import Microphone
from Client.Comms.videoComm     import VideoComm
from Client.Comms.audioComm     import AudioServer
from Client.GUI.VideoDisplay    import VideoDisplay
from Client.Protocol            import clientProtocol
# TODO note this is a problem!
from Client.Comms.ClientServerComm import ClientServer
from Common.Cipher import AESCipher


# current problems:
# using server code in the client - should add a common server code
# confusing workflow of starting meeting and comm with server

class Host:
    def __init__(self, port, meeting_key, comm):
        """

        :param port:
        :param meeting_key:
        :param comm:
        """
        self.open_clients = {} # [ip] = port
        self.microphone = None
        self.soc = socket.socket()
        self.msgQ = queue.Queue()
        self.display = VideoDisplay()
        self.host_comm = comm
        self.AES = AESCipher(meeting_key)
        self.host_server = ClientServer(port, self.msgQ, self.open_clients, self.AES)
        # todo add port to audio and video comm
        self.audio_comm = AudioServer(self.AES, self.open_clients)
        self.video_comm = VideoComm(self.AES, self.open_clients)
        # for getting the current user ip
        hostname = socket.gethostname()
        self.ip = socket.gethostbyname(hostname)

        self.commands = {
            "ha" : self.handle_audio,
            "hj" : self.handle_join,
            "hd" : self.handle_disconnect
        }
        self.camera = CameraControl()
        self.mic = Microphone(50)
        self.sync_buffer = {}
        self.meeting_start_time = None
        self.running = True

    def start(self):
        """
        Main call loop:
        - Start devices
        - Start communication
        - Send audio & video continuously
        """

        print("Starting call...")

        # Start devices
        self.camera.start()
        self.mic.start()
        self.mic.unmute()
        threading.Thread(target=self.receive_video_loop, daemon=True).start()
        threading.Thread(target=self.receive_audio_loop, daemon=True).start()

        self.meeting_start_time = time.time()
        # threading.Thread(
        #     target=self.handle_msgs,
        #     daemon=True
        # ).start()
        # threading.Thread(target=self.playback_loop, daemon=True).start()
        # start meeting
        try:
            while self.running:
                if self.meeting_start_time is not None:
                    timestamp = time.time() - self.meeting_start_time
                    frame = self.camera.get_frame()
                    if frame is not None:
                        frame_data = clientProtocol.build_video_msg(timestamp, frame)
                        self.video_comm.send_frame(frame_data)
                    if self.mic.running:
                        audio_chunk = self.mic.record()
                        if audio_chunk:
                            audio_msg = clientProtocol.build_audio_msg(timestamp, audio_chunk, self.ip)
                            self.audio_comm.broadcast_audio(audio_msg, self.ip)

                # Small sleep prevents CPU overuse
                time.sleep(0.001)

        except KeyboardInterrupt:
            print("Call interrupted.")

        finally:
            self.close()

    # def handle_msgs(self):
    #     """
    #     Threaded method: Waits for messages from clients.
    #     It will process the incoming messages, handle them accordingly.
    #     """
    #     while True:
    #         msg = self.msgQ.get()
    #         opcode, data = clientProtocol.unpack(msg)
    #         print(f"Received message: {opcode} {data}")
    #         if opcode in self.commands:
    #             self.commands[opcode](data)

    # def playback_loop(self):
    #     """
    #     plays audio and video in sync from the buffer and than deletes them
    #     """
    #     while True:
    #         for client in list(self.sync_buffer.keys()):
    #             timestamps = list(self.sync_buffer[client].keys())
    #             for timestamp in timestamps:
    #                 data = self.sync_buffer[client][timestamp]
    #                 if data["audio"] and data["video"]:
    #                     frame = data["video"]
    #                     audio = data["audio"]
    #                     # display video
    #                     self.display.show_frame(client, frame)
    #                     # play audio
    #                     self.AudioOutput.play(audio)
    #                     del self.sync_buffer[client][timestamp]
    #         time.sleep(0.01)

    def receive_video_loop(self):
        """Receive incoming frames from peers into sync_buffer"""
        while self.running:
            while not self.video_comm.frameQ.empty():
                frame, timestamp, addr = self.video_comm.frameQ.get()
                client_ip = addr[0]
                timestamp = timestamp - self.meeting_start_time
                if client_ip not in self.sync_buffer:
                    self.sync_buffer[client_ip] = {}
                if timestamp not in self.sync_buffer[client_ip]:
                    self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}
                self.sync_buffer[client_ip][timestamp]["video"] = frame
            time.sleep(0.005)

    def receive_audio_loop(self):
        while self.running:
            while not self.audio_comm.audio_queue.empty():
                audio_bytes, timestamp, sender_ip = self.audio_comm.audio_queue.get()
                client_ip = sender_ip
                timestamp -= self.meeting_start_time
                if client_ip not in self.sync_buffer:
                    self.sync_buffer[client_ip] = {}
                if timestamp not in self.sync_buffer[client_ip]:
                    self.sync_buffer[client_ip][timestamp] = {"video": None, "audio": None}
                self.sync_buffer[client_ip][timestamp]["audio"] = audio_bytes
            time.sleep(0.005)

    def handle_msgs_from_client_logic(self, opcode, data):
        """
        handle messages from client logic call functions
        :param opcode: function opcode
        :param data: data
        :return:
        """
        try:
            if opcode in self.commands:
                self.commands[opcode](data)
        except Exception as e:
            print(f"Error handling message: {e}")

    def handle_msgs_from_guests(self):
        """

        """
        while self.running:
            msg = self.msgQ.get()
            print(f"Received message from guest: {msg}")
            opcode, data = clientProtocol.unpack(msg)
            if opcode in self.commands:
                self.commands[opcode](data)

    def send_audio(self, username, audio, timestamp):
        """
        Send audio to a specific user.

        :param username: The username of the target client.
        :param audio: The audio data to send to the user.
        """
        self.audio_comm.broadcast_audio(audio, "", timestamp)

    def handle_audio(self, client_ip, username, timestamp, audio):
        """
        Handle audio data received from clients.

        :param client_ip: The IP address of the client sending the audio.
        :param username: The username of the client sending the audio.
        :param timestamp: The timestamp of the audio message.
        :param audio: The audio data received from the client.
        """
        audio_msg = clientProtocol.build_audio_msg(timestamp, audio)
        self.audio_comm.broadcast_audio(audio_msg, client_ip)
        if not hasattr(self, 'sync_buffer'):
            self.sync_buffer = {}
        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}
        if timestamp not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}
        self.sync_buffer[client_ip][timestamp]["audio"] = audio


    def handle_video(self, client_ip, username, timestamp, frame):
        """
        Handle video data received from clients.

        :param client_ip: The IP address of the client sending the video.
        :param username: The username of the client sending the video.
        :param timestamp: The timestamp of the video message.
        :param frame: The image (video frame) received from the client.
        """
        print("video from", username, timestamp)
        key = f"{client_ip}"

        if not hasattr(self, 'sync_buffer'):
            self.sync_buffer = {}

        if key not in self.sync_buffer:
            self.sync_buffer[key] = {}

        if timestamp not in self.sync_buffer[key]:
            self.sync_buffer[key][timestamp] = {"audio": None, "video": None}

        self.sync_buffer[key][timestamp]["video"] = frame

    def handle_disconnect(self, ip, username):
        """
        Safely disconnect a client from the server.

        :param ip: The IP address of the client to disconnect.
        :param username: The username of the client to disconnect.
        """
        #todo write the specific disconnect logic of host (closing the meeting)
        print(username, "left the call")
        self.display.remove_user(ip, username)
        if ip in self.open_clients:
            del self.open_clients[ip]

    def handle_join(self, data):
        """
        Connect a client to the call or server.
        :param port: port
        :param ip: The IP address of the client to connect.
        """
        ip = data[0]
        port = data[1]
        # [ip] = socket, port
        print("adding", ip, "to open clients")
        self.open_clients[ip] = [None,port]
        self.send_meeting_start_time(ip)

    def send_meeting_start_time(self, ip):
        """
        send the connected client the meeting start time for audio and video sync
        """
        self.host_server.send_msg(ip, clientProtocol.build_meeting_start_time(self.meeting_start_time))

    def close(self):
        print("Closing call...")
        print("Closing call...")
        # Stop running loops
        self.running = False
        # Stop camera
        if hasattr(self, 'camera'):
            self.camera.stop()
        # Stop microphone
        if hasattr(self, 'mic'):
            self.mic.stop()
            self.mic.close()
        # Close video communication
        if hasattr(self, 'video_comm'):
            self.video_comm.close()  # implement close_all to stop threads and sockets
        # Close audio communication
        # if hasattr(self, 'audio_comm'):
        #     self.audio_comm.close_all()  # implement close_all to stop threads and sockets

        # Allow threads to clean up
        time.sleep(0.1)
        sys.exit(1)