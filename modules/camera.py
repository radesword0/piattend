"""
camera.py — Camera capture and face detection for PiAttend.

This module wraps OpenCV's VideoCapture so the rest of the code never
has to deal with raw cv2 calls.  It also handles face detection using
a Haar Cascade classifier — a fast, classical computer-vision algorithm
that works well on the limited CPU of a Raspberry Pi 3B+.

How Haar Cascades work (for your presentation):
  The classifier was pre-trained by Haar to recognise patterns of light
  and dark rectangles that commonly appear in human faces (eyes, nose,
  mouth).  It scans across the image at multiple scales and flags any
  region that matches those patterns.  It is not deep learning — it uses
  hand-crafted features — which is why it runs in real time on a Pi.

Usage:
    cam = Camera()
    cam.open()
    frame = cam.read_frame()
    faces, gray = cam.detect_faces(frame)
    cam.release()          # always release when done to free the hardware
"""

import cv2
import config


class Camera:
    """Manages one physical camera and provides face-detection utilities."""

    def __init__(self):
        self._cap = None

        # Load the pre-trained frontal face Haar Cascade that ships with OpenCV.
        # cv2.data.haarcascades is a helper that gives the path to that folder.
        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    def open(self):
        """
        Open the camera at the index specified in config.py.

        Raises RuntimeError if the camera cannot be opened (e.g. wrong index,
        camera in use by another process, or no camera attached).
        """
        self._cap = cv2.VideoCapture(config.CAMERA_INDEX)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)

        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera at index {config.CAMERA_INDEX}. "
                "Check that a camera is connected and not used by another program."
            )

        print(f"[CAM] Camera opened (index={config.CAMERA_INDEX}, "
              f"{config.CAMERA_WIDTH}×{config.CAMERA_HEIGHT})")

    def read_frame(self):
        """
        Capture and return the current video frame as a BGR numpy array.

        Returns None if the camera is not open or the read fails.
        BGR (Blue-Green-Red) is OpenCV's default colour order — the opposite
        of the more common RGB convention.
        """
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def detect_faces(self, frame):
        """
        Run the Haar Cascade face detector on a colour frame.

        Returns
        -------
        faces : list of (x, y, w, h) bounding boxes — one per detected face.
                An empty list means no faces were found.
        gray  : the grayscale version of the frame (needed by the LBPH recogniser).

        Why grayscale?  Both the Haar detector and the LBPH recogniser work
        on intensity (brightness) values only, not colour.  Converting to
        grayscale cuts the data in third and speeds up processing on the Pi.

        scaleFactor=1.3 means the detector shrinks the image by 30% at each
        scale step.  Smaller values are more thorough but slower.

        minNeighbors=5 controls false-positive suppression: a region must be
        flagged by at least 5 overlapping detection windows to count as a face.
        Higher values reduce false positives but may miss real faces.

        minSize=(80, 80) ignores any face smaller than 80×80 pixels, which
        filters out tiny distant faces that are too small to recognise reliably.
        """
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.3,
            minNeighbors=5,
            minSize=(80, 80),
        )
        # detectMultiScale returns a numpy array or an empty tuple — normalise
        # to a plain list so callers can always use len(faces) safely.
        return (list(faces) if len(faces) > 0 else []), gray

    def draw_box(self, frame, faces, label: str = ""):
        """
        Draw a green bounding box (and optional text label) around each face.

        Modifies the frame array in-place and also returns it so calls can
        be chained:  cam.show("window", cam.draw_box(frame, faces, "Name")).
        """
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 0), 2)
            if label:
                # Draw the label just above the bounding box
                cv2.putText(frame, label, (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 0), 2)
        return frame

    def show(self, window_name: str, frame):
        """
        Display a frame in a named GUI window.

        This only works when the Pi has a monitor attached (or you are using
        SSH with X11 forwarding: ssh -X pi@<ip>).  When running headless
        over plain SSH this call is harmless but produces no visible output.
        """
        cv2.imshow(window_name, frame)

    def wait_key(self, delay_ms: int = 1) -> int:
        """
        Wait up to delay_ms milliseconds for a key press and return its code.

        Returns -1 if no key was pressed within the timeout.
        The bitwise AND with 0xFF is needed on some platforms to strip
        the high bits that OpenCV sometimes includes in the key code.
        """
        return cv2.waitKey(delay_ms) & 0xFF

    def save_frame(self, path: str, frame) -> bool:
        """Write a frame to disk as a JPEG file.  Returns True on success."""
        return cv2.imwrite(path, frame)

    def release(self):
        """
        Release the camera hardware and close any open OpenCV windows.

        Always call this when you are done — not releasing the camera
        can prevent other programs (or the next run of this script) from
        accessing it.
        """
        if self._cap:
            self._cap.release()
            self._cap = None
        cv2.destroyAllWindows()
        print("[CAM] Camera released.")
