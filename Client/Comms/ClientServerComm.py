import socket
import threading
import queue
import select
from Common.Cipher import DiffiHelman, AESCipher

class ClientServer:
    def __init__(self, port, recvQ, open_clients, meeting_AES):
        self.server_socket = socket.socket()
        self.port = port
        self.recvQ = recvQ
        self.open_clients = open_clients
        # soc: ip
        self.AES = meeting_AES
        self.open_clients_soc_ip = {}
        try:
            self.server_socket.bind(('0.0.0.0', self.port))
        except OSError as e:
            self.server_socket.close()
            raise RuntimeError(
                f"Host could not bind TCP meeting port {self.port} (already in use?). "
                f"Create a new meeting or free the port. ({e})"
            ) from e
        self.server_socket.listen(4)
        threading.Thread(target=self._mainLoop,).start()

    def _recv_exact(self, sock, size):
        """
        Receive exactly `size` bytes from a socket, handling TCP fragmentation.
        :param sock: The socket to read from.
        :param size: Number of bytes to read.
        :return: The received bytes, or None if the connection was lost or an error occurred.
        """
        data = b""
        error = False
        while len(data) < size and not error:
            try:
                chunk = sock.recv(size - len(data))
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
        adds new clients and recv messages
        :return:
        """
        print("host server listen on port:", self.port)
        while True:
            rlist, _, _ = select.select([self.server_socket] + list(self.open_clients_soc_ip.keys()), [], [], 0.01)
            for current_socket in rlist:
                if current_socket is self.server_socket:
                    client_socket, addr = self.server_socket.accept()
                    print(f"{addr[0]} connected to client server")
                    if addr[0] not in self.open_clients:
                        self.open_clients[addr[0]] = [None, None]
                    self.open_clients[addr[0]][0] = client_socket
                    self.open_clients_soc_ip[client_socket] = addr[0]
                else:
                    if current_socket in self.open_clients_soc_ip.keys():
                        decrypt_msg = ""
                        current_ip = self._find_ip_by_socket(current_socket)
                        try:
                            length_bytes = self._recv_exact(current_socket, 10)
                            if not length_bytes:
                                self.close_client(current_ip)
                                continue
                            msg = self._recv_exact(current_socket, int(length_bytes.decode()))
                            if not msg:
                                self.close_client(current_ip)
                                continue
                            if current_ip and current_ip in self.open_clients:
                                decrypt_msg = self.AES.decrypt(msg)
                        except Exception as e:
                            print(f"error in receiving message - {e}")
                            self.close_client(current_ip)
                            continue
                        if decrypt_msg:
                            self.recvQ.put([current_ip, decrypt_msg])

    def close_client(self, client_ip, notify=True):
        """Closes the client connection safely and optionally notifies the host."""
        try:
            if client_ip in self.open_clients:
                client_soc = self.open_clients[client_ip][0]
                if client_soc in self.open_clients_soc_ip:
                    del self.open_clients_soc_ip[client_soc]
                del self.open_clients[client_ip]
                try:
                    client_soc.close()
                except Exception:
                    pass
                print(f"Client {client_ip} closed.")
                if notify:
                    try:
                        disconnect_msg = f"hd^#^{client_ip}"
                        self.recvQ.put([client_ip, disconnect_msg])
                    except Exception:
                        pass
        except Exception as e:
            print(f"Error closing client {client_ip}: {e}")

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

    def send_msg(self, client_ip, msg):
        """
        send msg to client at client_ip
        :param client_ip: clients ip
        :param msg: msg to send
        :return: None
        """
        if client_ip in self.open_clients.keys():
            soc = self._find_socket_by_ip(client_ip)
            self._send_msg(soc, msg)

    def broadcast(self, msg):
        """
        send msg to all connected users
        :param msg: string
        :return: None
        """
        for ip in list(self.open_clients.keys()):
            if ip:
                self.send_msg(ip, msg)

    def close(self):
        """Close all client connections without triggering disconnect notifications (used on host shutdown)."""
        for ip in list(self.open_clients.keys()):
            self.close_client(ip, notify=False)

    def _send_msg(self, client_soc, msg):
        """
        send the encrypted msg
        :param client_ip: clients ip
        :param msg: msg 2 send
        :return: None
        """
        if client_soc in self.open_clients_soc_ip.keys():
            client_ip = self._find_ip_by_socket(client_soc)
            encrypted_msg =self.AES.encrypt(msg)
            try:
                client_soc.send(str(len(encrypted_msg)).zfill(10).encode())  # Send message length
                client_soc.send(encrypted_msg)  # Send the encrypted message
            except Exception as e:
                print(f"error in sending message - {e}")
                self.close_client(client_ip)

    def _find_ip_by_socket(self, client_soc):
        """
        find client ip by socket
        :param client_soc: the client's socket used for search
        :return: clients ip
        """
        ret = ""
        if client_soc in self.open_clients_soc_ip.keys():
            ret = self.open_clients_soc_ip[client_soc]
        return ret

if __name__ == "__main__":
    msgsQ = queue.Queue()
    # Create the server and client
    myServer = ClientServer(1234, msgsQ)
    print(msgsQ.get())
    myServer.send_msg("127.0.0.1", "hello client")
