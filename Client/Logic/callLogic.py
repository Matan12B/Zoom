
import queue
import threading
import time
import socket
import sys
import os
import cv2

# my imports
from Client.Comms.videoComm import VideoComm
from Client.Comms.audioComm import AudioClient
from Client.GUI.VideoDisplay import VideoDisplay
from Client.Devices.Camera import CameraControl
from Client.Devices.AudioOutputDevice import AudioOutput

from Client.Devices.Microphone import Microphone
from Client.Protocol import clientProtocol

class CallLogic:
    # todo video port audio port
    def __init__(self, port, key, open_clients, comm, audio_server_ip, video_server_ip):
        self.open_clients = open_clients
        self.soc = socket.socket()
        self.msgQ = queue.Queue()
        self.display = VideoDisplay()
        self.call_comm = comm
        self.audio_comm = AudioClient(audio_server_ip, port, self.msgQ)
        self.video_comm = VideoComm(video_server_ip, port, self.msgQ)
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
        self.AudioOutput = AudioOutput()
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
        threading.Thread(target=self.handle_msgs,
        args=(self.call_comm, self.msgQ, "CALL"),
            daemon=True
        ).start()
        threading.Thread(target=self.playback_loop, daemon=True).start()

        # TODO GUI
        try:
            while True:
                frame = self.camera.get_frame()
                if frame:
                    self.send_video(self.ip, frame)
                audio_chunk = self.mic.record()
                if audio_chunk:
                    self.send_audio(self.ip, audio_chunk)

                # Small sleep prevents CPU overuse
                time.sleep(0.01)

        except KeyboardInterrupt:
            print("Call interrupted.")

        finally:
            print("Closing call...")
            self.camera.stop()
            self.mic.stop()
            self.mic.close()

    def playback_loop(self):
        """
        plays audio and video in sync from the buffer and than deletes them
        """
        while True:
            for client in list(self.sync_buffer.keys()):
                timestamps = list(self.sync_buffer[client].keys())

                for timestamp in timestamps:
                    data = self.sync_buffer[client][timestamp]

                    if data["audio"] and data["video"]:
                        frame = data["video"]
                        audio = data["audio"]

                        # display video
                        self.display.show_frame(client, frame)

                        # play audio
                        self.AudioOutput.play(audio)

                        del self.sync_buffer[client][timestamp]

            time.sleep(0.01)

    def handle_msgs(self, comm, recvQ, state):
        """
        Handle incoming messages from the server.
        :param comm: Client communication object
        :param recvQ: Queue to receive messages
        :return: None
        """
        while True:
            msg = recvQ.get()
            opcode, data = clientProtocol.unpack(msg)
            if opcode in self.commands.keys():
                self.commands[opcode](comm, data, state)

    # Send video to a specific client
    def send_video(self, username, img):
        success, encoded = cv2.imencode(".jpg", img)
        if success:
            self.video_comm.send_frame(encoded.tobytes())

    def send_audio(self, username, audio):
        self.audio_comm.send_audio(audio)

    def handle_audio(self, client_ip, username, timestamp, audio):
        """
        add audio to buffer
        """
        if not hasattr(self, 'sync_buffer'):
            self.sync_buffer = {}
        if client_ip not in self.sync_buffer:
            self.sync_buffer[client_ip] = {}
        if timestamp not in self.sync_buffer[client_ip]:
            self.sync_buffer[client_ip][timestamp] = {"audio": None, "video": None}
        self.sync_buffer[client_ip][timestamp]["audio"] = audio

    def handle_video(self, client_ip, username, timestamp, img):
        """
        add video to buffer
        """
        key = f"{client_ip}"

        if not hasattr(self, 'sync_buffer'):
            self.sync_buffer = {}

        if key not in self.sync_buffer:
            self.sync_buffer[key] = {}

        if timestamp not in self.sync_buffer[key]:
            self.sync_buffer[key][timestamp] = {"audio": None, "video": None}

        self.sync_buffer[key][timestamp]["video"] = img

    def handle_disconnect(self, ip, username):
        print(username, "left the call")
        self.display.remove_user(ip, username)
        if ip in self.open_clients:
            del self.open_clients[ip]

    # Connect the client
    def handle_join(self, ip, port, username, key, state, video_port, audio_port):
        pass  # Connect the client

    def leave_call(self):
        pass

    def handle_kick(comm, recvQ):
        """
        Close all connections because client was kicked
        """

    if __name__ == "__main__":
        callLogic = CallLogic()
        callLogic.call()

