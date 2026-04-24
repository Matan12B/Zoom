import threading
import time
import cv2
import queue
# my modules
from Client.Comms.audioComm import AudioClient
from Client.Protocol import clientProtocol
from Client.Comms.ClientComm import ClientComm
from Client.Logic.callParticipant import CallParticipant

class CallLogic(CallParticipant):
    def __init__(self, port, meeting_key, comm, host_ip, meeting_code, username="",
                 video_port=5000, audio_port=3000):
        """
        Initialize the guest participant: shared devices via parent, plus
        an AudioClient and ClientComm to communicate with the host.
        :param port: TCP port of the host's ClientServer.
        :param meeting_key: Shared AES key for the meeting.
        :param comm: Communication channel to the central server.
        :param host_ip: IP address of the host.
        :param meeting_code: The meeting room code.
        :param username: Guest's display name.
        :param video_port: UDP port for video communication.
        :param audio_port: TCP port for audio communication.
        """
        super().__init__(
            meeting_key=meeting_key,
            comm=comm,
            meeting_code=meeting_code,
            username=username,
            fallback_target_ip=host_ip,
            playout_delay=0.04,
            video_port=video_port
        )
        self.msgs_from_host = queue.Queue()
        self.comm_with_host = ClientComm(host_ip, port, self.msgs_from_host, self.AES)
        self.host_ip = host_ip
        self.host_video_ip = None
        self.audio_comm = AudioClient(host_ip, self.AES, audio_port)
        # host is always known from the start; starts muted
        self.open_clients[self.host_ip] = {"username": "Host", "muted": True}
        self.send_queue = queue.Queue(maxsize=1)
        # some commands are in the parent class
        self.commands = {
            "ha": self.handle_audio_msg,
            "hv": self.handle_video_msg,
            "hj": self.handle_join,
            "hd": self.handle_disconnect,
            "gmst": self.get_meeting_start_time,
            "fd": self.force_disconnect,
            "gh": self.get_host_username,
            "cc": self.get_connected_clients,
            "tm": self.handle_mic_status,
            "co": self.handle_camera_state,
        }

    def _resolve_video_sender(self, addr):
        """
        Map the raw UDP sender IP to the canonical participant IP,
        and return None to skip frames from self.
        Never discards frames from the host even on same-machine testing.
        :param addr: UDP (ip, port) tuple from recvfrom.
        :return: Canonical IP string, or None to discard the frame.
        """
        sender_ip = self._canonical_sender_ip(addr[0])
        result = sender_ip
        if sender_ip == self.ip and sender_ip != self.host_ip:
            result = None
        return result

    def _canonical_sender_ip(self, sender_ip):
        """
        Map a raw UDP sender IP to the participant IP used by the GUI/control layer.
        Handles cases where the host's control IP and UDP IP differ.

        :param sender_ip: Raw IP from the UDP packet.
        :return: Canonical participant IP string.
        """
        result = sender_ip
        if sender_ip == self.ip:
            result = self.ip
        elif sender_ip in self.open_clients:
            result = sender_ip
        elif self.host_video_ip is not None and sender_ip == self.host_video_ip:
            result = self.host_ip
        elif self.host_video_ip is None and self.host_ip in self.open_clients:
            self.host_video_ip = sender_ip
            print("Mapped host UDP ip", sender_ip, "to host control ip", self.host_ip)
            result = self.host_ip
        return result

    def _pre_start(self):
        """
        Verify the host connection is established before starting the call.
        Raises ConnectionError if the connection timed out or failed.
        """
        connected_ok = False
        try:
            connected_ok = self.comm_with_host.connected.wait(timeout=5)
        except AttributeError:
            connected_ok = True
        if not connected_ok:
            raise ConnectionError("Timed out connecting to host")
        if getattr(self.comm_with_host, "error", ""):
            raise ConnectionError(self.comm_with_host.error)

    def _start_threads(self):
        """
        Start guest-specific background threads: host message handler,
        audio receive loop, video send loop, and mic send loop.
        """
        threading.Thread(target=self.handle_msgs_from_host, daemon=True).start()
        threading.Thread(target=self.receive_audio_loop, daemon=True).start()
        threading.Thread(target=self.send_loop, daemon=True).start()
        threading.Thread(target=self.audio_send_loop, daemon=True).start()

    def _send_video(self, frame, timestamp):
        """
        Queue the frame for the send_loop thread to encode and transmit.

        :param frame: Raw OpenCV frame (numpy array).
        :param timestamp: Float timestamp relative to meeting start.
        """
        if self.send_queue.full():
            try:
                self.send_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            self.send_queue.put_nowait((frame, timestamp))
        except queue.Full:
            pass

    def send_loop(self):
        """
        Encode queued frames as JPEG and send them over UDP.
        Runs in a background daemon thread.
        """
        while self.running:
            try:
                frame, timestamp = self.send_queue.get(timeout=1)
                ok, encoded = cv2.imencode(".jpg", frame, self.encode_params)
                if ok:
                    self.video_comm.send_frame(encoded.tobytes(), timestamp)
            except queue.Empty:
                continue
            except Exception as e:
                print("send_loop error:", e)
                time.sleep(0.02)

    def audio_send_loop(self):
        """
        Continuously record from the microphone and send audio to the host.
        Runs in a background daemon thread.
        """
        while self.running:
            try:
                if self.mic is None or not self.mic.running or self.meeting_start_time is None:
                    time.sleep(0.01)
                    continue
                audio_chunk = self.mic.record()
                if not audio_chunk:
                    continue
                timestamp = time.time() - self.meeting_start_time
                msg = clientProtocol.build_audio_msg(timestamp, audio_chunk, self.ip)
                self.audio_comm.send_audio(msg)
            except Exception as e:
                print("audio_send_loop error:", e)
                time.sleep(0.02)

    def receive_audio_loop(self):
        """
        Drain incoming audio from the host's AudioServer and feed into AV sync.
        Runs in a background daemon thread.
        """
        while self.running:
            try:
                while not self.audio_comm.audio_queue.empty():
                    try:
                        audio_bytes, timestamp, sender_ip = self.audio_comm.audio_queue.get_nowait()
                    except queue.Empty:
                        break

                    sender_ip = self._canonical_sender_ip(sender_ip)

                    if sender_ip == self.ip:
                        continue

                    if sender_ip not in self.open_clients:
                        self.open_clients[sender_ip] = {"username": sender_ip}

                    self.av_sync.add_audio(sender_ip, float(timestamp), audio_bytes)

                time.sleep(0.001)

            except Exception as e:
                print("receive_audio_loop error:", e)
                time.sleep(0.01)

    def handle_msgs_from_client_logic(self, opcode, data):
        """
        Dispatch a command received from the local client logic layer.

        :param opcode: Command string key.
        :param data: Associated data payload.
        """
        try:
            if opcode in self.commands:
                self.commands[opcode](data)
        except Exception as e:
            print(f"Error handling message: {e}")

    def handle_msgs_from_host(self):
        """
        Consume messages from the host TCP queue, unpack them,
        and dispatch to the appropriate command handler.
        Runs in a background daemon thread.
        """
        while self.running:
            try:
                msg = self.msgs_from_host.get(timeout=1)
            except queue.Empty:
                continue
            except Exception as e:
                print("host queue error:", e)
                time.sleep(0.05)
                continue

            print(f"Received message from host: {msg}")

            try:
                opcode, data = clientProtocol.unpack(msg)
            except Exception as e:
                print("unpack error:", e)
                continue

            if opcode in self.commands:
                try:
                    self.commands[opcode](data)
                except Exception as e:
                    print(f"Error in command {opcode}: {e}")

    def get_meeting_start_time(self, data):
        """
        Store the meeting start time received from the host for AV sync.

        :param data: Float or single-element list containing the start time.
        """
        try:
            self.meeting_start_time = float(data[0]) if isinstance(data, list) else float(data)
            print("meeting start time:", self.meeting_start_time)
        except Exception as e:
            print("meeting start time parse error:", e)

    def get_host_username(self, username):
        """
        Store the host's display name in open_clients.

        :param username: The host's username string.
        """
        if self.host_ip not in self.open_clients:
            self.open_clients[self.host_ip] = {}
        entry = self.open_clients[self.host_ip]
        if isinstance(entry, dict):
            entry.setdefault("muted", True)
            entry["username"] = username
        else:
            self.open_clients[self.host_ip] = {"username": username, "muted": True}

    def get_connected_clients(self, connected_clients):
        """
        Register participants already in the meeting when this guest joins.

        :param connected_clients: Dict of {ip: username} for existing participants.
        """
        if isinstance(connected_clients, dict):
            for ip, username in connected_clients.items():
                if ip != self.ip and ip != self.host_ip:
                    self.open_clients[ip] = {"username": username, "muted": True}

    def handle_video_msg(self, data):
        """
        Handle a video frame message forwarded by the host.

        :param data: List [sender_ip, ?, timestamp, frame_bytes].
        """
        try:
            sender_ip = self._canonical_sender_ip(data[0])
            timestamp = float(data[2])
            frame = data[3]
            self.av_sync.add_video(sender_ip, timestamp, frame)
        except Exception as e:
            print("video msg parse error:", e)

    def handle_audio_msg(self, data):
        """
        Handle an audio chunk message forwarded by the host.
        :param data: List [sender_ip, ?, timestamp, audio_bytes].
        """
        try:
            sender_ip = self._canonical_sender_ip(data[0])
            timestamp = float(data[2])
            audio = data[3]
            self.av_sync.add_audio(sender_ip, timestamp, audio)
        except Exception as e:
            print("audio msg parse error:", e)

    def handle_join(self, data):
        """
        Register a new participant who joined the meeting.
        :param data: List [ip, port, shared_key, username].
        """
        try:
            ip = data[0]
            username = data[3]
        except Exception as e:
            print("join parse error:", e)
            return
        if ip != self.ip:
            self.open_clients[ip] = {"username": username, "muted": True}

    def handle_mic_status(self, data):
        """
        Store a participant's mic mute state received from the host.
        :param data: [sender_ip, "1"|"0"]
        """
        try:
            sender_ip = data[0] if isinstance(data, list) else data
            muted = bool(int(data[1])) if isinstance(data, list) else False
        except Exception as e:
            print("handle_mic_status parse error:", e)
            return

        if sender_ip not in self.open_clients:
            self.open_clients[sender_ip] = {}
        entry = self.open_clients[sender_ip]
        if isinstance(entry, dict):
            entry["muted"] = muted

    def broadcast_mic_status(self, muted):
        """
        Guest sends their mic state to the host so it can relay it to others.
        :param muted: bool
        """
        try:
            msg = clientProtocol.build_toggle_mic(self.ip, muted)
            self.comm_with_host.send_msg(msg)
        except Exception as e:
            print("broadcast_mic_status error:", e)

    def toggle_mic(self, muted):
        """Alias for broadcast_mic_status — called by the GUI."""
        self.broadcast_mic_status(muted)

    def notify_camera_state(self, is_on):
        """
        Guest notifies the host that their camera turned on or off.
        The host will relay it to all other guests.
        """
        try:
            msg = clientProtocol.build_camera_state(self.ip, is_on)
            self.comm_with_host.send_msg(msg)
        except Exception as e:
            print("notify_camera_state error:", e)

    def force_disconnect(self, data=None):
        """
        Force-disconnect this client as instructed by the server.

        :param data: Unused payload.
        """
        self.leave_call()

    def _close_comms(self):
        """
        Close the AudioClient and host TCP connection after devices are cleaned up.
        """
        try:
            if hasattr(self.audio_comm, "close_client"):
                self.audio_comm.close_client()
        except Exception as e:
            print("audio close error:", e)

        try:
            if hasattr(self.comm_with_host, "close_client"):
                self.comm_with_host.close_client()
        except Exception as e:
            print("host comm close error:", e)

    def close(self):
        """
        Stop the guest call and clean up all resources.
        Notifies the signaling server that we left the meeting (session stays logged in).
        """
        if self.running:
            try:
                if self.meeting_code and self.comm and getattr(self.comm, "running", False):
                    self.comm.send_msg(clientProtocol.build_leave_meeting(self.meeting_code))
            except Exception as e:
                print("notify server leave error:", e)
            print("Closing guest call...")
            super().close()