"""
checkin.py — Attendance check-in logic and state machine for PiAttend.

This module is the core of the student-facing side of the system.
It manages two states:

  IDLE   — The camera is open but the system is waiting.
            The screen shows "PiAttend Ready — Press * to start".
            This lets the teacher start a check-in session for the class
            without needing to SSH in and type a command.

  ACTIVE — The system is actively checking in students.
            Each camera frame is analysed:
              1. Detect a face using the Haar Cascade classifier.
              2. If exactly one face is found, run LBPH recognition.
              3a. If confidence ≤ threshold  →  log attendance automatically.
              3b. If confidence >  threshold  →  prompt for keypad ID entry.
            Pressing * on the keypad returns to IDLE (ends the session).

Business rules enforced here:
  - Duplicate prevention : a student can only check in once per calendar day.
  - Late detection       : if the current time is after LATE_CUTOFF_TIME,
                           status is "Late" instead of "Present".
  - Cooldown             : after a student is processed, they are ignored for
                           COOLDOWN_SECS seconds so they don't trigger again
                           while still standing in front of the camera.
"""

import os
import time
from datetime import datetime
import cv2
import config
from modules.camera   import Camera
from modules          import recognizer
from modules.database import already_checked_in, log_attendance, get_student
from modules.keypad   import keypad

# ── State constants ────────────────────────────────────────────────────────────
STATE_IDLE   = "idle"    # waiting for * key to start a session
STATE_ACTIVE = "active"  # actively processing student check-ins

# Seconds to ignore a student after they have been processed.
# Prevents the same person from triggering recognition 20 times while
# they read the "Already checked in" message and walk away.
COOLDOWN_SECS = 10


def _determine_status() -> str:
    """
    Return "Present" or "Late" based on the current wall-clock time.

    Compares HH:MM strings because Python string comparison works correctly
    for zero-padded 24-hour times (e.g. "08:29" < "08:30").
    """
    now_hhmm = datetime.now().strftime("%H:%M")
    return "Late" if now_hhmm > config.LATE_CUTOFF_TIME else "Present"


def _save_snapshot(cam: Camera, frame, student_id: str) -> str | None:
    """
    Save a JPEG snapshot of the check-in frame to data/snapshots/.

    The filename encodes the student ID and timestamp so files are uniquely
    named and sorted chronologically.  Returns the file path, or None if
    snapshots are disabled in config.py.
    """
    if not config.SAVE_SNAPSHOTS:
        return None

    os.makedirs(config.SNAPSHOTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path      = os.path.join(config.SNAPSHOTS_DIR, f"{student_id}_{timestamp}.jpg")
    cam.save_frame(path, frame)
    return path


def _overlay_text(frame, text: str, y: int = 40, color=(255, 255, 255)):
    """
    Draw a single line of text on the frame at the given y-coordinate.

    A dark shadow offset by 2 px is drawn first so the white text is
    readable against any background colour.
    """
    cv2.putText(frame, text, (22, y + 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 0, 0), 2)   # shadow
    cv2.putText(frame, text, (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2)


def _show_banner(cam: Camera, frame, message: str, color=(0, 200, 0)):
    """
    Display a semi-transparent status banner at the top of the frame
    and hold it on screen for 2 seconds.

    The banner gives students visual feedback ("Present", "Late",
    "Already checked in", etc.) without requiring a separate display.
    """
    # Draw a filled dark rectangle as the banner background
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], 70), (20, 20, 20), -1)
    # addWeighted blends overlay (60%) with the original frame (40%)
    # to create a semi-transparent effect.
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    _overlay_text(frame, message, y=48, color=color)
    cam.show("PiAttend — Check-in", frame)
    time.sleep(2)


