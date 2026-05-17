import math
import struct
import time
import cv2
import numpy as np


class FrameReassembler:
    MAX_CHUNK_SIZE = 1000

    # frame_id      -> 4 bytes unsigned int
    # timestamp     -> 8 bytes double
    # total_parts   -> 2 bytes unsigned short
    # part_index    -> 2 bytes unsigned short
    # stream_type   -> 1 byte: 0 camera, 1 screen share
    # payload_size  -> 2 bytes unsigned short
    HEADER_FORMAT = "!IdHHBH"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    STREAM_CAMERA = 0
    STREAM_SCREEN = 1
    STREAM_NAMES = {
        STREAM_CAMERA: "camera",
        STREAM_SCREEN: "screen",
    }
    STREAM_VALUES = {
        "camera": STREAM_CAMERA,
        "screen": STREAM_SCREEN,
    }

    @staticmethod
    def split_frame_to_packets(frame_id, timestamp, frame_bytes, chunk_size=None, stream_type="camera"):
        """
        Split encoded frame bytes into many small UDP packets.
        :param frame_id:
        :param timestamp:
        :param frame_bytes:
        :param chunk_size:
        :return:
        """
        if chunk_size is None:
            chunk_size = FrameReassembler.MAX_CHUNK_SIZE
        packets = []
        if frame_bytes:
            stream_value = FrameReassembler.STREAM_VALUES.get(stream_type, FrameReassembler.STREAM_CAMERA)
            total_parts = math.ceil(len(frame_bytes) / chunk_size)
            if total_parts > 65535:
                raise ValueError("frame is too large for current packet format")
            for part_index in range(total_parts):
                start = part_index * chunk_size
                end = start + chunk_size
                chunk = frame_bytes[start:end]
                header = struct.pack(
                    FrameReassembler.HEADER_FORMAT,
                    frame_id,
                    float(timestamp),
                    total_parts,
                    part_index,
                    stream_value,
                    len(chunk)
                )
                packets.append(header + chunk)
        return packets

    def __init__(self):
        self.frame_store = {}

    def handle_packet(self, packet):
        """
        Return:
        (frame, timestamp, stream_type) or (None, None, "camera")
        """
        result_frame = None
        result_timestamp = None
        result_stream_type = "camera"
        if len(packet) >= self.HEADER_SIZE:
            try:
                header = packet[:self.HEADER_SIZE]
                payload = packet[self.HEADER_SIZE:]
                frame_id, timestamp, total_parts, part_index, stream_value, payload_size = struct.unpack(
                    self.HEADER_FORMAT,
                    header
                )
                result_stream_type = self.STREAM_NAMES.get(stream_value, "camera")
                if payload_size == len(payload):
                    if frame_id not in self.frame_store:
                        self.frame_store[frame_id] = {
                            "timestamp": timestamp,
                            "stream_type": result_stream_type,
                            "total_parts": total_parts,
                            "parts": {},
                            "last_update": time.time()
                        }
                    frame_data = self.frame_store[frame_id]
                    if frame_data["total_parts"] != total_parts:
                        del self.frame_store[frame_id]
                    else:
                        frame_data["parts"][part_index] = payload
                        frame_data["last_update"] = time.time()
                        if len(frame_data["parts"]) == total_parts:
                            result_frame, result_timestamp, result_stream_type = self.rebuild_frame(frame_id)
            except Exception as e:
                print("handle_packet error:", e)
        return result_frame, result_timestamp, result_stream_type

    def rebuild_frame(self, frame_id):
        """
        Rebuild complete frame.
        :param frame_id:
        :return:
        """
        result_frame = None
        result_timestamp = None
        result_stream_type = "camera"
        if frame_id in self.frame_store:
            try:
                frame_data = self.frame_store[frame_id]
                parts = frame_data["parts"]
                timestamp = frame_data["timestamp"]
                result_stream_type = frame_data.get("stream_type", "camera")
                total_parts = frame_data["total_parts"]
                full_bytes = b""
                missing = False
                for i in range(total_parts):
                    if i not in parts:
                        missing = True
                        break
                    full_bytes += parts[i]
                if not missing:
                    np_arr = np.frombuffer(full_bytes, dtype=np.uint8)
                    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    result_frame = frame
                    result_timestamp = timestamp
                del self.frame_store[frame_id]
            except Exception as e:
                print("rebuild_frame error:", e)
                if frame_id in self.frame_store:
                    del self.frame_store[frame_id]
        return result_frame, result_timestamp, result_stream_type

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
