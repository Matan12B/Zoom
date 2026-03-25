import threading
import queue
import time
from Server.DB import DB
from Server.ServerComm import ServerComm
from Server import serverProtocol
from random import choice
from string import ascii_uppercase
import random

class Server:
    def __init__(self, port=1231):
        self.port = port
        self.msgsQ = queue.Queue()
        self.comm = ServerComm(self.port, self.msgsQ)
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
            "dc": self.handle_disconnect
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
            print(f"Login successful: {username} from {ip}")
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
        meeting_id = self.generate_call_id()
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
        meeting_id = data
        if meeting_id in self.meetings:
            meeting_port = self.meetings[meeting_id][0]  # int
            shared_key = self.meetings[meeting_id][1]  # str
            self.meetings[meeting_id][2].append(ip)  # append to client IP list

            if ip in self.open_clients:
                self.open_clients[ip][1] = meeting_id

            # Get other clients
            other_clients = [client for client in self.meetings[meeting_id][2] if client != ip]

            print(f"Client {ip} joined meeting {meeting_id}")

            # Send success message to new client
            msg = serverProtocol.build_give_role("guest", meeting_port, shared_key, self.meetings[meeting_id][3])
            self.comm.send_msg(ip, msg)

            # Notify other clients
            for client_ip in other_clients:
                notify_msg = serverProtocol.build_client_joined(ip, meeting_port, shared_key)
                self.comm.send_msg(client_ip, notify_msg)
        else:
            print(f"Meeting {meeting_id} not found for client {ip}")
            msg = serverProtocol.build_error("Meeting not found")
            self.comm.send_msg(ip, msg)

    def close_meeting(self, ip, data):
        """
        Close a meeting (host only)
        :param ip: Client IP address
        :param data: meeting_id
        """
        meeting_id = data
        if meeting_id in self.meetings:
            # Notify all participants
            for client_ip in self.meetings[meeting_id][1]:
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

    def handle_disconnect(self, ip, data):
        """
        Handle client disconnection
        :param ip: Client IP address
        :param data: Additional data (optional)
        """
        if ip in self.open_clients:
            username = self.open_clients[ip][0]
            meeting_id = self.open_clients[ip][1]

            # Remove from meeting if in one
            if meeting_id and meeting_id in self.meetings:
                self.meetings[meeting_id][1].remove(ip)

                # Notify other participants
                for client_ip in self.meetings[meeting_id][1]:
                    msg = serverProtocol.build_participant_left(ip)
                    self.comm.send_msg(client_ip, msg)

                # If meeting is empty, close it
                if not self.meetings[meeting_id][1]:
                    del self.meetings[meeting_id]
                    print(f"Meeting {meeting_id} closed (empty)")

            # Remove client
            del self.open_clients[ip]
            print(f"Client disconnected: {username} ({ip})")

    def handle_msgs(self):
        """
        Handle incoming messages from clients (runs in loop)
        """
        while True:
            ip, msg = self.msgsQ.get()
            print(f"Received message from {ip}: {msg}")
            try:
                unpacked = serverProtocol.unpack(msg)
                if len(unpacked) < 2:
                    opcode = unpacked[0]
                    data = None
                else:
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
        Generate random 5 char string for meeting id
        :return: the meeting ID
        """
        return ''.join(choice(ascii_uppercase) for i in range(5))

    @staticmethod
    def generate_port():
        """

        """
        return random.randint(5000, 65535)

def main():
    """
    Create and start the server
    """
    server = Server(port=3018)
    server.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nServer shutting down...")


if __name__ == "__main__":
    main()
