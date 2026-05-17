"""
call_frame.py

this file contains the meeting window and the video panels.
"""

import os
import threading
import queue
import time
import wx
import cv2
import numpy as np
from Client.GUI import ui_theme

_MUTED_ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "muted.png")


class VideoPanel(wx.Panel):
    """
    shows one participant video tile.
    """
    def __init__(self, parent, width=478, height=359):
        super().__init__(parent, size=(width, height))
        self.panel_width = width
        self.panel_height = height
        self.current_bitmap = None
        self.show_black = False
        self.label_text = ""
        self.label_muted = False
        self._muted_bmp_cache = {}
        self.SetMinSize((width, height))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(ui_theme.PALETTE["video_tile"])
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def set_frame(self, frame):
        """show a live opencv frame."""
        if frame is None:
            return
        try:
            frame_h, frame_w = frame.shape[:2]
            scale = min(self.panel_width / frame_w, self.panel_height / frame_h)
            new_w = int(frame_w * scale)
            new_h = int(frame_h * scale)
            resized = cv2.resize(frame, (new_w, new_h))
            x_offset = (self.panel_width - new_w) // 2
            y_offset = (self.panel_height - new_h) // 2
            canvas = np.zeros((self.panel_height, self.panel_width, 3), dtype=frame.dtype)
            canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
            rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            self.current_bitmap = wx.Bitmap.FromBuffer(w, h, rgb)
            self.show_black = False
            self.Refresh(False)
        except Exception as e:
            print("VideoPanel set_frame error:", e)

    def set_black(self):
        """show the camera-off screen."""
        if self.show_black and self.current_bitmap is None:
            return
        self.current_bitmap = None
        self.show_black = True
        self.Refresh(False)

    def clear_panel(self):
        """clear an unused video tile."""
        if not self.current_bitmap and not self.show_black and not self.label_text:
            return
        self.current_bitmap = None
        self.show_black = False
        self.label_text = ""
        self.label_muted = False
        self.Refresh(False)

    def set_label(self, text, muted=False):
        """update the name label."""
        text = text or ""
        if text == self.label_text and muted == self.label_muted:
            return
        self.label_text = text
        self.label_muted = muted
        self.Refresh(False)

    def _on_size(self, event):
        w, h = event.GetSize()
        if w > 0 and h > 0:
            self.panel_width = w
            self.panel_height = h
        self.Refresh(False)
        event.Skip()

    def _on_paint(self, _event):
        dc = wx.BufferedPaintDC(self)
        w, h = self.GetClientSize()
        if self.current_bitmap:
            bw = self.current_bitmap.GetWidth()
            bh = self.current_bitmap.GetHeight()
            bmp = self.current_bitmap
            if bw != w or bh != h:
                bmp = bmp.ConvertToImage().Scale(w, h, wx.IMAGE_QUALITY_NORMAL).ConvertToBitmap()
            dc.DrawBitmap(bmp, 0, 0)
        else:
            colour = wx.Colour(0, 0, 0) if self.show_black else self.GetBackgroundColour()
            dc.SetBrush(wx.Brush(colour))
            dc.SetPen(wx.Pen(colour))
            dc.DrawRectangle(0, 0, w, h)
        if self.label_text:
            dc.SetTextForeground(wx.WHITE)
            cam_off = self.show_black and not self.current_bitmap
            self._draw_label(dc, w, h, big=cam_off)

    def _draw_label(self, dc, w, h, big):
        font = self.GetFont()
        font.PointSize += 8 if big else 1
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        dc.SetFont(font)
        tw, th = dc.GetTextExtent(self.label_text)
        icon_sz = 0
        icon_gap = 0
        if self.label_muted:
            icon_sz = 50 if big else 26
            icon_gap = 12 if big else 10
        pad = 15 if big else 8
        box_w = tw + icon_sz + icon_gap + pad * 2
        box_h = max(th, icon_sz) + (20 if big else 10)
        if big:
            box_x = max(0, (w - box_w) // 2)
            box_y = max(0, (h - box_h) // 2)
        else:
            box_x = 8
            box_y = h - box_h - 8
        bg = wx.Colour(0, 0, 0, 180 if big else 170)
        dc.SetBrush(wx.Brush(bg))
        dc.SetPen(wx.Pen(bg))
        dc.DrawRoundedRectangle(box_x, box_y, box_w, box_h, 8 if big else 6)
        cx = box_x + pad
        if self.label_muted:
            iy = box_y + max(0, (box_h - icon_sz) // 2)
            self._draw_muted_icon(dc, cx, iy, icon_sz)
            cx += icon_sz + icon_gap
        dc.DrawText(self.label_text, cx, box_y + (box_h - th) // 2)

    def _draw_muted_icon(self, dc, x, y, size):
        bmp = self._load_muted_bmp(size)
        if bmp:
            dc.DrawBitmap(bmp, x, y, True)
            return
        bw = max(6, size // 2)
        bh = max(8, size - 4)
        dc.SetPen(wx.Pen(wx.WHITE, 2))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRoundedRectangle(x, y + 1, bw, bh, max(3, bw // 2))
        dc.SetPen(wx.Pen(wx.Colour(255, 102, 102), 2))
        dc.DrawLine(x - 2, y + bh + 2, x + bw + 4, y - 1)

    def _load_muted_bmp(self, size):
        if size in self._muted_bmp_cache:
            return self._muted_bmp_cache[size]
        bmp = None
        if os.path.exists(_MUTED_ICON_PATH):
            try:
                img = wx.Image(_MUTED_ICON_PATH, wx.BITMAP_TYPE_PNG)
                if img.IsOk():
                    bmp = img.Scale(size, size, wx.IMAGE_QUALITY_HIGH).ConvertToBitmap()
                    if not bmp.IsOk():
                        bmp = None
            except Exception:
                pass
        self._muted_bmp_cache[size] = bmp
        return bmp


class CallFrame(wx.Frame):
    """
    the main meeting window.
    """
    VIDEO_TIMEOUT = 1.5
    PAGE_SIZE = 9
    MAX_PARTICIPANTS = 18

    def __init__(self, call_logic, home_frame=None, username=""):
        super().__init__(None, title="Face2Face Meeting", size=(1360, 820), style=wx.DEFAULT_FRAME_STYLE & ~wx.RESIZE_BORDER)
        self.call_logic = call_logic
        self.home_frame = home_frame
        self.username = username
        self.camera_width = 478
        self.camera_height = 359
        self.last_self_frame = None
        self.remote_frames = {}
        self.screen_share_frame = None
        self.screen_share_owner_ip = None
        self.screen_share_layout_active = False
        self.is_screen_sharing = False
        self.participant_page = 0
        self.video_grid_visible_count = 0
        self.video_grid_cols = 0
        self.video_grid_compact = None
        self.chat_messages = []
        self.is_closing = False
        self.is_camera_off = True
        self.no_mic = getattr(call_logic, "no_mic", False)
        self.is_muted = True if self.no_mic else False
        self.is_host = hasattr(call_logic, "host_server")
        mic = getattr(call_logic, "mic", None)
        if mic and hasattr(mic, "is_muted"):
            self.is_muted = bool(mic.is_muted)
        self.SetMinSize((1360, 820))
        self.SetBackgroundColour(ui_theme.PALETTE["call_bg"])
        self.panel = wx.Panel(self)
        ui_theme.style_window(self.panel, ui_theme.PALETTE["call_bg"], ui_theme.PALETTE["text_inverted"])
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._build_header(), 0, wx.EXPAND | wx.ALL, 18)
        sizer.Add(self._build_body(), 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        sizer.Add(self._build_controls(), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        self.panel.SetSizer(sizer)
        self._refresh_control_styles()
        self._bind_events()
        self._configure_video_grid(1)
        self.video_panels[0].set_black()
        for vp in self.video_panels[1:]:
            vp.clear_panel()
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self.timer)
        self.timer.Start(1000 // 24)
        threading.Thread(target=self._run_call, daemon=True).start()
        self.Center()

    def _build_header(self):
        panel = wx.Panel(self.panel)
        ui_theme.style_window(panel, ui_theme.PALETTE["call_surface"], ui_theme.PALETTE["text_inverted"])
        hsizer = wx.BoxSizer(wx.HORIZONTAL)
        left = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(panel, label="LIVE MEETING")
        title = wx.StaticText(panel, label="Meeting room")
        role = "Host controls enabled" if self.is_host else "Connected as participant"
        self.meeting_meta_text = wx.StaticText(panel, label=role)
        ui_theme.style_text(lbl, ui_theme.PALETTE["surface_alt"], size_delta=1, bold=True)
        ui_theme.style_text(title, ui_theme.PALETTE["text_inverted"], size_delta=10, bold=True)
        ui_theme.style_text(self.meeting_meta_text, ui_theme.PALETTE["surface_alt"], size_delta=1)
        left.Add(lbl, 0, wx.BOTTOM, 6)
        left.Add(title, 0, wx.BOTTOM, 6)
        left.Add(self.meeting_meta_text, 0)
        code = getattr(self.call_logic, "meeting_code", "") or "N/A"
        self.meeting_code = code
        right = wx.BoxSizer(wx.VERTICAL)
        code_lbl = wx.StaticText(panel, label="Meeting code")
        code_val = wx.StaticText(panel, label=code)
        ui_theme.style_text(code_lbl, ui_theme.PALETTE["surface_alt"], size_delta=1, bold=True)
        ui_theme.style_text(code_val, ui_theme.PALETTE["text_inverted"], size_delta=7, bold=True)
        self.copy_code_btn = ui_theme.create_button(panel, "Copy Code", kind="secondary", min_height=40, min_width=130)
        right.Add(code_lbl, 0, wx.BOTTOM, 6)
        right.Add(code_val, 0, wx.BOTTOM, 10)
        right.Add(self.copy_code_btn, 0, wx.ALIGN_LEFT)
        hsizer.Add(left, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 20)
        hsizer.Add(right, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 20)
        panel.SetSizer(hsizer)
        return panel

    def _build_meeting_area(self):
        panel = wx.Panel(self.panel)
        ui_theme.style_window(panel, ui_theme.PALETTE["call_bg"], ui_theme.PALETTE["text_inverted"])
        self.meeting_area = panel
        self.meeting_sizer = wx.BoxSizer(wx.VERTICAL)
        self.screen_panel = VideoPanel(panel, 960, 540)
        self.screen_panel.Hide()
        self.camera_panel = wx.Panel(panel)
        ui_theme.style_window(self.camera_panel, ui_theme.PALETTE["call_bg"], ui_theme.PALETTE["text_inverted"])
        self.camera_grid = self._build_video_grid(self.camera_panel)
        self.camera_panel.SetSizer(self.camera_grid)
        self.meeting_sizer.Add(self.camera_panel, 1, wx.EXPAND)
        panel.SetSizer(self.meeting_sizer)
        return panel

    def _build_video_grid(self, parent):
        self.video_grid = wx.GridSizer(0, 1, 12, 12)
        self.video_panels = []
        for _ in range(self.PAGE_SIZE):
            vp = VideoPanel(parent, self.camera_width, self.camera_height)
            self.video_panels.append(vp)
            vp.Hide()
        return self.video_grid

    def _build_body(self):
        body = wx.BoxSizer(wx.HORIZONTAL)
        body.Add(self._build_meeting_area(), 1, wx.EXPAND | wx.RIGHT, 14)
        body.Add(self._build_chat_panel(), 0, wx.EXPAND)
        return body

    def _build_chat_panel(self):
        panel = wx.Panel(self.panel)
        panel.SetMinSize((300, -1))
        ui_theme.style_window(panel, ui_theme.PALETTE["call_surface"], ui_theme.PALETTE["text_inverted"])

        sizer = wx.BoxSizer(wx.VERTICAL)
        title = wx.StaticText(panel, label="Chat")
        ui_theme.style_text(title, ui_theme.PALETTE["text_inverted"], size_delta=4, bold=True)

        self.chat_log = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE,
        )
        self.chat_log.SetMinSize((280, 420))
        self.chat_log.SetBackgroundColour(ui_theme.PALETTE["call_surface_alt"])
        self.chat_log.SetForegroundColour(ui_theme.PALETTE["call_ctrl_text"])
        ui_theme.style_text(self.chat_log, ui_theme.PALETTE["call_ctrl_text"], size_delta=1)

        input_row = wx.BoxSizer(wx.HORIZONTAL)
        self.chat_input = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.chat_input.SetHint("Message")
        self.chat_input.SetMinSize(wx.Size(190, 38))
        self.chat_input.SetBackgroundColour(ui_theme.PALETTE["call_ctrl"])
        self.chat_input.SetForegroundColour(ui_theme.PALETTE["text_inverted"])
        ui_theme.style_text(self.chat_input, ui_theme.PALETTE["text_inverted"], size_delta=1)
        self.chat_send_btn = ui_theme.create_button(panel, "Send", kind="call", min_height=38, min_width=76)
        input_row.Add(self.chat_input, 1, wx.RIGHT | wx.EXPAND, 8)
        input_row.Add(self.chat_send_btn, 0)

        sizer.Add(title, 0, wx.ALL, 14)
        sizer.Add(self.chat_log, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 14)
        sizer.Add(input_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 14)
        panel.SetSizer(sizer)
        return panel

    def _build_controls(self):
        panel = wx.Panel(self.panel)
        self.controls_panel = panel
        ui_theme.style_window(panel, ui_theme.PALETTE["call_surface"], ui_theme.PALETTE["call_ctrl_text"])
        row = wx.BoxSizer(wx.HORIZONTAL)
        mic_label = "Unmute" if self.is_muted else "Mute"
        cam_label = "Camera On" if self.is_camera_off else "Camera Off"
        self.mic_btn = ui_theme.create_button(panel, mic_label, kind="call", min_height=38, min_width=110)
        self.cam_btn = ui_theme.create_button(panel, cam_label, kind="call", min_height=38, min_width=118)
        self.kick_btn = ui_theme.create_button(panel, "Remove", kind="call", min_height=38, min_width=110)
        self.share_btn = ui_theme.create_button(panel, "Share Screen", kind="call", min_height=38, min_width=138)
        self.prev_page_btn = ui_theme.create_button(panel, "<", kind="call", min_height=38, min_width=46)
        self.page_label = wx.StaticText(panel, label="Page 1/1")
        ui_theme.style_text(self.page_label, ui_theme.PALETTE["call_ctrl_text"], bold=True)
        self.next_page_btn = ui_theme.create_button(panel, ">", kind="call", min_height=38, min_width=46)
        self.leave_btn = ui_theme.create_button(panel, "Leave", kind="call_danger", min_height=38, min_width=100)
        row.Add(self.mic_btn, 0, wx.ALL, 6)
        row.Add(self.cam_btn, 0, wx.ALL, 6)
        if self.is_host:
            row.Add(self.kick_btn, 0, wx.ALL, 6)
            row.Add(self.share_btn, 0, wx.ALL, 6)
        else:
            self.kick_btn.Hide()
            self.share_btn.Hide()
        row.Add(self.prev_page_btn, 0, wx.ALL, 6)
        row.Add(self.page_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        row.Add(self.next_page_btn, 0, wx.ALL, 6)
        self.prev_page_btn.Hide()
        self.page_label.Hide()
        self.next_page_btn.Hide()
        row.AddStretchSpacer()
        row.Add(self.leave_btn, 0, wx.ALL, 6)
        panel.SetSizer(row)
        return panel

    def _bind_events(self):
        self.leave_btn.Bind(wx.EVT_BUTTON, lambda e: self._shutdown())
        self.mic_btn.Bind(wx.EVT_BUTTON, self._toggle_mic)
        self.cam_btn.Bind(wx.EVT_BUTTON, self._toggle_camera)
        self.kick_btn.Bind(wx.EVT_BUTTON, self._on_kick)
        self.share_btn.Bind(wx.EVT_BUTTON, self._toggle_screen_share)
        self.prev_page_btn.Bind(wx.EVT_BUTTON, self._previous_participant_page)
        self.next_page_btn.Bind(wx.EVT_BUTTON, self._next_participant_page)
        self.copy_code_btn.Bind(wx.EVT_BUTTON, self._copy_code)
        self.chat_send_btn.Bind(wx.EVT_BUTTON, self._send_chat)
        self.chat_input.Bind(wx.EVT_TEXT_ENTER, self._send_chat)
        self.Bind(wx.EVT_CLOSE, lambda e: self._shutdown())

    def _refresh_control_styles(self):
        ui_theme.style_button(self.copy_code_btn, "secondary", min_height=40)
        ui_theme.style_button(self.mic_btn, "call_active" if self.is_muted else "call", min_height=38, min_width=110)
        ui_theme.style_button(self.cam_btn, "call_active" if self.is_camera_off else "call", min_height=38, min_width=118)
        if self.is_host:
            ui_theme.style_button(self.kick_btn, "call", min_height=38, min_width=110)
            ui_theme.style_button(
                self.share_btn,
                "call_active" if self.is_screen_sharing else "call",
                min_height=38,
                min_width=138
            )
        ui_theme.style_button(self.prev_page_btn, "call", min_height=38, min_width=46)
        ui_theme.style_button(self.next_page_btn, "call", min_height=38, min_width=46)
        ui_theme.style_button(self.chat_send_btn, "call", min_height=38, min_width=76)
        ui_theme.style_button(self.leave_btn, "call_danger", min_height=38, min_width=100)

    def _run_call(self):
        try:
            self.call_logic.start()
        except Exception as e:
            wx.CallAfter(self._on_call_error, str(e))

    def _on_call_error(self, msg):
        wx.MessageBox(f"Could not connect: {msg}", "Connection Error", wx.OK | wx.ICON_ERROR)
        self._shutdown()

    def _on_timer(self, _event):
        if self.is_closing:
            return
        if not getattr(self.call_logic, "running", True):
            self._shutdown()
            return
        self._drain_self_frame()
        self._drain_remote_queue()
        self._drain_screen_share_queue()
        self._draw_screen_share_panel()
        self._draw_participant_panels()
        self._drain_chat_queue()

    def _drain_self_frame(self):
        newest = None
        ui_q = getattr(self.call_logic, "UI_queue", None)
        if ui_q:
            while True:
                try:
                    newest = ui_q.get_nowait()
                except queue.Empty:
                    break
        if newest is not None:
            self.last_self_frame = newest

    def _drain_remote_queue(self):
        rq = getattr(self.call_logic, "remote_video_queue", None)
        if not rq:
            return
        my_ip = getattr(self.call_logic, "ip", None)
        while True:
            try:
                ip, frame = rq.get_nowait()
            except queue.Empty:
                break
            if ip == my_ip:
                continue
            if frame is not None:
                self.remote_frames[ip] = frame

    def _draw_participant_panels(self):
        participants = self._participant_keys()
        connected_set = set(k for kind, k in participants if kind == "remote")
        for ip in [k for k in self.remote_frames if k not in connected_set]:
            self.remote_frames.pop(ip, None)

        pages = max(1, (len(participants) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.participant_page = max(0, min(self.participant_page, pages - 1))
        start = self.participant_page * self.PAGE_SIZE
        visible = participants[start:start + self.PAGE_SIZE]
        self._configure_video_grid(len(visible))
        self._refresh_page_controls(pages)

        last_recv = getattr(self.call_logic, "last_video_received_time", {})
        cam_off_set = getattr(self.call_logic, "remote_camera_off", set())
        now = time.monotonic()
        for idx, (kind, ip) in enumerate(visible):
            vp = self.video_panels[idx]
            vp.Show()
            if kind == "self":
                vp.set_label(self.username or "You", muted=self.is_muted)
                if not self.is_camera_off and self.last_self_frame is not None:
                    vp.set_frame(self.last_self_frame)
                else:
                    vp.set_black()
            else:
                frame = self.remote_frames.get(ip)
                vp.set_label(self._display_name(ip), muted=self._is_remote_muted(ip))
                active = frame is not None and ip not in cam_off_set and (now - last_recv.get(ip, 0)) <= self.VIDEO_TIMEOUT
                if active:
                    vp.set_frame(frame)
                else:
                    vp.set_black()
        for vp in self.video_panels[len(visible):]:
            vp.clear_panel()
            vp.Hide()
        self.camera_panel.Layout()

    def _participant_keys(self):
        participants = [("self", self._self_key())]
        for ip in self._connected_remote_ips():
            participants.append(("remote", ip))
        return participants[:self.MAX_PARTICIPANTS]

    def _self_key(self):
        return getattr(self.call_logic, "participant_id", None) or getattr(self.call_logic, "ip", "self")

    def _grid_shape(self, count):
        if count <= 1:
            return 1, 1
        if count == 2:
            return 1, 2
        if count <= 4:
            return 2, 2
        if count <= 6:
            return 2, 3
        return 3, 3

    def _configure_video_grid(self, count):
        count = max(1, min(count, self.PAGE_SIZE))
        _, cols = self._grid_shape(max(1, count))
        compact = self.screen_share_layout_active
        min_size = (150, 105) if compact else (220, 150)
        for vp in self.video_panels:
            vp.SetMinSize(min_size)
        if (
            count == self.video_grid_visible_count
            and cols == self.video_grid_cols
            and compact == self.video_grid_compact
        ):
            return
        self.video_grid.Clear(False)
        self.video_grid.SetRows(0)
        self.video_grid.SetCols(cols)
        for idx, vp in enumerate(self.video_panels):
            if idx < count:
                vp.Show()
                self.video_grid.Add(vp, 1, wx.EXPAND)
            else:
                vp.Hide()
        self.video_grid_visible_count = count
        self.video_grid_cols = cols
        self.video_grid_compact = compact

    def _refresh_page_controls(self, pages):
        show = pages > 1
        self.prev_page_btn.Show(show)
        self.page_label.Show(show)
        self.next_page_btn.Show(show)
        self.prev_page_btn.Enable(self.participant_page > 0)
        self.next_page_btn.Enable(self.participant_page < pages - 1)
        self.page_label.SetLabel(f"Page {self.participant_page + 1}/{pages}")
        if hasattr(self, "controls_panel"):
            self.controls_panel.Layout()

    def _previous_participant_page(self, _event):
        self.participant_page = max(0, self.participant_page - 1)
        self._draw_participant_panels()

    def _next_participant_page(self, _event):
        participants = self._participant_keys()
        pages = max(1, (len(participants) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.participant_page = min(pages - 1, self.participant_page + 1)
        self._draw_participant_panels()

    def _set_screen_share_layout(self, active):
        if active == self.screen_share_layout_active:
            return
        self.screen_share_layout_active = active
        self.meeting_sizer.Detach(self.screen_panel)
        self.meeting_sizer.Detach(self.camera_panel)
        if active:
            self.screen_panel.Show()
            self.camera_panel.Show()
            self.meeting_sizer.Add(self.screen_panel, 1, wx.EXPAND | wx.BOTTOM, 12)
            self.meeting_sizer.Add(self.camera_panel, 0, wx.EXPAND)
        else:
            self.screen_panel.Hide()
            self.screen_panel.clear_panel()
            self.camera_panel.Show()
            self.meeting_sizer.Add(self.camera_panel, 1, wx.EXPAND)
        self.camera_panel.Layout()
        self.meeting_area.Layout()
        self.panel.Layout()

    def _drain_screen_share_queue(self):
        share_q = getattr(self.call_logic, "screen_share_queue", None)
        if not share_q:
            return
        while True:
            try:
                owner_ip, frame = share_q.get_nowait()
            except queue.Empty:
                break
            self.screen_share_owner_ip = owner_ip
            if frame is not None:
                self.screen_share_frame = frame

    def _draw_screen_share_panel(self):
        active = bool(getattr(self.call_logic, "screen_share_active", False))
        owner_ip = getattr(self.call_logic, "screen_share_owner_ip", None) or self.screen_share_owner_ip
        self._set_screen_share_layout(active)
        if not active:
            self.screen_share_frame = None
            self.screen_share_owner_ip = None
            if self.is_screen_sharing:
                self.is_screen_sharing = False
                self.share_btn.SetLabel("Share Screen")
                self._refresh_control_styles()
            return

        if self.screen_share_frame is not None:
            my_ip = getattr(self.call_logic, "ip", None)
            my_id = getattr(self.call_logic, "participant_id", None)
            owner_name = "You are" if owner_ip in (my_ip, my_id) else f"{self._display_name(owner_ip)} is"
            self.screen_panel.set_label(f"{owner_name} sharing screen")
            self.screen_panel.set_frame(self.screen_share_frame)
        else:
            label = "Starting screen share..."
            error = self._screen_share_error_text()
            if owner_ip in (getattr(self.call_logic, "ip", None), getattr(self.call_logic, "participant_id", None)):
                if error:
                    label = error
                else:
                    started = getattr(self.call_logic, "last_screen_received_time", 0)
                    if started and time.monotonic() - started > 2:
                        label = "Allow Screen Recording for Terminal or Python"
            else:
                label = "Waiting for shared screen..."
            self.screen_panel.set_label(label)
            self.screen_panel.set_black()

    def _screen_share_error_text(self):
        error = getattr(self.call_logic, "last_screen_share_error", "")
        capture = getattr(self.call_logic, "screen_capture", None)
        if not error and capture is not None:
            error = getattr(capture, "last_error", "")
        if not error:
            return ""
        lowered = str(error).lower()
        if "create image from display" in lowered or "blank" in lowered or "screen" in lowered:
            return "Allow Screen Recording for Terminal or Python"
        return "Screen capture is unavailable"

    def _connected_remote_ips(self):
        oc = getattr(self.call_logic, "open_clients", None)
        if not oc:
            return []
        my_ip = getattr(self.call_logic, "ip", None)
        my_id = getattr(self.call_logic, "participant_id", None)
        host_ip = getattr(self.call_logic, "host_ip", None)
        seen = set()
        out = []
        for ip in oc:
            if ip in (my_ip, my_id) and ip != host_ip:
                continue
            if ip not in seen:
                seen.add(ip)
                out.append(ip)
        return out

    def _display_name(self, ip):
        oc = getattr(self.call_logic, "open_clients", {})
        val = oc.get(ip)
        if isinstance(val, dict):
            return val.get("username", ip)
        if isinstance(val, list) and len(val) >= 3:
            return val[2] or ip
        if isinstance(val, str):
            return val
        return ip

    def _is_remote_muted(self, ip):
        oc = getattr(self.call_logic, "open_clients", {})
        val = oc.get(ip)
        if isinstance(val, dict):
            return any(bool(val.get(k)) for k in ("muted", "is_muted", "mic_muted"))
        if isinstance(val, list) and len(val) >= 4 and isinstance(val[3], bool):
            return val[3]
        return False

    def _send_chat(self, _event):
        text = self.chat_input.GetValue().strip()
        if not text:
            return
        self.chat_input.SetValue("")
        try:
            sent = self.call_logic.send_chat_message(text)
            if sent is False:
                self._append_chat_message({
                    "username": "System",
                    "text": "Message could not be sent.",
                    "timestamp": time.time(),
                })
        except Exception as e:
            print("send chat error:", e)
            self._append_chat_message({
                "username": "System",
                "text": "Message could not be sent.",
                "timestamp": time.time(),
            })

    def _drain_chat_queue(self):
        chat_q = getattr(self.call_logic, "chat_queue", None)
        if not chat_q:
            return
        while True:
            try:
                msg = chat_q.get_nowait()
            except queue.Empty:
                break
            self._append_chat_message(msg)

    def _append_chat_message(self, msg):
        username = msg.get("username") or "Unknown"
        text = msg.get("text") or ""
        timestamp = msg.get("timestamp") or time.time()
        try:
            sent_time = time.strftime("%H:%M", time.localtime(float(timestamp)))
        except Exception:
            sent_time = time.strftime("%H:%M")
        line = f"[{sent_time}] {username}: {text}\n"
        self.chat_messages.append(line)
        if len(self.chat_messages) > 200:
            self.chat_messages = self.chat_messages[-200:]
            self.chat_log.SetValue("".join(self.chat_messages))
        else:
            self.chat_log.AppendText(line)
        self.chat_log.ShowPosition(self.chat_log.GetLastPosition())

    def _toggle_mic(self, _event):
        mic = getattr(self.call_logic, "mic", None)
        if mic is None:
            wx.MessageBox("No microphone available.", "Microphone", wx.OK | wx.ICON_INFORMATION)
            return
        try:
            if self.is_muted:
                mic.unmute()
                self.mic_btn.SetLabel("Mute Mic")
                self.is_muted = False
            else:
                mic.mute()
                self.mic_btn.SetLabel("Unmute Mic")
                self.is_muted = True
            self._refresh_control_styles()
            try:
                self.call_logic.toggle_mic(self.is_muted)
            except Exception as e:
                print("toggle_mic error:", e)
        except Exception as e:
            print("toggle mic error:", e)

    def _toggle_camera(self, _event):
        cam = getattr(self.call_logic, "camera", None)
        if cam is None or (getattr(self.call_logic, "no_camera", False) and self.is_camera_off):
            wx.MessageBox("No camera available.", "Camera", wx.OK | wx.ICON_INFORMATION)
            return
        try:
            if self.is_camera_off:
                cam.start()
                self.cam_btn.SetLabel("Camera Off")
                self.is_camera_off = False
                try:
                    self.call_logic.notify_camera_state(True)
                except Exception:
                    pass
            else:
                cam.stop()
                self.cam_btn.SetLabel("Camera On")
                self.is_camera_off = True
                self.last_self_frame = None
                self.video_panels[0].set_black()
                try:
                    self.call_logic.notify_camera_state(False)
                except Exception:
                    pass
            self._refresh_control_styles()
        except Exception as e:
            print("toggle camera error:", e)

    def _toggle_screen_share(self, _event):
        if not self.is_host:
            return
        next_state = not self.is_screen_sharing
        try:
            ok = self.call_logic.toggle_screen_share(next_state)
        except Exception as e:
            print("toggle screen share error:", e)
            ok = False
        if ok:
            self.is_screen_sharing = next_state
            self.share_btn.SetLabel("Stop Share" if self.is_screen_sharing else "Share Screen")
            self._refresh_control_styles()
            self._draw_screen_share_panel()
        else:
            msg = "Could not start screen sharing."
            error = self._screen_share_error_text()
            if error:
                msg = f"{msg}\n\n{error}."
            wx.MessageBox(msg, "Screen Share", wx.OK | wx.ICON_ERROR)

    def _on_kick(self, _event):
        if not self.is_host:
            return
        guests = self._connected_remote_ips()
        if not guests:
            wx.MessageBox("No guests to remove.", "Kick", wx.OK | wx.ICON_INFORMATION)
            return
        names = [f"{self._display_name(ip)} ({ip})" for ip in guests]
        dlg = wx.SingleChoiceDialog(self, "Select a guest to remove:", "Kick Guest", names)
        if dlg.ShowModal() == wx.ID_OK:
            selected = dlg.GetSelection()
            ip = guests[selected]
            if wx.YES == wx.MessageBox(f"Remove {names[selected]}?", "Confirm", wx.YES_NO | wx.ICON_QUESTION):
                threading.Thread(target=self.call_logic.kick_client, args=(ip,), daemon=True).start()
        dlg.Destroy()

    def _copy_code(self, _event):
        code = getattr(self.call_logic, "meeting_code", "")
        if not code:
            wx.MessageBox("No meeting code available.", "Meeting Code")
            return
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(code))
            wx.TheClipboard.Close()
            wx.MessageBox("Copied!", "Meeting Code")
        else:
            wx.MessageBox("Could not open clipboard.", "Meeting Code")

    def _shutdown(self):
        if self.is_closing:
            return
        self.is_closing = True
        try:
            self.timer.Stop()
        except Exception:
            pass
        for attr in ("camera", "mic"):
            dev = getattr(self.call_logic, attr, None)
            if not dev:
                continue
            try:
                if attr == "camera":
                    dev.stop(pause_only=False)
                else:
                    dev.stop()
            except Exception:
                pass
        try:
            vc = getattr(self.call_logic, "video_comm", None)
            if vc:
                vc.close()
        except Exception:
            pass
        home = self.home_frame
        client = home.client if home else None
        try:
            if home:
                home.Show()
            self.Destroy()
        except Exception:
            pass
        cl = self.call_logic

        def _bg_close():
            try:
                if hasattr(cl, "cleanup"):
                    cl.cleanup()
                else:
                    cl.close()
            except Exception:
                pass
            finally:
                def _reset():
                    if client and client.role is cl:
                        client.role = None
                        client.meeting_code = None
                    if home:
                        home._enable_buttons()
                wx.CallAfter(_reset)

        threading.Thread(target=_bg_close, daemon=True).start()
