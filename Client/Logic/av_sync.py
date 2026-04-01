import time
import heapq


class AVSyncManager:
    def __init__(self, playout_delay=0.03):
        self.playout_delay = playout_delay
        self.states = {}

    def _ensure_state(self, sender_ip, sender_ts):
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
        state = self._ensure_state(sender_ip, sender_ts)
        target_time = state["playout_base"] + (float(sender_ts) - state["first_sender_ts"])
        heapq.heappush(state["audio_heap"], (target_time, float(sender_ts), audio_bytes))

        if len(state["audio_heap"]) > 50:
            newest = sorted(state["audio_heap"], key=lambda x: x[1], reverse=True)[:50]
            state["audio_heap"] = newest
            heapq.heapify(state["audio_heap"])

    def add_video(self, sender_ip, sender_ts, frame):
        state = self._ensure_state(sender_ip, sender_ts)
        target_time = state["playout_base"] + (float(sender_ts) - state["first_sender_ts"])
        heapq.heappush(state["video_heap"], (target_time, float(sender_ts), frame))

        # keep only the newest few video frames
        if len(state["video_heap"]) > 3:
            newest = sorted(state["video_heap"], key=lambda x: x[1], reverse=True)[:3]
            state["video_heap"] = newest
            heapq.heapify(state["video_heap"])

    def pop_due_audio(self, sender_ip, now=None):
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
        Return exactly ONE due audio chunk for sender_ip, dropping stale chunks first.
        Stale = target_time older than (now - stale_threshold).

        Returns (sender_ts, audio_bytes) tuple, or None if nothing is due yet.
        """
        if now is None:
            now = time.monotonic()

        state = self.states.get(sender_ip)
        if not state:
            return None

        heap = state["audio_heap"]

        # Drop chunks that are too old to bother playing
        while heap and heap[0][0] < now - stale_threshold:
            heapq.heappop(heap)

        # Return the single oldest chunk that is due now
        if heap and heap[0][0] <= now:
            _, sender_ts, audio_bytes = heapq.heappop(heap)
            return (sender_ts, audio_bytes)

        return None

    def pop_latest_due_video(self, sender_ip, now=None):
        if now is None:
            now = time.monotonic()

        state = self.states.get(sender_ip)
        if not state:
            return None

        latest_frame = None
        while state["video_heap"] and state["video_heap"][0][0] <= now:
            _, _, frame = heapq.heappop(state["video_heap"])
            latest_frame = frame

        if latest_frame is not None:
            state["last_video_frame"] = latest_frame
            return latest_frame

        return state["last_video_frame"]

    def remove_sender(self, sender_ip):
        if sender_ip in self.states:
            del self.states[sender_ip]