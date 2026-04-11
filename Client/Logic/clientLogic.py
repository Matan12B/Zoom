import queue
import threading
import time
from Client.Comms.ClientComm import ClientComm
from Client.Protocol import clientProtocol
from Client.Logic.Host import Host
from Client.Logic.callLogic import CallLogic


class Client:
    def __init__(self, ip="127.0.0.1", port=1231, video_port=5000, audio_port=3000, dh_p=797, dh_g=100):
        self.server_ip = ip
        self.port = port
        self.video_port = video_port
        self.audio_port = audio_port
        self._dh_p = dh_p
        self._dh_g = dh_g
        self.msgsQ = queue.Queue()
        self.comm = ClientComm(self.server_ip, self.port, self.msgsQ, dh_p=dh_p, dh_g=dh_g)
        self.role = None
        self.username = ""
        self.password = ""
        self.meeting_code = None
        self.active = None
        self.last_error = None
        self.handle_msgs_running = False
        self.commands = {
            "gmc": self.get_meeting_code,
            "ir": self.initialize_role,
            "ls": self.get_login_status,
            "rs": self.get_signup_status,
            "ge": self.get_error,
        }

    def start(self):
        """
        Start the client and message thread
        """
        if not self.handle_msgs_running:
            self.handle_msgs_running = True
            time.sleep(0.2)
            threading.Thread(
                target=self.handle_msgs,
                daemon=True
            ).start()

    def start_meeting(self):
        """
        Send a request to create a meeting
        """
        self.last_error = None
        msg = clientProtocol.build_open_meeting_msg()
        self.comm.send_msg(msg)

    def get_meeting_code(self, meeting_code):
        """
        Receive meeting code from the server for host
        """
        self.meeting_code = meeting_code

    def request_join_meeting(self, meeting_code):
        """
        Send request to join meeting
        """
        self.last_error = None
        self.meeting_code = meeting_code
        msg = clientProtocol.build_enter_meeting(meeting_code, self.username)
        self.comm.send_msg(msg)

    def initialize_role(self, data):
        """
        Initialize the meeting role
        """
        role = data[0]
        port = int(data[1])
        meeting_key = data[2]

        if role == "host":
            self.role = Host(
                port,
                meeting_key,
                self.comm,
                self.meeting_code,
                self.username,
                video_port=self.video_port,
                audio_port=self.audio_port
            )
        elif role == "guest" and len(data) == 4:
            host_ip = data[3]
            self.role = CallLogic(
                port,
                meeting_key,
                self.comm,
                host_ip,
                self.meeting_code,
                self.username,
                video_port=self.video_port,
                audio_port=self.audio_port
            )
        else:
            print("Invalid role")

    def handle_msgs(self):
        """
        Handle incoming messages from server
        """
        while True:
            msg = self.msgsQ.get()
            print(msg)
            opcode, data = clientProtocol.unpack(msg)
            if self.role:
                # Server sends participant_left as hd^#^<ip> → data is a string; handlers expect [ip].
                if opcode == "hd" and isinstance(data, str):
                    data = [data]
                self.role.handle_msgs_from_client_logic(opcode, data)
                continue
            if opcode in self.commands:
                self.commands[opcode](data)

    def get_login_status(self, status):
        """
        save login status
        """
        print("log in status", status)
        self.active = status

    def get_signup_status(self, status):
        """
        save signup status
        """
        print("signup status", status)

        self.active = status

    def log_in(self, username, password):
        """
        send login request
        """
        self.username = username
        self.password = password
        self.active = None
        self.last_error = None
        msg = clientProtocol.build_login(username, password)
        self.comm.send_msg(msg)

    def sign_up(self, username, password):
        """
        send signup request
        """
        self.username = username
        self.password = password
        self.active = None
        self.last_error = None
        msg = clientProtocol.build_register(username, password)
        self.comm.send_msg(msg)

    def get_error(self, data):
        """
        Store a human-readable server error (e.g. meeting not found) for the GUI.
        """
        if isinstance(data, str):
            self.last_error = data
        elif isinstance(data, list) and data:
            self.last_error = str(data[0])
        else:
            self.last_error = str(data)
        print("error from server - ", self.last_error)

    def wait_signaling(self, timeout=15.0):
        """Block until the TCP + key exchange to the signaling server completes (or timeout)."""
        return self.comm.connected.wait(timeout=timeout)

    def disconnect_from_server(self):
        """
        Close the signaling TCP session and open a new one (user must log in again).
        Does not close meeting P2P — call that first if still in a call.
        """
        self.role = None
        self.meeting_code = None
        self.active = None
        try:
            if getattr(self.comm, "running", False) and self.comm.cipher:
                self.comm.send_msg(clientProtocol.build_logout())
        except Exception as e:
            print("logout notify error:", e)
        try:
            self.comm.close_client()
        except Exception as e:
            print("close signaling error:", e)
        self.msgsQ = queue.Queue()
        self.comm = ClientComm(
            self.server_ip, self.port, self.msgsQ, dh_p=self._dh_p, dh_g=self._dh_g
        )

def main():
    ip = input("Enter ip")
    port = int(input("Enter port"))
    client = Client(ip, port)
    client.start()
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()