"""
run_checkin.py — Entry point for the student-facing check-in system.

Run this script on the Raspberry Pi to start accepting student check-ins.
It can be launched manually from a terminal or set up to start automatically
on boot using a systemd service or the Pi's autostart configuration.

Usage:
    python run_checkin.py

How it works:
  1. The camera and keypad are initialised.
  2. The system enters IDLE mode and displays a "Ready" screen.
  3. A teacher or admin presses * on the keypad to start a session.
  4. Students walk up, face the camera, and the system logs their attendance.
  5. Pressing * again ends the session and returns to IDLE.
  6. Press Q in the camera window (or Ctrl-C in the terminal) to exit.

Note on SSH:
  When connected over plain SSH the OpenCV camera window is not visible.
  Use  ssh -X pi@<ip>  (X11 forwarding) to see the window on your Mac,
  or connect a monitor directly to the Pi for the demo.
  The * start/stop feature works on the physical GPIO keypad regardless.
"""

import sys
import os

# Add the project root to Python's module search path so that
# "import config" and "from modules.xxx import ..." work correctly
# no matter which directory the script is launched from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.checkin import run_checkin_loop

if __name__ == "__main__":
    run_checkin_loop()
