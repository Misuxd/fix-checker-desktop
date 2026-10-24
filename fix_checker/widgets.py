"""Styled CustomTkinter widget helpers."""
import customtkinter as ctk

from .config import C, FONT, STATUS_COLORS


def card(parent, **kw):
    """A rounded dark panel with a subtle border."""
    kw.setdefault("fg_color", C["card"])
    kw.setdefault("corner_radius", 12)
    kw.setdefault("border_color", C["border"])
    kw.setdefault("border_width", 1)
    return ctk.CTkFrame(parent, **kw)


def label(parent, text, size=13, color=None, bold=False, **kw):
    weight = "bold" if bold else "normal"
    kw.setdefault("text_color", color or C["text"])
    kw.setdefault("font", (FONT, size, weight))
    return ctk.CTkLabel(parent, text=text, **kw)


def entry(parent, **kw):
    kw.setdefault("fg_color", C["panel"])
    kw.setdefault("border_color", C["border"])
    kw.setdefault("border_width", 1)
    kw.setdefault("text_color", C["text"])
    kw.setdefault("placeholder_text_color", C["muted"])
    kw.setdefault("font", (FONT, 13))
    return ctk.CTkEntry(parent, **kw)


def primary_btn(parent, text, command, **kw):
    kw.setdefault("fg_color", C["accent"])
    kw.setdefault("hover_color", "#4a7ae0")
    kw.setdefault("text_color", "#0a0c0f")
    kw.setdefault("font", (FONT, 13, "bold"))
    kw.setdefault("corner_radius", 8)
    return ctk.CTkButton(parent, text=text, command=command, **kw)


def ghost_btn(parent, text, command, **kw):
    kw.setdefault("fg_color", "transparent")
    kw.setdefault("border_color", C["border"])
    kw.setdefault("border_width", 1)
    kw.setdefault("text_color", C["muted"])
    kw.setdefault("hover_color", C["card_hover"])
    kw.setdefault("font", (FONT, 12))
    kw.setdefault("corner_radius", 8)
    return ctk.CTkButton(parent, text=text, command=command, **kw)


def pill(parent, status, **kw):
    """Colored status chip: green passed, red failed, amber running, violet queued."""
    color = STATUS_COLORS.get(status, C["muted"])
    kw.setdefault("fg_color", color)
    kw.setdefault("text_color", "#0a0c0f")
    kw.setdefault("corner_radius", 6)
    kw.setdefault("font", (FONT, 11, "bold"))
    kw.setdefault("width", 74)
    kw.setdefault("height", 20)
    return ctk.CTkLabel(parent, text=str(status).upper(), **kw)
