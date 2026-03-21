from Client.Devices.Microphone import Microphone
from Client.Devices.AudioOutputDevice import AudioOutput
import socket
import threading
import queue
import sys
import time
from Client.Protocol import clientProtocol
from Common.Cipher import DiffiHelman, AESCipher
import os
import select

# client
class AudioClient:
    def __init__(self, server_ip, port, recvQ):
        self.my_socket = socket.socket()
        self.server_ip = server_ip
        self.port = port
        self.recvQ = recvQ
        self.cipher = None
        self.open = False
        self.file_counter = 0
        threading.Thread(target=self._mainLoop,).start()

    def _mainLoop(self):
        """
        conect to client and exhcange keys and recv messages
        :return: None
        """
        try:
            self.my_socket.connect((self.server_ip, self.port))
        except Exception as e:
            print("error in connect:", e)
            sys.exit("server is down - try later")

        self._exchange_key()
        if not self.cipher:
            sys.exit("couldn't exchange keys")
        self.open = True
        while True:
            if self.open:
                decrypt_audio_chunk = ""
                try:
                    length = self.my_socket.recv(8).decode()
                    if length:
                        msg = self.my_socket.recv(int(length))
                        decrypt_audio_chunk = self.cipher.decrypt_file(msg)
                except Exception as e:
                    print(f"error in receiving message here - {e}")
                    self._close_client()
                    continue
                if decrypt_audio_chunk:
                    self.recvQ.put(decrypt_audio_chunk)

    def _close_client(self):
        """
        close the connection
        :return: None
        """
        try:
            self.my_socket.close()
            print("Client connection closed.")
        except Exception as e:
            print(f"Error closing client: {e}")
        self.open = False

    def close_client(self):
        """
        close the connection
        :return: None
        """
        self._close_client()

    def client_exchange(self, diffie, socket):
        """
        exchange keys with server according to clientProtocol
        :param diffie: diffie helman object
        :param socket: socket
        :return: shared key as string
        """
        server_public_key = None
        ret = None
        try:
            server_public_key = int(socket.recv(5).decode())
            socket.send(str(diffie.public_key).zfill(5).encode())
        except Exception as e:
            print(f"Error in receiving/sending public key: {e}")
        if server_public_key:
            shared_key = pow(server_public_key, diffie.private_key, diffie.p)
            ret = str(shared_key)
        return ret

    def _exchange_key(self):
        """
        Exchange key with server
        :return: if exchanged
        """
        diffie = DiffiHelman()
        diffie.create_keys()
        shared_key = self.client_exchange(diffie, self.my_socket)
        flag = False
        if shared_key:
            self.cipher = AESCipher(shared_key)
            print(f"Shared key established with server - {shared_key}")
            flag = True
        return flag

    def send_audio(self, audio_chunk):
        """
        send message to server
        :param msg:
        :return:
        """
        flag = False
        if self.cipher and self.open:
            audio_chunk = self.cipher.encrypt_file(audio_chunk)
            if len(audio_chunk) > 0:
                try:
                    self.my_socket.send(str(len(audio_chunk)).zfill(8).encode())
                    self.my_socket.send(audio_chunk)
                    flag = True
                except Exception as e:
                    print(f"error in sending message - {e}")
                    self._close_client()
                    self.open = False
        return flag


