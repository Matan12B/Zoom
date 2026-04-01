import time
import threading
import wx
from call_frame import CallFrame


class HomeFrame(wx.Frame):
    def __init__(self, client):
        super().__init__(None, title="Python Zoom", size=wx.Size(400, 300))
        self.client = client

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(panel, label=f"Python Zoom - {self.client.username}")
        font = title.GetFont()
        font.PointSize += 10
        title.SetFont(font)

        self.start_btn = wx.Button(panel, label="Start Meeting")
        self.join_btn = wx.Button(panel, label="Join Meeting")
        self.code_box = wx.TextCtrl(panel)

        vbox.Add(title, 0, wx.ALL | wx.CENTER, 20)
        vbox.Add(self.start_btn, 0, wx.ALL | wx.EXPAND, 10)
        vbox.Add(self.code_box, 0, wx.ALL | wx.EXPAND, 10)
        vbox.Add(self.join_btn, 0, wx.ALL | wx.EXPAND, 10)

        panel.SetSizer(vbox)

        self.start_btn.Bind(wx.EVT_BUTTON, self.start_meeting)
        self.join_btn.Bind(wx.EVT_BUTTON, self.join_meeting)

    def start_meeting(self, event):
        self.client.start_meeting()
        wx.CallLater(500, self._open_call_frame)

    def join_meeting(self, event):
        code = self.code_box.GetValue().strip()

        if not code:
            wx.MessageBox("Enter meeting code")
            return

        self.client.request_join_meeting(code)
        wx.CallLater(500, self._open_call_frame)

    def _open_call_frame(self):
        # Run the role-wait loop in a background thread so the GUI thread
        # never blocks. Once role is ready, create the CallFrame on the GUI thread.
        def _wait_for_role():
            deadline = time.time() + 10.0
            while self.client.role is None and time.time() < deadline:
                time.sleep(0.02)

            wx.CallAfter(self._create_call_frame)

        threading.Thread(target=_wait_for_role, daemon=True).start()

    def _create_call_frame(self):
        if self.client.role:
            call = CallFrame(
                self.client.role,
                home_frame=self,
                username=self.client.username
            )
            call.Show()
            self.Hide()
