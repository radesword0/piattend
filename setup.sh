#!/bin/bash
# setup.sh — First-time setup for PiAttend on Raspberry Pi OS
# Run once: bash setup.sh

set -e

echo "=== PiAttend Setup ==="

# System packages
sudo apt-get update -y
sudo apt-get install -y python3-pip python3-opencv libopencv-dev

# Python packages (use headless OpenCV on Pi to save RAM)
pip3 install flask numpy opencv-contrib-python-headless

# Create data directories (in case they're missing)
mkdir -p data/faces data/snapshots data/model

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Enroll students:   python3 run_enrollment.py"
echo "  2. Start check-in:    python3 run_checkin.py"
echo "  3. Start dashboard:   python3 app.py"
echo "     Then open http://$(hostname -I | awk '{print $1}'):5000 on any device."
