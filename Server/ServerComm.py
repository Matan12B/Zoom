import socket
import threading
import queue
import select
from Common.Cipher import DiffiHelman, AESCipher

class ServerComm:
    def __init__(self, port, recvQ, dh_p=797, dh_g=100):
        self.server_socket = socket.socket()
        self.port = port
        self.recvQ = recvQ
        self.dh_p = dh_p
        self.dh_g = dh_g
        # client_id: [soc, AES]
        self.open_clients= {}
        # soc: client_id
        self.open_clients_soc_ip = {}
        self.client_addresses = {}
        self.server_socket.bind(('0.0.0.0', self.port))
        self.server_socket.listen(32)
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
            except Exception as e:
                print(f"server recv error: {e}")
                error = True
            if not error and not chunk:
                error = True
            if not error:
                data += chunk
        return None if error else data

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
                    client_id = f"{addr[0]}:{addr[1]}"
                    self.client_addresses[client_id] = addr[0]
                    print(f"{client_id} connected")
                    threading.Thread(target=self._exchange_key, args=(client_socket, client_id,)).start()
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
                                decrypt_msg = self.open_clients[current_ip][1].decrypt(msg)
                        except Exception as e:
                            print(f"error in receiving message - {e}")
                            self.close_client(current_ip)
                            continue
                        if decrypt_msg:
                            self.recvQ.put([current_ip, decrypt_msg])

    def _exchange_key(self, client_soc, client_ip):
        """
        Exchange the Diffie-Hellman key with the client and establish a shared AES key.
        :param client_soc: The client's socket.
        :param client_ip: The client's IP address.
        """
        diffie = DiffiHelman(self.dh_p, self.dh_g)
        shared_key = None
        client_public_key = None
        try:
            client_soc.send(str(diffie.public_key).zfill(5).encode())
            raw = self._recv_exact(client_soc, 5)
            if raw:
                client_public_key = int(raw.decode())
        except Exception as e:
            print(f"Error in sending/receiving public key: {e}")
        if client_public_key:
            shared_key = diffie.create_shared_key(client_public_key)

        if shared_key:
            print(f"Shared key established with client {client_ip}: {shared_key}")
            self.open_clients[client_ip] = [client_soc, AESCipher(shared_key)]
            self.open_clients_soc_ip[client_soc] = client_ip
        else:
            print(f"Failed to establish shared key with {client_ip}")

    def close_client(self, client_ip):
        """
        Safely disconnects a client and removes them from tracking dictionaries.
        Notifies serverLogic via recvQ with a "dc" (disconnect) message so that
        meetings owned by this client are properly cleaned up.
        Note: use .pop() instead of del to prevent thread-safety errors
        (KeyErrors) if multiple threads try to close the same client at once.
        :param client_ip: The IP address of the client to disconnect.
        """
        try:
            if client_ip in self.open_clients:
                client_soc = self.open_clients[client_ip][0]
                # Safely remove from dictionaries without throwing KeyErrors
                self.open_clients_soc_ip.pop(client_soc, None)
                self.open_clients.pop(client_ip, None)
                self.client_addresses.pop(client_ip, None)
                client_soc.close()
                print(f"Client {client_ip} closed.")
                # Notify serverLogic so it can tear down any meeting this client owned
                self.recvQ.put([client_ip, "dc^#^"])
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
        send msg to client
        :param client_ip: clients ip
        :param msg: msg to send
        :return: None
        """
        if client_ip in self.open_clients.keys():
            soc = self._find_socket_by_ip(client_ip)
            self._send_msg(soc, msg)

    def get_client_address(self, client_ip):
        """
        Return the network address for a signaling client id.
        """
        return self.client_addresses.get(client_ip, client_ip.split(":")[0])

    def broadcast(self, msg):
        """
        send msg to all connected users
        :param msg: string
        :return:
        """
        for ip in list(self.open_clients.keys()):
            if ip:
                self.send_msg(ip, msg)

    def _send_msg(self, client_soc, msg):
        """
        send the encrypted msg
        :param client_ip:
        :param msg:
        :return:
        """
        if client_soc in self.open_clients_soc_ip.keys():
            client_ip = self._find_ip_by_socket(client_soc)
            encrypted_msg = self.open_clients[client_ip][1].encrypt(msg)
            try:
                client_soc.send(str(len(encrypted_msg)).zfill(10).encode())  # Send message length
                client_soc.send(encrypted_msg)  # Send the encrypted message
            except Exception as e:
                print(f"error in sending message - {e}")
                self.close_client(client_ip)

    def _find_ip_by_socket(self, client_soc):
        ret = ""
        if client_soc in self.open_clients_soc_ip.keys():
            ret = self.open_clients_soc_ip[client_soc]
        return ret

if __name__ == "__main__":
    msgsQ = queue.Queue()
    # Create the server and client
    myServer = ServerComm(1234, msgsQ)
    print(msgsQ.get())
    myServer.send_msg("127.0.0.1", "hello client")
