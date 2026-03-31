import socket
import threading
import queue
import sys
import time
from Client.Protocol import clientProtocol
from Common.Cipher import DiffiHelman, AESCipher
import os

class ClientComm:
    def __init__(self, server_ip, port, recvQ, AES=None):
        self.my_socket = socket.socket()
        self.server_ip = server_ip
        self.port = port
        self.recvQ = recvQ
        self.cipher = AES
        self.running = False
        self.open_clients= {}
        self.connected = threading.Event()
        self.error: str = ""
        threading.Thread(target=self._mainLoop,).start()

    def _recv_exact(self, size):
        """
        Receive exactly `size` bytes from the server socket, handling TCP fragmentation.

        :param size: Number of bytes to read.
        :return: The received bytes, or None if the connection was lost or an error occurred.
        """
        data = b""
        error = False
        while len(data) < size and self.running and not error:
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

    def _mainLoop(self):
        """
        connect to client and exchange keys and recv messages
        :return: None
        """
        connect = False
        try:
            self.my_socket.connect((self.server_ip, self.port))
            connect = True
        except Exception as e:
            self.error = f"connection failed: {e}"
            self.connected.set()
        if connect:
            if self.cipher is None:
                self._exchange_key()
            if not self.cipher:
                self.error = "key exchange failed"
                self.connected.set()
            else:
                self.running = True
                self.connected.set()
        while self.running:
            try:
                length_bytes = self._recv_exact(10)
                if not length_bytes:
                    print("Server disconnected gracefully.")
                    self._close_client()
                    break
                msg = self._recv_exact(int(length_bytes.decode()))
                if not msg:
                    print("Server disconnected gracefully.")
                    self._close_client()
                    break
                decrypt_msg = self.cipher.decrypt(msg)
            except Exception as e:
                print(f"error in receiving message here - {e}")
                self._close_client()
                break
            if decrypt_msg:
                self.recvQ.put(decrypt_msg)

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
        self.running = False

    def close_client(self):
        """
        close the connection
        :return: None
        """
        self._close_client()

    def client_exchange(self, diffie):
        """
        exchange keys with server according to clientProtocol
        :param diffie: diffie helman object
        :return: shared key as string
        """
        server_public_key = None
        ret = None
        try:
            raw = self._recv_exact(5)
            if raw:
                server_public_key = int(raw.decode())
            self.my_socket.send(str(diffie.public_key).zfill(5).encode())
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
        shared_key = self.client_exchange(diffie)
        flag = False
        if shared_key:
            self.cipher = AESCipher(shared_key)
            print(f"Shared key established with server - {shared_key}")
            flag = True
        return flag

    def send_msg(self, msg):
        """
        send message to server
        :param msg:
        :return:
        """
        flag = False
        if self.cipher and self.running:
            msg = self.cipher.encrypt(msg)
            if len(msg) > 0:
                try:
                    self.my_socket.send(str(len(msg)).zfill(10).encode())
                    self.my_socket.send(msg)
                    flag = True
                except Exception as e:
                    print(f"error in sending message - {e}")
                    self._close_client()
                    self.running = False
        return flag

if __name__ == "__main__":
    msgsQ = queue.Queue()
    myClient = ClientComm("127.0.0.1", 1234, msgsQ)
    time.sleep(0.2)
    myClient.send_msg("hello server")
    print(msgsQ.get())







