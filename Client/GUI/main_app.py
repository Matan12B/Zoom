# main_app.py

import wx
from auth_frame import AuthFrame
from Client.Logic.clientLogic import Client


class ZoomApp(wx.App):
    def OnInit(self):
        ip = "10.0.0.14"
        self.client = Client(ip, 3018)
        self.client.start()

        frame = AuthFrame(self.client)
        frame.Show()
        return True


if __name__ == "__main__":
    app = ZoomApp()
    app.MainLoop()