class AudioServer:
    def __init__(self, port, audioQ):
        self.server_socket = socket.socket()
        self.port = port
        self.audioQ = audioQ
        # ip: [soc, AES]
        self.open_clients= {}
        # soc: ip
        self.open_clients_soc_ip = {}
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(4)
        self.mic = Microphone(50)
        threading.Thread(target=self._mainLoop,).start()

    def _mainLoop(self):
        """
        adds new clients and recv messages
        :return:
        """
        print("server listen on port:", self.port)
        while True:
            rlist, _, _ = select.select([self.server_socket] + list(self.open_clients_soc_ip.keys()), [], [], 0.01)
            for current_socket in rlist:
                if current_socket is self.server_socket:
                    client_socket, addr = self.server_socket.accept()
                    print(f"{addr[0]} connected")
                    threading.Thread(target=self._exchange_key, args=(client_socket, addr[0],)).start()
                else:
                    if current_socket in self.open_clients_soc_ip.keys():
                        decrypt_audio_chunk = ""
                        audio_chunk = ""
                        current_ip = self._find_ip_by_socket(current_socket)
                        try:
                            length = current_socket.recv(8).decode()
                            if length:
                                audio_chunk = current_socket.recv(int(length))
                            else:
                                self.close_client(current_ip)
                            if current_ip and current_ip in self.open_clients and audio_chunk:
                                decrypt_audio_chunk = self.open_clients[current_ip][1].decrypt_file(audio_chunk)
                        except Exception as e:
                            print(f"error in receiving message - {e}")
                            self.close_client(current_ip)
                            continue
                        if decrypt_audio_chunk:
                            self.audioQ.put([current_ip, decrypt_audio_chunk])

    def _exchange_key(self, client_soc, client_ip):
        """
        Exchange the Diffie-Hellman key with the client and establish a shared AES key.
        :param client_soc: The client's socket.
        :param client_ip: The client's IP address.
        """
        diffie = DiffiHelman()
        diffie.create_keys()
        shared_key = None
        client_public_key = None
        try:
            client_soc.send(str(diffie.public_key).zfill(5).encode())
            client_public_key = int(client_soc.recv(5).decode())
        except Exception as e:
            print(f"Error in sending/receiving public key: {e}")
        if client_public_key:
            shared_key = pow(client_public_key, diffie.private_key, diffie.p)
            shared_key = str(shared_key)

        if shared_key:
            print(f"Shared key established with client {client_ip}: {shared_key}")
            self.open_clients[client_ip] = [client_soc, AESCipher(shared_key)]
            self.open_clients_soc_ip[client_soc] = client_ip
        else:
            print(f"Failed to establish shared key with {client_ip}")

    def close_client(self, client_ip):
        """Closes the client connection safely."""
        try:
            if client_ip in self.open_clients:
                client_soc = self.open_clients[client_ip][0]

                # Remove from dicts first
                del self.open_clients_soc_ip[client_soc]
                del self.open_clients[client_ip]
                # Now close socket
                client_soc.close()
                print(f"Client {client_ip} closed.")
        except Exception as e:
            print(f"Error closing client {client_ip}: {e}")


    def broadcast_audio(self, audio_chunk, sender_ip, timestamp):
        """
        send audio to all connected users except the sender
        :param audio: audio file
        :param sender_ip: ip of the sender
        :param timestamp: timestamp of the audio chunk
        :return: None
        """
        for ip in list(self.open_clients.keys()):
            if ip and not ip == sender_ip:
                self.send_audio(ip, audio_chunk, timestamp)

    def send_audio(self, client_ip, audio_chunk, timestamp):
        """

        """
        if client_ip in self.open_clients.keys():
            soc = self._find_socket_by_ip(client_ip)
            audio_msg = clientProtocol.build_audio_msg(timestamp, audio_chunk)
            self._send_audio(soc, audio_msg)

    def _send_audio(self, client_soc, audio_msg):
        """
        encrypt the audio and send it to the client
        :param client_ip:
        :param audio_msg: audio file and timestamp
        :return:
        """
        if client_soc in self.open_clients_soc_ip.keys():
            client_ip = self._find_ip_by_socket(client_soc)
            encrypted_audio_chunk = self.open_clients[client_ip][1].encrypt_file(audio_msg)
            try:
                client_soc.send(str(len(encrypted_audio_chunk)).zfill(8).encode())
                client_soc.send(encrypted_audio_chunk)
            except Exception as e:
                print(f"error in sending message - {e}")
                self.close_client(client_ip)

    def _find_ip_by_socket(self, client_soc):
        """

        """
        ret = ""
        if client_soc in self.open_clients_soc_ip.keys():
            ret = self.open_clients_soc_ip[client_soc]
        return ret

    def _find_socket_by_ip(self, client_ip):
        """
        return the matching socket for the ip
        :param client_ip: ip
        :return: client socket
        """
        if client_ip in self.open_clients.keys():
            # socket
            ret = self.open_clients[client_ip][0]
        else:
            ret = None
        return ret


if __name__ == "__main__":
    import sys

    # if len(sys.argv) < 2:
    #     print("Usage: python audioComm.py [server|client]")
    #     sys.exit(1)

    # mode = sys.argv[1].lower()
    mode = "server"

    if mode == "server":
        print("Starting audio server on port 1234...")
        audioQ = queue.Queue()
        server = AudioServer(1234, audioQ)

        # Wait for audio chunks and print info
        print("Server running. Waiting for clients and audio chunks...")
        try:
            while True:
                if not audioQ.empty():
                    ip, audio_chunk = audioQ.get()
                    print(f"Received audio from {ip}: {len(audio_chunk)} bytes")

                    # Broadcast to other clients with timestamp
                    timestamp = int(time.time() * 1000)
                    server.broadcast_audio(audio_chunk, ip, timestamp)
                    print(f"Broadcasted audio to other clients (timestamp: {timestamp})")
                time.sleep(0.01)
        except KeyboardInterrupt:
            print("\nServer shutting down...")


    elif mode == "client":
        print("Starting audio client, connecting to 127.0.0.1:1234...")
        recvQ = queue.Queue()
        client = AudioClient("127.0.0.1", 1234, recvQ)
        # 🔊 NEW: import your audio classes

        mic = Microphone(volume=70, rate=16000, channels=1, chunk=1024)
        speaker = AudioOutput(rate=16000, channels=1)
        # Wait for connection
        time.sleep(1)
        if not client.open:
            print("Failed to connect to server")
            sys.exit(1)
        print("Connected! Starting live audio...")
        mic.start()
        mic.unmute()
        try:
            while True:
                # 🎙️ RECORD + SEND
                audio_chunk = mic.record()
                client.send_audio(audio_chunk)
                # 🔊 RECEIVE + PLAy
                while not recvQ.empty():
                    received_audio = recvQ.get()
                    speaker.play_bytes(received_audio)
        except KeyboardInterrupt:
            print("\nClient shutting down...")
        finally:
            mic.close()
            speaker.stop()
            client.close_client()
    else:
        print("Invalid mode. Use 'server' or 'client'")
        sys.exit(1)
