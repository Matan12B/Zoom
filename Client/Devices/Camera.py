import cv2
import threading
import numpy as np


class CameraControl:
    """
    Threaded camera capture class.
    Continuously captures frames from the webcam, encodes them as JPEG bytes.
    """

    def __init__(self, width=320, height=240, jpeg_quality=90):
        self.width = width
        self.height = height
        self.jpeg_quality = jpeg_quality

        self.cam = cv2.VideoCapture(0)
        self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        self.last_frame = None
        self.running = False
        self.lock = threading.Lock()
        self.encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]

    def start(self):
        """Start the camera capture thread."""
        if not self.running:
            self.running = True
            threading.Thread(target=self._capture_loop, daemon=True).start()
            print("Camera started.")

    def stop(self):
        """Stop the camera capture."""
        if self.running:
            self.running = False
            self.cam.release()
            print("Camera stopped.")

    def _capture_loop(self):
        """Continuously capture frames, encode to JPEG, and store bytes."""
        while self.running:
            ret, frame = self.cam.read()
            if not ret:
                continue

            # Encode as JPEG
            success, encoded_frame = cv2.imencode('.jpg', frame, self.encode_param)
            if not success:
                continue

            # Convert to raw bytes and store
            frame_bytes = encoded_frame.tobytes()
            with self.lock:
                self.last_frame = frame_bytes

    def get_frame(self):
        """Return the latest JPEG-encoded frame bytes."""
        with self.lock:
            return self.last_frame


# Test the camera class
if __name__ == "__main__":
    cam = CameraControl(width=320, height=240)
    cam.start()

    try:
        while True:
            frame_bytes = cam.get_frame()
            if frame_bytes is not None:
                # Decode JPEG bytes for display
                frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    cv2.imshow("Camera", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cam.stop()
        cv2.destroyAllWindows()