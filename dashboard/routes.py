"""
dashboard/routes.py — All URL routes for the PiAttend teacher dashboard.

This file defines what happens when a browser requests each URL.
Flask uses "routes" (URL patterns) mapped to Python functions.
Each function collects data from the database and passes it to an
HTML template which renders the final page the teacher sees.

Routes defined here:
  GET  /             — today's attendance summary
  GET  /students     — list of all enrolled students
  GET  /enroll       — enrollment form
  POST /enroll       — process a submitted enrollment form
  GET  /history      — full attendance history (with optional date filter)
  GET  /export/csv   — download today's attendance as a .csv file

The Blueprint system lets us keep routes in a separate file from app.py,
which makes the project easier to navigate and extend later.
"""

import csv
import io
from datetime import date

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, Response
)

# Adjust sys.path so imports work when routes.py is loaded by app.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.database import (
    get_today_attendance,
    get_all_students,
    get_attendance_by_date,
    get_all_attendance,
    init_db,
)
from modules.enrollment import enroll_student

# A Blueprint groups related routes.  The name "main" is used internally
# by Flask when generating URLs with url_for("main.index"), etc.
bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    """
    Today's attendance page — the main view a teacher checks each morning.

    Fetches all check-in records for today and counts Present vs Late
    so the summary cards at the top of the page are always accurate.
    """
    records = get_today_attendance()
    today   = date.today().strftime("%B %d, %Y")   # e.g. "May 04, 2026"

    # Count each status type for the summary cards
    present_count = sum(1 for r in records if r["status"] == "Present")
    late_count    = sum(1 for r in records if r["status"] == "Late")

    return render_template(
        "index.html",
        records       = records,
        today         = today,
        present_count = present_count,
        late_count    = late_count,
    )


@bp.route("/students")
def students():
    """
    Enrolled students list.

    Shows each student's ID, name, how many face samples were captured
    during enrollment (more = better recognition accuracy), and when
    they were enrolled.
    """
    all_students = get_all_students()
    return render_template("students.html", students=all_students)


@bp.route("/enroll", methods=["GET", "POST"])
def enroll():
    """
    Student enrollment page — admin only.

    GET  : Show the enrollment form.
    POST : Read the submitted ID and name, trigger the camera capture
           workflow on the Pi, and redirect back to the form with a
           success or error message.

    Note: because enrollment opens the Pi's camera, this route should
    only be accessed from the Pi itself (http://localhost:5000/enroll),
    not from a remote device — the camera is a local hardware resource.
    """
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        name       = request.form.get("name", "").strip()

        try:
            captured = enroll_student(student_id, name)
            # flash() stores a one-time message that appears on the next page load.
            # The category ("success" or "error") controls which CSS style is applied.
            flash(f"Enrolled {name} ({student_id}) with {captured} face samples.",
                  "success")
        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            flash(f"Enrollment failed: {e}", "error")

        # Redirect to the same page (POST → Redirect → GET pattern) so that
        # refreshing the page doesn't resubmit the form accidentally.
        return redirect(url_for("main.enroll"))

    return render_template("enroll.html")


@bp.route("/history")
def history():
    """
    Full attendance history with an optional date filter.

    If a ?date=YYYY-MM-DD query parameter is present, only records for
    that date are returned.  Otherwise the complete history is shown.

    Example: /history?date=2026-05-04
    """
    filter_date = request.args.get("date", "")

    if filter_date:
        records = get_attendance_by_date(filter_date)
    else:
        records = get_all_attendance()

    return render_template("history.html", records=records, filter_date=filter_date)


@bp.route("/export/csv")
def export_csv():
    """
    Download today's attendance as a CSV file.

    The browser will prompt the teacher to save a file named
    attendance_YYYY-MM-DD.csv which can be opened in Excel or Google Sheets.

    io.StringIO creates an in-memory text buffer — no temporary file is
    created on disk, which keeps the Pi's SD card writes to a minimum.
    """
    records = get_today_attendance()
    today   = date.today().isoformat()

    # Write the CSV into memory rather than a real file
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "student_id", "student_name", "date", "time",
        "status", "confidence", "method", "snapshot_path"
    ])
    writer.writeheader()
    for record in records:
        writer.writerow(record)

    # Flask's Response lets us set the Content-Type and Content-Disposition
    # headers so the browser knows to download the file rather than display it.
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=attendance_{today}.csv"
        }
    )
