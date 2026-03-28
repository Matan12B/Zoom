import socket
import threading
import queue
import time
import select

from Client.Protocol import clientProtocol


class AudioClient:
    def __init__(self, server_ip, AES, port=3000):
        """
        Audio TCP client.
        Uses the already-shared meeting AES key.
        """
        self.server_ip = server_ip
        self.port = port
        self.cipher = AES

        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.my_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        self.audio_queue = queue.Queue()

        self.running = True
        self.open = False

        threading.Thread(target=self._main_loop, daemon=True).start()

    def _recv_exact(self, size):
        """
        Receive exactly size bytes from the socket.
        Returns None if the socket closes.
        """
        data = b""
        while len(data) < size and self.running and self.open:
            try:
                chunk = self.my_socket.recv(size - len(data))
            except Exception as e:
                print(f"audio client recv error: {e}")
                return None

            if not chunk:
                return None

            data += chunk

        return data

    def _main_loop(self):
        """
        Connect and keep receiving audio messages.
        """
        try:
            self.my_socket.connect((self.server_ip, self.port))
        except Exception as e:
            print(f"audio client connect error: {e}")
            return

        if not self.cipher:
            print("audio client has no AES cipher")
            return

        self.open = True
        print(f"audio client connected to {self.server_ip}:{self.port}")

        while self.running and self.open:
            try:
                length_bytes = self._recv_exact(8)
                if not length_bytes:
                    self._close_client()
                    break

                msg_len = int(length_bytes.decode())
                payload = self._recv_exact(msg_len)
                if not payload:
                    self._close_client()
                    break

                decrypt_audio_chunk = self.cipher.decrypt_file(payload)

                if decrypt_audio_chunk:
                    audio, header = clientProtocol.unpack_file(decrypt_audio_chunk)

                    if len(header) == 3:
                        timestamp = float(header[1])
                        sender_ip = header[2]
                        self.audio_queue.put((audio, timestamp, sender_ip))
                    else:
                        print("incorrect audio msg header on client")

            except Exception as e:
                print(f"error in receiving audio message - {e}")
                self._close_client()
                break

    def send_audio(self, audio_chunk):
        """
        Send already-built audio protocol message.
        Returns True on success.
        """
        if not self.cipher or not self.open:
            return False

        try:
            encrypted = self.cipher.encrypt_file(audio_chunk)
            self.my_socket.sendall(str(len(encrypted)).zfill(8).encode())
            self.my_socket.sendall(encrypted)
            return True
        except Exception as e:
            print(f"error in sending audio message - {e}")
            self._close_client()
            return False

    def _close_client(self):
        """
        Internal socket close.
        """
        if not self.open and not self.running:
            return

        self.open = False

        try:
            self.my_socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass

        try:
            self.my_socket.close()
        except Exception as e:
            print(f"error closing audio client socket: {e}")

    def close_client(self):
        """
        Public close.
        """
        self.running = False
        self._close_client()


class AudioServer:
    def __init__(self, port=3000, AES=None, open_clients=None):
        """
        Audio TCP server.
        Receives audio from participants and allows broadcast/send.
        """
        self.port = port
        self.AES = AES
        self.open_clients = open_clients if open_clients is not None else {}

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        self.server_socket.bind(("0.0.0.0", self.port))
        self.server_socket.listen(8)

        self.audio_queue = queue.Queue()

        # audio only
        self.audio_clients = {}      # ip -> socket
        self.socket_to_ip = {}       # socket -> ip

        self.running = True

        threading.Thread(target=self._main_loop, daemon=True).start()

    def _recv_exact(self, sock, size):
        """
        Receive exactly size bytes from a client socket.
        Returns None if the socket closes.
        """
        data = b""
        while len(data) < size and self.running:
            try:
                chunk = sock.recv(size - len(data))
            except Exception as e:
                print(f"audio server recv error: {e}")
                return None

            if not chunk:
                return None

            data += chunk

        return data

    def _main_loop(self):
        """
        Accept new audio clients and receive audio messages.
        """
        print("audio server listen on port:", self.port)

        while self.running:
            try:
                rlist, _, _ = select.select(
                    [self.server_socket] + list(self.socket_to_ip.keys()),
                    [],
                    [],
                    0.01
                )
            except Exception:
                continue

            for current_socket in rlist:
                if current_socket is self.server_socket:
                    try:
                        client_socket, addr = self.server_socket.accept()
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                        client_ip = addr[0]
                        self.audio_clients[client_ip] = client_socket
                        self.socket_to_ip[client_socket] = client_ip

                        print(f"{client_ip} connected to audio server")
                    except Exception as e:
                        print(f"audio accept error: {e}")

                else:
                    client_ip = self.socket_to_ip.get(current_socket)
                    if not client_ip:
                        continue

                    try:
                        length_bytes = self._recv_exact(current_socket, 8)
                        if not length_bytes:
                            self.close_client(client_ip)
                            continue

                        msg_len = int(length_bytes.decode())
                        payload = self._recv_exact(current_socket, msg_len)
                        if not payload:
                            self.close_client(client_ip)
                            continue

                        if not self.AES:
                            continue

                        decrypt_audio_chunk = self.AES.decrypt_file(payload)
                        audio, header = clientProtocol.unpack_file(decrypt_audio_chunk)

                        if len(header) == 3:
                            timestamp = float(header[1])
                            sender_ip = header[2]
                            self.audio_queue.put((audio, timestamp, sender_ip))
                        else:
                            print("incorrect audio msg header on server")

                    except Exception as e:
                        print(f"audio receive error from {client_ip}: {e}")
                        self.close_client(client_ip)

    def send_audio(self, client_ip, audio_msg):
        """
        Send already-built audio protocol message to one client.
        """
        if client_ip not in self.audio_clients or not self.AES:
            return

        client_socket = self.audio_clients[client_ip]

        try:
            encrypted = self.AES.encrypt_file(audio_msg)
            client_socket.sendall(str(len(encrypted)).zfill(8).encode())
            client_socket.sendall(encrypted)
        except Exception as e:
            print(f"audio send error to {client_ip}: {e}")
            self.close_client(client_ip)

    def broadcast_audio(self, audio_msg, sender_ip):
        """
        Broadcast already-built audio protocol message to everyone except sender.
        """
        for ip in list(self.audio_clients.keys()):
            if ip != sender_ip:
                self.send_audio(ip, audio_msg)

    def close_client(self, client_ip):
        """
        Close one audio client safely.
        """
        try:
            if client_ip not in self.audio_clients:
                return

            client_socket = self.audio_clients[client_ip]

            if client_socket in self.socket_to_ip:
                del self.socket_to_ip[client_socket]

            del self.audio_clients[client_ip]

            try:
                client_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass

            client_socket.close()
            print(f"Audio client {client_ip} closed.")

        except Exception as e:
            print(f"error closing audio client {client_ip}: {e}")

    def close(self):
        """
        Close whole audio server.
        """
        self.running = False

        for ip in list(self.audio_clients.keys()):
            self.close_client(ip)

        try:
            self.server_socket.close()
        except Exception:
            pass