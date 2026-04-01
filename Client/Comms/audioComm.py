# audioComm.py

import socket
import threading
import queue
import select

from Client.Protocol import clientProtocol


class AudioClient:
    def __init__(self, server_ip, AES, port=3000):
        """
        Initialize the AudioClient and connect to the audio server in a background thread.

        :param server_ip: IP address of the audio server to connect to.
        :param AES: AES cipher instance used for encrypting/decrypting audio data.
        :param port: TCP port of the audio server (default: 3000).
        """
        self.server_ip = server_ip
        self.port = port
        self.cipher = AES
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.my_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.audio_queue = queue.Queue(maxsize=60)  # ~600 ms cap; oldest dropped on overflow
        self.running = True
        self.open = False
        threading.Thread(target=self._main_loop, daemon=True).start()

    def _recv_exact(self, size):
        """
        Receive exactly `size` bytes from the server socket.

        :param size: Number of bytes to read.
        :return: The received bytes, or None if the connection was lost or an error occurred.
        """
        data = b""
        error = False
        while len(data) < size and self.running and self.open and not error:
            try:
                chunk = self.my_socket.recv(size - len(data))
                if not chunk:
                    error = True
                else:
                    data += chunk
            except Exception as e:
                print(f"client recv error: {e}")
                error = True
        return None if error else data

    def _main_loop(self):
        """
        Connect to the server and continuously receive encrypted audio chunks,
        decrypting and queuing them for playback. Runs in a background daemon thread.
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
                length_bytes = self._recv_exact(10)
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
                        if self.audio_queue.full():
                            # Drop the oldest chunk to keep latency low
                            try:
                                self.audio_queue.get_nowait()
                            except queue.Empty:
                                pass
                        try:
                            self.audio_queue.put_nowait((audio, timestamp, sender_ip))
                        except queue.Full:
                            pass
                    else:
                        print("incorrect audio msg header on client")
            except Exception as e:
                print(f"error in receiving audio message -msg: {decrypt_audio_chunk} {e}")
                self._close_client()
                break

    def send_audio(self, audio_chunk):
        """
        Encrypt and send an audio chunk to the server.

        :param audio_chunk: Raw audio bytes to send.
        :return: True if sent successfully, False otherwise.
        """
        if not self.cipher or not self.open:
            return False
        try:
            encrypted = self.cipher.encrypt_file(audio_chunk)
            self.my_socket.sendall(str(len(encrypted)).zfill(10).encode())
            self.my_socket.sendall(encrypted)
            return True
        except Exception as e:
            print(f"error in sending audio message - {e}")
            self._close_client()
            return False

    def _close_client(self):
        """
        Shut down and close the client socket, marking the connection as closed.
        """
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
        Stop the client's receive loop and close the connection gracefully.
        """
        self.running = False
        self._close_client()

class AudioServer:
    def __init__(self, port=3000, AES=None, open_clients=None):
        """
        Initialize and start the AudioServer, binding to the given port and listening for connections.

        :param port: TCP port to listen on (default: 3000).
        :param AES: AES cipher instance used for encrypting/decrypting audio data.
        :param open_clients: Optional dict of already-tracked clients (IP -> socket).
        """
        self.port = port
        self.AES = AES
        self.open_clients = open_clients if open_clients is not None else {}
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # for reusing port after server close
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # for faster data transfer
        self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.server_socket.bind(("0.0.0.0", self.port))
        self.server_socket.listen(5)
        self.audio_queue = queue.Queue()
        self.audio_clients = {}
        self.socket_to_ip = {}
        self.running = True
        threading.Thread(target=self._main_loop, daemon=True).start()

    def _recv_exact(self, sock, size):
        """
        Receive exactly `size` bytes from a given client socket.

        :param sock: The client socket to read from.
        :param size: Number of bytes to read.
        :return: The received bytes, or None if the connection was lost or an error occurred.
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
        Accept new client connections and receive encrypted audio from connected clients
        using select-based multiplexing. Decrypted audio is placed on the audio_queue.
        Runs in a background daemon thread.
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
                        length_bytes = self._recv_exact(current_socket, 10)
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
                            self.audio_queue.put((audio, timestamp, client_ip))
                        else:
                            print("incorrect audio msg header on server")
                    except Exception as e:
                        print(f"audio receive error from {client_ip}: {e}")
                        self.close_client(client_ip)

    def send_audio(self, client_ip, audio_msg):
        """
        Encrypt and send an audio message to a specific connected client.

        :param client_ip: IP address of the target client.
        :param audio_msg: Raw audio bytes to send.
        """
        if client_ip not in self.audio_clients or not self.AES:
            return
        client_socket = self.audio_clients[client_ip]
        try:
            encrypted = self.AES.encrypt_file(audio_msg)
            client_socket.sendall(str(len(encrypted)).zfill(10).encode())
            client_socket.sendall(encrypted)
        except Exception as e:
            print(f"audio send error to {client_ip}: {e}")
            self.close_client(client_ip)

    def broadcast_audio(self, audio_msg, sender_ip):
        """
        Send an audio message to all connected clients except the sender.
        Encrypts the payload exactly once and reuses the same ciphertext for every
        recipient (all clients share the same meeting AES key), reducing CPU load
        from O(N) to O(1) AES operations per broadcast.

        :param audio_msg: Raw audio bytes to broadcast.
        :param sender_ip: IP address of the original sender, who will be excluded.
        """
        recipients = [ip for ip in self.audio_clients if ip != sender_ip]
        if not recipients or not self.AES:
            return
        try:
            encrypted = self.AES.encrypt_file(audio_msg)
            length_header = str(len(encrypted)).zfill(10).encode()
        except Exception as e:
            print(f"audio broadcast encrypt error: {e}")
            return
        for ip in recipients:
            client_socket = self.audio_clients.get(ip)
            if not client_socket:
                continue
            try:
                client_socket.sendall(length_header)
                client_socket.sendall(encrypted)
            except Exception as e:
                print(f"audio broadcast send error to {ip}: {e}")
                self.close_client(ip)

    def close_client(self, client_ip):
        """
        Disconnect and remove a specific client from the server.

        :param client_ip: IP address of the client to close.
        """
        if client_ip in self.audio_clients:
            try:
                client_socket = self.audio_clients[client_ip]
                self.socket_to_ip.pop(client_socket, None)
                self.audio_clients.pop(client_ip, None)
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
        Stop the server, close all client connections, and release the server socket.
        """
        self.running = False
        for ip in list(self.audio_clients.keys()):
            self.close_client(ip)
        try:
            self.server_socket.close()
        except Exception:
            pass