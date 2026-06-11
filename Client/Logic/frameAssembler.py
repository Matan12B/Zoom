import math
import struct
import time
import cv2
import numpy as np


class FrameReassembler:
    """
    Split encoded video frames into UDP-sized packets and rebuild them on receipt.

    A JPEG frame is usually too large to send as one small UDP datagram. The sender
    divides it into chunks and adds a binary header to every chunk. The receiver
    groups packets by frame_id and stores them by part_index, so packets may arrive
    out of order. A frame is decoded only after every expected part has arrived.

    UDP does not guarantee delivery or ordering. If any part is lost, this class
    keeps the incomplete frame temporarily and cleanup_old_frames() later discards
    it. There is no retransmission because displaying the next current video frame
    is preferable to delaying the call while waiting for an old frame.
    """

    # Keep each plaintext payload small to reduce IP fragmentation risk. Encryption
    # and the custom header add a small amount of data to each UDP datagram.
    MAX_CHUNK_SIZE = 1000

    # Header fields shared by every packet belonging to a frame:
    # frame_id      -> 4 bytes unsigned int
    # timestamp     -> 8 bytes double
    # total_parts   -> 1 byte
    # part_index    -> 1 byte
    # payload_size  -> 2 bytes unsigned short
    #
    # "!" selects network byte order (big-endian), so sender and receiver interpret
    # the binary values consistently even if they run on different computer types.
    HEADER_FORMAT = "!IdBBH"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    @staticmethod
    def split_frame_to_packets(frame_id, timestamp, frame_bytes, chunk_size=None):
        """
        Split one encoded JPEG frame into independently sendable UDP payloads.

        Each returned packet is: binary header + one consecutive frame chunk.

        :param frame_id: Unsigned identifier shared by all parts of this frame.
        :param timestamp: Capture time used later for audio/video synchronization.
        :param frame_bytes: Complete JPEG-encoded frame as bytes.
        :param chunk_size: Maximum frame bytes per packet; defaults to 1000.
        :return: List of packet bytes in part-index order.
        :raises ValueError: If more than 255 parts are required, because total_parts
                            and part_index each occupy one byte in the header.
        """
        if chunk_size is None:
            chunk_size = FrameReassembler.MAX_CHUNK_SIZE
        packets = []
        if frame_bytes:
            # Ceiling division includes a final packet even when it is only partly full.
            total_parts = math.ceil(len(frame_bytes) / chunk_size)
            if total_parts > 255:
                raise ValueError("frame is too large for current packet format")
            for part_index in range(total_parts):
                # Extract this packet's consecutive section of the encoded JPEG.
                start = part_index * chunk_size
                end = start + chunk_size
                chunk = frame_bytes[start:end]
                # Every packet repeats the frame metadata so it can be identified
                # independently, regardless of UDP arrival order.
                header = struct.pack(
                    FrameReassembler.HEADER_FORMAT,
                    frame_id,
                    float(timestamp),
                    total_parts,
                    part_index,
                    len(chunk)
                )
                packets.append(header + chunk)
        return packets

    def __init__(self):
        # frame_id -> metadata and the parts received so far. A dictionary keyed by
        # part_index naturally handles out-of-order packets and duplicate packets.
        self.frame_store = {}

    def handle_packet(self, packet):
        """
        Process one decrypted UDP packet and possibly complete a video frame.

        :param packet: Decrypted packet containing the custom header and frame chunk.
        :return: ``(decoded_frame, timestamp)`` when the final missing part arrives;
                 otherwise ``(None, None)``.
        """
        result_frame = None
        result_timestamp = None
        # A packet shorter than the header cannot contain valid frame metadata.
        if len(packet) >= self.HEADER_SIZE:
            try:
                header = packet[:self.HEADER_SIZE]
                payload = packet[self.HEADER_SIZE:]
                frame_id, timestamp, total_parts, part_index, payload_size = struct.unpack(
                    self.HEADER_FORMAT,
                    header
                )
                # Reject truncated or malformed packets whose declared payload length
                # does not match the bytes actually received.
                if payload_size == len(payload):
                    if frame_id not in self.frame_store:
                        # Create temporary storage when the first part of a frame arrives.
                        # The first received part does not have to be part zero.
                        self.frame_store[frame_id] = {
                            "timestamp": timestamp,
                            "total_parts": total_parts,
                            "parts": {},
                            "last_update": time.time()
                        }
                    frame_data = self.frame_store[frame_id]
                    # Parts claiming the same frame ID must agree on the part count.
                    if frame_data["total_parts"] != total_parts:
                        del self.frame_store[frame_id]
                    else:
                        # Store by index so UDP packets can arrive in any order.
                        # Receiving the same index again simply replaces the duplicate.
                        frame_data["parts"][part_index] = payload
                        frame_data["last_update"] = time.time()
                        if len(frame_data["parts"]) == total_parts:
                            # All expected parts appear to be present; join and decode them.
                            result_frame, result_timestamp = self.rebuild_frame(frame_id)
            except Exception as e:
                print("handle_packet error:", e)
        return result_frame, result_timestamp

    def rebuild_frame(self, frame_id):
        """
        Join all stored chunks in index order and decode the JPEG with OpenCV.

        The temporary frame entry is removed after this attempt, whether decoding
        succeeds or fails, so corrupted data cannot remain in memory indefinitely.

        :param frame_id: Identifier of the stored frame to rebuild.
        :return: ``(decoded_frame, timestamp)`` on success, otherwise
                 ``(None, None)``.
        """
        result_frame = None
        result_timestamp = None
        if frame_id in self.frame_store:
            try:
                frame_data = self.frame_store[frame_id]
                parts = frame_data["parts"]
                timestamp = frame_data["timestamp"]
                total_parts = frame_data["total_parts"]
                full_bytes = b""
                missing = False
                # Dictionary insertion order is irrelevant: concatenate explicitly
                # from index 0 through total_parts - 1.
                for i in range(total_parts):
                    if i not in parts:
                        missing = True
                        break
                    full_bytes += parts[i]
                if not missing:
                    # OpenCV expects an unsigned-byte NumPy array containing the
                    # complete JPEG file, then converts it back into a BGR image.
                    np_arr = np.frombuffer(full_bytes, dtype=np.uint8)
                    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    result_frame = frame
                    result_timestamp = timestamp
                # A complete frame is used once; a malformed rebuild is also discarded.
                del self.frame_store[frame_id]
            except Exception as e:
                print("rebuild_frame error:", e)
                if frame_id in self.frame_store:
                    del self.frame_store[frame_id]
        return result_frame, result_timestamp

    def cleanup_old_frames(self, max_age=0.5):
        """
        Remove frames that stopped receiving parts before they became complete.

        This is the packet-loss policy: do not request retransmission or block later
        video. Discard the old incomplete frame and continue displaying newer frames.

        :param max_age: Maximum seconds since the most recently received part.
        :return: None.
        """
        now = time.time()
        old_ids = []
        # Collect IDs first to avoid changing the dictionary during iteration.
        for frame_id, data in self.frame_store.items():
            if now - data["last_update"] > max_age:
                old_ids.append(frame_id)
        for frame_id in old_ids:
            del self.frame_store[frame_id]
