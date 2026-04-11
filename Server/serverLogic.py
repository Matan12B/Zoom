import threading
import queue
import time
from Server.DB import DB
from Server.ServerComm import ServerComm
from Server import serverProtocol
from Common.settings import load_settings
from random import choice
from string import ascii_uppercase
import random

class Server:
    def __init__(self, port=1231, dh_p=797, dh_g=100):
        self.port = port
        self.dh_p = dh_p
        self.dh_g = dh_g
        self.msgsQ = queue.Queue()
        self.comm = ServerComm(self.port, self.msgsQ, self.dh_p, self.dh_g)
        self.db = DB()
        # [ip] = [username, call_id]
        self.open_clients = {}
        # [call_id] = [call_key, list_of_clients, host_ip]
        self.meetings = {}
        # Command handlers
        self.commands = {
            "li": self.log_in,
            "su": self.sign_up,
            "om": self.open_meeting,
            "jm": self.join_meeting,
            "cm": self.close_meeting,
            "hd": self.handle_disconnect,
            "lo": self.log_out,
        }

    def start(self):
        """
        Start the server and message handling thread
        """
        print(f"Server starting on port {self.port}...")
        time.sleep(0.2)
        threading.Thread(
            target=self.handle_msgs,
            daemon=True
        ).start()
        print(f"Server listening on port {self.port}")

    def log_in(self, ip, data):
        """
        Handle login request from client
        :param ip: Client IP address
        :param data: [username, password]
        """
        username, password = data
        if self.db.verify_user(username, password):
            status = "1"
            self.open_clients[ip] = [username, None]
            print(f"Login successful: \n"
                  f"username: {username} ip: {ip}")
        else:
            status = "0"
            print(f"Login failed for {username} from {ip}")

        msg = serverProtocol.build_login_status(status)
        self.comm.send_msg(ip, msg)

    def sign_up(self, ip, data):
        """
        Handle signup request from client
        :param ip: Client IP address
        :param data: [username, password]
        """
        username, password = data

        if self.db.add_user(username, password):
            status = "1"
            self.open_clients[ip] = [username, None]
            print(f"Signup successful: {username} from {ip}")
        else:
            status = "0"
            print(f"Signup failed for {username} from {ip}")

        msg = serverProtocol.build_register_status(status)
        self.comm.send_msg(ip, msg)

    def open_meeting(self, ip, data=None):
        """
        Create a new meeting for the client
        :param ip: Client IP address
        :param data: Additional meeting data (optional)
        """
        for _ in range(64):
            meeting_id = self.generate_call_id()
            if meeting_id not in self.meetings:
                break
        else:
            raise RuntimeError("Could not allocate a unique meeting code")
        shared_key = self.generate_shared_key()
        # Store meeting: [call_id] = [port, shared_key, [list of client IPs], host]
        meeting_port = self.generate_port()
        self.meetings[meeting_id] = [meeting_port, shared_key, [ip], ip]
        # Update client's meeting ID
        if ip in self.open_clients:
            self.open_clients[ip][1] = meeting_id
        print(f"Meeting created: {meeting_id} by {ip}")
        # Send meeting code and role back to client
        msg = serverProtocol.build_give_meeting_code(meeting_id)
        print("sending meeting code", meeting_id)
        self.comm.send_msg(ip, msg)
        msg = serverProtocol.build_give_role("host", meeting_port, shared_key)
        self.comm.send_msg(ip, msg)

    def join_meeting(self, ip, data):
        meeting_id = data[0]
        if meeting_id in self.meetings:
            meeting_port = self.meetings[meeting_id][0]
            shared_key = self.meetings[meeting_id][1]
            participants = self.meetings[meeting_id][2]
            username = data[1]
            participants.append(ip)

            existing_clients = {}
            for oc_ip in self.open_clients.keys():
                if self.open_clients[oc_ip][1] == meeting_id:
                    existing_clients[oc_ip] = self.open_clients[oc_ip][0]
            print(f"Client {ip} joined meeting {meeting_id}")

            if ip in self.open_clients:
                self.open_clients[ip][1] = meeting_id

            give_role = serverProtocol.build_give_role("guest", meeting_port, shared_key, self.meetings[meeting_id][3])
            self.comm.send_msg(ip, give_role)
            print("sending role")

            give_existing_clients = serverProtocol.build_clients_connected(existing_clients)
            self.comm.send_msg(ip, give_existing_clients)

            for other_ip in existing_clients:
                if other_ip == ip:
                    continue
                notify_existing = serverProtocol.build_client_joined(ip, meeting_port, shared_key, username)
                self.comm.send_msg(other_ip, notify_existing)
        else:
            print(f"Meeting {meeting_id} not found for client {ip}")
            msg = serverProtocol.build_error("Meeting not found")
            self.comm.send_msg(ip, msg)

    def close_meeting(self, ip, meeting_id):
        """
        Close a meeting (host only)
        :param ip: Client IP address
        :param data: meeting_id
        """
        if meeting_id in self.meetings.keys():
            # Notify all participants
            for client_ip in self.meetings[meeting_id][2]:
                msg = serverProtocol.build_meeting_closed()
                self.comm.send_msg(client_ip, msg)
                # Clear client's meeting ID
                if client_ip in self.open_clients:
                    self.open_clients[client_ip][1] = None
            # Remove meeting
            del self.meetings[meeting_id]
            print(f"Meeting {meeting_id} closed by {ip}")
        else:
            print(f"Meeting {meeting_id} not found")

    def _remove_client_from_meeting(self, ip, meeting_id, notify_others=True):
        """
        Remove ip from a meeting roster. Does not remove signaling login.
        """
        if not meeting_id or meeting_id not in self.meetings:
            return
        try:
            self.meetings[meeting_id][2].remove(ip)
        except ValueError:
            pass
        if notify_others:
            for client_ip in self.meetings[meeting_id][2]:
                msg = serverProtocol.build_participant_left(ip)
                self.comm.send_msg(client_ip, msg)
        if not self.meetings[meeting_id][2]:
            del self.meetings[meeting_id]
            print(f"Meeting {meeting_id} closed (empty)")

    def handle_disconnect(self, ip, data):
        """
        Leave a meeting while staying logged in to the signaling server (hd).
        Host ending their meeting uses the first branch (meeting id + host ip).
        """
        meeting_id = data

        if meeting_id in self.meetings.keys() and self.meetings[meeting_id][3] == ip:
            self.close_meeting(ip, meeting_id)
        elif ip in self.open_clients:
            username = self.open_clients[ip][0]
            current = self.open_clients[ip][1]

            if current and current in self.meetings:
                self._remove_client_from_meeting(ip, current, notify_others=True)

            self.open_clients[ip][1] = None
            print(f"Client left meeting (signaling still connected): {username} ({ip})")
        else:
            print("ip or meeting code are incorrect")

    def log_out(self, ip, data=None):
        """
        End signaling session: leave any meeting, then drop login state for this IP.
        """
        if ip not in self.open_clients:
            return
        username = self.open_clients[ip][0]
        meeting_id = self.open_clients[ip][1]

        if meeting_id and meeting_id in self.meetings:
            if self.meetings[meeting_id][3] == ip:
                self.close_meeting(ip, meeting_id)
            else:
                self._remove_client_from_meeting(ip, meeting_id, notify_others=True)

        del self.open_clients[ip]
        print(f"Logged out from signaling server: {username} ({ip})")

    def handle_msgs(self):
        """
        Handle incoming messages from clients (runs in loop)
        """
        while True:
            ip, msg = self.msgsQ.get()
            try:
                opcode, data = serverProtocol.unpack(msg)
                if opcode in self.commands:
                    self.commands[opcode](ip, data)
                else:
                    print(f"Unknown opcode received from {ip}: {opcode}")
            except Exception as e:
                print(f"Error handling message from {ip}: {e}")

    @staticmethod
    def generate_shared_key():
        """
        Generate random 5 char string for meeting encryption key
        :return: the key
        """
        return ''.join(choice(ascii_uppercase) for i in range(5))


    @staticmethod
    def generate_call_id():
        """
        Generate random uppercase string for meeting id (reduces collision rate).
        :return: the meeting ID
        """
        return ''.join(choice(ascii_uppercase) for i in range(5))

    @staticmethod
    def generate_port():
        """
        create a random port between 5000 and 65535
        :return: the port
        """
        return random.randint(5000, 65535)

def main():
    """
    Create and start the server
    """
    server_ip, server_port, video_port, audio_port, dh_p, dh_g = load_settings()
    server = Server(port=server_port, dh_p=dh_p, dh_g=dh_g)
    server.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nServer shutting down...")


if __name__ == "__main__":
    main()
