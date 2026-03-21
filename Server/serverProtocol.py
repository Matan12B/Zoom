
def unpack(msg):
    """
    Return list of parameters from the msg
    """
    split = msg.split("^#^")
    return split

def build_login_status(status):
    """
    Return a message of the status of the login in the protocol structure
    """
    return status

def build_register_status(status):
    """
    Return a message of the status of the register in the protocol structure
    """
    return status

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

def build_give_role(role):
    """
    give the client a role
    """
    return f"ir^#^{role}"

def build_give_meeting_code(meeting_code):
    """

    """
    return f"gmc^#^{meeting_code}"

def build_start_meeting():
    """

    """
    return f"sm^#^"

def build_client_joined(ip, port, shared_key):
    """

    """
    return f"hj^#^{ip, port, shared_key}"



