import os
import wx
import cv2
import threading
import queue
import time

from Client.GUI import ui_theme


_MUTED_ICON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "assets",
    "muted.png",
)


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
        self.label_muted = False
        self._muted_icon_cache = {}

        self.SetMinSize(wx.Size(width, height))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(ui_theme.PALETTE["video_tile"])
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
        if self.show_black and self.current_bitmap is None:
            return

        self.current_bitmap = None
        self.show_black = True
        self.Refresh(False)

    def clear_panel(self):
        """
        Show empty panel.
        :return:
        """
        if self.current_bitmap is None and not self.show_black and self.label_text == "":
            return

        self.current_bitmap = None
        self.show_black = False
        self.label_text = ""
        self.label_muted = False
        self.Refresh(False)

    def set_label(self, text, muted=False):
        """
        Set overlay label text.
        :param text:
        :return:
        """
        text = text or ""

        if text == self.label_text and muted == self.label_muted:
            return

        self.label_text = text
        self.label_muted = muted
        self.Refresh(False)

    def _draw_muted_icon(self, dc, x, y, size=14):
        bitmap = self._get_muted_icon_bitmap(size)
        if bitmap is not None:
            dc.DrawBitmap(bitmap, x, y, True)
            return

        body_w = max(6, size // 2)
        body_h = max(8, size - 4)
        body_x = x
        body_y = y + 1

        dc.SetPen(wx.Pen(wx.Colour(255, 255, 255), 2))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawRoundedRectangle(body_x, body_y, body_w, body_h, max(3, body_w // 2))
        dc.DrawLine(body_x + (body_w // 2), body_y + body_h, body_x + (body_w // 2), body_y + body_h + 4)
        dc.DrawArc(
            body_x - 1,
            body_y + body_h - 1,
            body_x + body_w + 1,
            body_y + body_h - 1,
            body_x + (body_w // 2),
            body_y + body_h + 8,
        )
        dc.DrawLine(body_x - 2, body_y + body_h + 8, body_x + body_w + 2, body_y + body_h + 8)
        dc.SetPen(wx.Pen(wx.Colour(255, 102, 102), 2))
        dc.DrawLine(body_x - 2, body_y + body_h + 2, body_x + body_w + 4, body_y - 2)

    def _get_muted_icon_bitmap(self, size):
        if size in self._muted_icon_cache:
            return self._muted_icon_cache[size]

        if not os.path.exists(_MUTED_ICON_PATH):
            self._muted_icon_cache[size] = None
            return None

        try:
            image = wx.Image(_MUTED_ICON_PATH, wx.BITMAP_TYPE_PNG)
            if not image.IsOk():
                self._muted_icon_cache[size] = None
                return None

            bitmap = image.Scale(size, size, wx.IMAGE_QUALITY_HIGH).ConvertToBitmap()
            self._muted_icon_cache[size] = bitmap if bitmap.IsOk() else None
        except Exception as e:
            print("muted icon load error:", e)
            self._muted_icon_cache[size] = None

        return self._muted_icon_cache[size]

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
            icon_size = 50 if self.label_muted else 0
            icon_gap = 12 if self.label_muted else 0
            icon_w = icon_size

            box_w = text_w + icon_w + icon_gap + 30
            box_h = text_h + 20
            box_x = max(0, (width - box_w) // 2)
            box_y = max(0, (height - box_h) // 2)

            dc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 180)))
            dc.SetPen(wx.Pen(wx.Colour(0, 0, 0, 180)))
            dc.DrawRoundedRectangle(box_x, box_y, box_w, box_h, 8)

            content_x = box_x + 15
            if self.label_muted:
                icon_y = box_y + max(1, (box_h - icon_size) // 2)
                self._draw_muted_icon(dc, content_x, icon_y, size=icon_size)
                content_x += icon_w + icon_gap

            text_x = content_x
            text_y = (height - text_h) // 2
            dc.DrawText(self.label_text, text_x, text_y)

        # camera on -> small text bottom left
        elif self.current_bitmap is not None:
            font = self.GetFont()
            font.PointSize += 1
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            dc.SetFont(font)

            text_w, text_h = dc.GetTextExtent(self.label_text)
            icon_size = 26 if self.label_muted else 0
            icon_gap = 10 if self.label_muted else 0
            icon_w = icon_size

            pad_x = 8
            pad_y = 5
            box_w = text_w + icon_w + icon_gap + (pad_x * 2)
            box_h = max(text_h, icon_size) + (pad_y * 2)
            box_x = 8
            box_y = height - box_h - 8

            dc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 170)))
            dc.SetPen(wx.Pen(wx.Colour(0, 0, 0, 170)))
            dc.DrawRoundedRectangle(box_x, box_y, box_w, box_h, 6)
            text_x = box_x + pad_x
            if self.label_muted:
                icon_y = box_y + max(0, (box_h - icon_size) // 2)
                self._draw_muted_icon(dc, text_x, icon_y, size=icon_size)
                text_x += icon_w + icon_gap

            dc.DrawText(self.label_text, text_x, box_y + (box_h - text_h) // 2)


class CallFrame(wx.Frame):
    VIDEO_TIMEOUT = 1.5  # seconds without a new network frame → show camera-off

    def __init__(self, call_logic, home_frame=None, username=""):
        super().__init__(None, title="Python Zoom Meeting", size=wx.Size(1180, 820))

        self.call_logic = call_logic
        self.home_frame = home_frame
        self.username = username

        self.camera_width = 478
        self.camera_height = 359
        self.remote_timeout = 1.0

        self.last_self_frame = None
        self.remote_frames = {}
        self.remote_frame_times = {}

        self.is_muted = False
        self.is_camera_off = False
        self.is_closing = False
        # Host check: only the Host class has a host_server attribute
        self.is_host = hasattr(self.call_logic, "host_server")
        if hasattr(self.call_logic, "mic") and hasattr(self.call_logic.mic, "is_muted"):
            self.is_muted = bool(self.call_logic.mic.is_muted)

        self.SetMinSize(wx.Size(1024, 740))
        self.SetBackgroundColour(ui_theme.PALETTE["call_bg"])
        self.panel = wx.Panel(self)
        ui_theme.style_window(self.panel, ui_theme.PALETTE["call_bg"], ui_theme.PALETTE["text_inverted"])
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # display meeting code
        self.meeting_code = getattr(self.call_logic, "meeting_code", "")

        header_panel = wx.Panel(self.panel)
        ui_theme.style_window(header_panel, ui_theme.PALETTE["call_surface"], ui_theme.PALETTE["text_inverted"])
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        header_copy = wx.BoxSizer(wx.VERTICAL)
        meeting_label = wx.StaticText(header_panel, label="LIVE MEETING")
        meeting_title = wx.StaticText(header_panel, label="Meeting room")
        role_text = "Host controls enabled" if self.is_host else "Connected as participant"
        self.meeting_meta_text = wx.StaticText(header_panel, label=role_text)
        ui_theme.style_text(meeting_label, ui_theme.PALETTE["surface_alt"], size_delta=1, bold=True)
        ui_theme.style_text(meeting_title, ui_theme.PALETTE["text_inverted"], size_delta=10, bold=True)
        ui_theme.style_text(self.meeting_meta_text, ui_theme.PALETTE["surface_alt"], size_delta=1)
        header_copy.Add(meeting_label, 0, wx.BOTTOM, 6)
        header_copy.Add(meeting_title, 0, wx.BOTTOM, 6)
        header_copy.Add(self.meeting_meta_text, 0)

        code_wrap = wx.BoxSizer(wx.VERTICAL)
        code_label = wx.StaticText(header_panel, label="Meeting code")
        ui_theme.style_text(code_label, ui_theme.PALETTE["surface_alt"], size_delta=1, bold=True)
        self.meeting_code_text = wx.StaticText(
            header_panel,
            label=self.meeting_code if self.meeting_code else "N/A"
        )
        ui_theme.style_text(self.meeting_code_text, ui_theme.PALETTE["text_inverted"], size_delta=7, bold=True)
        self.copy_code_btn = ui_theme.create_button(
            header_panel,
            "Copy Code",
            kind="secondary",
            min_height=40,
            min_width=130,
        )
        code_wrap.Add(code_label, 0, wx.BOTTOM, 6)
        code_wrap.Add(self.meeting_code_text, 0, wx.BOTTOM, 10)
        code_wrap.Add(self.copy_code_btn, 0, wx.ALIGN_LEFT)

        header_sizer.Add(header_copy, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 20)
        header_sizer.Add(code_wrap, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 20)
        header_panel.SetSizer(header_sizer)
        main_sizer.Add(header_panel, 0, wx.EXPAND | wx.ALL, 18)

        self.video_grid = wx.GridSizer(2, 2, 12, 12)
        self.video_panels = []

        for _ in range(4):
            video_panel = VideoPanel(
                self.panel,
                width=self.camera_width,
                height=self.camera_height
            )
            self.video_panels.append(video_panel)
            self.video_grid.Add(video_panel, 1, wx.EXPAND)

        main_sizer.Add(self.video_grid, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)

        controls_panel = wx.Panel(self.panel)
        ui_theme.style_window(controls_panel, ui_theme.PALETTE["call_surface"], ui_theme.PALETTE["text_inverted"])
        controls = wx.BoxSizer(wx.HORIZONTAL)

        self.mic_btn = ui_theme.create_button(controls_panel, "Mute Mic", kind="secondary", min_height=46, min_width=138)
        self.cam_btn = ui_theme.create_button(controls_panel, "Stop Camera", kind="secondary", min_height=46, min_width=154)
        self.kick_btn = ui_theme.create_button(controls_panel, "Remove", kind="warning", min_height=46, min_width=132)
        self.leave_btn = ui_theme.create_button(controls_panel, "Leave", kind="danger", min_height=46, min_width=128)

        controls.Add(self.mic_btn, 0, wx.ALL, 8)
        controls.Add(self.cam_btn, 0, wx.ALL, 8)
        if self.is_host:
            controls.Add(self.kick_btn, 0, wx.ALL, 8)
        else:
            self.kick_btn.Hide()
        controls.AddStretchSpacer()
        controls.Add(self.leave_btn, 0, wx.ALL, 8)

        controls_panel.SetSizer(controls)
        main_sizer.Add(controls_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        self.panel.SetSizer(main_sizer)
        self._refresh_control_styles()

        self.leave_btn.Bind(wx.EVT_BUTTON, self.leave_call)
        self.mic_btn.Bind(wx.EVT_BUTTON, self.toggle_mic)
        self.cam_btn.Bind(wx.EVT_BUTTON, self.toggle_camera)
        self.kick_btn.Bind(wx.EVT_BUTTON, self.on_kick)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.copy_code_btn.Bind(wx.EVT_BUTTON, self.copy_meeting_code)

        self.video_panels[0].set_black()
        for i in range(1, 4):
            self.video_panels[i].clear_panel()

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_frames, self.timer)
        self.timer.Start(1000 // 24)

        threading.Thread(target=self._run_call, daemon=True).start()
        self.Center()

    def _refresh_control_styles(self):
        ui_theme.style_button(self.copy_code_btn, "secondary", min_height=40)
        ui_theme.style_button(self.mic_btn, "warning" if self.is_muted else "secondary", min_height=46, min_width=138)
        ui_theme.style_button(self.cam_btn, "warning" if self.is_camera_off else "secondary", min_height=46, min_width=154)
        if self.is_host:
            ui_theme.style_button(self.kick_btn, "warning", min_height=46, min_width=132)
        ui_theme.style_button(self.leave_btn, "danger", min_height=46, min_width=128)

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

        self.video_panels[0].set_label(
            self.username if self.username else "You",
            muted=self.is_muted,
        )

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
        connected_clients = self._get_connected_remote_clients()
        connected_set = set(connected_clients)
        panel_idx = 1
        now = time.monotonic()

        # Remove stale frame entries for clients that have left
        for stale_ip in [ip for ip in self.remote_frames if ip not in connected_set]:
            self.remote_frames.pop(stale_ip, None)
            self.remote_frame_times.pop(stale_ip, None)

        # Per-sender receive timestamps from the logic layer (updated only on real network frames)
        last_received = getattr(self.call_logic, "last_video_received_time", {})

        for client_ip in connected_clients:
            if panel_idx >= len(self.video_panels):
                break

            frame = self.remote_frames.get(client_ip)
            display_name = self._get_display_name_for_ip(client_ip)
            self.video_panels[panel_idx].set_label(
                display_name,
                muted=self._is_remote_muted(client_ip),
            )

            # Use the network-arrival time so a frozen cached frame doesn't fool the timeout
            last_network_time = last_received.get(client_ip, 0)
            camera_active = frame is not None and (now - last_network_time) <= self.VIDEO_TIMEOUT

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

    def _is_remote_muted(self, client_ip):
        if not hasattr(self.call_logic, "open_clients") or client_ip not in self.call_logic.open_clients:
            return False

        value = self.call_logic.open_clients[client_ip]

        if isinstance(value, dict):
            for key in ("muted", "is_muted", "mic_muted"):
                if key in value:
                    return bool(value[key])

        if isinstance(value, list) and len(value) >= 4 and isinstance(value[3], bool):
            return value[3]

        return False

    def toggle_mic(self, event):
        """
        Toggle microphone.
        """
        try:
            if not hasattr(self.call_logic, "mic"):
                return

            if self.is_muted:
                self.call_logic.mic.unmute()
                self.mic_btn.SetLabel("Mute Mic")
                self.is_muted = False
            else:
                self.call_logic.mic.mute()
                self.mic_btn.SetLabel("Unmute Mic")
                self.is_muted = True
            self._refresh_control_styles()
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
                self.cam_btn.SetLabel("Stop Camera")
                self.is_camera_off = False
            else:
                self.call_logic.camera.stop()
                self.cam_btn.SetLabel("Start Camera")
                self.is_camera_off = True
                self.last_self_frame = None
                self.video_panels[0].set_black()
            self._refresh_control_styles()
        except Exception as e:
            print("toggle camera error:", e)

    def on_kick(self, event):
        """
        Show a dialog listing connected guests and kick the selected one.
        Only available for the host.
        """
        if not self.is_host:
            return

        # Build list of connected guests (exclude self)
        guests = self._get_connected_remote_clients()
        if not guests:
            wx.MessageBox("No guests to kick.", "Kick", wx.OK | wx.ICON_INFORMATION)
            return

        # Build display names for the dialog
        display_names = []
        ip_list = []
        for ip in guests:
            name = self._get_display_name_for_ip(ip)
            display_names.append(f"{name} ({ip})")
            ip_list.append(ip)

        dlg = wx.SingleChoiceDialog(
            self,
            "Select a guest to kick:",
            "Kick Guest",
            display_names
        )

        if dlg.ShowModal() == wx.ID_OK:
            selected_idx = dlg.GetSelection()
            selected_ip = ip_list[selected_idx]
            selected_name = display_names[selected_idx]

            # Confirm
            confirm = wx.MessageBox(
                f"Kick {selected_name} from the meeting?",
                "Confirm Kick",
                wx.YES_NO | wx.ICON_QUESTION
            )
            if confirm == wx.YES:
                threading.Thread(
                    target=self.call_logic.kick_client,
                    args=(selected_ip,),
                    daemon=True
                ).start()

        dlg.Destroy()

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

        self._stop_local_media()

        # Release UDP port 5000 immediately so a rejoin can bind it
        try:
            if hasattr(self.call_logic, "video_comm"):
                self.call_logic.video_comm.close()
        except Exception as e:
            print("video_comm early close error:", e)

        # Restore home screen immediately — don't wait for network teardown.
        # Keep client.role set until meeting close() finishes so late server messages (e.g. fd) still dispatch.
        home = self.home_frame
        client = home.client if home else None
        try:
            if home:
                home.Show()
            self.Destroy()
        except Exception as e:
            print("destroy error:", e)

        call_logic = self.call_logic

        def _do_close():
            try:
                if hasattr(call_logic, "cleanup"):
                    call_logic.cleanup()
                elif hasattr(call_logic, "close"):
                    call_logic.close()
            except Exception as e:
                print("close error:", e)
            finally:

                def _after_teardown():
                    if client is not None:
                        if client.role is call_logic:
                            client.role = None
                            client.meeting_code = None
                    if home is not None:
                        home._enable_buttons()

                wx.CallAfter(_after_teardown)

        threading.Thread(target=_do_close, daemon=True).start()

    def _stop_local_media(self):
        try:
            if hasattr(self.call_logic, "camera"):
                self.call_logic.camera.stop(pause_only=False)
        except Exception as e:
            print("camera early stop error:", e)

        try:
            if hasattr(self.call_logic, "mic"):
                self.call_logic.mic.stop()
        except Exception as e:
            print("mic early stop error:", e)

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
