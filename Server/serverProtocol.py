
def unpack(msg):
    """
    Return opcode and list of parameters from the msg
    """
    split = msg.split("^#^")
    opcode = split[0]
    data = split[1:]
    return opcode, data

def build_login_status(status):
    """
    Return a message of the status of the login in the protocol structure
    """
    return f"ls^#^{status}"

def build_register_status(status):
    """
    Return a message of the status of the register in the protocol structure
    """
    return f"rs^#^{status}"

def build_video_msg(video_data):
    """
    Return an video  msg build in the protocol structure
    """
    return f"hv^#^{video_data}"

def build_audio_msg(audio_data):
    """
    Return an audio msg build in the protocol structure
    """
    return f"ha^#^{audio_data}"

def build_give_role(role, meeting_port, shared_key, host_ip=""):
    """
    give the client a role
    """
    return f"ir^#^{role}^#^{meeting_port}^#^{shared_key}^#^{host_ip}"

def build_give_meeting_code(meeting_code):
    """

    """
    return f"gmc^#^{meeting_code}"

def build_start_meeting():
    """

    """
    return f"sm^#^"

def build_client_joined(ip, port, shared_key, username):
    """
    build msg with data about client
    """
    return f"hj^#^{ip}^#^{port}^#^{shared_key}^#^{username}"

def build_meeting_closed():
    """

    :param meeting_code:
    :return:
    """
    return f"fd^#^"

def build_error(error):
    """
    return error msg
    """
    return f"ge^#^{error}"

def build_clients_connected(existing_clients):
    """
    build a message to send to a new client with all the currently connected clients to a meeting
    """
    return f"cc^#^{existing_clients}"



