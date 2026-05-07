import os
import sys

# Repo root on sys.path so `Client.*` and `Common.*` imports work when launched from GUI dir.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import wx

from Client.GUI.auth_frame import AuthFrame
from Client.Logic.clientLogic import Client
from Common.settings import load_settings


class Face2FaceApp(wx.App):
    def OnInit(self):
        # Load network and encryption settings from file
        try:
            ip, port, video_port, audio_port, dh_p, dh_g = load_settings()
        except (FileNotFoundError, ValueError) as e:
            wx.MessageBox(str(e), "Settings Error", wx.OK | wx.ICON_ERROR)
            return False
        # Start the core client background thread
        self.client = Client(ip, port, video_port, audio_port, dh_p, dh_g)
        self.client.start()
        # Launch the initial login screen
        frame = AuthFrame(self.client)
        frame.Show()
        return True


if __name__ == "__main__":
    app = Face2FaceApp()
    app.MainLoop()
