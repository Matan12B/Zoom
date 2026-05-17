import threading
import time
import os
import platform
import subprocess
import tempfile

import cv2
import numpy as np
import wx

try:
    import mss
except ImportError:
    mss = None


class ScreenCaptureControl:
    """
    Threaded screen capture class that returns OpenCV BGR frames.
    Uses macOS screencapture when available, then falls back to wx.ScreenDC.
    """

    def __init__(self, max_width=1280, max_height=720, fps=5):
        self.max_width = max_width
        self.max_height = max_height
        self.fps = fps
        self.running = False
        self.last_frame = None
        self.last_frame_time = 0
        self.capture_thread = None
        self.lock = threading.Lock()
        self.last_error = ""
        self._mss = None

    def start(self):
        if not self.running:
            self.running = True
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()

    def stop(self):
        self.running = False
        try:
            if self.capture_thread is not None:
                self.capture_thread.join(timeout=1)
        except Exception:
            pass
        try:
            if self._mss is not None:
                self._mss.close()
        except Exception:
            pass
        self._mss = None
        with self.lock:
            self.last_frame = None

    def _capture_loop(self):
        delay = 1.0 / max(1, self.fps)
        while self.running:
            start = time.time()
            try:
                frame = self._capture_from_gui_thread()
                if frame is not None:
                    with self.lock:
                        self.last_frame = frame
                        self.last_frame_time = time.time()
                        self.last_error = ""
            except Exception as e:
                self.last_error = str(e)
                print("screen capture error:", e)
            elapsed = time.time() - start
            time.sleep(max(0.01, delay - elapsed))

    def _capture_from_gui_thread(self):
        if platform.system() == "Darwin":
            return self._capture_once(allow_wx=False)
        if wx.GetApp() is None:
            return self._capture_once(allow_wx=False)

        done = threading.Event()
        result = {"frame": None, "error": None}

        def capture():
            try:
                result["frame"] = self._capture_once(allow_wx=True)
            except Exception as e:
                result["error"] = e
            finally:
                done.set()

        wx.CallAfter(capture)
        if not done.wait(timeout=2):
            return None
        if result["error"] is not None:
            raise result["error"]
        return result["frame"]

    def _capture_once(self, allow_wx=True):
        frame = self._capture_mss()
        if self._is_usable_frame(frame):
            return self._scale_frame(frame)
        if frame is not None:
            self.last_error = "Screen capture returned a blank frame."
        if platform.system() == "Darwin":
            frame = self._capture_macos_screencapture()
            if self._is_usable_frame(frame):
                return self._scale_frame(frame)
            if frame is not None:
                self.last_error = "Screen capture returned a blank frame."
        if not allow_wx:
            if not self.last_error:
                self.last_error = "Screen capture did not return a usable frame."
            return None
        if wx.GetApp() is None:
            self.last_error = "Screen capture fallback needs a running wx application."
            return None
        try:
            frame = self._capture_wx_screen()
        except Exception as e:
            self.last_error = str(e)
            return None
        if self._is_usable_frame(frame):
            return self._scale_frame(frame)
        if frame is not None:
            self.last_error = "Screen capture returned a blank frame."
        elif not self.last_error:
            self.last_error = "Screen capture did not return a usable frame."
        return None

    def _capture_mss(self):
        if mss is None:
            return None
        try:
            if self._mss is None:
                self._mss = mss.mss()
            monitor = self._mss.monitors[0]
            shot = self._mss.grab(monitor)
            bgra = np.asarray(shot)
            return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)
        except Exception as e:
            self.last_error = f"mss capture failed: {e}"
            try:
                if self._mss is not None:
                    self._mss.close()
            except Exception:
                pass
            self._mss = None
            return None

    def _capture_macos_screencapture(self):
        fd, path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            result = subprocess.run(
                ["/usr/sbin/screencapture", "-x", "-t", "jpg", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=3,
            )
            if result.returncode != 0:
                err = result.stderr.decode(errors="ignore").strip()
                self.last_error = err or "screencapture failed"
                return None
            frame = cv2.imread(path, cv2.IMREAD_COLOR)
            return frame
        except Exception as e:
            self.last_error = f"screencapture failed: {e}"
            return None
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def _capture_wx_screen(self):
        width, height = wx.DisplaySize()
        if width <= 0 or height <= 0:
            return None

        screen_dc = wx.ScreenDC()
        bitmap = wx.Bitmap(width, height)
        mem_dc = wx.MemoryDC(bitmap)
        mem_dc.Blit(0, 0, width, height, screen_dc, 0, 0)
        mem_dc.SelectObject(wx.NullBitmap)

        image = bitmap.ConvertToImage()
        rgb = np.frombuffer(image.GetData(), dtype=np.uint8).reshape((height, width, 3))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return bgr

    def _is_usable_frame(self, frame):
        if frame is None or getattr(frame, "size", 0) == 0:
            return False
        try:
            return int(frame.max()) > 8 or float(frame.std()) > 1.0
        except Exception:
            return False

    def _scale_frame(self, frame):
        height, width = frame.shape[:2]
        scale = min(self.max_width / width, self.max_height / height, 1.0)
        if scale < 1.0:
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            frame = cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)
        return frame

    def get_frame(self):
        with self.lock:
            if self.last_frame is None or time.time() - self.last_frame_time > 1.0:
                return None
            return self.last_frame.copy()
