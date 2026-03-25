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
        self.open_clients = {} # from server
        self.microphone = None
        self.soc = socket.socket()
        self.msgQ = queue.Queue()
        self.display = VideoDisplay()
        self.host_comm = comm
        self.host_server = ClientServer(port, self.msgQ, self.open_clients)
        # todo add port to audio and video comm
        self.audio_comm = AudioServer(port, meeting_key, self.host_comm.open_clients)
        self.video_comm = VideoComm(port, meeting_key, self.host_comm.open_clients)
        # for getting the current user ip
        hostname = socket.gethostname()
        self.ip = socket.gethostbyname(hostname)

        self.commands = {
            "hv" : self.handle_video,
            "ha" : self.handle_audio,
            "hj" : self.handle_join,
            "hd" : self.handle_disconnect
        }
        self.camera = CameraControl()
        self.mic = Microphone(50)
        self.sync_buffer = {}

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

        # Start communication threads (assuming they have start() method)
        threading.Thread(
            target=self.handle_msgs,
            daemon=True
        ).start()
        # threading.Thread(target=self.playback_loop, daemon=True).start()
        # TODO GUI
        # start meeting
        try:
            while True:
                frame = self.camera.get_frame()
                if frame is not None:
                    self.send_video(self.ip, frame)
                # audio_chunk = self.mic.record()
                # if audio_chunk:
                #     self.send_audio(self.ip, audio_chunk)

                # Small sleep prevents CPU overuse
                time.sleep(0.01)

        except KeyboardInterrupt:
            print("Call interrupted.")

        finally:
            print("Closing call...")
            self.camera.stop()
            self.mic.stop()
            self.mic.close()

    def handle_msgs(self):
        """
        Threaded method: Waits for messages from clients.
        It will process the incoming messages, handle them accordingly.
        """
        while True:
            msg = self.msgQ.get()
            opcode, data = clientProtocol.unpack(msg)
            if opcode in self.commands:
                self.commands[opcode](data)

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

    def send_video(self, username, img):
        """
        Send video (image) to a specific user.

        :param username: The username of the target client.
        :param img: The image (video frame) to send to the user.
        """
        if img:
            self.video_comm.send_frame(img)

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


    def handle_video(self, client_ip, username, timestamp, img):
        """
        Handle video data received from clients.

        :param client_ip: The IP address of the client sending the video.
        :param username: The username of the client sending the video.
        :param timestamp: The timestamp of the video message.
        :param img: The image (video frame) received from the client.
        """
        print("video from", username, timestamp)
        key = f"{client_ip}"

        if not hasattr(self, 'sync_buffer'):
            self.sync_buffer = {}

        if key not in self.sync_buffer:
            self.sync_buffer[key] = {}

        if timestamp not in self.sync_buffer[key]:
            self.sync_buffer[key][timestamp] = {"audio": None, "video": None}

        self.sync_buffer[key][timestamp]["video"] = img

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


    def handle_join(self, ip, port, shared_key):
        """
        Connect a client to the call or server.

        :param ip: The IP address of the client to connect.
        :param username: The username of the client to connect.
        """
        pass  # Logic to connect the client
        self.host_comm.connect_client(ip, username)
        self.open_clients[ip] = [AESCipher(shared_key), port]
