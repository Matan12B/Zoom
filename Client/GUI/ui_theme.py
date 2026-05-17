import wx
import wx.adv
import wx.lib.buttons as wx_buttons


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
    "call_ctrl": wx.Colour(38, 40, 50),
    "call_ctrl_text": wx.Colour(210, 215, 228),
    "call_ctrl_active": wx.Colour(180, 35, 35),
    "call_ctrl_danger": wx.Colour(160, 30, 30),
}

def style_window(window, bg, fg=None):
    """
    Set background and foreground window colors
    """
    window.SetBackgroundColour(bg)
    if fg is not None:
        window.SetForegroundColour(fg)
    return window


def style_text(control, colour=None, size_delta=0, bold=False):
    """
    Style a text control with font size, weight, and color.
    :param control: The wx control to style
    :param colour: Text color (optional)
    :param size_delta: Font size adjustment
    :param bold: Whether to make text bold
    :return: The styled control
    """
    font = control.GetFont()
    font.PointSize = max(9, font.PointSize + size_delta)
    font.SetWeight(wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL)
    control.SetFont(font)
    if colour is not None:
        control.SetForegroundColour(colour)
    return control

def style_text_input(control, hint=""):
    """
    Style a text input control with colors and hint text.
    :param control: The wx text input control
    :param hint: Placeholder hint text
    :return: The styled control
    """
    control.SetMinSize(wx.Size(-1, 34))
    control.SetBackgroundColour(PALETTE["surface_muted"])
    control.SetForegroundColour(PALETTE["text"])
    style_text(control, PALETTE["text"], size_delta=5)
    if hint:
        control.SetHint(hint)
    return control


def create_button(parent, label, kind="primary", min_height=44, min_width=-1):
    """
    Create and style a button.
    :param parent: Parent wx window
    :param label: Button label
    :param kind: Button style kind
    :param min_height: Minimum height
    :param min_width: Minimum width
    :return: The created and styled button
    """
    if kind in ("call", "call_active", "call_danger"):
        button = wx_buttons.GenButton(parent, label=label)
        if hasattr(button, "SetBezelWidth"):
            button.SetBezelWidth(0)
    else:
        button = wx.Button(parent, label=label)
    return style_button(button, kind=kind, min_height=min_height, min_width=min_width)


def style_button(button, kind="primary", min_height=44, min_width=-1):
    """
    Style an existing button with colors and size.
    :param button: The wx button to style
    :param kind: Button style kind
    :param min_height: Minimum height
    :param min_width: Minimum width
    :return: The styled button
    """
    palettes = {
        "primary": (PALETTE["primary"], PALETTE["text_inverted"]),
        "secondary": (PALETTE["surface_alt"], PALETTE["text"]),
        "ghost": (PALETTE["surface_muted"], PALETTE["text"]),
        "warning": (PALETTE["warning_bg"], PALETTE["warning_text"]),
        "danger": (PALETTE["danger"], PALETTE["text_inverted"]),
        "danger_soft": (PALETTE["danger_bg"], PALETTE["danger_text"]),
        "call": (PALETTE["call_ctrl"], PALETTE["call_ctrl_text"]),
        "call_active": (PALETTE["call_ctrl_active"], PALETTE["text_inverted"]),
        "call_danger": (PALETTE["call_ctrl_danger"], PALETTE["text_inverted"]),
    }
    bg, fg = palettes.get(kind, palettes["primary"])
    button.SetMinSize(wx.Size(min_width, min_height))
    if hasattr(button, "SetInitialSize"):
        button.SetInitialSize(wx.Size(min_width, min_height))
    button.SetBackgroundColour(bg)
    button.SetForegroundColour(fg)
    if hasattr(button, "SetLabelColour"):
        button.SetLabelColour(fg)
    style_text(button, fg, bold=True)
    font = button.GetFont()
    font.SetWeight(wx.FONTWEIGHT_BOLD)
    button.SetFont(font)
    button.Refresh()
    return button


def create_link(parent, label):
    """
    Create and style a hyperlink control.
    :param parent: Parent wx window
    :param label: Link label
    :return: The created hyperlink control
    """
    link = wx.adv.HyperlinkCtrl(parent, label=label, url="")
    link.SetNormalColour(PALETTE["primary"])
    link.SetHoverColour(PALETTE["primary_dark"])
    link.SetVisitedColour(PALETTE["primary"])
    style_text(link, PALETTE["primary"], bold=True)
    return link


def style_status_panel(panel, label, tone="neutral"):
    """
    Style a status panel with background and text colors based on tone.
    :param panel: The wx panel to style
    :param label: The label control in the panel
    :param tone: Tone type (neutral, success, error, warning)
    :return: None
    """
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

def _blend_colour(base, target, ratio):
    """
    Blend two colors together based on a ratio.
    :param base: Base wx.Colour
    :param target: Target wx.Colour
    :param ratio: Blend ratio (0.0 to 1.0)
    :return: Blended wx.Colour
    """
    ratio = max(0.0, min(1.0, ratio))
    return wx.Colour(
        int(base.Red() + (target.Red() - base.Red()) * ratio),
        int(base.Green() + (target.Green() - base.Green()) * ratio),
        int(base.Blue() + (target.Blue() - base.Blue()) * ratio),
    )