def _attempt_recognition(cam: Camera, frame) -> dict | None:
    """
    Try to recognise the face in frame using LBPH.

    If recognition confidence is acceptable, returns a result dict.
    If confidence is too low, launches the keypad fallback.
    Returns None if the process should be skipped (e.g. no face, cancelled).

    The returned dict always has keys:
        student_id, student_name, confidence (may be None), method
    or a single "error" key with a human-readable message.
    """
    faces, gray = cam.detect_faces(frame)

    if len(faces) == 0:
        return None   # nobody in frame yet — keep looping silently

    if len(faces) > 1:
        # Cannot tell whose face to recognise
        _overlay_text(frame, "One person at a time please", color=(0, 80, 255))
        cam.show("PiAttend — Check-in", frame)
        return None

    # Exactly one face found
    x, y, w, h = faces[0]

    # Extract the face region and resize it to match the training image size
    face_roi = cv2.resize(gray[y : y + h, x : x + w], (200, 200))

    student_id, confidence = recognizer.predict(face_roi)

    if student_id and confidence <= config.CONFIDENCE_THRESHOLD:
        # Confidence is low enough to trust — recognised!
        student = get_student(student_id)
        if not student:
            # The label map points to an ID that no longer exists in the DB.
            # This shouldn't happen in normal use but is handled gracefully.
            return {"error": "Recognised face maps to unknown student. Retrain model."}

        cam.draw_box(frame, faces, f"{student['name']} ({confidence:.0f})")
        cam.show("PiAttend — Check-in", frame)

        return {
            "student_id":   student["student_id"],
            "student_name": student["name"],
            "confidence":   confidence,
            "method":       "Face",
        }

    else:
        # Confidence too high (face not recognised) — try keypad fallback.
        cam.draw_box(frame, faces, f"Unknown ({confidence:.0f}) — enter ID")
        cam.show("PiAttend — Check-in", frame)
        time.sleep(0.5)
        return _keypad_fallback(cam, frame)


def _keypad_fallback(cam: Camera, frame) -> dict | None:
    """
    Prompt the student to type their student ID on the numeric keypad.

    This is the safety net for when face recognition fails — it ensures
    every student can still check in even if lighting is bad or their
    face wasn't enrolled perfectly.

    Returns a result dict on success, or a dict with "error" key on failure.
    """
    print("[CHECKIN] Face not recognised — switching to keypad fallback.")
    _overlay_text(frame, "Not recognised — enter your ID on the keypad",
                  color=(0, 160, 255))
    cam.show("PiAttend — Check-in", frame)

    # Block here while the student types their ID
    student_id = keypad.read_id("Student ID: ")

    if not student_id:
        # Student pressed # with nothing typed, or timed out
        return None

    student = get_student(student_id)
    if not student:
        return {"error": f"ID '{student_id}' not found — see your teacher"}

    return {
        "student_id":   student["student_id"],
        "student_name": student["name"],
        "confidence":   None,   # no face confidence when using keypad
        "method":       "Keypad Fallback",
    }


def _process_result(cam: Camera, frame, result: dict, cooldown: dict) -> dict:
    """
    Take a recognised result dict and write the attendance record.

    Handles duplicate checking, late detection, snapshot saving, and
    the cooldown timer.  Updates the cooldown dict in-place and returns it.
    """
    sid  = result["student_id"]
    name = result["student_name"]

    # Cooldown: skip if this student was processed very recently.
    # This prevents the same recognition event from firing multiple times
    # while the student is still standing in front of the camera.
    if time.time() - cooldown.get(sid, 0) < COOLDOWN_SECS:
        return cooldown

    # Duplicate prevention: only one check-in per student per day.
    if already_checked_in(sid):
        print(f"[CHECKIN] {name} already checked in today.")
        _show_banner(cam, frame, f"{name}: already checked in today",
                     color=(0, 200, 200))
        cooldown[sid] = time.time()
        return cooldown

    # Determine Present vs Late based on current time
    status        = _determine_status()
    snapshot_path = _save_snapshot(cam, frame, sid)

    # Write the permanent attendance record to SQLite
    log_attendance(
        student_id    = sid,
        student_name  = name,
        status        = status,
        confidence    = result["confidence"],
        method        = result["method"],
        snapshot_path = snapshot_path,
    )

    cooldown[sid] = time.time()

    # Show green banner for Present, orange for Late
    color = (0, 200, 0) if status == "Present" else (0, 140, 255)
    _show_banner(cam, frame, f"{name} — {status}", color=color)
    return cooldown


# ── Main loop ──────────────────────────────────────────────────────────────────

