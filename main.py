"""FixGuard - AI regression testing after every change.

Install:
    pip install -r requirements.txt
    playwright install chromium

Run:
    python main.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fix_checker.app import DeveloperAppUI

if __name__ == "__main__":
    DeveloperAppUI().mainloop()
