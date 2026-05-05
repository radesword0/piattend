"""
enrollment.py — Student enrollment workflow for PiAttend.

Enrollment is an admin task performed once per student before the system
is used for attendance.  The process works like this:

  1. The admin enters the student's ID number and full name.
  2. The camera opens and the student sits in front of it.
  3. The system automatically captures FACE_SAMPLES_COUNT face images
     (default 30) and saves them to data/faces/<student_id>/.
  4. The student record is written to the SQLite database.
  5. The LBPH face recogniser is retrained on ALL enrolled students
     so that the new student is immediately recognisable at check-in.

Why capture multiple images?
  A single photo cannot capture the natural variation in a person's face
  (slight head tilts, blinking, different lighting angles).  30 samples
  gives the LBPH recogniser enough variety to be robust during check-in.

Note: enrollment is done with a keyboard (admin only).
Students only ever use the numeric keypad during check-in.
"""

import os
import cv2
import config
from modules.camera import Camera
from modules.database import add_student, student_exists
from modules import recognizer


def enroll_student(student_id: str, name: str) -> int:
    """
    Run the full enrollment workflow for one student.

    Parameters
    ----------
    student_id : numeric string (e.g. "1042") — must be digits only
                 because students type it on a numeric keypad.
    name       : the student's full name.

    Returns the number of face images captured.
    Returns 0 if the user aborted by pressing Q.

    Raises ValueError for invalid input or a duplicate student ID.
    """
    student_id = student_id.strip()
    name       = name.strip()

    # Validate inputs before opening the camera
    if not student_id.isdigit():
        raise ValueError("Student ID must contain digits only.")
    if not name:
        raise ValueError("Student name cannot be empty.")
    if student_exists(student_id):
        raise ValueError(f"Student ID '{student_id}' is already enrolled.")

    # Create the directory that will hold this student's face images.
    # exist_ok=True means no error if the folder already exists.
    save_dir = os.path.join(config.FACES_DIR, student_id)
    os.makedirs(save_dir, exist_ok=True)

    cam    = Camera()
    cam.open()

    count  = 0
    target = config.FACE_SAMPLES_COUNT

    print(f"\n[ENROLL] Starting enrollment for {name} (ID: {student_id})")
    print(f"[ENROLL] Capturing {target} face samples — look directly at the camera.")
    print("[ENROLL] Press Q at any time to abort.")

    try:
        # Keep looping until we have collected the required number of samples.
        while count < target:
            frame = cam.read_frame()
            if frame is None:
                continue

            # detect_faces returns a list of (x,y,w,h) bounding boxes and
            # the grayscale version of the frame.
            faces, gray = cam.detect_faces(frame)

            if len(faces) == 1:
                # Exactly one face found — extract the face region of interest
                x, y, w, h = faces[0]
                face_roi   = gray[y : y + h, x : x + w]

                # Resize every sample to the same fixed size (200×200 px).
                # Consistent sizing is required by the LBPH trainer — all
                # training images for a given label must have the same dimensions.
                face_roi = cv2.resize(face_roi, (200, 200))

                # Save the image with a zero-padded filename (000.jpg, 001.jpg …)
                img_path = os.path.join(save_dir, f"{count:03d}.jpg")
                cv2.imwrite(img_path, face_roi)
                count += 1

                # Overlay the progress count on the live camera feed
                label = f"Captured {count}/{target} — keep still"
                cam.draw_box(frame, faces, label)
                print(f"\r[ENROLL] {label}   ", end="", flush=True)

            elif len(faces) == 0:
                # No face visible — prompt the student to move into frame
                cv2.putText(frame, "No face detected — move closer",
                            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 220), 2)

            else:
                # Multiple faces visible — we cannot tell whose images to save
                cv2.putText(frame, "Multiple faces — only one student please",
                            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 140, 255), 2)

            cam.show("PiAttend — Enrollment (Q to abort)", frame)

            # wait_key(1) pauses for 1 ms and returns the ASCII code of any key
            # pressed.  ord('q') converts 'q' to its ASCII code (113) for comparison.
            if cam.wait_key(1) == ord('q'):
                print("\n[ENROLL] Aborted by user — no changes saved.")
                cam.release()
                return 0

    finally:
        # The finally block runs whether we exit normally or via an exception,
        # ensuring the camera is always released even if an error occurs.
        cam.release()

    print(f"\n[ENROLL] Captured {count} images for {name}.")

    # Write the student record to the database now that we have the images.
    add_student(student_id, name, face_sample_count=count)

    # Retrain the recogniser so the new student is immediately active.
    # This scans ALL students' image folders, so it gets slower as more
    # students are enrolled — but for a classroom-sized demo it is instant.
    print("[ENROLL] Retraining face recogniser with new student data…")
    recognizer.train()

    print(f"[ENROLL] Enrollment complete for {name} ({student_id}).\n")
    return count


def delete_student_faces(student_id: str):
    """
    Delete all face images for a student from disk.

    Used if a student needs to be re-enrolled (e.g. their images were
    captured in poor lighting and recognition is failing).
    Does NOT remove the student from the database — call the DB function
    separately if the record should also be deleted.
    """
    import shutil
    face_dir = os.path.join(config.FACES_DIR, student_id)
    if os.path.isdir(face_dir):
        shutil.rmtree(face_dir)
        print(f"[ENROLL] Deleted face data folder for student {student_id}.")
    else:
        print(f"[ENROLL] No face data found for student {student_id}.")
