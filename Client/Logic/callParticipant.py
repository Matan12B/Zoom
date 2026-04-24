import threading
import time
import cv2
import queue
import socket
import psutil
import numpy as np
from Client.Devices.Camera import CameraControl
from Client.Devices.Microphone import Microphone
from Client.Devices.AudioOutputDevice import AudioOutput
from Client.Comms.videoComm import VideoComm
from Common.Cipher import AESCipher
from Client.Logic.av_sync import AVSyncManager


def get_ip_by_interface(interface_name="Ethernet 4"):
    """
    Return the IPv4 address of the given network interface.

    :param interface_name: Name of the network interface to look up.
    :return: IPv4 address string, or None if not found.
    """
    result = None
    addrs = psutil.net_if_addrs()
    if interface_name in addrs:
        for addr in addrs[interface_name]:
            if addr.family == socket.AF_INET:
                result = addr.address
                break
    return result


def get_fallback_ip(target_ip):
    """
    Return the local IP used to reach target_ip by opening a temporary UDP socket.

    :param target_ip: A reachable IP to route towards.
    :return: Local IPv4 address string, or '127.0.0.1' on failure.
    """
    result = "127.0.0.1"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target_ip, 1))
        result = s.getsockname()[0]
    except Exception:
        pass
    finally:
        s.close()
    return result


