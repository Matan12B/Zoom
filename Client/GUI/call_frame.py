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
            rgb = cv2.cvtColor(cv2.resize(frame, (self.panel_width, self.panel_height)), cv2.COLOR_BGR2RGB)
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

    def __init__(self, call_logic, home_frame=None, username=""):
        super().__init__(None, title="Face2Face Meeting", size=(1180, 820), style=wx.DEFAULT_FRAME_STYLE & ~wx.RESIZE_BORDER)
        self.call_logic = call_logic
        self.home_frame = home_frame
        self.username = username
        self.camera_width = 478
        self.camera_height = 359
        self.last_self_frame = None
        self.remote_frames = {}
        self.is_closing = False
        self.is_camera_off = True
        self.no_mic = getattr(call_logic, "no_mic", False)
        self.is_muted = True if self.no_mic else False
        self.is_host = hasattr(call_logic, "host_server")
        mic = getattr(call_logic, "mic", None)
        if mic and hasattr(mic, "is_muted"):
            self.is_muted = bool(mic.is_muted)
        self.SetMinSize((1180, 820))
        self.SetBackgroundColour(ui_theme.PALETTE["call_bg"])
        self.panel = wx.Panel(self)
        ui_theme.style_window(self.panel, ui_theme.PALETTE["call_bg"], ui_theme.PALETTE["text_inverted"])
        # Main layout sizer: stacks header, video grid, and controls vertically
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._build_header(), 0, wx.EXPAND | wx.ALL, 18)
        sizer.Add(self._build_video_grid(), 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        sizer.Add(self._build_controls(), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        self.panel.SetSizer(sizer)
        self._refresh_control_styles()
        self._bind_events()
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
        # Horizontal sizer to split header info between left (title) and right (code)
        hsizer = wx.BoxSizer(wx.HORIZONTAL)
        # Vertical stack for "Meeting Room" and participant role text
        left = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(panel, label="LIVE MEETING")
        title = wx.StaticText(panel, label="Meeting room")
        role = "Host controls enabled" if self.is_host else "Connected as guest"
        self.meeting_meta_text = wx.StaticText(panel, label=role)
        ui_theme.style_text(lbl, ui_theme.PALETTE["surface_alt"], size_delta=1, bold=True)
        ui_theme.style_text(title, ui_theme.PALETTE["text_inverted"], size_delta=10, bold=True)
        ui_theme.style_text(self.meeting_meta_text, ui_theme.PALETTE["surface_alt"], size_delta=1)
        left.Add(lbl, 0, wx.BOTTOM, 6)
        left.Add(title, 0, wx.BOTTOM, 6)
        left.Add(self.meeting_meta_text, 0)
        code = getattr(self.call_logic, "meeting_code", "") or "N/A"
        self.meeting_code = code
        # Vertical stack for the meeting code display and Copy button
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

    def _build_video_grid(self):
        # 2x2 Grid sizer to hold participant video panels
        self.video_grid = wx.GridSizer(2, 2, 12, 12)
        self.video_panels = []
        for _ in range(4):
            vp = VideoPanel(self.panel, self.camera_width, self.camera_height)
            self.video_panels.append(vp)
            self.video_grid.Add(vp, 1, wx.EXPAND)
        return self.video_grid

    def _build_controls(self):
        panel = wx.Panel(self.panel)
        ui_theme.style_window(panel, ui_theme.PALETTE["call_surface"], ui_theme.PALETTE["call_ctrl_text"])
        # Horizontal row for Mic, Camera, and Leave buttons
        row = wx.BoxSizer(wx.HORIZONTAL)
        mic_label = "Unmute" if self.is_muted else "Mute"
        cam_label = "Camera On" if self.is_camera_off else "Camera Off"
        self.mic_btn = ui_theme.create_button(panel, mic_label, kind="call", min_height=38, min_width=110)
        self.cam_btn = ui_theme.create_button(panel, cam_label, kind="call", min_height=38, min_width=118)
        self.kick_btn = ui_theme.create_button(panel, "Remove", kind="call", min_height=38, min_width=110)
        self.leave_btn = ui_theme.create_button(panel, "Leave", kind="call_danger", min_height=38, min_width=100)
        row.Add(self.mic_btn, 0, wx.ALL, 6)
        row.Add(self.cam_btn, 0, wx.ALL, 6)
        if self.is_host:
            row.Add(self.kick_btn, 0, wx.ALL, 6)
        else:
            self.kick_btn.Hide()
        row.AddStretchSpacer()
        row.Add(self.leave_btn, 0, wx.ALL, 6)
        panel.SetSizer(row)
        return panel

    def _bind_events(self):
        self.leave_btn.Bind(wx.EVT_BUTTON, lambda e: self._shutdown())
        self.mic_btn.Bind(wx.EVT_BUTTON, self._toggle_mic)
        self.cam_btn.Bind(wx.EVT_BUTTON, self._toggle_camera)
        self.kick_btn.Bind(wx.EVT_BUTTON, self._on_kick)
        self.copy_code_btn.Bind(wx.EVT_BUTTON, self._copy_code)
        self.Bind(wx.EVT_CLOSE, lambda e: self._shutdown())

    def _refresh_control_styles(self):
        ui_theme.style_button(self.copy_code_btn, "secondary", min_height=40)
        ui_theme.style_button(self.mic_btn, "call_active" if self.is_muted else "call", min_height=38, min_width=110)
        ui_theme.style_button(self.cam_btn, "call_active" if self.is_camera_off else "call", min_height=38, min_width=118)
        if self.is_host:
            ui_theme.style_button(self.kick_btn, "call", min_height=38, min_width=110)
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
        self._update_self_panel()
        self._drain_remote_queue()
        self._draw_remote_panels()

    def _update_self_panel(self):
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
        self.video_panels[0].set_label(self.username or "You", muted=self.is_muted)
        if not self.is_camera_off and self.last_self_frame is not None:
            self.video_panels[0].set_frame(self.last_self_frame)
        else:
            self.video_panels[0].set_black()

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

    def _draw_remote_panels(self):
        connected = self._connected_remote_ips()
        connected_set = set(connected)
        for ip in [k for k in self.remote_frames if k not in connected_set]:
            self.remote_frames.pop(ip, None)
        last_recv = getattr(self.call_logic, "last_video_received_time", {})
        cam_off_set = getattr(self.call_logic, "remote_camera_off", set())
        now = time.monotonic()
        idx = 1
        for ip in connected:
            if idx >= len(self.video_panels):
                break
            vp = self.video_panels[idx]
            frame = self.remote_frames.get(ip)
            vp.set_label(self._display_name(ip), muted=self._is_remote_muted(ip))
            active = frame is not None and ip not in cam_off_set and (now - last_recv.get(ip, 0)) <= self.VIDEO_TIMEOUT
            if active:
                vp.set_frame(frame)
            else:
                vp.set_black()
            idx += 1
        for vp in self.video_panels[idx:]:
            vp.clear_panel()

    def _connected_remote_ips(self):
        oc = getattr(self.call_logic, "open_clients", None)
        if not oc:
            return []
        my_ip = getattr(self.call_logic, "ip", None)
        host_ip = getattr(self.call_logic, "host_ip", None)
        seen = set()
        out = []
        for ip in oc:
            if ip == my_ip and ip != host_ip:
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