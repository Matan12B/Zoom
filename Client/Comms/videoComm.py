import socket
import threading
import queue
import pickle
import time
from Common.Cipher import AESCipher

class VideoComm:

    def __init__(self, port, key_string, msgQ=None, users={}):
        """
        Create comm objects queues and starts _receive_frames
        """
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(("0.0.0.0", port))
        self.AES = AESCipher(key_string)
        self.frameQ = queue.Queue()
        self.users = users
        self.MAX_SIZE = 65507
        self.running = True
        threading.Thread(target=self._receive_frames, daemon=True).start()

    def _receive_frames(self):
        """
        Thread that constantly receives frames
        """
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(self.MAX_SIZE)
                decrypted_data = self.AES.decrypt_file(data)
                frame = pickle.loads(decrypted_data)
                self.frameQ.put((frame, addr))
            except OSError:
                # happens when socket closes
                break

            except Exception as e:
                print("Receive error:", e)

    def send_frame(self, frame):
        """
        Send frame to all users
        """
        try:
            raw_data = pickle.dumps(frame)
            encrypted = self.AES.encrypt_file(raw_data)
            for user in self.users:
                self.udp_socket.sendto(encrypted, user)
        except Exception as e:
            print("Send error:", e)

    def add_user(self, user_ip, user_port):
        """
        Add user to broadcast list
        """
        if (user_ip, user_port) not in self.users:
            self.users[user_ip] =
            self.users.append((user_ip, user_port))

    def remove_user(self, user_ip, user_port):
        """
        Remove user
        """
        if (user_ip, user_port) in self.users:
            self.users.remove((user_ip, user_port))

    def close(self):
        """
        Close communication
        """
        self.running = False
        try:
            self.udp_socket.shutdown(socket.SHUT_RDWR)
        except Exception as e:
            print("Close error:", e)
        self.udp_socket.close()


def main():
    key = "testkey123"

    # create two endpoints
    server = VideoComm(5000, key, users=[])
    client = VideoComm(5001, key, users=[])

    # connect them
    server.add_user("127.0.0.1", 5001)
    client.add_user("127.0.0.1", 5000)

    print("Users connected")

    # send frame from server
    frame1 = {"frame_id": 1, "data": "Hello frame"}
    print("Sending frame from server...")
    server.send_frame(frame1)

    time.sleep(1)

    if not client.frameQ.empty():
        frame, addr = client.frameQ.get()
        print("Client received frame:", frame)
        print("From:", addr)
    else:
        print("Client did not receive frame")
    # send frame from client
    frame2 = {"frame_id": 2, "data": "Reply frame"}
    print("Sending frame from client...")
    client.send_frame(frame2)
    time.sleep(1)
    if not server.frameQ.empty():
        frame, addr = server.frameQ.get()
        print("Server received frame:", frame)
        print("From:", addr)
    else:
        print("Server did not receive frame")
    server.close()
    client.close()


if __name__ == "__main__":
    main()