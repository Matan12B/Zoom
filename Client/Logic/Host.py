import threading
import time
import cv2
import queue

from Client.Devices.Camera import CameraControl
from Client.Devices.Microphone import Microphone
from Client.Devices.AudioOutputDevice import AudioOutput
from Client.Comms.videoComm import VideoComm
from Client.Comms.audioComm import AudioServer
from Client.Protocol import clientProtocol
from Client.Comms.ClientServerComm import ClientServer
from Common.Cipher import AESCipher
from Client.Logic.av_sync import AVSyncManager
from Client.Logic.callParticipant import CallParticipant


class Host(CallParticipant):
    def __init__(self, port, meeting_key, comm, meeting_code, username,
                 video_port=5000, audio_port=3000):
        """
        Initialize the host participant: shared devices via parent, plus
        the host-side TCP server and AudioServer for managing guests.

        :param port: TCP port for the host's ClientServer.
        :param meeting_key: Shared AES key for the meeting.
        :param comm: Communication channel to the central server.
        :param meeting_code: The meeting room code.
        :param username: Host's display name.
        :param video_port: UDP port for video communication.
        :param audio_port: TCP port for audio communication.
        """
        super().__init__(
            meeting_key=meeting_key,
            comm=comm,
            meeting_code=meeting_code,
            username=username,
            fallback_target_ip="8.8.8.8",
            playout_delay=0.03,
            video_port=video_port
        )

        self.msgQ = queue.Queue()
        self.host_server = ClientServer(port, self.msgQ, self.open_clients, self.AES)
        self.audio_comm = AudioServer(port=audio_port, AES=self.AES, open_clients=self.open_clients)

        self.commands = {
            "hj": self.handle_join,
            "hd": self.handle_disconnect,
            "fd": self.on_meeting_closed_by_server,
        }

    def _default_client_entry(self, ip):
        """
        Return a host-style open_clients entry for a newly seen video sender.

        :param ip: The new client's IP address.
        :return: List placeholder [socket, port].
        """
        return [None, 0]

    def _pre_start(self):
        """
        Set the meeting start time so the host can immediately begin timestamping AV data.
        """
        self.meeting_start_time = time.time()

    def _start_threads(self):
        """
        Start host-specific background threads: guest message handler,
        audio receive/relay loop, and host mic send loop.
        """
        threading.Thread(target=self.handle_msgs_from_guests, daemon=True).start()
        threading.Thread(target=self.receive_audio_loop, daemon=True).start()
        threading.Thread(target=self.host_audio_send_loop, daemon=True).start()

    def _send_video(self, frame, timestamp):
        """
        Encode the frame as JPEG and send it directly to all guests.

        :param frame: Raw OpenCV frame (numpy array).
        :param timestamp: Float timestamp relative to meeting start.
        """
        ok, encoded = cv2.imencode(".jpg", frame, self.encode_params)
        if ok:
            self.video_comm.send_frame(encoded.tobytes(), timestamp)

    def receive_audio_loop(self):
        """
        Drain incoming audio from guests, feed into AV sync,
        and broadcast each chunk back to all other guests.
        Runs in a background daemon thread.
        """
        while self.running:
            try:
                while not self.audio_comm.audio_queue.empty():
                    try:
                        audio_bytes, timestamp, sender_ip = self.audio_comm.audio_queue.get_nowait()
                    except queue.Empty:
                        break

                    self.av_sync.add_audio(sender_ip, float(timestamp), audio_bytes)

                    try:
                        msg = clientProtocol.build_audio_msg(float(timestamp), audio_bytes, sender_ip)
                        self.audio_comm.broadcast_audio(msg, sender_ip)
                    except Exception as e:
                        print("audio relay error:", e)

                time.sleep(0.001)

            except Exception as e:
                print("receive_audio_loop error:", e)
                time.sleep(0.01)

    def host_audio_send_loop(self):
        """
        Continuously record from the microphone and broadcast the host's
        audio to all connected guests.
        Runs in a background daemon thread.
        """
        while self.running:
            try:
                if not self.mic.running or self.meeting_start_time is None:
                    time.sleep(0.01)
                    continue

                audio_chunk = self.mic.record()
                if not audio_chunk:
                    continue

                timestamp = time.time() - self.meeting_start_time
                audio_msg = clientProtocol.build_audio_msg(timestamp, audio_chunk, self.ip)
                self.audio_comm.broadcast_audio(audio_msg, self.ip)

            except Exception as e:
                print("host_audio_send_loop error:", e)
                time.sleep(0.02)

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

    def handle_msgs_from_guests(self):
        """
        Consume messages from the guest TCP queue, unpack them,
        and dispatch to the appropriate command handler.
        Runs in a background daemon thread.
        """
        while self.running:
            try:
                msg = self.msgQ.get(timeout=0.5)
            except queue.Empty:
                continue

            print(f"Received message from guest: {msg}")

            try:
                guest_ip = msg[0]
                raw_msg = msg[1]
                opcode, data = clientProtocol.unpack(raw_msg)
            except Exception as e:
                print("unpack error:", e)
                continue

            if opcode == "hd":
                if isinstance(data, list):
                    if len(data) == 0:
                        data = [guest_ip]
                    else:
                        data[0] = guest_ip
                else:
                    data = [guest_ip]

            if opcode in self.commands:
                try:
                    self.commands[opcode](data)
                except Exception as e:
                    print(f"Error in command {opcode}: {e}")

    def kick_client(self, client_ip):
        """
        Kick a specific guest from the meeting.
        Sends them a force-disconnect message, then cleans up as if they left.

        :param client_ip: IP address of the guest to kick.
        """
        if client_ip not in self.open_clients:
            print(f"Cannot kick {client_ip}: not in open_clients")
            return

        # Send force-disconnect to the kicked guest
        try:
            kick_msg = clientProtocol.build_kick_msg()
            self.host_server.send_msg(client_ip, kick_msg)
        except Exception as e:
            print(f"kick send error to {client_ip}: {e}")

        # Small delay so the message has time to arrive before we tear down their socket
        time.sleep(0.1)

        # Reuse the existing disconnect handler to clean up everything
        self.handle_disconnect([client_ip])

    def handle_disconnect(self, data):
        """
        Handle a guest leaving: resolve their username, clean up shared state,
        close their audio connection, and broadcast the departure to remaining guests.

        :param data: List where data[0] is the leaver's IP, data[1] is optional username.
        """
        try:
            leaving_ip = data[0] if len(data) > 0 else ""
            leaving_username = leaving_ip

            # Capture username before base class removes the open_clients entry
            if leaving_ip and leaving_ip in self.open_clients:
                entry = self.open_clients[leaving_ip]
                if isinstance(entry, list) and len(entry) >= 3 and entry[2]:
                    leaving_username = entry[2]
        except Exception:
            leaving_ip = ""
            leaving_username = ""

        # Close host_server TCP socket BEFORE base-class cleanup deletes the IP
        # from the shared open_clients dict.  If we delete first, ClientServerComm
        # can no longer look up the socket → it stays in open_clients_soc_ip and
        # select() keeps returning the dead socket, causing endless recv errors.
        try:
            self.host_server.close_client(leaving_ip, notify=False)
        except Exception:
            pass

        # Close the audio server connection for the departed client
        try:
            self.audio_comm.close_client(leaving_ip)
        except Exception:
            pass

        # Base-class cleanup: removes from open_clients, av_sync, video_comm, frames
        super().handle_disconnect(data)

        # Notify all remaining guests so their UIs remove the departed participant
        if leaving_ip:
            try:
                notify_msg = f"hd^#^{leaving_ip}^#^{leaving_username}"
                self.host_server.broadcast(notify_msg)
            except Exception as e:
                print("disconnect broadcast error:", e)

    def handle_join(self, data):
        """
        Handle a guest joining: register their info, wait for socket assignment,
        then send them the meeting start time, host username, and current client list.

        :param data: List [ip, port, ?, username].
        """
        ip = data[0]
        port = int(data[1])
        client_username = data[3]

        if ip == self.ip:
            return

        if ip not in self.open_clients:
            self.open_clients[ip] = [None, port, client_username]
        else:
            existing_socket = self.open_clients[ip][0] if isinstance(self.open_clients[ip], list) else None
            self.open_clients[ip] = [existing_socket, port, client_username]

        time.sleep(0.1)

        # Wait until ClientServer assigns the TCP socket (or client disconnects)
        deadline = time.time() + 5.0
        while self.running and time.time() < deadline:
            try:
                if ip not in self.open_clients or self.open_clients[ip][0] is not None:
                    break
            except (KeyError, IndexError, TypeError):
                break
            time.sleep(0.01)

        if self.running and ip in self.open_clients:
            self.send_meeting_start_time(ip)
            self.send_username(ip, self.username)
            self.send_connected_clients(ip)

    def send_meeting_start_time(self, ip):
        """
        Send the meeting start timestamp to a guest for AV sync alignment.

        :param ip: Target guest's IP address.
        """
        msg = clientProtocol.build_meeting_start_time(self.meeting_start_time)
        self.host_server.send_msg(ip, msg)

    def send_username(self, ip, username):
        """
        Send the host's display name to a guest.

        :param ip: Target guest's IP address.
        :param username: The host's username string.
        """
        msg = clientProtocol.build_username_msg(username)
        self.host_server.send_msg(ip, msg)

    def send_connected_clients(self, target_ip):
        """
        Send the list of currently connected clients to a newly joined guest.

        :param target_ip: The new guest's IP address.
        """
        clients_dict = {}
        for ip, value in self.open_clients.items():
            if ip == target_ip or ip == self.ip:
                continue
            if isinstance(value, list) and len(value) >= 3:
                clients_dict[ip] = value[2]

        msg = clientProtocol.build_connected_clients(clients_dict)
        self.host_server.send_msg(target_ip, msg)

    def _close_comms(self):
        """
        Close the AudioServer and host TCP server after devices are cleaned up.
        """
        try:
            self.audio_comm.close()
        except Exception as e:
            print("audio close error:", e)

        try:
            if hasattr(self.host_server, "close"):
                self.host_server.close()
        except Exception as e:
            print("host server close error:", e)

    def on_meeting_closed_by_server(self, data=None):
        """
        Server already closed the meeting and notified guests; tear down local P2P only.
        Signaling connection to the main server stays open.
        """
        self.close(remote_end=True)

    def close(self, remote_end=False):
        """
        End the meeting: disconnect all guest P2P links. If remote_end is False, notify
        guests (fd) and the signaling server; the main server TCP session is never closed here.
        """
        if not self.running:
            return
        if not remote_end:
            try:
                kick_msg = clientProtocol.build_kick_msg()
                for ip in list(self.open_clients.keys()):
                    try:
                        self.host_server.send_msg(ip, kick_msg)
                    except Exception:
                        pass
                time.sleep(0.15)
            except Exception as e:
                print("kick broadcast error:", e)
            try:
                if self.meeting_code:
                    self.comm.send_msg(clientProtocol.build_leave_meeting(self.meeting_code))
            except Exception as e:
                print("leave server error:", e)
        super().close()

