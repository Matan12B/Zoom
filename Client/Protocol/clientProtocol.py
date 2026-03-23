def unpack(msg):
    """
    Return list of parameters from the msg
    """
    split = msg.split("^#^")
    if len(split) > 2:
        return [split[0], split[1:]]
    return split

def build_msg(msg):
    """
    Return a msg build in the protocol structure
    """

def build_login(username,password):
    """
    Return a login msg build in the protocol structure
    """

def build_register(username,password):
    """
    Return a register msg build in the protocol structure
    """

def build_enter_meeting(meeting_code):
    """
    Return a request to enter meeting msg build in the protocol structure
    """
    return f"jm^#^{meeting_code}"

def build_force_close_camera():
    """
    Return a force close msg build in the protocol structure
    """

def build_mute_msg():
    """
    Return a mute msg build in the protocol structure
    """

def build_kick_msg():
    """
    Return a kick msg build in the protocol structure
    """

def build_video_msg(timestamp, video_data):
    """
    Return an video  msg build in the protocol structure
    """
    return f"hv^{timestamp}^{video_data}"

def build_audio_msg(timestamp, audio_data):
    """
    Return an audio msg build in the protocol structure
    """
    return f"ha^{timestamp}^{audio_data}"

def build_toggle_mic():
    """
    Return a register msg build in the protocol structure
    """

def build_toggle_camera():
    """
    Return a register msg build in the protocol structure
    """

def build_leave_meeting():
    """
    Return a register msg build in the protocol structure
    """

def build_open_meeting_msg():
    """
    Return a register msg build in the protocol structure
    """
    return "om"
def build_username_msg(username):
    """
    Return a register msg build in the protocol structure
    """