def run_checkin_loop():
    """
    Start the check-in system.  This function runs until the user presses Q
    in the OpenCV window or Ctrl-C in the terminal.

    State machine:

      IDLE   →  shows a "Ready" screen
                press * on keypad → switches to ACTIVE
                (mock mode: press Enter in terminal to start)

      ACTIVE →  processes student check-ins frame by frame
                press * on keypad to stop → switches back to IDLE
                press Q in the OpenCV window to quit entirely
    """
    from modules.database import init_db
    init_db()

    if not recognizer.model_exists():
        print("[CHECKIN] ERROR: No trained model found.")
        print("[CHECKIN] Run  python run_enrollment.py  first to enroll students.")
        return

    # Open camera and keypad — these stay open for the life of the program
    cam = Camera()
    cam.open()
    keypad.open()

    state    = STATE_IDLE
    cooldown = {}   # maps student_id → timestamp of last processed check-in

    print("\n" + "=" * 55)
    print("  PiAttend — Check-in System")
    print(f"  Late cutoff : {config.LATE_CUTOFF_TIME}")
    print(f"  Confidence  : {config.CONFIDENCE_THRESHOLD} (lower = better match)")
    if config.USE_GPIO_KEYPAD:
        print("  Press * on the keypad to start / stop a session.")
    else:
        print("  Mock mode: press Enter in this terminal to start a session.")
    print("  Press Q in the camera window to exit completely.")
    print("=" * 55 + "\n")

    try:
        while True:
            frame = cam.read_frame()
            if frame is None:
                continue   # camera glitch — try next frame

            # ── IDLE state ─────────────────────────────────────────────────
            if state == STATE_IDLE:
                # Draw the standby message on every frame so it stays visible
                _overlay_text(frame, "PiAttend Ready", y=40, color=(200, 200, 200))
                if config.USE_GPIO_KEYPAD:
                    _overlay_text(frame, "Press * to start check-in", y=75, color=(120, 120, 120))
                else:
                    _overlay_text(frame, "Mock mode: press Enter in terminal to start",
                                  y=75, color=(120, 120, 120))
                cam.show("PiAttend — Check-in", frame)

                # GPIO mode: poll for * key (non-blocking)
                if config.USE_GPIO_KEYPAD:
                    key = keypad.poll_key()
                    if key == "*":
                        print("[CHECKIN] * pressed — starting check-in session.")
                        state = STATE_ACTIVE
                else:
                    # Mock mode: block briefly with a short timeout,
                    # then check the OpenCV window for Q before looping
                    pass   # session starts when user presses Enter (handled below)

                # Check for Q key in the OpenCV window to quit
                if cam.wait_key(1) == ord('q'):
                    print("[CHECKIN] Q pressed — exiting.")
                    break

                # Mock mode only: prompt to start (blocks until Enter)
                if not config.USE_GPIO_KEYPAD and state == STATE_IDLE:
                    input("[CHECKIN] Press Enter to start check-in session "
                          "(or Ctrl-C to quit)… ")
                    state = STATE_ACTIVE
                    print("[CHECKIN] Check-in session started.")

            # ── ACTIVE state ───────────────────────────────────────────────
            elif state == STATE_ACTIVE:
                # Check for * to stop the session (GPIO mode only)
                if config.USE_GPIO_KEYPAD:
                    key = keypad.poll_key()
                    if key == "*":
                        print("[CHECKIN] * pressed — session ended, returning to idle.")
                        state = STATE_IDLE
                        continue

                # Try to recognise whoever is in front of the camera
                result = _attempt_recognition(cam, frame)

                if result:
                    if "error" in result:
                        # Something went wrong — show the error banner and continue
                        print(f"[CHECKIN] {result['error']}")
                        _show_banner(cam, frame, result["error"], color=(0, 0, 200))
                    else:
                        # Valid recognition or keypad fallback — log attendance
                        cooldown = _process_result(cam, frame, result, cooldown)

                # Show the live camera feed with the current frame
                cam.show("PiAttend — Check-in", frame)

                # Q key in the window exits the whole program
                if cam.wait_key(1) == ord('q'):
                    print("[CHECKIN] Q pressed — exiting.")
                    break

    except KeyboardInterrupt:
        # Ctrl-C from the SSH terminal — exit cleanly
        print("\n[CHECKIN] Interrupted — shutting down.")

    finally:
        # Always clean up hardware resources, even if an exception occurred
        cam.release()
        keypad.close()
        print("[CHECKIN] Goodbye.")
