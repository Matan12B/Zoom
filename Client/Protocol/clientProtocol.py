import struct
import json

def unpack(msg):
    """
    Return opcode and params from the msg
    """
    split = msg.split("^#^")
    opcode = split[0]
    data = split[1:]
    if opcode == "cc" and data:
        return opcode, json.loads(data[0])
    if len(data) == 1:
        return opcode, data[0]
    return opcode, data

def build_username_msg(username):
    """
    build host username msg
    """
    return f"gh^#^{username}"

def build_connected_clients(clients_dict):
    """
    build connected clients dict msg
    """
    return f"cc^#^{json.dumps(clients_dict)}"

def unpack_file(msg):
    """
    unpack files
    """
    header_len = struct.unpack(">I", msg[:4])[0]
    # Extract header and video
    header_bytes = msg[4:4 + header_len]
    file_data = msg[4 + header_len:]
    # "hv^#^12345678"
    header_str = header_bytes.decode()
    # video_data, opcode , timestamp or sender_ip
    return file_data, header_str.split("^#^")

def build_login(username,password):
    """
    Return a login msg build in the protocol structure
    """
    return f"li^#^{username}^#^{password}"

def build_register(username,password):
    """
    Return a register msg build in the protocol structure
    """
    return f"su^#^{username}^#^{password}"

def build_enter_meeting(meeting_code, username):
    """
    Return a join-meeting message: meeting code first, then username (server expects this order).
    """
    return f"jm^#^{meeting_code}^#^{username}"

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

    return f"fd^#^"

def build_video_msg(timestamp, frame):
    """
    Return an video  msg build in the protocol structure
    :return: f"hv^#^{timestamp}^#^{video_data}"
    """
    header = f"hv^#^{timestamp}".encode()
    header_len_bytes = struct.pack(">I", len(header))
    video_bytes = frame
    return header_len_bytes + header + video_bytes

def build_audio_msg(timestamp, audio_data, sender_ip):
    """
    Return an audio msg build in the protocol structure
    """
    header = f"ha^#^{timestamp}^#^{sender_ip}".encode()
    header_len_bytes = struct.pack(">I", len(header))
    audio_bytes = audio_data
    return header_len_bytes + header + audio_bytes

def build_toggle_mic():
    """
    Return a register msg build in the protocol structure
    """

def build_toggle_camera():
    """
    Return a register msg build in the protocol structure
    """

def build_leave_meeting(meeting_code):
    """
    Return a register msg build in the protocol structure
    """
    return f"hd^#^{meeting_code}"


def build_logout():
    """Tell the signaling server to end this login session (TCP may close next)."""
    return "lo^#^"

def build_open_meeting_msg():
    """
    Return a open meeting msg built in the protocol structure
    """
    return "om^#^"


def build_meeting_start_time(meeting_start):
    """
    build meeting start time to send to guests
    """
    return f"gmst^#^{meeting_start}"





