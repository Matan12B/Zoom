import socket
import threading
import queue
import pickle
import time
import cv2
import numpy as np
from Common.Cipher import AESCipher


class VideoComm:
    def __init__(self, port, key_string, users=None):
        """
        Create comm objects, queues and start receiving frames
        """
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(("0.0.0.0", port))
        self.AES = AESCipher(key_string)
        self.frameQ = queue.Queue()
        self.users = users if users else []
        self.MAX_SIZE = 65507  # max UDP packet size
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
                break  # happens when socket closes
            except Exception as e:
                print("Receive error:", e)

    def send_frame(self, frame):
        """
        Send frame (numpy array) to all users
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
        except Exception:
            pass
        self.udp_socket.close()


# ----------------- Example Usage -----------------
def main():
    key = "testkey123"

    # Video comm setup
    server = VideoComm(5000, key, users=[])
    client = VideoComm(5001, key, users=[])

    # Connect them
    server.add_user("127.0.0.1", 5001)
    client.add_user("127.0.0.1", 5000)

    print("Users connected. Press 'q' to quit.")

    # Open local camera for server
    cap = cv2.VideoCapture(0)  # camera 0
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    try:
        while True:
            # --- Capture and send frame ---
            ret, frame = cap.read()
            if not ret:
                continue

            server.send_frame(frame)

            # --- Display received frames from client ---
            while not server.frameQ.empty():
                recv_frame, addr = server.frameQ.get()
                cv2.imshow(f"Received from {addr}", recv_frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            time.sleep(0.02)  # small delay to reduce CPU usage

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        server.close()
        client.close()


if __name__ == "__main__":
    main()