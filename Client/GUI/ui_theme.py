import wx
import wx.adv


PALETTE = {
    "app_bg": wx.Colour(244, 247, 251),
    "surface": wx.Colour(255, 255, 255),
    "surface_alt": wx.Colour(233, 240, 250),
    "surface_muted": wx.Colour(247, 249, 252),
    "border": wx.Colour(220, 228, 240),
    "primary": wx.Colour(14, 113, 235),
    "primary_dark": wx.Colour(10, 86, 190),
    "sidebar": wx.Colour(11, 26, 48),
    "text": wx.Colour(20, 33, 61),
    "text_muted": wx.Colour(98, 112, 136),
    "text_inverted": wx.Colour(255, 255, 255),
    "success_bg": wx.Colour(231, 248, 238),
    "success_text": wx.Colour(25, 110, 67),
    "warning_bg": wx.Colour(255, 244, 224),
    "warning_text": wx.Colour(153, 88, 13),
    "danger": wx.Colour(218, 61, 48),
    "danger_dark": wx.Colour(177, 40, 35),
    "danger_bg": wx.Colour(255, 234, 231),
    "danger_text": wx.Colour(155, 34, 28),
    "call_bg": wx.Colour(0, 0, 0),
    "call_surface": wx.Colour(12, 12, 14),
    "call_surface_alt": wx.Colour(22, 22, 26),
    "video_tile": wx.Colour(14, 14, 17),
    "call_ctrl":        wx.Colour(38, 40, 50),
    "call_ctrl_text":   wx.Colour(210, 215, 228),
    "call_ctrl_active": wx.Colour(180, 35, 35),
    "call_ctrl_danger": wx.Colour(160, 30, 30),
}


def _blend_colour(base, target, ratio):
    ratio = max(0.0, min(1.0, ratio))
    return wx.Colour(
        int(base.Red() + (target.Red() - base.Red()) * ratio),
        int(base.Green() + (target.Green() - base.Green()) * ratio),
        int(base.Blue() + (target.Blue() - base.Blue()) * ratio),
    )


class RoundedButton(wx.Control):
    def __init__(self, parent, label="", size=wx.DefaultSize):
        super().__init__(parent, style=wx.BORDER_NONE, size=size)
        self.SetLabel(label)
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        self._base_bg = PALETTE["primary"]
        self._base_fg = PALETTE["text_inverted"]
        self._radius = 16
        self._hovered = False
        self._pressed = False

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_SET_FOCUS, self._on_state_change)
        self.Bind(wx.EVT_KILL_FOCUS, self._on_state_change)

    def SetCornerRadius(self, radius):
        self._radius = max(6, radius)
        self.Refresh()

    def SetBaseColours(self, bg, fg):
        self._base_bg = bg
        self._base_fg = fg
        self.SetBackgroundColour(bg)
        self.SetForegroundColour(fg)
        self.Refresh()

    def DoGetBestSize(self):
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        text_w, text_h = dc.GetTextExtent(self.GetLabel() or "")
        width = max(120, text_w + 34)
        height = max(44, text_h + 20)
        return wx.Size(width, height)

    def Enable(self, enable=True):
        changed = super().Enable(enable)
        self.Refresh()
        return changed

    def SetLabel(self, label):
        super().SetLabel(label)
        self.Refresh()

    def _on_enter(self, event):
        self._hovered = True
        self.Refresh()
        event.Skip()

    def _on_leave(self, event):
        self._hovered = False
        self._pressed = False
        self.Refresh()
        event.Skip()

    def _on_left_down(self, event):
        if self.IsEnabled():
            self._pressed = True
            self.CaptureMouse()
            self.Refresh()
        event.Skip()

    def _on_left_up(self, event):
        was_pressed = self._pressed
        self._pressed = False
        if self.HasCapture():
            self.ReleaseMouse()
        self.Refresh()

        if was_pressed and self.IsEnabled():
            x, y = event.GetPosition()
            width, height = self.GetClientSize()
            if 0 <= x <= width and 0 <= y <= height:
                click_evt = wx.CommandEvent(wx.EVT_BUTTON.typeId, self.GetId())
                click_evt.SetEventObject(self)
                wx.PostEvent(self, click_evt)
        event.Skip()

    def _on_state_change(self, event):
        self.Refresh()
        event.Skip()

    def _current_colours(self):
        bg = self._base_bg
        fg = self._base_fg

        if not self.IsEnabled():
            bg = _blend_colour(bg, PALETTE["surface"], 0.45)
            fg = _blend_colour(fg, PALETTE["text_muted"], 0.4)
        elif self._pressed:
            bg = _blend_colour(bg, wx.Colour(0, 0, 0), 0.18)
        elif self._hovered:
            bg = _blend_colour(bg, wx.Colour(255, 255, 255), 0.08)

        border = _blend_colour(bg, wx.Colour(0, 0, 0), 0.14)
        return bg, fg, border

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        width, height = self.GetClientSize()
        parent_bg = self.GetParent().GetBackgroundColour()

        dc.SetBackground(wx.Brush(parent_bg))
        dc.Clear()

        if width <= 1 or height <= 1:
            return

        bg, fg, border = self._current_colours()

        gc = wx.GraphicsContext.Create(dc)
        if gc:
            gc.SetAntialiasMode(wx.ANTIALIAS_DEFAULT)
            path = gc.CreatePath()
            path.AddRoundedRectangle(0, 0, width - 1, height - 1, self._radius)

            gc.SetPen(gc.CreatePen(wx.Pen(border, 1)))
            gc.SetBrush(gc.CreateBrush(wx.Brush(bg)))
            gc.DrawPath(path)


            gc.SetFont(self.GetFont(), fg)
            text = self.GetLabel() or ""
            text_w, text_h = gc.GetTextExtent(text)
            gc.DrawText(text, (width - text_w) / 2, (height - text_h) / 2)


