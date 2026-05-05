"""
app.py — Web dashboard entry point for PiAttend.

WHO uses this:   The TEACHER or admin — not students.
HOW to access:   Open a browser on any device connected to the same
                 Wi-Fi network and go to  http://<pi-ip-address>:5000
                 The Pi's IP address can be found by running  hostname -I
                 on the Pi, or checking your router's device list.

The dashboard shows:
  /            — today's attendance table (present/late count, timestamps)
  /history     — full history with date filter
  /students    — list of enrolled students
  /enroll      — enrollment form (triggers camera capture on the Pi)
  /export/csv  — download today's attendance as a spreadsheet

This script never needs to run at the same time as run_checkin.py on the
same machine, but it CAN — they don't conflict because they use different
resources (the dashboard only reads from the database; check-in writes to it).

Usage:
    python app.py
"""

import sys
import os

# Add the project root to the path so Flask can find config.py and modules/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from dashboard.routes import bp
from modules.database import init_db
import config

# Create the Flask application.
# template_folder and static_folder point to the dashboard sub-directory
# so templates and CSS are organised separately from the Python code.
app = Flask(
    __name__,
    template_folder="dashboard/templates",
    static_folder="dashboard/static",
)

# A secret key is required for Flask's "flash" messaging (the alert banners
# that appear after enrollment).  Change this to any random string in production.
app.secret_key = "piattend-secret-change-this"

# Register all URL routes defined in dashboard/routes.py
app.register_blueprint(bp)


@app.context_processor
def inject_globals():
    """
    Make today's date string available in every HTML template automatically.

    Without this, every route function would have to pass today's date as
    a separate variable.  Context processors inject variables globally so
    templates can use {{ today }} anywhere.
    """
    from datetime import date
    return {"today": date.today().isoformat()}


if __name__ == "__main__":
    # Create database tables if this is the first run
    init_db()

    print(f"\n[APP] PiAttend dashboard starting…")
    print(f"[APP] Open in a browser on this device : http://localhost:{config.FLASK_PORT}")
    print(f"[APP] Open from another device on LAN  : http://<pi-ip>:{config.FLASK_PORT}")
    print(f"[APP] Find the Pi's IP with: hostname -I\n")

    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
