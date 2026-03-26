import cv2
import threading
import numpy as np
import time

class CameraControl:
    """
    Threaded camera capture class.
    Continuously captures frames from the webcam, encodes them as JPEG bytes.
    Stop/start just pauses capture without releasing camera.
    """

    def __init__(self, width=478, height=359, jpeg_quality=60):
        self.width = width
        self.height = height
        self.jpeg_quality = jpeg_quality

        self.cam = cv2.VideoCapture(0)
        self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.last_frame = None
        self.running = False
        self.paused = False
        self.lock = threading.Lock()
        self.encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]

    def start(self):
        """Start or resume camera capture."""
        if not self.running:
            self.running = True
            threading.Thread(target=self._capture_loop, daemon=True).start()
        self.paused = False
        print("Camera started/resumed.")

    def stop(self, pause_only=True):
        """Pause camera capture. Fully release if pause_only=False."""
        self.paused = True
        if not pause_only:
            self.running = False
            if self.cam.isOpened():
                self.cam.release()
            print("Camera fully stopped.")

    def _capture_loop(self):
        while self.running:
            if self.paused:
                time.sleep(0.01)
                continue
            ret, frame = self.cam.read()
            if not ret:
                continue

            try:
                frame_resized = cv2.resize(frame, (self.width, self.height))
                with self.lock:
                    self.last_frame = frame_resized.copy()

            except Exception as e:
                print(f"Camera capture error: {e}")

    def get_frame(self):
        with self.lock:
            ret = None
            if self.last_frame is not None:
                ret = self.last_frame.copy()
            return ret

    def release(self):
        """Call this only on app exit."""
        self.running = False
        if self.cam.isOpened():
            self.cam.release()