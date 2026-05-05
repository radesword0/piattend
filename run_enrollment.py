"""
run_enrollment.py — Admin entry point for enrolling new students.

This script is run ONCE before the system is used for attendance,
and again whenever a new student joins the class.  It requires a
keyboard (admin task) — students only ever use the numeric keypad.

Usage:
    python run_enrollment.py

Typical workflow for a demo:
  1. Run this script and choose option 1.
  2. Type the student's ID number (e.g. 1042) and their name.
  3. Have the student sit in front of the camera.
  4. The system captures 30 face photos automatically.
  5. Repeat for each student you want to demonstrate with.
  6. When done, option 2 lists everyone to confirm they were saved.
  7. Exit, then launch run_checkin.py for the live demo.
"""

import sys
import os

# Ensure imports resolve from the project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database   import init_db, get_all_students
from modules.enrollment import enroll_student


def main():
    # Initialise the database (creates tables if this is the first run)
    init_db()

    print("=" * 50)
    print("  PiAttend — Student Enrollment")
    print("=" * 50)

    while True:
        print("\nOptions:")
        print("  1. Enroll a new student")
        print("  2. List enrolled students")
        print("  3. Exit")

        choice = input("\nChoice: ").strip()

        if choice == "1":
            student_id = input("Student ID (digits only): ").strip()
            name       = input("Student full name       : ").strip()
            try:
                captured = enroll_student(student_id, name)
                if captured > 0:
                    print(f"\n  {name} enrolled with {captured} face samples.")
            except ValueError as e:
                print(f"\n  [ERROR] {e}")
            except Exception as e:
                print(f"\n  [ERROR] Unexpected error: {e}")

        elif choice == "2":
            students = get_all_students()
            if not students:
                print("\n  No students enrolled yet.")
            else:
                print(f"\n  {'ID':<12} {'Name':<25} {'Samples':>7}  Enrolled")
                print("  " + "-" * 58)
                for s in students:
                    print(f"  {s['student_id']:<12} {s['name']:<25} "
                          f"{s['face_sample_count']:>7}  {s['enrolled_at']}")

        elif choice == "3":
            print("Exiting enrollment.\n")
            break

        else:
            print("  Invalid choice — enter 1, 2, or 3.")


if __name__ == "__main__":
    main()
