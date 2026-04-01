import socket
import threading
import queue
import time
from Client.Logic import frameAssembler

class VideoComm:
    def __init__(self, AES, open_clients):
        """
        Video communication over UDP with AES encryption.
        :param AES:
        :param open_clients:
        :return:
        """
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.port = 5000
        self.udp_socket.bind(("0.0.0.0", self.port))
        self.AES = AES
        self.open_clients = open_clients
        self.frameQ = queue.Queue()
        self.running = True
        self.max_packet_size = 65507
        self.frame_id_counter = 0
        self.counter_lock = threading.Lock()
        # one reassembler per sender ip
        self.reassemblers = {}
        self.last_cleanup = time.time()
        threading.Thread(target=self._receive_frames, daemon=True).start()

    def _next_frame_id(self):
        """
        Return next frame id.
        :return:
        """
        with self.counter_lock:
            self.frame_id_counter = (self.frame_id_counter + 1) % 4294967295
            return self.frame_id_counter

    def _get_reassembler(self, sender_ip):
        """
        Return sender reassembler.
        :param sender_ip:
        :return:
        """
        if sender_ip not in self.reassemblers:
            self.reassemblers[sender_ip] = frameAssembler.FrameReassembler()
        return self.reassemblers[sender_ip]

    def _receive_frames(self):
        """
        Continuously receive small encrypted video packets and rebuild frames.
        :return:
        """
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(self.max_packet_size)
                decrypted_packet = self.AES.decrypt_file(data)
                sender_ip = addr[0]
                reassembler = self._get_reassembler(sender_ip)
                frame, timestamp = reassembler.handle_packet(decrypted_packet)
                if frame is not None:
                    # Allow enough room for all connected clients (at least 20 frames)
                    max_queued = max(20, len(self.open_clients) * 4)
                    while self.frameQ.qsize() >= max_queued:
                        try:
                            self.frameQ.get_nowait()
                        except queue.Empty:
                            break
                    self.frameQ.put((frame, timestamp, addr))
                now = time.time()
                if now - self.last_cleanup > 0.2:
                    self.last_cleanup = now
                    for item in self.reassemblers.values():
                        item.cleanup_old_frames(max_age=0.5)
            except OSError:
                break
            except Exception as e:
                print("Receive error:", e)

    def send_frame(self, frame_bytes, timestamp):
        """
        Send encoded JPEG bytes to all open clients using many small UDP packets.
        Each packet is encrypted exactly once; the same ciphertext is sent to every
        client (they all share the same meeting AES key), cutting encryption cost
        from O(N*packets) to O(packets).
        :param frame_bytes:
        :param timestamp:
        :return:
        """
        if not frame_bytes:
            return
        try:
            frame_id = self._next_frame_id()
            packets = frameAssembler.split_frame_to_packets(frame_id, timestamp, frame_bytes)
        except Exception as e:
            print("split frame error:", e)
            return

        clients = [ip for ip in list(self.open_clients.keys()) if ip]
        if not clients:
            return

        # Encrypt once per packet, broadcast same bytes to every client
        for packet in packets:
            try:
                encrypted_packet = self.AES.encrypt_file(packet)
            except Exception as e:
                print("encrypt packet error:", e)
                return
            for ip in clients:
                try:
                    self.udp_socket.sendto(encrypted_packet, (ip, self.port))
                except Exception as e:
                    print(f"send frame error to {ip}:", e)

    def add_user(self, user_ip, user_port):
        """
        Add user to broadcast list.
        :param user_ip:
        :param user_port:
        :return:
        """
        self.open_clients[user_ip] = user_port

    def remove_user(self, user_ip, user_port):
        """
        Remove user from broadcast list.
        :param user_ip:
        :param user_port:
        :return:
        """
        if user_ip in self.open_clients:
            del self.open_clients[user_ip]

        if user_ip in self.reassemblers:
            del self.reassemblers[user_ip]

    def close(self):
        """
        Close udp socket.
        :return:
        """
        self.running = False
        try:
            self.udp_socket.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        self.udp_socket.close()