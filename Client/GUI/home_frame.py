import time
import threading
import wx

from Client.GUI.call_frame import CallFrame
from Client.GUI import ui_theme


class HomeFrame(wx.Frame):
    def __init__(self, client):
        super().__init__(None, title="Face2Face", size=wx.Size(1120, 720))
        self.client = client
        self._pending_previous_role = None

        self.SetMinSize(wx.Size(1120, 720))
        self._build_ui()

        self.start_btn.Bind(wx.EVT_BUTTON, self.start_meeting)
        self.join_btn.Bind(wx.EVT_BUTTON, self.join_meeting)
        self.logout_btn.Bind(wx.EVT_BUTTON, self.on_logout_server)
        self.code_box.Bind(wx.EVT_TEXT_ENTER, self.join_meeting)

        self.Center()

    def _build_ui(self):
        panel = wx.Panel(self)
        ui_theme.style_window(self, ui_theme.PALETTE["app_bg"])
        ui_theme.style_window(panel, ui_theme.PALETTE["app_bg"])
        # Top-level vertical sizer for the entire home screen
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        header = wx.Panel(panel)
        ui_theme.style_window(header, ui_theme.PALETTE["surface"])
        # Horizontal sizer for branding (left) and log out (right)
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        # Vertical stack for the "Face2Face" name and user greeting
        brand_wrap = wx.BoxSizer(wx.VERTICAL)

        brand = wx.StaticText(header, label="Face2Face")
        ui_theme.style_text(brand, ui_theme.PALETTE["primary"], size_delta=2, bold=True)

        greeting = wx.StaticText(header, label=f"Welcome, {self.client.username}")
        ui_theme.style_text(greeting, ui_theme.PALETTE["text"], size_delta=10, bold=True)

        subtitle = wx.StaticText(header, label="Start or join a meeting.")
        ui_theme.style_text(subtitle, ui_theme.PALETTE["text_muted"], size_delta=1)

        brand_wrap.Add(brand, 0, wx.BOTTOM, 4)
        brand_wrap.Add(greeting, 0, wx.BOTTOM, 4)
        brand_wrap.Add(subtitle, 0)

        self.logout_btn = ui_theme.create_button(
            header,
            "Log Out",
            kind="ghost",
            min_height=42,
            min_width=120
        )

        header_sizer.Add(brand_wrap, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 24)
        header_sizer.Add(self.logout_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 24)

        header.SetSizer(header_sizer)
        # Container for the central content cards
        content = wx.BoxSizer(wx.VERTICAL)
        # Horizontal sizer to put "Create" and "Join" cards side-by-side
        card_row = wx.BoxSizer(wx.HORIZONTAL)
        # "New Meeting" card layout
        create_card = wx.Panel(panel)
        ui_theme.style_window(create_card, ui_theme.PALETTE["surface"])

        create_sizer = wx.BoxSizer(wx.VERTICAL)
        card_margin = 28

        create_eyebrow = wx.StaticText(create_card, label="NEW ROOM")
        create_title = wx.StaticText(create_card, label="Create a meeting")
        create_body = wx.StaticText(create_card, label="Open a room and share the code.")

        ui_theme.style_text(create_eyebrow, ui_theme.PALETTE["primary"], size_delta=1, bold=True)
        ui_theme.style_text(create_title, ui_theme.PALETTE["text"], size_delta=8, bold=True)
        ui_theme.style_text(create_body, ui_theme.PALETTE["text_muted"], size_delta=1)

        self.start_btn = ui_theme.create_button(
            create_card,
            "New Meeting",
            kind="primary",
            min_height=50,
            min_width=260
        )

        create_sizer.Add(create_eyebrow, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, card_margin)
        create_sizer.Add(create_title, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, card_margin)
        create_sizer.Add(create_body, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, card_margin)
        create_sizer.AddStretchSpacer()
        create_sizer.Add(self.start_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, card_margin)
        create_card.SetSizer(create_sizer)
        # "Join Meeting" card layout
        join_card = wx.Panel(panel)
        ui_theme.style_window(join_card, ui_theme.PALETTE["surface"])
        join_sizer = wx.BoxSizer(wx.VERTICAL)
        join_inner = wx.BoxSizer(wx.VERTICAL)
        join_eyebrow = wx.StaticText(join_card, label="JOIN ROOM")
        join_title = wx.StaticText(join_card, label="Join a meeting")
        join_label = wx.StaticText(join_card, label="Meeting code")
        ui_theme.style_text(join_eyebrow, ui_theme.PALETTE["primary"], size_delta=1, bold=True)
        ui_theme.style_text(join_title, ui_theme.PALETTE["text"], size_delta=8, bold=True)
        ui_theme.style_text(join_label, ui_theme.PALETTE["text"], bold=True)
        self.code_box = wx.TextCtrl(join_card, style=wx.TE_PROCESS_ENTER)
        ui_theme.style_text_input(self.code_box, "Enter code")
        self.code_box.SetMinSize(wx.Size(-1, 42))
        self.join_btn = ui_theme.create_button(
            join_card,
            "Join Meeting",
            kind="secondary",
            min_height=50,
            min_width=260
        )
        join_inner.Add(join_eyebrow, 0, wx.BOTTOM, 28)
        join_inner.Add(join_title, 0, wx.BOTTOM, 28)
        join_inner.Add(join_label, 0, wx.BOTTOM, 8)
        join_inner.Add(self.code_box, 0, wx.EXPAND | wx.BOTTOM, 16)
        join_inner.AddStretchSpacer()
        join_inner.Add(self.join_btn, 0, wx.EXPAND)
        join_sizer.Add(join_inner, 1, wx.EXPAND | wx.ALL, card_margin)
        join_card.SetSizer(join_sizer)
        # "Tips" card layout
        tips_card = wx.Panel(panel)
        ui_theme.style_window(tips_card, ui_theme.PALETTE["surface"])

        tips_sizer = wx.BoxSizer(wx.VERTICAL)

        tips_title = wx.StaticText(tips_card, label="Tip")
        tips_body = wx.StaticText(tips_card, label="Keep the meeting code nearby before joining.")

        ui_theme.style_text(tips_title, ui_theme.PALETTE["text"], size_delta=4, bold=True)
        ui_theme.style_text(tips_body, ui_theme.PALETTE["text_muted"], size_delta=1)

        tips_sizer.Add(tips_title, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, 24)
        tips_sizer.Add(tips_body, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)

        tips_card.SetSizer(tips_sizer)

        card_row.Add(create_card, 1, wx.RIGHT | wx.EXPAND, 12)
        card_row.Add(join_card, 1, wx.LEFT | wx.EXPAND, 12)

        content.Add(card_row, 1, wx.EXPAND | wx.BOTTOM, 24)
        content.Add(tips_card, 0, wx.EXPAND)

        main_sizer.Add(header, 0, wx.EXPAND | wx.ALL, 24)
        main_sizer.Add(content, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 24)

        panel.SetSizer(main_sizer)

    def _disable_buttons(self):
        self.start_btn.Disable()
        self.join_btn.Disable()
        self.logout_btn.Disable()
        self.code_box.Disable()

    def _enable_buttons(self):
        self.start_btn.Enable()
        self.join_btn.Enable()
        self.logout_btn.Enable()
        self.code_box.Enable()

    def on_logout_server(self, event):
        from Client.GUI.auth_frame import AuthFrame

        self._disable_buttons()
        self.logout_btn.Disable()

        try:
            self.client.disconnect_from_server()
        except Exception as e:
            wx.MessageBox(str(e), "Disconnect failed", wx.OK | wx.ICON_ERROR)
            self._enable_buttons()
            return

        self.Hide()
        auth = AuthFrame(self.client)
        auth.Show()

    def start_meeting(self, event):
        self._disable_buttons()
        self._pending_previous_role = self.client.role
        self.client.start_meeting()
        wx.CallLater(500, self._open_call_frame)

    def join_meeting(self, event):
        code = self.code_box.GetValue().strip()

        if code:
            if code.isascii():
                self._disable_buttons()
                self._pending_previous_role = self.client.role
                self.client.request_join_meeting(code)
                wx.CallLater(500, self._open_call_frame)
            else:
                wx.MessageBox(
                    "Meeting code must contain only English letters and numbers.",
                    "Invalid Code",
                    wx.OK | wx.ICON_WARNING
                )
        else:
            wx.MessageBox("Enter meeting code")

    def _open_call_frame(self):
        def _wait_for_role():
            deadline = time.time() + 10.0

            while time.time() < deadline:
                role = self.client.role

                if role is not None and role is not self._pending_previous_role:
                    break

                if getattr(self.client, "last_error", None):
                    break

                time.sleep(0.02)

            wx.CallAfter(self._create_call_frame)

        threading.Thread(target=_wait_for_role, daemon=True).start()

    def _create_call_frame(self):
        if self.client.role and self.client.role is not self._pending_previous_role:
            call = CallFrame(
                self.client.role,
                home_frame=self,
                username=self.client.username
            )

            call.Show()
            self.Hide()
        else:
            detail = getattr(self.client, "last_error", None) or ""
            msg = "Could not join the meeting.\nCheck the code and try again."

            if detail:
                msg = f"{msg}\n\nServer: {detail}"

            wx.MessageBox(
                msg,
                "Connection Failed",
                wx.OK | wx.ICON_ERROR
            )

            self._enable_buttons()

        self._pending_previous_role = None