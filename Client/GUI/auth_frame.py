
import wx
from home_frame import HomeFrame


class AuthFrame(wx.Frame):
    def __init__(self, client):
        super().__init__(None, title="Python Zoom - Login / Sign Up", size=wx.Size(420, 400))

        self.client = client
        self.mode = "login"

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(panel, label="Python Zoom")
        title_font = title.GetFont()
        title_font.PointSize += 10
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)

        # mode buttons
        mode_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.login_mode_btn = wx.Button(panel, label="Login")
        self.signup_mode_btn = wx.Button(panel, label="Sign Up")
        mode_sizer.Add(self.login_mode_btn, 1, wx.RIGHT, 5)
        mode_sizer.Add(self.signup_mode_btn, 1, wx.LEFT, 5)

        # form
        self.username_box = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.password_box = wx.TextCtrl(
            panel,
            style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER
        )

        self.submit_btn = wx.Button(panel, label="Login")
        self.status_text = wx.StaticText(panel, label="Choose Login or Sign Up")

        main_sizer.Add(title, 0, wx.ALL | wx.CENTER, 20)
        main_sizer.Add(mode_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        main_sizer.Add(wx.StaticText(panel, label="Username"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 15)
        main_sizer.Add(self.username_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        main_sizer.Add(wx.StaticText(panel, label="Password"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 15)
        main_sizer.Add(self.password_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)

        main_sizer.Add(self.submit_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 15)
        main_sizer.Add(self.status_text, 0, wx.ALL | wx.LEFT, 15)

        panel.SetSizer(main_sizer)

        self.login_mode_btn.Bind(wx.EVT_BUTTON, self.set_login_mode)
        self.signup_mode_btn.Bind(wx.EVT_BUTTON, self.set_signup_mode)
        self.submit_btn.Bind(wx.EVT_BUTTON, self.on_submit)

        self.password_box.Bind(wx.EVT_TEXT_ENTER, self.on_submit)
        self.username_box.Bind(wx.EVT_TEXT_ENTER, self.on_submit)

        self.set_login_mode()
        self.Center()

    def set_login_mode(self, event=None):
        """
        Set frame to login mode.
        :param event:
        :return:
        """
        self.mode = "login"
        self.submit_btn.SetLabel("Login")
        self.status_text.SetLabel("Mode: Login")

    def set_signup_mode(self, event=None):
        """
        Set frame to sign up mode.
        :param event:
        :return:
        """
        self.mode = "signup"
        self.submit_btn.SetLabel("Sign Up")
        self.status_text.SetLabel("Mode: Sign Up")

    def validate_fields(self):
        """
        Validate username and password.
        :return:
        """
        username = self.username_box.GetValue().strip()
        password = self.password_box.GetValue().strip()

        if not username or not password:
            self.status_text.SetLabel("Username and password are required")
            return None, None

        if len(username) > 15:
            self.status_text.SetLabel("Username must be up to 15 characters")
            return None, None

        if len(password) > 10:
            self.status_text.SetLabel("Password must be up to 10 characters")
            return None, None

        return username, password

    def on_submit(self, event):
        """
        Submit according to current mode.
        :param event:
        :return:
        """
        username, password = self.validate_fields()
        if username is None:
            return

        if self.mode == "login":
            self.status_text.SetLabel("Checking login...")
            self.client.log_in(username, password)
            wx.CallLater(300, self.check_login_result)
        else:
            self.status_text.SetLabel("Creating account...")
            self.client.sign_up(username, password)
            wx.CallLater(300, self.check_signup_result)

    def check_login_result(self):
        """
        Check login result from server.
        :return:
        """
        if self.client.active is None:
            wx.CallLater(200, self.check_login_result)
            return

        if self.client.active == "1":
            self.status_text.SetLabel("Login successful!")
            wx.CallLater(500, self.open_home)
        else:
            self.status_text.SetLabel("Login failed: incorrect username or password")

    def check_signup_result(self):
        """
        Check signup result from server.
        :return:
        """
        if self.client.active is None:
            wx.CallLater(200, self.check_signup_result)
            return

        if self.client.active == "1":
            self.status_text.SetLabel("Account created! Logging in...")
            wx.CallLater(500, self.open_home)
        else:
            self.status_text.SetLabel("Sign up failed: username already taken")

    def open_home(self):
        """
        Open home frame after success.
        :return:
        """
        home = HomeFrame(self.client)
        home.Show()
        self.Hide()