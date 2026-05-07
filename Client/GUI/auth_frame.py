import time

import wx
import wx.adv

from Client.GUI.home_frame import HomeFrame
from Client.GUI import ui_theme

import time
import wx
import wx.adv
from Client.GUI.home_frame import HomeFrame
from Client.GUI import ui_theme


class _BaseAuthFrame(wx.Frame):
    def __init__(self, client, title_suffix, submit_label):
        super().__init__(None, title=f"Face2Face - {title_suffix}", size=wx.Size(540, 480),
                         style=wx.DEFAULT_FRAME_STYLE & ~wx.RESIZE_BORDER & ~wx.MAXIMIZE_BOX)
        self.client = client
        self.submit_label = submit_label
        self._auth_wait_deadline = 0.0
        self._build_ui()
        self._bind_common_events()
        self.Center()

    def _build_ui(self):
        root = wx.Panel(self)
        ui_theme.style_window(self, ui_theme.PALETTE["app_bg"])
        ui_theme.style_window(root, ui_theme.PALETTE["app_bg"])

        # Main vertical sizer that centers the auth card on the screen
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.AddStretchSpacer()  # Push content to center

        title = wx.StaticText(root, label="Face2Face")
        ui_theme.style_text(title, ui_theme.PALETTE["primary"], size_delta=14, bold=True)
        outer.Add(title, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 18)

        # White "card" panel to hold input fields
        auth_card = wx.Panel(root)
        ui_theme.style_window(auth_card, ui_theme.PALETTE["surface"])
        auth_card.SetMinSize(wx.Size(420, -1))
        auth_card.SetMaxSize(wx.Size(420, -1))

        # Vertical sizer for everything inside the white card
        auth_sizer = wx.BoxSizer(wx.VERTICAL)
        margin = 24

        username_label = wx.StaticText(auth_card, label="Username")
        password_label = wx.StaticText(auth_card, label="Password")
        ui_theme.style_text(username_label, ui_theme.PALETTE["text"], bold=True)
        ui_theme.style_text(password_label, ui_theme.PALETTE["text"], bold=True)

        self.username_box = wx.TextCtrl(auth_card, style=wx.TE_PROCESS_ENTER)
        self.password_box = wx.TextCtrl(auth_card, style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER)
        ui_theme.style_text_input(self.username_box, "Username")
        ui_theme.style_text_input(self.password_box, "Password")

        self.submit_btn = ui_theme.create_button(auth_card, self.submit_label, kind="primary", min_height=48)

        self.status_panel = wx.Panel(auth_card)
        self.status_text = wx.StaticText(self.status_panel, label="")

        # Sizer for the status message to give it internal padding
        status_sizer = wx.BoxSizer(wx.VERTICAL)
        status_sizer.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 10)
        self.status_panel.SetSizer(status_sizer)

        # Groups the text inputs and their labels vertically
        fields = wx.BoxSizer(wx.VERTICAL)
        fields.Add(username_label, 0, wx.BOTTOM, 6)
        fields.Add(self.username_box, 0, wx.EXPAND | wx.BOTTOM, 14)
        fields.Add(password_label, 0, wx.BOTTOM, 6)
        fields.Add(self.password_box, 0, wx.EXPAND | wx.BOTTOM, 18)

        # Combine all parts into the main card sizer
        auth_sizer.Add(fields, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, margin)
        self._add_extra_fields(auth_card, auth_sizer)
        auth_sizer.Add(self.submit_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, margin)
        auth_sizer.Add(self.status_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, margin)
        self._add_footer_actions(auth_card, auth_sizer)
        auth_card.SetSizer(auth_sizer)

        outer.Add(auth_card, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT, 40)
        outer.AddStretchSpacer()  # Push content to center
        root.SetSizer(outer)
        self._set_status("Welcome to Face2Face.", "neutral")

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
        self.status_text.Wrap(360)
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
        result = (username, password)

        if not username or not password:
            self._set_status("Username and password are required.", "error")
            result = (None, None)
        elif not username.isascii() or not password.isascii():
            self._set_status("Use English letters, numbers, or symbols only.", "error")
            result = (None, None)
        elif len(username) > 15:
            self._set_status("Username must be up to 15 characters.", "error")
            result = (None, None)
        elif len(password) > 10:
            self._set_status("Password must be up to 10 characters.", "error")
            result = (None, None)

        return result

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
            submit_label="Log In",
        )

    def _add_footer_actions(self, auth_card, auth_sizer):
        footer_row = wx.BoxSizer(wx.HORIZONTAL)

        prompt = wx.StaticText(auth_card, label="New here?")
        ui_theme.style_text(prompt, ui_theme.PALETTE["call_ctrl_text"])

        self.signup_link = ui_theme.create_link(auth_card, "Create account")
        self.signup_link.Bind(wx.adv.EVT_HYPERLINK, self.open_signup)

        footer_row.Add(prompt, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        footer_row.Add(self.signup_link, 0, wx.ALIGN_CENTER_VERTICAL)

        auth_sizer.Add(footer_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)

    def _set_auth_controls_enabled(self, enabled):
        super()._set_auth_controls_enabled(enabled)
        if enabled:
            self.signup_link.Enable()
        else:
            self.signup_link.Disable()

    def open_signup(self, event):
        if self.signup_frame and not self.signup_frame.IsBeingDeleted():
            self.signup_frame.Raise()
        else:
            self.signup_frame = SignupFrame(self.client, login_frame=self)
            self.signup_frame.Show()
            self.Hide()

    def on_submit(self, event):
        username, password = self.validate_fields()

        if username is None:
            pass
        elif not self.client.wait_signaling(15.0):
            err = getattr(self.client.comm, "error", "") or "timeout"
            self._set_status(f"Server unavailable ({err}).", "error")
        else:
            self._set_auth_controls_enabled(False)
            self._auth_wait_deadline = time.time() + 30.0
            self._set_status("Signing you in...", "neutral")
            self.client.log_in(username, password)
            wx.CallLater(300, self.check_login_result)

    def check_login_result(self):
        if self.client.active is None:
            if time.time() > self._auth_wait_deadline:
                self._set_status("No response from server. Try again.", "error")
                self._set_auth_controls_enabled(True)
            else:
                wx.CallLater(200, self.check_login_result)
        elif self.client.active == "1":
            self._set_status("Login successful.", "success")
            wx.CallLater(500, self.open_home)
        else:
            self._set_status("Login failed. Check your details.", "error")
            self._set_auth_controls_enabled(True)


class SignupFrame(_BaseAuthFrame):
    def __init__(self, client, login_frame=None):
        self.login_frame = login_frame
        super().__init__(
            client=client,
            title_suffix="Sign Up",
            submit_label="Create Account",
        )
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def _add_footer_actions(self, auth_card, auth_sizer):
        footer_row = wx.BoxSizer(wx.HORIZONTAL)

        prompt = wx.StaticText(auth_card, label="Already registered?")
        ui_theme.style_text(prompt, ui_theme.PALETTE["call_ctrl_text"])

        self.back_link = ui_theme.create_link(auth_card, "Log in")
        self.back_link.Bind(wx.adv.EVT_HYPERLINK, self.back_to_login)

        footer_row.Add(prompt, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 6)
        footer_row.Add(self.back_link, 0, wx.ALIGN_CENTER_VERTICAL)

        auth_sizer.Add(footer_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)

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
            pass
        elif not self.client.wait_signaling(15.0):
            err = getattr(self.client.comm, "error", "") or "timeout"
            self._set_status(f"Server unavailable ({err}).", "error")
        else:
            self._set_auth_controls_enabled(False)
            self._auth_wait_deadline = time.time() + 30.0
            self._set_status("Creating account...", "neutral")
            self.client.sign_up(username, password)
            wx.CallLater(300, self.check_signup_result)

    def check_signup_result(self):
        if self.client.active is None:
            if time.time() > self._auth_wait_deadline:
                self._set_status("No response from server. Try again.", "error")
                self._set_auth_controls_enabled(True)
            else:
                wx.CallLater(200, self.check_signup_result)
        elif self.client.active == "1":
            self._set_status("Account created.", "success")
            self._release_login_frame()
            wx.CallLater(500, self.open_home)
        else:
            self._set_status("That username is already taken.", "error")
            self._set_auth_controls_enabled(True)