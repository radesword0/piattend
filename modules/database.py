"""
database.py — All SQLite database operations for PiAttend.

SQLite is a lightweight database stored as a single file on disk.
It requires no server process, which makes it perfect for a Raspberry Pi
project where simplicity and reliability matter more than scale.

Two tables are used:
  - students    : one row per enrolled student (ID, name, enrollment date)
  - attendance  : one row per check-in event (who, when, how they were verified)

Call init_db() once at program startup to create the tables if they
don't already exist.  It is safe to call every time — it does nothing
if the tables are already there.
"""

import sqlite3
from datetime import date, datetime
import config


def _connect():
    """
    Open and return a connection to the SQLite database file.

    row_factory = sqlite3.Row makes every returned row behave like a
    dictionary, so you can write row["student_id"] instead of row[0].
    This makes the rest of the code much easier to read.
    """
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Create the database tables on the first run.

    Uses "CREATE TABLE IF NOT EXISTS" so this function is safe to call
    every time the program starts — it only creates tables when they are
    missing and leaves existing data completely untouched.
    """
    conn = _connect()
    cur  = conn.cursor()

    # executescript runs multiple SQL statements in one call.
    # We define both tables here so the schema is easy to read in one place.
    cur.executescript("""
        -- One row per enrolled student.
        CREATE TABLE IF NOT EXISTS students (
            student_id        TEXT PRIMARY KEY,   -- e.g. "1042"
            name              TEXT NOT NULL,       -- full name
            enrolled_at       TEXT NOT NULL,       -- ISO timestamp
            face_sample_count INTEGER DEFAULT 0    -- how many photos were captured
        );

        -- One row per check-in event.  student_name is stored here as well
        -- (denormalised) so that attendance reports still make sense even if
        -- a student record were ever deleted.
        CREATE TABLE IF NOT EXISTS attendance (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id    TEXT    NOT NULL,
            student_name  TEXT    NOT NULL,
            date          TEXT    NOT NULL,   -- YYYY-MM-DD
            time          TEXT    NOT NULL,   -- HH:MM:SS
            status        TEXT    NOT NULL,   -- "Present" or "Late"
            confidence    REAL,              -- LBPH score (NULL if keypad fallback)
            method        TEXT    NOT NULL,   -- "Face" or "Keypad Fallback"
            snapshot_path TEXT,              -- path to saved JPEG, or NULL
            FOREIGN KEY (student_id) REFERENCES students(student_id)
        );
    """)

    conn.commit()
    conn.close()
    print("[DB] Database initialised at:", config.DB_PATH)


# ── Student record operations ──────────────────────────────────────────────────

def add_student(student_id: str, name: str, face_sample_count: int = 0):
    """
    Insert a new student record into the database.

    Raises ValueError if the student_id already exists so the caller
    can show the user a clear error message rather than crashing.
    """
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO students (student_id, name, enrolled_at, face_sample_count)
               VALUES (?, ?, ?, ?)""",
            (
                student_id,
                name,
                datetime.now().isoformat(timespec="seconds"),  # e.g. "2026-05-04T09:15:00"
                face_sample_count,
            )
        )
        conn.commit()
        print(f"[DB] Student added: {student_id} — {name}")
    except sqlite3.IntegrityError:
        # IntegrityError is raised when a PRIMARY KEY constraint is violated,
        # meaning this student_id is already in the table.
        raise ValueError(f"Student ID '{student_id}' is already enrolled.")
    finally:
        conn.close()


def update_face_count(student_id: str, count: int):
    """Update the stored face sample count after re-enrollment or additions."""
    conn = _connect()
    conn.execute(
        "UPDATE students SET face_sample_count = ? WHERE student_id = ?",
        (count, student_id)
    )
    conn.commit()
    conn.close()


def get_student(student_id: str):
    """
    Return a single student record as a plain dict, or None if not found.

    Returning None (instead of raising an exception) lets callers handle
    "student not found" gracefully with a simple  `if student is None`  check.
    """
    conn  = _connect()
    row   = conn.execute(
        "SELECT * FROM students WHERE student_id = ?", (student_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_students():
    """Return every enrolled student, sorted alphabetically by name."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM students ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def student_exists(student_id: str) -> bool:
    """Convenience helper — returns True if the student ID is in the database."""
    return get_student(student_id) is not None


# ── Attendance record operations ───────────────────────────────────────────────

def already_checked_in(student_id: str, today: str = None) -> bool:
    """
    Return True if this student already has an attendance record for today.

    This is the duplicate-prevention check.  We look for any row that
    matches both the student_id AND today's date, so a student can only
    appear once per day regardless of how many times they stand in front
    of the camera.
    """
    # Default to today's date; the parameter exists so tests can pass a
    # specific date without having to mess with the system clock.
    today = today or date.today().isoformat()
    conn  = _connect()
    row   = conn.execute(
        "SELECT id FROM attendance WHERE student_id = ? AND date = ?",
        (student_id, today)
    ).fetchone()
    conn.close()
    return row is not None   # fetchone() returns None if no match exists


def log_attendance(student_id: str, student_name: str, status: str,
                   confidence: float = None, method: str = "Face",
                   snapshot_path: str = None) -> int:
    """
    Write a new attendance record to the database and return its row id.

    Parameters
    ----------
    student_id    : the student's unique numeric ID string
    student_name  : stored here so reports still work if the student is deleted
    status        : "Present" or "Late" (determined by compare to LATE_CUTOFF_TIME)
    confidence    : LBPH confidence score; None when the keypad fallback was used
    method        : "Face" or "Keypad Fallback"
    snapshot_path : path to the saved check-in photo, or None
    """
    now  = datetime.now()
    conn = _connect()
    cur  = conn.execute(
        """INSERT INTO attendance
           (student_id, student_name, date, time, status, confidence, method, snapshot_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            student_id,
            student_name,
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            status,
            round(confidence, 2) if confidence is not None else None,
            method,
            snapshot_path,
        )
    )
    conn.commit()
    row_id = cur.lastrowid   # the auto-assigned integer id of the new row
    conn.close()
    print(f"[DB] Logged: {student_name} ({student_id}) — {status} via {method}")
    return row_id


def get_today_attendance():
    """Return all attendance records for today, most recent first."""
    today = date.today().isoformat()
    conn  = _connect()
    rows  = conn.execute(
        "SELECT * FROM attendance WHERE date = ? ORDER BY time DESC",
        (today,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_attendance_by_date(target_date: str):
    """Return attendance records for a specific date (YYYY-MM-DD), oldest first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM attendance WHERE date = ? ORDER BY time",
        (target_date,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_attendance():
    """Return the complete attendance history, newest dates first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM attendance ORDER BY date DESC, time DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
