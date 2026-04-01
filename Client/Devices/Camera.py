import cv2
import threading
import time
import platform


class CameraControl:
    """
    Threaded camera capture class.
    Continuously captures frames from the webcam.
    If camera read fails repeatedly, it reopens the camera.
    """

    def __init__(self, width=478, height=359, jpeg_quality=60):
        self.width = width
        self.height = height
        self.jpeg_quality = jpeg_quality

        self.cam = None
        self.last_frame = None
        self.running = False
        self.paused = False
        self.lock = threading.Lock()
        self.capture_thread = None
        self.failed_reads = 0
        self.last_frame_time = 0

        self._open_camera()

    def _open_camera(self):
        """
        Open camera with a platform-appropriate backend.
        """
        try:
            if self.cam is not None and self.cam.isOpened():
                self.cam.release()
        except Exception:
            pass

        system = platform.system()
        if system == "Windows":
            self.cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        elif system == "Darwin":
            self.cam = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
        else:
            self.cam = cv2.VideoCapture(0)

        if not self.cam or not self.cam.isOpened():
            self.cam = cv2.VideoCapture(0)

        if self.cam and self.cam.isOpened():
            self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            print("Camera opened.")
        else:
            print("Failed to open camera.")

    def start(self):
        """
        Start or resume camera capture.
        """
        if self.cam is None or not self.cam.isOpened():
            self._open_camera()

        if not self.running:
            self.running = True
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()

        self.paused = False
        print("Camera started/resumed.")

    def stop(self, pause_only=True):
        """
        Pause camera capture. Fully release if pause_only=False.
        """
        self.paused = True

        if not pause_only:
            self.running = False
            try:
                if self.capture_thread is not None:
                    self.capture_thread.join(timeout=1)
            except Exception:
                pass

            if self.cam is not None and self.cam.isOpened():
                self.cam.release()

            print("Camera fully stopped.")

    def _capture_loop(self):
        while self.running:
            if self.paused:
                time.sleep(0.02)
                continue

            try:
                if self.cam is None or not self.cam.isOpened():
                    print("Camera is closed, reopening...")
                    self._open_camera()
                    time.sleep(0.2)
                    continue

                ret, frame = self.cam.read()

                if not ret or frame is None:
                    self.failed_reads += 1
                    print(f"Camera read failed: {self.failed_reads}")

                    # After repeated failures, reopen camera
                    if self.failed_reads >= 10:
                        print("Reopening camera after repeated read failures...")
                        self._open_camera()
                        self.failed_reads = 0

                    # if camera is stale for too long, clear last_frame
                    if time.time() - self.last_frame_time > 1.0:
                        with self.lock:
                            self.last_frame = None

                    time.sleep(0.03)
                    continue

                self.failed_reads = 0

                frame_resized = cv2.resize(frame, (self.width, self.height))

                with self.lock:
                    self.last_frame = frame_resized.copy()
                    self.last_frame_time = time.time()

                time.sleep(0.01)

            except Exception as e:
                print(f"Camera capture error: {e}")
                time.sleep(0.05)

    def get_frame(self):
        with self.lock:
            if self.last_frame is None:
                return None

            # if frame is too old, treat camera as stalled
            if time.time() - self.last_frame_time > 1.0:
                return None

            return self.last_frame.copy()

    def release(self):
        """
        Call this only on app exit.
        """
        self.running = False

        try:
            if self.capture_thread is not None:
                self.capture_thread.join(timeout=1)
        except Exception:
            pass

        if self.cam is not None and self.cam.isOpened():
            self.cam.release()