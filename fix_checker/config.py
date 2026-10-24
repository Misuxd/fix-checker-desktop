"""Paths and dark theme colors."""
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
TASKS_FILE = APP_DIR / "tasks.json"
SETTINGS_FILE = APP_DIR / "settings.json"
HISTORY_FILE = APP_DIR / "history.json"

# Near-black palette, matching the FIX Checker mock-up.
C = {
    "bg": "#0a0c0f",
    "panel": "#0f1216",
    "card": "#15191f",
    "card_hover": "#1b2028",
    "border": "#242c36",
    "text": "#e9eef4",
    "muted": "#8a95a3",
    "accent": "#5b8dff",
    "green": "#2ecc71",
    "red": "#ff5d5d",
    "amber": "#f0b429",
    "violet": "#9d6bff",
}

FONT = "Segoe UI"
MONO = "Consolas"

STATUS_COLORS = {
    "passed": C["green"],
    "failed": C["red"],
    "running": C["amber"],
    "queued": C["violet"],
}
