import struct
import json

def unpack(msg):
    """
    Return opcode and list of parameters from the msg
    """
    split = msg.split("^#^")
    opcode = split[0]
    data = split[1:]
    if len(data) == 1:
        data = data[0]
    print(split)
    if opcode == "cc" and data:
        return opcode, json.loads(data)
    return opcode, data

def unpack_file(msg):
    """
    unpack files
    """
    header_len = struct.unpack(">I", msg[:4])[0]
    # Extract header and video
    header_bytes = msg[4:4 + header_len]
    file_data = msg[4 + header_len:]
    header_str = header_bytes.decode()  # "hv^#^12345678"
    return file_data, header_str.split("^#^") # video_data, opcode , timestamp or sender_ip

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

def build_enter_meeting(username ,meeting_code):
    """
    Return a request to enter meeting msg build in the protocol structure
    """
    return f"jm^#^{username}^#^{meeting_code}"

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
    """
    # return f"hv^#^{timestamp}^#^{video_data}"
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

def build_open_meeting_msg():
    """
    Return a open meeting msg built in the protocol structure
    """
    return "om"

def build_username_msg(username):
    """
    Return a username msg built in the protocol structure
    """
    return f"gh^#^{username}"

def build_meeting_start_time(meeting_start):
    """
    build meeting start time to send to guests
    """
    return f"gmst^#^{meeting_start}"

