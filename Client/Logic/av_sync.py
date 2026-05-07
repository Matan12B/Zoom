import time
import heapq

class AVSyncManager:
    """
    Manages synchronization between audio and video streams from multiple senders.
    Uses priority queues (heaps) to buffer and reorder packets based on timestamps.
    """

    def __init__(self, playout_delay=0.03):
        """
        Initialize the manager with a fixed playout buffer delay.
        :param playout_delay: Initial buffer time (seconds) to handle network jitter.
        """
        self.playout_delay = playout_delay
        self.states = {}

    def _ensure_state(self, sender_ip, sender_ts):
        """
        Initialize a tracking state for a new sender or return existing state.
        Sets the base timing for synchronization when the first packet arrives.
        :param sender_ip: The identifier for the source.
        :param sender_ts: The timestamp from the sender's clock.
        :return: Dictionary containing the sender's synchronization state.
        """
        if sender_ip not in self.states:
            now = time.monotonic()
            self.states[sender_ip] = {
                "first_sender_ts": float(sender_ts),
                "playout_base": now + self.playout_delay,
                "audio_heap": [],
                "video_heap": [],
                "last_video_frame": None
            }
        return self.states[sender_ip]

    def add_audio(self, sender_ip, sender_ts, audio_bytes):
        """
        Calculate target playout time and add audio bytes to the priority queue.
        Maintains a maximum buffer size of 50 chunks to prevent memory bloat.
        :param sender_ip: Source IP address.
        :param sender_ts: Timestamp attached to the audio chunk.
        :param audio_bytes: Raw audio data.
        """
        state = self._ensure_state(sender_ip, sender_ts)
        target_time = state["playout_base"] + (float(sender_ts) - state["first_sender_ts"])
        heapq.heappush(state["audio_heap"], (target_time, float(sender_ts), audio_bytes))

        # Audio is small but critical for continuity. 50 chunks (~1-2 seconds of audio)
        # is enough to handle network spikes without creating massive lag or memory leak.
        if len(state["audio_heap"]) > 50:
            newest = sorted(state["audio_heap"], key=lambda x: x[1], reverse=True)[:50]
            state["audio_heap"] = newest
            heapq.heapify(state["audio_heap"])

    def add_video(self, sender_ip, sender_ts, frame):
        """
        Calculate target playout time and add a video frame to the priority queue.
        Strictly keeps only the 3 most recent frames to ensure low latency.
        :param sender_ip: Source IP address.
        :param sender_ts: Timestamp attached to the video frame.
        :param frame: The decoded image/frame.
        """
        state = self._ensure_state(sender_ip, sender_ts)
        target_time = state["playout_base"] + (float(sender_ts) - state["first_sender_ts"])
        heapq.heappush(state["video_heap"], (target_time, float(sender_ts), frame))

        # Video frames are memory-heavy wee keep only 3 because if we fall more
        # than 3 frames behind it is better to skip to the latest frame than
        # to show old lagged video.
        if len(state["video_heap"]) > 3:
            newest = sorted(state["video_heap"], key=lambda x: x[1], reverse=True)[:3]
            state["video_heap"] = newest
            heapq.heapify(state["video_heap"])

    def pop_due_audio(self, sender_ip, now=None):
        """
        Retrieve all audio chunks whose target playout time has passed.
        :param sender_ip: Source IP address.
        :param now: Current reference time (defaults to monotonic clock).
        :return: List of tuples containing (sender_ts, audio_bytes).
        """
        if now is None:
            now = time.monotonic()

        state = self.states.get(sender_ip)
        if not state:
            return []

        due_audio = []
        while state["audio_heap"] and state["audio_heap"][0][0] <= now:
            _, sender_ts, audio_bytes = heapq.heappop(state["audio_heap"])
            due_audio.append((sender_ts, audio_bytes))

        return due_audio

    def pop_one_due_audio(self, sender_ip, now=None, stale_threshold=0.15):
        """
        Retrieve exactly one audio chunk that is ready for playout.
        Discards chunks that arrived too late to be played (stale).
        :param sender_ip: Source IP address.
        :param now: Current reference time.
        :param stale_threshold: Max age in seconds before a chunk is considered stale.
        :return: Tuple (sender_ts, audio_bytes) or None.
        """
        if now is None:
            now = time.monotonic()

        result = None
        state = self.states.get(sender_ip)
        if state:
            heap = state["audio_heap"]

            while heap and heap[0][0] < now - stale_threshold:
                heapq.heappop(heap)

            if heap and heap[0][0] <= now:
                _, sender_ts, audio_bytes = heapq.heappop(heap)
                result = (sender_ts, audio_bytes)

        return result

    def pop_latest_due_video(self, sender_ip, now=None):
        """
        Retrieve the most recent video frame that is ready for playout.
        Skips older intermediate frames to maintain real-time visual sync.
        :param sender_ip: Source IP address.
        :param now: Current reference time.
        :return: The latest due frame or the last displayed frame if none are due.
        """
        if now is None:
            now = time.monotonic()

        state = self.states.get(sender_ip)
        result = None
        if state:
            latest_frame = None
            while state["video_heap"] and state["video_heap"][0][0] <= now:
                _, _, frame = heapq.heappop(state["video_heap"])
                latest_frame = frame

            if latest_frame is not None:
                state["last_video_frame"] = latest_frame
                result = latest_frame
            else:
                result = state["last_video_frame"]

        return result

    def remove_sender(self, sender_ip):
        """
        Clean up and remove all synchronization data for a specific sender.
        Used when a user disconnects from the call.
        :param sender_ip: Source IP address to remove.
        """
        if sender_ip in self.states:
            del self.states[sender_ip]