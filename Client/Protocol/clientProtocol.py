import struct
import json
import time
import base64

def unpack(msg):
    """
    Return opcode and params from the msg
    """
    split = msg.split("^#^")
    opcode = split[0]
    data = split[1:]
    if opcode == "cc" and data:
        result = json.loads(data[0])
    elif opcode == "tc" and data:
        payload = base64.b64decode(data[0].encode()).decode()
        result = json.loads(payload)
    elif len(data) == 1:
        result = data[0]
    else:
        result = data
    return opcode, result

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


def build_client_identity(client_id):
    """
    Identify this guest to the host-side meeting TCP server.
    """
    return f"ci^#^{client_id}"

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

def build_mute_state(ip, is_muted):
    """
    Broadcast local mute state to peers.
    is_muted=True  → "1"  (participant is muted)
    is_muted=False → "0"  (participant can be heard)
    """
    return f"ms^#^{ip}^#^{1 if is_muted else 0}"

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

def build_camera_state(ip, is_on):
    """
    Signal that a participant turned their camera on or off.
    is_on=True → "1"  (camera is now on)
    is_on=False → "0" (camera is now off)
    """
    return f"cs^#^{ip}^#^{1 if is_on else 0}"


def build_screen_share_state(ip, is_on):
    """
    Signal that a participant started or stopped sharing their screen.
    is_on=True -> "1", is_on=False -> "0"
    """
    return f"ss^#^{ip}^#^{1 if is_on else 0}"

def build_toggle_mic(ip, muted):
    """
    Broadcast mic mute state.
    muted: bool — True = muted, False = unmuted
    """
    return f"tm^#^{ip}^#^{1 if muted else 0}"


def build_chat_message(sender_ip, username, text, timestamp=None):
    """
    Build a text-chat message for the meeting control channel.
    The payload is JSON so chat text can safely contain protocol separators.
    """
    payload = {
        "sender_ip": sender_ip or "",
        "username": username or "",
        "text": text or "",
        "timestamp": time.time() if timestamp is None else timestamp,
    }
    payload_json = json.dumps(payload)
    payload_b64 = base64.b64encode(payload_json.encode()).decode()
    return f"tc^#^{payload_b64}"

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
