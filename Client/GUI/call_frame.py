import wx
import cv2
import numpy as np
import threading
import queue


class CallFrame(wx.Frame):
    def __init__(self, call_logic):
        super().__init__(None, title="Meeting", size=(1024, 768))
        self.call_logic = call_logic

        threading.Thread(target=self.call_logic.start, daemon=True).start()

        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.video_grid = wx.GridSizer(2, 2, 5, 5)
        self.video_panels = []

        self.camera_width = 478
        self.camera_height = 359

        for _ in range(4):
            bmp = wx.StaticBitmap(self.panel, size=(self.camera_width, self.camera_height))
            self.video_panels.append(bmp)
            self.video_grid.Add(bmp, 1, wx.EXPAND)

        main_sizer.Add(self.video_grid, 1, wx.EXPAND | wx.ALL, 10)

        controls = wx.BoxSizer(wx.HORIZONTAL)
        self.mic_btn = wx.Button(self.panel, label="Mute")
        self.cam_btn = wx.Button(self.panel, label="Camera Off")
        self.leave_btn = wx.Button(self.panel, label="Leave")

        controls.Add(self.mic_btn, 0, wx.ALL, 5)
        controls.Add(self.cam_btn, 0, wx.ALL, 5)
        controls.AddStretchSpacer()
        controls.Add(self.leave_btn, 0, wx.ALL, 5)

        main_sizer.Add(controls, 0, wx.EXPAND | wx.ALL, 10)
        self.panel.SetSizer(main_sizer)

        self.is_muted = False
        self.is_camera_off = False
        self.last_self_frame = None

        self.black_frame = np.zeros((self.camera_height, self.camera_width, 3), dtype=np.uint8)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_frames, self.timer)
        self.timer.Start(1000 // 24)

        self.leave_btn.Bind(wx.EVT_BUTTON, self.leave_call)
        self.mic_btn.Bind(wx.EVT_BUTTON, self.toggle_mic)
        self.cam_btn.Bind(wx.EVT_BUTTON, self.toggle_camera)

        # start with empty remote panels
        self._display_black(0)
        for i in range(1, 4):
            self.video_panels[i].SetBitmap(wx.NullBitmap)

    def update_frames(self, event):
        # -----------------
        # SELF PANEL (always panel 0)
        # if no self video -> black
        # -----------------
        newest_self_frame = None

        if hasattr(self.call_logic, "UI_queue"):
            while True:
                try:
                    newest_self_frame = self.call_logic.UI_queue.get_nowait()
                except queue.Empty:
                    break

        if newest_self_frame is not None:
            self.last_self_frame = newest_self_frame

        if not self.is_camera_off and self.last_self_frame is not None:
            self._display_frame(0, self.last_self_frame)
        else:
            self._display_black(0)

        # -----------------
        # REMOTE PANELS (1..3)
        # connected client with no video -> black
        # not connected client -> empty
        # -----------------
        panel_idx = 1

        if hasattr(self.call_logic, "sync_buffer"):
            for client_ip, timestamps in list(self.call_logic.sync_buffer.items()):
                if panel_idx >= len(self.video_panels):
                    break

                frame_displayed = False

                if timestamps:
                    latest_ts = max(timestamps.keys())
                    data = timestamps[latest_ts]

                    if data.get("video") is not None:
                        self._display_frame(panel_idx, data["video"])
                        frame_displayed = True

                if not frame_displayed:
                    # client exists but no video yet
                    self._display_black(panel_idx)

                panel_idx += 1

        # remaining slots = no connected client
        for i in range(panel_idx, len(self.video_panels)):
            self.video_panels[i].SetBitmap(wx.NullBitmap)

    def _display_frame(self, idx, frame):
        if frame is None or idx >= len(self.video_panels):
            return

        try:
            frame = cv2.resize(frame, (self.camera_width, self.camera_height))
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            bitmap = wx.Bitmap.FromBuffer(w, h, rgb)
            self.video_panels[idx].SetBitmap(bitmap)
        except Exception as e:
            print("display frame error:", e)

    def _display_black(self, idx):
        self._display_frame(idx, self.black_frame)

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

        try:
            if hasattr(self.call_logic, "cleanup"):
                self.call_logic.cleanup()
            elif hasattr(self.call_logic, "close"):
                self.call_logic.close()
        except Exception as e:
            print("close error:", e)

        self.Destroy()