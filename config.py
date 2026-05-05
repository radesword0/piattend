"""
config.py — Central configuration for PiAttend.

All tuneable settings live here so you never have to dig through
multiple files to adjust behaviour.  Change a value here and every
module that imports config will pick it up automatically.
"""

import os

# ── Directory layout ───────────────────────────────────────────────────────────
# BASE_DIR is the folder this file lives in (the project root).
# Everything else is expressed relative to it so the project works
# regardless of where on the Pi it is installed.
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DATA_DIR      = os.path.join(BASE_DIR, "data")

# Each enrolled student gets their own sub-folder: data/faces/<student_id>/
FACES_DIR     = os.path.join(DATA_DIR, "faces")

# Optional JPEG snapshots saved at each check-in for audit/demo purposes
SNAPSHOTS_DIR = os.path.join(DATA_DIR, "snapshots")

# The trained LBPH model file (created by recognizer.train())
MODEL_DIR     = os.path.join(DATA_DIR, "model")
MODEL_PATH    = os.path.join(MODEL_DIR, "trainer.yml")

# SQLite database — a single file that stores students and attendance records
DB_PATH       = os.path.join(DATA_DIR, "piattend.db")

# ── Attendance timing ──────────────────────────────────────────────────────────
# Students who check in after this time (24-hour HH:MM) are marked "Late".
# Adjust to match your school's bell schedule.
LATE_CUTOFF_TIME = "08:30"

# ── Face recognition thresholds ────────────────────────────────────────────────
# LBPH (Local Binary Patterns Histograms) returns a "confidence" score that
# represents how DIFFERENT the face is from the closest match in the dataset.
# LOWER confidence  →  BETTER match  (counter-intuitive but correct for LBPH).
# If confidence is above this threshold, the face is considered unrecognised
# and the system falls back to keypad ID entry.
CONFIDENCE_THRESHOLD = 70.0

# Number of face sample images captured per student during enrollment.
# More samples generally improve recognition accuracy; 30 is a good balance
# for a Raspberry Pi 3B+ (fast enough to capture without tiring the student).
FACE_SAMPLES_COUNT = 30

# ── Camera settings ────────────────────────────────────────────────────────────
# Index 0 selects the first available camera (Pi Camera via v4l2 or USB webcam).
# Change to 1 if you have two cameras and want the second one.
CAMERA_INDEX  = 0
CAMERA_WIDTH  = 640
CAMERA_HEIGHT = 480

# ── Keypad settings ────────────────────────────────────────────────────────────
# Set USE_GPIO_KEYPAD = True when running on the real Pi with the keypad wired up.
# Set USE_GPIO_KEYPAD = False on a development machine (Mac/Linux) so the
# program reads from the keyboard instead of GPIO pins.
USE_GPIO_KEYPAD = False

# BCM GPIO pin numbers for the 4×3 matrix keypad.
# Row pins are driven HIGH one at a time (outputs).
# Column pins are read to detect which key was pressed (inputs with pull-down).
# Adjust these to match how YOUR keypad is actually wired to the Pi header.
KEYPAD_ROWS = [18, 23, 24, 25]   # R1 → R4  (BCM numbering)
KEYPAD_COLS = [4,  17, 27]       # C1 → C3  (BCM numbering)

# How long (seconds) to wait for a student to finish typing their ID
# before giving up and returning to the recognition loop.
KEYPAD_TIMEOUT = 30

# ── Flask web dashboard ────────────────────────────────────────────────────────
# "0.0.0.0" means Flask listens on all network interfaces, so the teacher
# can open the dashboard from any laptop on the same Wi-Fi network.
FLASK_HOST  = "0.0.0.0"
FLASK_PORT  = 5000
FLASK_DEBUG = False   # keep False in production so Flask doesn't auto-reload

# ── Snapshot saving ────────────────────────────────────────────────────────────
# When True, a JPEG photo is saved to data/snapshots/ at every successful
# check-in.  Useful for the demo and for audit trails.
SAVE_SNAPSHOTS = True
