import math
import struct
import time
import cv2
import numpy as np

MAX_CHUNK_SIZE = 1000

# frame_id      -> 4 bytes unsigned int
# timestamp     -> 8 bytes double
# total_parts   -> 1 byte
# part_index    -> 1 byte
# payload_size  -> 2 bytes unsigned short
HEADER_FORMAT = "!IdBBH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def split_frame_to_packets(frame_id, timestamp, frame_bytes, chunk_size=MAX_CHUNK_SIZE):
    """
    Split encoded frame bytes into many small UDP packets.
    :param frame_id:
    :param timestamp:
    :param frame_bytes:
    :param chunk_size:
    :return:
    """
    if not frame_bytes:
        return []

    total_parts = math.ceil(len(frame_bytes) / chunk_size)

    if total_parts > 255:
        raise ValueError("frame is too large for current packet format")

    packets = []

    for part_index in range(total_parts):
        start = part_index * chunk_size
        end = start + chunk_size
        chunk = frame_bytes[start:end]

        header = struct.pack(
            HEADER_FORMAT,
            frame_id,
            float(timestamp),
            total_parts,
            part_index,
            len(chunk)
        )

        packets.append(header + chunk)

    return packets


class FrameReassembler:
    def __init__(self):
        self.frame_store = {}

    def handle_packet(self, packet):
        """
        Return:
        (frame, timestamp) or (None, None)
        """
        if len(packet) < HEADER_SIZE:
            return None, None

        try:
            header = packet[:HEADER_SIZE]
            payload = packet[HEADER_SIZE:]

            frame_id, timestamp, total_parts, part_index, payload_size = struct.unpack(
                HEADER_FORMAT,
                header
            )

            if payload_size != len(payload):
                return None, None

            if frame_id not in self.frame_store:
                self.frame_store[frame_id] = {
                    "timestamp": timestamp,
                    "total_parts": total_parts,
                    "parts": {},
                    "last_update": time.time()
                }

            frame_data = self.frame_store[frame_id]

            if frame_data["total_parts"] != total_parts:
                del self.frame_store[frame_id]
                return None, None

            frame_data["parts"][part_index] = payload
            frame_data["last_update"] = time.time()

            if len(frame_data["parts"]) == total_parts:
                return self.rebuild_frame(frame_id)

        except Exception as e:
            print("handle_packet error:", e)

        return None, None

    def rebuild_frame(self, frame_id):
        """
        Rebuild complete frame.
        :param frame_id:
        :return:
        """
        if frame_id not in self.frame_store:
            return None, None

        try:
            frame_data = self.frame_store[frame_id]
            parts = frame_data["parts"]
            timestamp = frame_data["timestamp"]
            total_parts = frame_data["total_parts"]

            full_bytes = b""
            for i in range(total_parts):
                if i not in parts:
                    return None, None
                full_bytes += parts[i]

            np_arr = np.frombuffer(full_bytes, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            del self.frame_store[frame_id]

            return frame, timestamp

        except Exception as e:
            print("rebuild_frame error:", e)
            if frame_id in self.frame_store:
                del self.frame_store[frame_id]
            return None, None

    def cleanup_old_frames(self, max_age=0.5):
        """
        Remove incomplete old frames.
        :param max_age:
        :return:
        """
        now = time.time()
        old_ids = []

        for frame_id, data in self.frame_store.items():
            if now - data["last_update"] > max_age:
                old_ids.append(frame_id)

        for frame_id in old_ids:
            del self.frame_store[frame_id]