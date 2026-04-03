# call_frame.py

import wx
import cv2
import threading
import queue
import time


class VideoPanel(wx.Panel):
    """
    Custom video panel that draws frames with EVT_PAINT.
    Can show:
    - a video frame
    - black screen
    - empty panel
    - overlay text
    """

    def __init__(self, parent, width=478, height=359):
        super().__init__(parent, size=wx.Size(width, height))

        self.panel_width = width
        self.panel_height = height

        self.current_bitmap = None
        self.show_black = False
        self.label_text = ""

        self.SetMinSize(wx.Size(width, height))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)

    def set_frame(self, frame):
        """
        Receive OpenCV frame and convert it to wx.Bitmap.
        :param frame:
        :return:
        """
        if frame is None:
            return

        try:
            frame = cv2.resize(frame, (self.panel_width, self.panel_height))
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            self.current_bitmap = wx.Bitmap.FromBuffer(w, h, rgb)
            self.show_black = False
            self.Refresh(False)
        except Exception as e:
            print("VideoPanel set_frame error:", e)

    def set_black(self):
        """
        Show black panel.
        :return:
        """
        already_black = self.show_black and self.current_bitmap is None
        self.current_bitmap = None
        self.show_black = True

        if not already_black:
            self.Refresh(False)

    def clear_panel(self):
        """
        Show empty panel.
        :return:
        """
        already_clear = (self.current_bitmap is None) and (not self.show_black) and (self.label_text == "")
        self.current_bitmap = None
        self.show_black = False
        self.label_text = ""

        if not already_clear:
            self.Refresh(False)

    def set_label(self, text):
        """
        Set overlay label text.
        :param text:
        :return:
        """
        text = text if text else ""

        if text == self.label_text:
            return

        self.label_text = text
        self.Refresh(False)

    def on_paint(self, event):
        """
        Draw current frame / black / empty state + label.
        :param event:
        :return:
        """
        dc = wx.AutoBufferedPaintDC(self)
        width, height = self.GetClientSize()

        # ---------- draw background / frame ----------
        if self.current_bitmap is not None:
            bmp_w = self.current_bitmap.GetWidth()
            bmp_h = self.current_bitmap.GetHeight()
            if bmp_w != width or bmp_h != height:
                img = self.current_bitmap.ConvertToImage().Scale(width, height, wx.IMAGE_QUALITY_NORMAL)
                dc.DrawBitmap(img.ConvertToBitmap(), 0, 0)
            else:
                dc.DrawBitmap(self.current_bitmap, 0, 0)
        elif self.show_black:
            dc.SetBrush(wx.Brush(wx.Colour(0, 0, 0)))
            dc.SetPen(wx.Pen(wx.Colour(0, 0, 0)))
            dc.DrawRectangle(0, 0, width, height)
        else:
            bg = self.GetBackgroundColour()
            dc.SetBrush(wx.Brush(bg))
            dc.SetPen(wx.Pen(bg))
            dc.DrawRectangle(0, 0, width, height)

        # ---------- draw label ----------
        if not self.label_text:
            return

        dc.SetTextForeground(wx.Colour(255, 255, 255))

        # camera off / black screen -> big centered text
        if self.show_black and self.current_bitmap is None:
            font = self.GetFont()
            font.PointSize += 8
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            dc.SetFont(font)

            text_w, text_h = dc.GetTextExtent(self.label_text)

            box_w = text_w + 30
            box_h = text_h + 20
            box_x = max(0, (width - box_w) // 2)
            box_y = max(0, (height - box_h) // 2)

            dc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 180)))
            dc.SetPen(wx.Pen(wx.Colour(0, 0, 0, 180)))
            dc.DrawRoundedRectangle(box_x, box_y, box_w, box_h, 8)

            text_x = (width - text_w) // 2
            text_y = (height - text_h) // 2
            dc.DrawText(self.label_text, text_x, text_y)

        # camera on -> small text bottom left
        elif self.current_bitmap is not None:
            font = self.GetFont()
            font.PointSize += 1
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            dc.SetFont(font)

            text_w, text_h = dc.GetTextExtent(self.label_text)

            pad_x = 8
            pad_y = 4
            box_w = text_w + (pad_x * 2)
            box_h = text_h + (pad_y * 2)
            box_x = 8
            box_y = height - box_h - 8

            dc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 170)))
            dc.SetPen(wx.Pen(wx.Colour(0, 0, 0, 170)))
            dc.DrawRoundedRectangle(box_x, box_y, box_w, box_h, 6)

            dc.DrawText(self.label_text, box_x + pad_x, box_y + pad_y)