def style_window(window, bg, fg=None):
    window.SetBackgroundColour(bg)
    if fg is not None:
        window.SetForegroundColour(fg)
    return window


def style_text(control, colour=None, size_delta=0, bold=False):
    font = control.GetFont()
    font.PointSize = max(9, font.PointSize + size_delta)
    font.SetWeight(wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL)
    control.SetFont(font)
    if colour is not None:
        control.SetForegroundColour(colour)
    return control


def style_text_input(control, hint=""):
    control.SetMinSize(wx.Size(-1, 34))
    control.SetBackgroundColour(PALETTE["surface_muted"])
    control.SetForegroundColour(PALETTE["text"])
    style_text(control, PALETTE["text"], size_delta=5)
    if hint:
        control.SetHint(hint)
    return control


def create_button(parent, label, kind="primary", min_height=44, min_width=-1):
    button = RoundedButton(parent, label=label)
    return style_button(button, kind=kind, min_height=min_height, min_width=min_width)


def style_button(button, kind="primary", min_height=44, min_width=-1):
    palettes = {
        "primary":      (PALETTE["primary"],        PALETTE["text_inverted"]),
        "secondary":    (PALETTE["surface_alt"],    PALETTE["text"]),
        "ghost":        (PALETTE["surface_muted"],  PALETTE["text"]),
        "warning":      (PALETTE["warning_bg"],     PALETTE["warning_text"]),
        "danger":       (PALETTE["danger"],         PALETTE["text_inverted"]),
        "danger_soft":  (PALETTE["danger_bg"],      PALETTE["danger_text"]),
        "call":         (PALETTE["call_ctrl"],      PALETTE["call_ctrl_text"]),
        "call_active":  (PALETTE["call_ctrl_active"],PALETTE["text_inverted"]),
        "call_danger":  (PALETTE["call_ctrl_danger"],PALETTE["text_inverted"]),
    }
    bg, fg = palettes.get(kind, palettes["primary"])
    button.SetMinSize(wx.Size(min_width, min_height))
    if isinstance(button, RoundedButton):
        button.SetCornerRadius(min_height // 2)
        button.SetBaseColours(bg, fg)
    else:
        button.SetBackgroundColour(bg)
        button.SetForegroundColour(fg)
    if hasattr(button, "SetInitialSize"):
        button.SetInitialSize(wx.Size(min_width, min_height))
    style_text(button, fg, bold=True)
    return button


def create_link(parent, label):
    link = wx.adv.HyperlinkCtrl(parent, label=label, url="")
    link.SetNormalColour(PALETTE["primary"])
    link.SetHoverColour(PALETTE["primary_dark"])
    link.SetVisitedColour(PALETTE["primary"])
    style_text(link, PALETTE["primary"], bold=True)
    return link


def style_status_panel(panel, label, tone="neutral"):
    tones = {
        "neutral": (PALETTE["surface_alt"], PALETTE["text_muted"]),
        "success": (PALETTE["success_bg"], PALETTE["success_text"]),
        "error": (PALETTE["danger_bg"], PALETTE["danger_text"]),
        "warning": (PALETTE["warning_bg"], PALETTE["warning_text"]),
    }
    bg, fg = tones.get(tone, tones["neutral"])
    style_window(panel, bg)
    style_window(label, bg, fg)
    style_text(label, fg)
