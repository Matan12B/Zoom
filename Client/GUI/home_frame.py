import time

import wx
from call_frame import CallFrame


class HomeFrame(wx.Frame):

    def __init__(self, client):
        super().__init__(None, title="Python Zoom", size=(400,300))
        self.client = client
        self.client.start()

        panel = wx.Panel(self)

        vbox = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(panel, label="Python Zoom")
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
        # Request server to create a meeting
        self.client.start_meeting()

        # Wait briefly for meeting code
        wx.CallLater(500, self._open_call_frame)


    def join_meeting(self, event):
        code = self.code_box.GetValue()

        if not code:
            wx.MessageBox("Enter meeting code")
            return

        # Request to join meeting
        # todo if isinstance(client, callLogic)
        self.client.request_join_meeting(code)

        # Wait briefly for server response
        wx.CallLater(500, self._open_call_frame)

    def _open_call_frame(self):
        # Open call frame with client logic
        while self.client.role is None:
            time.sleep(0.02)
            continue
        if self.client.role:
            call = CallFrame(self.client.role)
            call.Show()
            self.Close()