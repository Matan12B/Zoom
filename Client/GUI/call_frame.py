import wx
import cv2
import numpy as np
import time
import threading


class CallFrame(wx.Frame):
    def __init__(self, call_logic):
        super().__init__(None, title="Meeting", size=(1024, 768))
        self.call_logic = call_logic

        # Start call logic
        threading.Thread(target=self.call_logic.start, daemon=True).start()

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # -----------------
        # Video grid (dynamic: max 4)
        # -----------------
        self.video_grid = wx.GridSizer(2, 2, 5, 5)
        self.video_panels = []

        self.camera_width = 478
        self.camera_height = 359

        for i in range(4):  # max 4 panels
            bmp = wx.StaticBitmap(panel, size=(self.camera_width, self.camera_height))
            self.video_panels.append(bmp)
            self.video_grid.Add(bmp, 1, wx.EXPAND)

        main_sizer.Add(self.video_grid, 1, wx.EXPAND | wx.ALL, 10)

        # -----------------
        # Controls
        # -----------------
        controls = wx.BoxSizer(wx.HORIZONTAL)
        self.mic_btn = wx.Button(panel, label="Mute")
        self.cam_btn = wx.Button(panel, label="Camera Off")
        self.leave_btn = wx.Button(panel, label="Leave")
        controls.Add(self.mic_btn, 0, wx.ALL, 5)
        controls.Add(self.cam_btn, 0, wx.ALL, 5)
        controls.AddStretchSpacer()
        controls.Add(self.leave_btn, 0, wx.ALL, 5)
        main_sizer.Add(controls, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(main_sizer)

        # -----------------
        # State
        # -----------------
        self.is_muted = False
        self.is_camera_off = False
        self.panel_has_video = [False] * 4

        # Pre-create black frame ONCE
        self.black_frame = np.zeros((self.camera_height, self.camera_width, 3), dtype=np.uint8)

        # Timer
        self.fps = 24
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_frames)
        self.timer.Start(int(1000 / self.fps))

        # Event bindings
        self.leave_btn.Bind(wx.EVT_BUTTON, self.leave_call)
        self.mic_btn.Bind(wx.EVT_BUTTON, self.toggle_mic)
        self.cam_btn.Bind(wx.EVT_BUTTON, self.toggle_camera)

    # -----------------
    # Frame update
    # -----------------
    def update_frames(self, event):
        # ---- SELF ----
        if hasattr(self.call_logic, 'camera') and self.call_logic.camera:
            frame_bytes = self.call_logic.camera.get_frame()
            if frame_bytes is not None and not self.is_camera_off:
                frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    self._display_frame(0, frame)
                    self.panel_has_video[0] = True
                else:
                    self._display_black(0)
            else:
                self._display_black(0)

        # ---- OTHERS ----
        if hasattr(self.call_logic, 'sync_buffer'):
            panel_idx = 1
            for client_ip, timestamps in list(self.call_logic.sync_buffer.items()):
                if panel_idx >= len(self.video_panels):
                    break

                frame_displayed = False
                if timestamps:
                    latest_ts = max(timestamps.keys())
                    data = timestamps[latest_ts]
                    if data.get("video") is not None:
                        self._display_frame(panel_idx, data["video"])
                        self.panel_has_video[panel_idx] = True
                        frame_displayed = True

                # Only display black if client exists but no video yet
                if not frame_displayed:
                    self._display_black(panel_idx)

                panel_idx += 1

            # Clear remaining panels (no client connected)
            for i in range(panel_idx, len(self.video_panels)):
                self.video_panels[i].SetBitmap(wx.NullBitmap)
                self.panel_has_video[i] = False

    # -----------------
    # Display helpers
    # -----------------
    def _display_frame(self, idx, frame):
        if frame is None or idx >= len(self.video_panels):
            return
        frame = cv2.resize(frame, (self.camera_width, self.camera_height))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        bitmap = wx.Bitmap.FromBuffer(w, h, rgb)
        panel = self.video_panels[idx]
        panel.SetBitmap(bitmap)
        panel.Refresh()

    def _display_black(self, idx):
        self._display_frame(idx, self.black_frame)

    # -----------------
    # Controls
    # -----------------
    def toggle_mic(self, event):
        if hasattr(self.call_logic, 'mic'):
            if self.is_muted:
                self.call_logic.mic.unmute()
                self.mic_btn.SetLabel("Mute")
                self.is_muted = False
            else:
                self.call_logic.mic.mute()
                self.mic_btn.SetLabel("Unmute")
                self.is_muted = True

    def toggle_camera(self, event):
        if hasattr(self.call_logic, 'camera'):
            if self.is_camera_off:
                self.call_logic.camera.start()
                self.cam_btn.SetLabel("Camera Off")
                self.is_camera_off = False
            else:
                self.call_logic.camera.stop()
                self.cam_btn.SetLabel("Camera On")
                self.is_camera_off = True
                self._display_black(0)

    def leave_call(self, event):
        self.timer.Stop()
        for frame in wx.GetTopLevelWindows():
            frame.Close()  # triggers EVT_CLOSE and destroys frames
        # Exit wxPython main loop
        wx.CallAfter(wx.GetApp().ExitMainLoop)
        self.call_logic.close()