class CallParticipant:
    """
    Abstract base class shared by Host and CallLogic.
    Manages shared devices, video/audio playback loop, and disconnect handling.
    Subclasses provide their own audio/comms setup and override hooks as needed.
    """

    def __init__(self, meeting_key, comm, meeting_code, username,
                 fallback_target_ip="8.8.8.8", playout_delay=0.03, video_port=5000):
        """
        Initialize shared call state, devices, and media pipeline.

        :param meeting_key: Shared AES encryption key for the meeting.
        :param comm: Communication channel to the central server.
        :param meeting_code: The meeting room code.
        :param username: This participant's display name.
        :param fallback_target_ip: Used to determine local IP if interface lookup fails.
        :param playout_delay: AV sync playout buffer delay in seconds.
        """
        self.open_clients = {}
        self.meeting_code = meeting_code
        self.username = username
        self.comm = comm
        self.AES = AESCipher(meeting_key)

        self.ip = get_ip_by_interface("Ethernet 4")
        if not self.ip:
            self.ip = get_fallback_ip(fallback_target_ip)
        print(f"Local IP: {self.ip}")
        self.UI_queue = queue.Queue()
        self.remote_video_queue = queue.Queue()
        self.latest_remote_frames = {}
        # Tracks when the last real video frame arrived from each sender over the network.
        # Used to detect camera-off: if no frame arrives for >VIDEO_TIMEOUT seconds the
        # GUI shows a black placeholder instead of the frozen last frame.
        self.last_video_received_time = {}

        try:
            self.camera = CameraControl(width=320, height=240, jpeg_quality=5)
            # Check if the camera actually opened
            if self.camera.cam is None or not self.camera.cam.isOpened():
                print("No camera available – joining with camera off.")
                self.no_camera = True
            else:
                self.no_camera = False
        except Exception as e:
            print(f"Camera init failed ({e}) – joining with camera off.")
            self.camera = None
            self.no_camera = True
        self.encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
        try:
            self.mic = Microphone(80, rate=16000, channels=1, chunk=160)
            self.no_mic = False
        except Exception as e:
            print(f"Microphone init failed ({e}) – joining muted without mic.")
            self.mic = None
            self.no_mic = True

        try:
            self.AudioOutput = AudioOutput(rate=16000, channels=1)
        except Exception as e:
            print(f"AudioOutput init failed ({e}) – joining without audio output.")
            self.AudioOutput = None
        self.av_sync = AVSyncManager(playout_delay=playout_delay)
        self.video_comm = VideoComm(self.AES, self.open_clients, video_port)

        self.video_send_interval = 1 / 15.0
        self.last_video_send_time = 0.0
        self.last_video_enqueue_time = 0.0
        self.meeting_start_time = None
        self.running = True

    def _pre_start(self):
        """
        Hook called at the beginning of start() before devices and threads are initialized.
        Override to add pre-start validation or state setup.
        """
        pass

    def _start_threads(self):
        """
        Hook called by start() to launch subclass-specific background threads.
        Override to start threads that differ between Host and CallLogic.
        """
        pass

    def _send_video(self, frame, timestamp):
        """
        Hook called by start() to send an encoded video frame.
        Override to define how the subclass delivers frames (inline or via queue).

        :param frame: Raw OpenCV frame (numpy array).
        :param timestamp: Float timestamp relative to meeting start.
        """
        pass

    def start(self):
        """
        Start the call: run pre-start hook, initialize devices, launch shared and
        subclass-specific background threads, then run the camera capture loop
        on the calling thread until the call ends.

        Camera is NOT started here — the user must press "Camera On" in the UI.
        Microphone IS started but stays muted (is_muted=True by default) until
        the user presses "Unmute".
        """
        self._pre_start()
        print("Starting call...")
        # Camera intentionally NOT started — user enables it explicitly via the UI.
        if self.mic is not None and not self.no_mic:
            try:
                self.mic.start()
                # Do NOT call unmute() here — mic starts muted by default so the
                # UI mute indicator and the actual device state stay in sync.
            except Exception as e:
                print(f"Mic start failed ({e}) – continuing without mic.")
                self.no_mic = True
        threading.Thread(target=self.receive_video_loop, daemon=True).start()
        threading.Thread(target=self.playback_loop, daemon=True).start()
        self._start_threads()
        try:
            while self.running:
                now = time.time()
                # Sleep longer when camera hardware is absent or not yet started by user
                if self.camera is None or self.no_camera or not self.camera.running:
                    time.sleep(0.02)
                    continue
                frame = self.camera.get_frame()
                if frame is None:
                    time.sleep(0.005)
                    continue
                frame = frame.copy()
                while self.UI_queue.qsize() >= 1:
                    try:
                        self.UI_queue.get_nowait()
                    except queue.Empty:
                        break
                self.UI_queue.put(frame)
                if self.meeting_start_time is not None:
                    if now - self.last_video_send_time >= self.video_send_interval:
                        self.last_video_send_time = now
                        timestamp = now - self.meeting_start_time
                        self._send_video(frame, timestamp)
                time.sleep(0.005)
        except Exception as e:
            print("start loop error:", e)
        finally:
            self.close()

    def toggle_mic(self, is_muted):
        """
        Notify all peers of this participant's current mute state.
        Overridden by Host and CallLogic with the appropriate transport.
        """
        pass

    def notify_camera_state(self, is_on):
        """
        Notify all peers that this participant turned their camera on or off.
        Overridden by Host and CallLogic with the appropriate transport.
        """
        pass

    def handle_camera_state(self, data):
        """
        A remote participant changed their camera state.
        Force-expire their video timeout so the GUI immediately shows black (camera off)
        or resumes normally (camera on — next real frame will update the timer).
        """
        try:
            ip = data[0] if isinstance(data, list) else data
            is_on = bool(int(data[1])) if isinstance(data, list) and len(data) > 1 else True
        except Exception as e:
            print("handle_camera_state parse error:", e)
            return
        if not is_on:
            # Setting to 0 makes (now - 0) >> VIDEO_TIMEOUT → active=False immediately
            self.last_video_received_time[ip] = 0

    def _resolve_video_sender(self, addr):
        """
        Resolve the canonical sender IP from a UDP addr tuple.
        Return None to skip the frame entirely.
        Default returns addr[0]. Override in subclasses for IP mapping or self-skip.

        :param addr: UDP (ip, port) tuple from recvfrom.
        :return: Canonical IP string, or None to discard the frame.
        """
        return addr[0]

    def _default_client_entry(self, ip):
        """
        Return the default open_clients entry for a newly seen IP.
        Subclasses override to match their expected open_clients structure.

        :param ip: The new client's IP address.
        :return: Default entry value to store in open_clients.
        """
        return {"username": ip}

    def _close_comms(self):
        """
        Hook called by close() after devices are cleaned up.
        Subclasses override to close their specific communication channels.
        """
        pass

    def receive_video_loop(self):
        """
        Drain the video frame queue and feed frames into the AV sync manager.
        Runs in a background daemon thread.
        """
        while self.running:
            try:
                while not self.video_comm.frameQ.empty():
                    try:
                        video_data, timestamp, addr = self.video_comm.frameQ.get_nowait()
                    except queue.Empty:
                        break
                    sender_ip = self._resolve_video_sender(addr)
                    if sender_ip is None:
                        continue
                    if sender_ip not in self.open_clients:
                        self.open_clients[sender_ip] = self._default_client_entry(sender_ip)
                    if video_data is None:
                        continue
                    self.av_sync.add_video(sender_ip, float(timestamp), video_data)
                    self.last_video_received_time[sender_ip] = time.monotonic()
                time.sleep(0.005)
            except Exception as e:
                print("receive_video_loop error:", e)
                time.sleep(0.05)

    def playback_loop(self):
        """
        Pop due audio and video from AV sync and forward to output devices and UI queue.
        Takes exactly ONE audio chunk per sender per tick so that accumulated chunks drain
        sequentially instead of being smashed into a single mixed write (which causes
        garbled/saturated audio).
        Runs in a background daemon thread.
        """
        while self.running:
            now = time.monotonic()
            got_audio = False
            mixed_audio = None
            for client_ip in list(self.av_sync.states.keys()):
                try:
                    result = self.av_sync.pop_one_due_audio(client_ip, now)
                    if result is None:
                        continue
                    got_audio = True
                    _, audio_bytes = result
                    if not audio_bytes:
                        continue
                    chunk = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.int32)
                    if mixed_audio is None:
                        mixed_audio = chunk.copy()
                    elif len(chunk) == len(mixed_audio):
                        mixed_audio += chunk
                    elif len(chunk) < len(mixed_audio):
                        mixed_audio[:len(chunk)] += chunk
                    else:
                        extended = chunk.copy()
                        extended[:len(mixed_audio)] += mixed_audio
                        mixed_audio = extended
                except Exception as e:
                    print("playback_loop audio error:", e)
            if mixed_audio is not None and self.AudioOutput is not None:
                try:
                    mixed_clipped = np.clip(mixed_audio, -32768, 32767).astype(np.int16)
                    self.AudioOutput.play_bytes(mixed_clipped.tobytes())
                except Exception as e:
                    print("playback_loop write error:", e)
            for client_ip in list(self.av_sync.states.keys()):
                try:
                    frame = self.av_sync.pop_latest_due_video(client_ip, now)
                    if frame is not None:
                        self.latest_remote_frames[client_ip] = frame
                        while self.remote_video_queue.qsize() >= max(6, len(self.av_sync.states) * 2):
                            try:
                                self.remote_video_queue.get_nowait()
                            except queue.Empty:
                                break
                        self.remote_video_queue.put((client_ip, frame))
                except Exception as e:
                    print("playback_loop video error:", e)
            # When audio was played, loop immediately to drain any backlog quickly.
            # When idle, sleep briefly to avoid burning CPU.
            if not got_audio:
                time.sleep(0.005)

    def handle_disconnect(self, data):
        """
        Handle a participant leaving the call.
        Removes them from open_clients, AV sync, video comm, and cached frames.

        :param data: List where data[0] is the leaver's IP, data[1] is optional username.
        """
        try:
            ip = data[0] if len(data) > 0 else ""
            username = data[1] if len(data) > 1 else ip
        except Exception as e:
            print("disconnect parse error:", e)
            return
        print(f"{username} left the call")
        if ip in self.open_clients:
            del self.open_clients[ip]
        if ip in self.latest_remote_frames:
            del self.latest_remote_frames[ip]
        self.last_video_received_time.pop(ip, None)
        self.av_sync.remove_sender(ip)
        try:
            self.video_comm.remove_user(ip, 0)
        except Exception:
            pass

    def _cleanup_devices(self):
        """
        Stop all local media devices and close the video communication socket.
        """
        devices = []
        if self.camera is not None:
            devices.append(("camera", self.camera))
        if self.mic is not None:
            devices.append(("mic", self.mic))
        if self.AudioOutput is not None:
            devices.append(("audio output", self.AudioOutput))
        for label, device in devices:
            try:
                device.stop()
            except Exception as e:
                print(f"{label} stop error:", e)
        try:
            self.video_comm.close()
        except Exception as e:
            print("video close error:", e)

    def close(self):
        """
        Stop the call, clean up all devices, and close communication channels.
        Subclasses should call super().close() or override _close_comms() for extra teardown.
        """
        if self.running:
            print("Closing call...")
            self.running = False
            self._cleanup_devices()
            self._close_comms()
            time.sleep(0.1)

    def leave_call(self):
        """
        Trigger graceful call shutdown. Alias for close().
        """
        self.close()
