import socket
import threading
import queue
import time
import cv2
import numpy as np
from Common.Cipher import AESCipher


class VideoComm:
    def __init__(self, port, key_string, users=None):
        """
        Video communication over UDP with AES encryption and JPEG compression.
        :param port: Local UDP port to bind
        :param key_string: AES encryption key
        :param users: list of (ip, port) tuples
        """
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(("0.0.0.0", port))
        self.AES = AESCipher(key_string)
        self.frameQ = queue.Queue()
        self.users = users if users else []
        self.running = True
        self.MAX_PACKET_SIZE = 65507  # max UDP datagram size
        threading.Thread(target=self._receive_frames, daemon=True).start()

    def _receive_frames(self):
        """
        Continuously receive frames from other users.
        """
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(self.MAX_PACKET_SIZE)
                decrypted_data = self.AES.decrypt_file(data)
                # Decode JPEG bytes back to NumPy array
                np_arr = np.frombuffer(decrypted_data, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    self.frameQ.put((frame, addr))
            except OSError:
                break  # Socket closed
            except Exception as e:
                print("Receive error:", e)

    def send_frame(self, frame):
        """
        Compress frame to JPEG, encrypt it, and send to all users.
        :param frame: NumPy array (BGR)
        """
        try:
            # Compress frame as JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 15])
            if not ret:
                return
            frame_bytes = buffer.tobytes()
            size_bytes = len(frame_bytes)
            print(f"Frame size: {size_bytes} bytes")
            # Encrypt
            encrypted = self.AES.encrypt_file(frame_bytes)

            # Send to all users
            for user in self.users:
                self.udp_socket.sendto(encrypted, user)

        except Exception as e:
            print("Send error:", e)

    def add_user(self, user_ip, user_port):
        """
        Add a user to broadcast list.
        """
        if (user_ip, user_port) not in self.users:
            self.users.append((user_ip, user_port))

    def remove_user(self, user_ip, user_port):
        """
        Remove user from broadcast list.
        """
        if (user_ip, user_port) in self.users:
            self.users.remove((user_ip, user_port))

    def close(self):
        """
        Close the UDP socket.
        """
        self.running = False
        try:
            self.udp_socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        self.udp_socket.close()


def main():
    key = "testkey123"
    port = 5000

    # Get remote IP from user
    # remote_ip = input("Enter remote machine IP (or press Enter to skip): ").strip()
    remote_ip = "10.0.0.5"
    # Create video comm
    video_comm = VideoComm(port, key, users=[])

    # Add remote user if provided
    if remote_ip:
        video_comm.add_user(remote_ip, port)
        print(f"Connected to {remote_ip}:{port}")
    else:
        print("No remote IP provided. Waiting for incoming connections...")

    print("Video communication started. Press 'q' to quit.")

    # Open local camera
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    try:
        while True:
            ret, frame = cap.read()
            if ret:
                video_comm.send_frame(frame)
                cv2.imshow("My Camera", frame)
            while not video_comm.frameQ.empty():
                recv_frame, addr = video_comm.frameQ.get()
                cv2.imshow(f"Received from {addr}", recv_frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            time.sleep(0.02)  # slight delay to reduce CPU

    except KeyboardInterrupt:
        print("Shutting down...")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        video_comm.close()


if __name__ == "__main__":
    main()
