import queue
import threading
import time
from Client.Comms.ClientComm import ClientComm
from Client.Protocol import clientProtocol
from Client.Logic.Host import Host
from Client.Logic.callLogic import CallLogic


class Client:
    def __init__(self, ip="127.0.0.1", port=1231):
        self.server_ip = ip
        self.port = port
        self.msgsQ = queue.Queue()
        self.comm = ClientComm(self.server_ip, self.port, self.msgsQ)
        self.role = None
        self.username = ""
        self.password = ""
        self.meeting_code = None
        self.active = None
        self.handle_msgs_running = False
        self.commands = {
            "gmc": self.get_meeting_code,
            "ir": self.initialize_role,
            "ls": self.get_login_status,
            "rs": self.get_signup_status
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
                self.username
            )
        elif role == "guest" and len(data) == 4:
            host_ip = data[3]
            self.role = CallLogic(
                port,
                meeting_key,
                self.comm,
                host_ip,
                self.meeting_code,
                self.username
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
        msg = clientProtocol.build_login(username, password)
        self.comm.send_msg(msg)

    def sign_up(self, username, password):
        """
        send signup request
        """
        self.username = username
        self.password = password
        self.active = None
        msg = clientProtocol.build_register(username, password)
        self.comm.send_msg(msg)

    def get_error(self, data):
        """
        print error from server
        """
        print("error from server - ", data)

def main():
    ip = input("Enter ip")
    port = int(input("Enter port"))
    client = Client(ip, port)
    client.start()
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()