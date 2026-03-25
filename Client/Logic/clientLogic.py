import queue
import threading
import time
from Client.Comms.ClientComm import ClientComm
from Client.Protocol import clientProtocol
from Client.Logic.Host import Host
from Client.Logic.callLogic import CallLogic
from Server.ServerComm import ServerComm


class Client:
    def __init__(self, ip="127.0.0.1", port=1231):
        self.ip = ip
        self.port = port
        self.msgsQ = queue.Queue()
        self.comm = ClientComm(self.ip, self.port, self.msgsQ)
        # using this server comm for now
        self.role = None
        self.username = ""
        # keep password temp
        self.password = ""
        self.meeting_code = None
        self.active = None
        self.commands = {
            "sm" : self.start_meeting,
            "rjm": self.request_join_meeting,
            "gmc": self.get_meeting_code,
            "ir": self.initialize_role,
            "ls": self.get_login_status,
            "ss": self.get_signup_status,
            "cj": self.client_joined
        }

    def start(self):
        """
        Start the client and message thread
        """
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
        Receive meeting code from the server
        """
        self.meeting_code = meeting_code
        print("Meeting code:", self.meeting_code)

    def request_join_meeting(self, meeting_code):
        """
        Send request to join meeting
        """
        msg = clientProtocol.build_enter_meeting(meeting_code)
        self.comm.send_msg(msg)

    def initialize_role(self, data):
        """
        Initializes the role of the object based on the provided data.

        This method determines the role of the object (either 'host' or 'guest')
        and initializes it accordingly. If the role is invalid, it outputs an
        appropriate message. The GUI will call start() on the role when ready.

        Parameters:
        data: list
            A list containing initialization information:
            - data[0]: str - Specifies the role ('host' or 'guest').
            - data[1]: Any - Contains open client information.
            - data[2]: int - meeting_key

        Raises:
        ValueError
            If the role specified in data[0] is invalid or unsupported.
        """
        role = data[0]
        port = int(data[1])
        meeting_key = data[2]
        host_ip = data[3]
        print("giving role", data[0])

        if role == "host":
            self.role = Host(port, meeting_key, self.comm)
        elif role == "guest":
            self.role = CallLogic(port, meeting_key, self.comm, host_ip)
        else:
            print("Invalid role")

    def handle_msgs(self):
        """
        Handle incoming messages from server
        """
        while True:
            msg = self.msgsQ.get()
            print(f"Received message: {msg}")
            opcode, data = clientProtocol.unpack(msg)
            if opcode in self.commands:
                self.commands[opcode](data)

    def get_login_status(self, status):
        """

        """
        self.active = status

    def get_signup_status(self, status):
        """

        """
        self.active = status

    def log_in(self, username, password):
        """

        """
        msg = clientProtocol.build_login(username, password)
        self.comm.send_msg(msg)

    def sign_up(self, username, password):
        """

        """
        msg = clientProtocol.build_register(username, password)
        self.comm.send_msg(msg)

    def client_joined(self, data):
        """
        Handle when a new client joins the call
        """
        # TODO: implement client joined logic
        pass

def main():
    ip = input("Enter ip")
    port = int(input("Enter port"))
    client = Client(ip, port)

    client.start()

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()