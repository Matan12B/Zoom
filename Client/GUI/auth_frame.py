import time

import wx
import wx.adv

from Client.GUI.home_frame import HomeFrame
from Client.GUI import ui_theme


class _BaseAuthFrame(wx.Frame):
    def __init__(self, client, title_suffix, heading, helper_text, submit_label):
        super().__init__(None, title=f"Python Zoom - {title_suffix}", size=wx.Size(1080, 700))

        self.client = client
        self.heading = heading
        self.helper_text_value = helper_text
        self.submit_label = submit_label
        self._auth_wait_deadline = 0.0

        self.SetMinSize(wx.Size(980, 640))
        self._build_ui()
        self._bind_common_events()
        self.Center()

    def _build_ui(self):
        root = wx.Panel(self)
        ui_theme.style_window(self, ui_theme.PALETTE["app_bg"])
        ui_theme.style_window(root, ui_theme.PALETTE["app_bg"])

        outer = wx.BoxSizer(wx.HORIZONTAL)

        brand_panel = wx.Panel(root, size=wx.Size(340, -1))
        ui_theme.style_window(brand_panel, ui_theme.PALETTE["sidebar"], ui_theme.PALETTE["text_inverted"])
        brand_sizer = wx.BoxSizer(wx.VERTICAL)

        badge = wx.StaticText(brand_panel, label="PYTHON ZOOM")
        ui_theme.style_text(badge, ui_theme.PALETTE["surface_alt"], size_delta=6, bold=True)

        title = wx.StaticText(brand_panel, label="Meet, join, and share\nwithout the hassle.")
        ui_theme.style_text(title, ui_theme.PALETTE["text_inverted"], size_delta=8, bold=True)

        copy = wx.StaticText(
            brand_panel,
            label=(
                "Sign in to start a meeting in seconds, join with a room code, "
                "and stay connected from one simple desktop workspace."
            )
        )
        ui_theme.style_text(copy, ui_theme.PALETTE["surface_alt"], size_delta=1)
        copy.Wrap(290)

        highlights_title = wx.StaticText(brand_panel, label="Why use it")
        ui_theme.style_text(highlights_title, ui_theme.PALETTE["text_inverted"], size_delta=3, bold=True)

        highlights = [
            "Start your own room and share the meeting code instantly",
            "Join another meeting quickly with a single invite code",
            "Keep video, audio, and account access in one focused app",
        ]

        brand_sizer.AddSpacer(60)
        brand_sizer.Add(badge, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 34)
        brand_sizer.Add(title, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)
        brand_sizer.Add(copy, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 34)
        brand_sizer.Add(highlights_title, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 18)

        for line in highlights:
            item = wx.StaticText(brand_panel, label=line)
            ui_theme.style_text(item, ui_theme.PALETTE["surface_alt"], size_delta=1)
            item.Wrap(290)
            brand_sizer.Add(item, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 22)

        brand_panel.SetSizer(brand_sizer)

        content_wrap = wx.BoxSizer(wx.VERTICAL)
        content_wrap.AddStretchSpacer()

        shell = wx.Panel(root)
        ui_theme.style_window(shell, ui_theme.PALETTE["app_bg"])
        shell_sizer = wx.BoxSizer(wx.VERTICAL)

        mini_badge = wx.StaticText(shell, label="SECURE ACCESS")
        ui_theme.style_text(mini_badge, ui_theme.PALETTE["primary"], size_delta=1, bold=True)

        shell_title = wx.StaticText(shell, label=self.heading)
        ui_theme.style_text(shell_title, ui_theme.PALETTE["text"], size_delta=11, bold=True)

        shell_copy = wx.StaticText(shell, label=self.helper_text_value)
        ui_theme.style_text(shell_copy, ui_theme.PALETTE["text_muted"], size_delta=1)
        shell_copy.Wrap(450)

        auth_card = wx.Panel(shell)
        ui_theme.style_window(auth_card, ui_theme.PALETTE["surface"])
        auth_card.SetMinSize(wx.Size(480, -1))
        auth_card.SetMaxSize(wx.Size(480, -1))
        auth_sizer = wx.BoxSizer(wx.VERTICAL)
        field_margin = 28

        username_label = wx.StaticText(auth_card, label="Username")
        password_label = wx.StaticText(auth_card, label="Password")
        ui_theme.style_text(username_label, ui_theme.PALETTE["text"], bold=True)
        ui_theme.style_text(password_label, ui_theme.PALETTE["text"], bold=True)

        self.username_box = wx.TextCtrl(auth_card, style=wx.TE_PROCESS_ENTER)
        self.password_box = wx.TextCtrl(auth_card, style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER)
        ui_theme.style_text_input(self.username_box, "Enter your username")
        ui_theme.style_text_input(self.password_box, "Enter your password")

        self.submit_btn = ui_theme.create_button(
            auth_card,
            self.submit_label,
            kind="primary",
            min_height=48,
        )

        self.status_panel = wx.Panel(auth_card)
        self.status_text = wx.StaticText(self.status_panel, label="")
        status_sizer = wx.BoxSizer(wx.VERTICAL)
        status_sizer.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 12)
        self.status_panel.SetSizer(status_sizer)

        footer_hint = wx.StaticText(
            auth_card,
            label="Usernames can be up to 15 characters. Passwords can be up to 10 characters."
        )
        ui_theme.style_text(footer_hint, ui_theme.PALETTE["text_muted"])
        footer_hint.Wrap(420)

        field_sizer = wx.BoxSizer(wx.VERTICAL)
        field_sizer.Add(username_label, 0, wx.BOTTOM, 6)
        field_sizer.Add(self.username_box, 0, wx.EXPAND | wx.BOTTOM, 14)
        field_sizer.Add(password_label, 0, wx.BOTTOM, 6)
        field_sizer.Add(self.password_box, 0, wx.EXPAND | wx.BOTTOM, 18)

        auth_sizer.Add(field_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, field_margin)
        self._add_extra_fields(auth_card, auth_sizer)
        auth_sizer.Add(self.submit_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, field_margin)
        auth_sizer.Add(self.status_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, field_margin)
        auth_sizer.Add(footer_hint, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, field_margin)
        self._add_footer_actions(auth_card, auth_sizer)
        auth_card.SetSizer(auth_sizer)

        shell_sizer.Add(mini_badge, 0, wx.BOTTOM, 10)
        shell_sizer.Add(shell_title, 0, wx.BOTTOM, 8)
        shell_sizer.Add(shell_copy, 0, wx.BOTTOM, 28)
        shell_sizer.Add(auth_card, 0, wx.ALIGN_LEFT)
        shell.SetSizer(shell_sizer)

        content_wrap.Add(shell, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 40)
        content_wrap.AddStretchSpacer()

        outer.Add(brand_panel, 0, wx.EXPAND | wx.ALL, 26)
        outer.Add(content_wrap, 1, wx.EXPAND | wx.TOP | wx.BOTTOM | wx.RIGHT, 26)
        root.SetSizer(outer)

        self._set_status("Enter your details to continue.", "neutral")

    def _bind_common_events(self):
        self.submit_btn.Bind(wx.EVT_BUTTON, self.on_submit)
        self.password_box.Bind(wx.EVT_TEXT_ENTER, self.on_submit)
        self.username_box.Bind(wx.EVT_TEXT_ENTER, self.on_submit)

    def _add_extra_fields(self, auth_card, auth_sizer):
        return

    def _add_footer_actions(self, auth_card, auth_sizer):
        return

    def _set_status(self, message, tone="neutral"):
        self.status_text.SetLabel(message)
        self.status_text.Wrap(420)
        ui_theme.style_status_panel(self.status_panel, self.status_text, tone)

    def _set_auth_controls_enabled(self, enabled):
        if enabled:
            self.submit_btn.Enable()
            self.username_box.Enable()
            self.password_box.Enable()
        else:
            self.submit_btn.Disable()
            self.username_box.Disable()
            self.password_box.Disable()

    def validate_fields(self):
        username = self.username_box.GetValue().strip()
        password = self.password_box.GetValue().strip()

        if not username or not password:
            self._set_status("Username and password are required.", "error")
            return None, None

        if len(username) > 15:
            self._set_status("Username must be up to 15 characters.", "error")
            return None, None

        if len(password) > 10:
            self._set_status("Password must be up to 10 characters.", "error")
            return None, None

        return username, password

    def open_home(self):
        home = HomeFrame(self.client)
        home.Show()
        self.Hide()