class CallFrame(wx.Frame):
    def __init__(self, call_logic, home_frame=None, username=""):
        super().__init__(None, title="Meeting", size=wx.Size(1024, 768))

        self.call_logic = call_logic
        self.home_frame = home_frame
        self.username = username

        self.camera_width = 478
        self.camera_height = 359
        self.remote_timeout = 1.0

        self.last_self_frame = None
        self.remote_frames = {}
        self.remote_frame_times = {}
        self.remote_usernames = {}

        self.is_muted = False
        self.is_camera_off = False
        self.is_closing = False

        self.panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # display meeting code
        self.meeting_code = getattr(self.call_logic, "meeting_code", "")

        meeting_bar = wx.BoxSizer(wx.HORIZONTAL)

        meeting_title = wx.StaticText(self.panel, label="Meeting Code:")
        title_font = meeting_title.GetFont()
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        meeting_title.SetFont(title_font)

        self.meeting_code_text = wx.StaticText(
            self.panel,
            label=self.meeting_code if self.meeting_code else "N/A"
        )

        code_font = self.meeting_code_text.GetFont()
        code_font.PointSize += 2
        code_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self.meeting_code_text.SetFont(code_font)

        self.copy_code_btn = wx.Button(self.panel, label="Copy Code")

        meeting_bar.Add(meeting_title, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        meeting_bar.Add(self.meeting_code_text, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        meeting_bar.AddStretchSpacer()
        meeting_bar.Add(self.copy_code_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        main_sizer.Add(meeting_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.video_grid = wx.GridSizer(2, 2, 5, 5)
        self.video_panels = []

        for _ in range(4):
            video_panel = VideoPanel(
                self.panel,
                width=self.camera_width,
                height=self.camera_height
            )
            self.video_panels.append(video_panel)
            self.video_grid.Add(video_panel, 1, wx.EXPAND)

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

        self.leave_btn.Bind(wx.EVT_BUTTON, self.leave_call)
        self.mic_btn.Bind(wx.EVT_BUTTON, self.toggle_mic)
        self.cam_btn.Bind(wx.EVT_BUTTON, self.toggle_camera)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.copy_code_btn.Bind(wx.EVT_BUTTON, self.copy_meeting_code)

        self.video_panels[0].set_black()
        for i in range(1, 4):
            self.video_panels[i].clear_panel()

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_frames, self.timer)
        self.timer.Start(1000 // 24)

        threading.Thread(target=self._run_call, daemon=True).start()

    def _run_call(self):
        try:
            self.call_logic.start()
        except Exception as e:
            wx.CallAfter(self._on_call_error, str(e))

    def _on_call_error(self, message):
        wx.MessageBox(f"Could not connect: {message}", "Connection Error", wx.OK | wx.ICON_ERROR)
        self._shutdown()

    def update_frames(self, event):
        """
        Update self panel and remote panels.
        """
        if self.is_closing:
            return

        # Call ended externally (e.g. kicked by host)
        if not getattr(self.call_logic, 'running', True):
            self._shutdown()
            return

        self._update_self_frame()
        self._update_remote_frames_from_queue()
        self._draw_remote_panels()

    def _update_self_frame(self):
        """
        Pull newest self frame from call logic.
        """
        newest_self_frame = None

        if hasattr(self.call_logic, "UI_queue"):
            while True:
                try:
                    newest_self_frame = self.call_logic.UI_queue.get_nowait()
                except queue.Empty:
                    break
                except Exception as e:
                    print("self queue error:", e)
                    break

        if newest_self_frame is not None:
            self.last_self_frame = newest_self_frame

        self.video_panels[0].set_label(self.username if self.username else "You")

        if not self.is_camera_off and self.last_self_frame is not None:
            self.video_panels[0].set_frame(self.last_self_frame)
        else:
            self.video_panels[0].set_black()

    def _update_remote_frames_from_queue(self):
        """
        Pull remote frames from queue.
        """
        if not hasattr(self.call_logic, "remote_video_queue"):
            return

        while True:
            try:
                client_ip, frame = self.call_logic.remote_video_queue.get_nowait()

                # safety: do not show self as remote
                if hasattr(self.call_logic, "ip") and client_ip == self.call_logic.ip:
                    continue

                if frame is not None:
                    self.remote_frames[client_ip] = frame
                    self.remote_frame_times[client_ip] = time.time()
            except queue.Empty:
                break
            except Exception as e:
                print("remote queue error:", e)
                break

    def _draw_remote_panels(self):
        """
        Draw remote users. Also cleans up stale remote_frames entries for
        clients that are no longer connected.
        Camera-off detection: if no real frame has arrived from a sender within
        VIDEO_TIMEOUT seconds, show a black placeholder + username instead of the
        frozen last frame (av_sync caches the last frame indefinitely).
        """
        VIDEO_TIMEOUT = 1.5  # seconds without a new network frame → show camera-off

        connected_clients = self._get_connected_remote_clients()
        connected_set = set(connected_clients)
        panel_idx = 1
        now = time.monotonic()

        # Remove stale frame entries for clients that have left
        for stale_ip in [ip for ip in list(self.remote_frames.keys()) if ip not in connected_set]:
            self.remote_frames.pop(stale_ip, None)
            self.remote_frame_times.pop(stale_ip, None)

        # Per-sender receive timestamps from the logic layer (updated only on real network frames)
        last_received = getattr(self.call_logic, "last_video_received_time", {})

        for client_ip in connected_clients:
            if panel_idx >= len(self.video_panels):
                break

            frame = self.remote_frames.get(client_ip)
            display_name = self._get_display_name_for_ip(client_ip)
            self.video_panels[panel_idx].set_label(display_name)

            # Use the network-arrival time so a frozen cached frame doesn't fool the timeout
            last_network_time = last_received.get(client_ip, 0)
            camera_active = frame is not None and (now - last_network_time) <= VIDEO_TIMEOUT

            if camera_active:
                self.video_panels[panel_idx].set_frame(frame)
            else:
                self.video_panels[panel_idx].set_black()

            panel_idx += 1

        for i in range(panel_idx, len(self.video_panels)):
            self.video_panels[i].clear_panel()

    def _get_display_name_for_ip(self, client_ip):
        if hasattr(self.call_logic, "open_clients") and client_ip in self.call_logic.open_clients:
            value = self.call_logic.open_clients[client_ip]

            if isinstance(value, dict):
                return value.get("username", client_ip)

            if isinstance(value, list) and len(value) >= 3:
                return value[2] if value[2] else client_ip

            if isinstance(value, str):
                return value
        return client_ip

    def _get_connected_remote_clients(self):
        """
        Return connected clients except self.
        Never excludes the host even when testing on the same machine.
        """
        connected_clients = []

        if not hasattr(self.call_logic, "open_clients"):
            return connected_clients

        my_ip = getattr(self.call_logic, "ip", None)
        host_ip = getattr(self.call_logic, "host_ip", None)

        try:
            seen = set()

            for client_ip in self.call_logic.open_clients.keys():
                # Skip self IP, but always keep the host (same-machine testing)
                if client_ip == my_ip and client_ip != host_ip:
                    continue

                if client_ip in seen:
                    continue

                seen.add(client_ip)
                connected_clients.append(client_ip)

        except Exception as e:
            print("connected clients error:", e)

        return connected_clients

    def toggle_mic(self, event):
        """
        Toggle microphone.
        """
        try:
            if not hasattr(self.call_logic, "mic"):
                return

            if self.is_muted:
                self.call_logic.mic.unmute()
                self.mic_btn.SetLabel("Mute")
                self.is_muted = False
            else:
                self.call_logic.mic.mute()
                self.mic_btn.SetLabel("Unmute")
                self.is_muted = True
        except Exception as e:
            print("toggle mic error:", e)

    def toggle_camera(self, event):
        """
        Toggle camera.
        """
        try:
            if not hasattr(self.call_logic, "camera"):
                return

            if self.is_camera_off:
                self.call_logic.camera.start()
                self.cam_btn.SetLabel("Camera Off")
                self.is_camera_off = False
            else:
                self.call_logic.camera.stop()
                self.cam_btn.SetLabel("Camera On")
                self.is_camera_off = True
                self.last_self_frame = None
                self.video_panels[0].set_black()
        except Exception as e:
            print("toggle camera error:", e)

    def leave_call(self, event):
        """
        Leave call from button.
        """
        self._shutdown()

    def on_close(self, event):
        """
        Handle window close.
        """
        self._shutdown()

    def _shutdown(self):
        """
        Close frame safely and return to HomeFrame.
        VideoComm is closed synchronously first (releases UDP port 5000 immediately
        so a rejoin can bind it right away). Everything else tears down in a background
        thread so the GUI never blocks.
        """
        if self.is_closing:
            return

        self.is_closing = True

        try:
            if hasattr(self, "timer"):
                self.timer.Stop()
        except Exception as e:
            print("timer stop error:", e)

        # Release UDP port 5000 immediately so a rejoin can bind it
        try:
            if hasattr(self.call_logic, "video_comm"):
                self.call_logic.video_comm.close()
        except Exception as e:
            print("video_comm early close error:", e)

        # Restore home screen immediately — don't wait for network teardown
        try:
            if self.home_frame:
                if hasattr(self.home_frame.client, "role"):
                    self.home_frame.client.role = None
                self.home_frame._enable_buttons()
                self.home_frame.Show()

            self.Destroy()
        except Exception as e:
            print("destroy error:", e)

        # Tear down the rest of the call logic in a background thread
        call_logic = self.call_logic

        def _do_close():
            try:
                if hasattr(call_logic, "cleanup"):
                    call_logic.cleanup()
                elif hasattr(call_logic, "close"):
                    call_logic.close()
            except Exception as e:
                print("close error:", e)

        threading.Thread(target=_do_close, daemon=True).start()

    def copy_meeting_code(self, event):
        code = getattr(self.call_logic, "meeting_code", "")

        if not code:
            wx.MessageBox("No meeting code available", "Meeting Code")
            return

        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(code))
            wx.TheClipboard.Close()
            wx.MessageBox("Meeting code copied", "Meeting Code")
        else:
            wx.MessageBox("Could not open clipboard", "Meeting Code")