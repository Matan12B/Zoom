import wx
from home_frame import HomeFrame
from Client.Logic.clientLogic import Client
class ZoomApp(wx.App):

    def OnInit(self):
        # Pass None for client to run in UI-only mode
        ip = input("Enter server ip: ")
        self.client = Client(ip, 3018)
        frame = HomeFrame(client=self.client)
        frame.Show()
        return True

if __name__ == "__main__":
    app = ZoomApp()
    app.MainLoop()