class AuthFrame(_BaseAuthFrame):
    def __init__(self, client):
        self.signup_frame = None
        super().__init__(
            client=client,
            title_suffix="Log In",
            heading="Welcome back",
            helper_text="Log in first, then head into a cleaner create or join meeting dashboard.",
            submit_label="Log In",
        )

    def _add_footer_actions(self, auth_card, auth_sizer):
        footer_row = wx.BoxSizer(wx.HORIZONTAL)
        prompt = wx.StaticText(auth_card, label="Don't have an account yet?")
        ui_theme.style_text(prompt, ui_theme.PALETTE["text_muted"])

        self.signup_link = ui_theme.create_link(auth_card, "Create one")
        self.signup_link.Bind(wx.adv.EVT_HYPERLINK, self.open_signup)

        footer_row.Add(prompt, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        footer_row.Add(self.signup_link, 0, wx.ALIGN_CENTER_VERTICAL)
        auth_sizer.Add(footer_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 30)

    def _set_auth_controls_enabled(self, enabled):
        super()._set_auth_controls_enabled(enabled)
        if enabled:
            self.signup_link.Enable()
        else:
            self.signup_link.Disable()

    def open_signup(self, event):
        if self.signup_frame and not self.signup_frame.IsBeingDeleted():
            self.signup_frame.Raise()
            return

        self.signup_frame = SignupFrame(self.client, login_frame=self)
        self.signup_frame.Show()
        self.Hide()

    def on_submit(self, event):
        username, password = self.validate_fields()
        if username is None:
            return

        if not self.client.wait_signaling(15.0):
            err = getattr(self.client.comm, "error", "") or "timeout"
            self._set_status(f"Signaling server unavailable ({err}).", "error")
            return

        self._set_auth_controls_enabled(False)
        self._auth_wait_deadline = time.time() + 30.0
        self._set_status("Checking your login details...", "neutral")
        self.client.log_in(username, password)
        wx.CallLater(300, self.check_login_result)

    def check_login_result(self):
        if self.client.active is None:
            if time.time() > self._auth_wait_deadline:
                self._set_status("No response from server. Check the connection and try again.", "error")
                self._set_auth_controls_enabled(True)
                return
            wx.CallLater(200, self.check_login_result)
            return

        if self.client.active == "1":
            self._set_status("Login successful. Opening your dashboard...", "success")
            wx.CallLater(500, self.open_home)
        else:
            self._set_status("Login failed. Check your username or password and try again.", "error")
            self._set_auth_controls_enabled(True)


class SignupFrame(_BaseAuthFrame):
    def __init__(self, client, login_frame=None):
        self.login_frame = login_frame
        super().__init__(
            client=client,
            title_suffix="Sign Up",
            heading="Create your account",
            helper_text="Set up your account in a dedicated signup window, then go straight into the meeting dashboard.",
            submit_label="Create Account",
        )
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def _add_footer_actions(self, auth_card, auth_sizer):
        footer_row = wx.BoxSizer(wx.HORIZONTAL)
        prompt = wx.StaticText(auth_card, label="Already have an account?")
        ui_theme.style_text(prompt, ui_theme.PALETTE["text_muted"])

        self.back_link = ui_theme.create_link(auth_card, "Back to login")
        self.back_link.Bind(wx.adv.EVT_HYPERLINK, self.back_to_login)

        footer_row.Add(prompt, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        footer_row.Add(self.back_link, 0, wx.ALIGN_CENTER_VERTICAL)
        auth_sizer.Add(footer_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 30)

    def _set_auth_controls_enabled(self, enabled):
        super()._set_auth_controls_enabled(enabled)
        if enabled:
            self.back_link.Enable()
        else:
            self.back_link.Disable()

    def back_to_login(self, event=None):
        if self.login_frame and not self.login_frame.IsBeingDeleted():
            self.login_frame.signup_frame = None
            self.login_frame.Show()
            self.login_frame.Raise()
        self.Unbind(wx.EVT_CLOSE)
        self.Destroy()

    def on_close(self, event):
        event.Veto(False)
        self.back_to_login()

    def _release_login_frame(self):
        if self.login_frame and not self.login_frame.IsBeingDeleted():
            self.login_frame.signup_frame = None
            self.login_frame.Destroy()
        self.login_frame = None

    def on_submit(self, event):
        username, password = self.validate_fields()
        if username is None:
            return

        if not self.client.wait_signaling(15.0):
            err = getattr(self.client.comm, "error", "") or "timeout"
            self._set_status(f"Signaling server unavailable ({err}).", "error")
            return

        self._set_auth_controls_enabled(False)
        self._auth_wait_deadline = time.time() + 30.0
        self._set_status("Creating your account...", "neutral")
        self.client.sign_up(username, password)
        wx.CallLater(300, self.check_signup_result)

    def check_signup_result(self):
        if self.client.active is None:
            if time.time() > self._auth_wait_deadline:
                self._set_status("No response from server. Check the connection and try again.", "error")
                self._set_auth_controls_enabled(True)
                return
            wx.CallLater(200, self.check_signup_result)
            return

        if self.client.active == "1":
            self._set_status("Account created. Opening your dashboard...", "success")
            self._release_login_frame()
            wx.CallLater(500, self.open_home)
        else:
            self._set_status("Sign up failed. That username is already taken.", "error")
            self._set_auth_controls_enabled(True)
