"""
recognizer.py — Face recognition using OpenCV's LBPH algorithm.

LBPH stands for Local Binary Patterns Histograms.  Here is how it works
at a high level (useful for your presentation):

  1. Training:
     - Each face image is divided into a grid of small cells.
     - For each pixel in a cell, the algorithm compares its brightness to
       the 8 surrounding pixels and writes a 1 (brighter) or 0 (darker)
       for each, producing an 8-bit binary number (the "local binary pattern").
     - The distribution of these patterns across the cell is stored as a
       histogram (a bar chart of how often each pattern appears).
     - All cell histograms are concatenated into one feature vector
       that describes the face.
     - The vectors for all training images are stored alongside their labels.

  2. Prediction:
     - The same process is applied to the new face.
     - The resulting vector is compared to every stored training vector
       using the chi-squared distance formula.
     - The closest match wins, and its distance becomes the "confidence" score.

Why LBPH for a Raspberry Pi?
     - It is built into OpenCV — no extra packages needed.
     - It is fast enough to predict in well under a second on a Pi 3B+.
     - It handles slight changes in lighting reasonably well.
     - It can be updated with new students without full retraining from scratch.

IMPORTANT: The LBPH "confidence" score is a DISTANCE, not a percentage.
  - A score of 0   means a perfect match.
  - A score of 100 means the faces are very different.
  - So LOWER confidence → BETTER match (the opposite of what the name implies).
  - We compare against config.CONFIDENCE_THRESHOLD:
      score < threshold  →  recognised
      score ≥ threshold  →  unknown, fall back to keypad entry

Public functions:
    train()        — build the model from enrolled face images
    predict(roi)   — return (student_id, confidence) for one face image
    model_exists() — check whether a trained model is already saved on disk
"""

import os
import json
import cv2
import numpy as np
import config

# The label map is saved alongside trainer.yml so we can look up which
# integer label corresponds to which student_id after prediction.
_LABEL_MAP_PATH = os.path.join(config.MODEL_DIR, "label_map.json")


def train():
    """
    Read all enrolled face images, train the LBPH recogniser, and save the model.

    Each student's images live in data/faces/<student_id>/.
    We assign each student a sequential integer label (0, 1, 2 …) because
    LBPH internally works with integers, not strings.  The mapping between
    integer labels and student IDs is saved to label_map.json.

    Returns the total number of images the model was trained on.
    Raises ValueError if there are no images to train on.
    """
    face_samples = []   # list of grayscale face images (numpy arrays)
    labels       = []   # parallel list of integer labels
    label_map    = {}   # int label → student_id string
    next_label   = 0    # counter that increases by 1 for each new student

    if not os.path.isdir(config.FACES_DIR):
        raise FileNotFoundError(f"Faces directory not found: {config.FACES_DIR}")

    # Walk through each sub-folder in data/faces/
    for student_id in sorted(os.listdir(config.FACES_DIR)):
        student_dir = os.path.join(config.FACES_DIR, student_id)
        if not os.path.isdir(student_dir):
            continue   # skip stray files at the top level

        images_found = 0
        for fname in os.listdir(student_dir):
            if not fname.lower().endswith((".jpg", ".png")):
                continue

            # cv2.IMREAD_GRAYSCALE loads the image in grayscale directly,
            # avoiding the need for a separate cvtColor call.
            img = cv2.imread(os.path.join(student_dir, fname), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue   # skip any corrupted files

            face_samples.append(img)
            labels.append(next_label)
            images_found += 1

        if images_found > 0:
            label_map[next_label] = student_id
            print(f"[REC] Loaded {images_found} images for '{student_id}' "
                  f"(label {next_label})")
            next_label += 1

    if not face_samples:
        raise ValueError(
            "No face images found.  Enroll at least one student before training."
        )

    # Create and train the LBPH recogniser.
    # LBPHFaceRecognizer_create() comes from opencv-contrib-python.
    recogniser = cv2.face.LBPHFaceRecognizer_create()
    recogniser.train(face_samples, np.array(labels, dtype=np.int32))

    # Save the trained model so it persists across program restarts.
    os.makedirs(config.MODEL_DIR, exist_ok=True)
    recogniser.save(config.MODEL_PATH)

    # JSON does not allow integer keys, so we store them as strings.
    with open(_LABEL_MAP_PATH, "w") as f:
        json.dump({str(k): v for k, v in label_map.items()}, f, indent=2)

    print(f"[REC] Model trained on {len(face_samples)} images "
          f"across {next_label} student(s).")
    print(f"[REC] Saved → {config.MODEL_PATH}")
    return len(face_samples)


def predict(gray_face_roi):
    """
    Predict the identity of a face from a grayscale face image region.

    Parameters
    ----------
    gray_face_roi : numpy array — a cropped, grayscale image of a single face.

    Returns
    -------
    (student_id, confidence)
        student_id : the matched student's ID string, or None if model is missing.
        confidence : the LBPH distance score (lower = more confident).
                     Returns 999.0 when the model is unavailable.

    The caller is responsible for comparing confidence to
    config.CONFIDENCE_THRESHOLD to decide whether to trust the result.
    """
    if not model_exists():
        print("[REC] No trained model found.  Run enrollment and train first.")
        return None, 999.0

    # Re-load the model from disk on each call.
    # On a Pi 3B+ this takes ~50 ms — fast enough for real-time use.
    recogniser = cv2.face.LBPHFaceRecognizer_create()
    recogniser.read(config.MODEL_PATH)

    with open(_LABEL_MAP_PATH) as f:
        label_map = json.load(f)   # keys are strings because of JSON serialisation

    # predict() returns (label, confidence).
    # label is the integer we assigned during training.
    # confidence is the chi-squared distance to the best matching training image.
    label, confidence = recogniser.predict(gray_face_roi)
    student_id = label_map.get(str(label))

    print(f"[REC] label={label}, confidence={confidence:.1f}, "
          f"student_id={student_id}")
    return student_id, confidence


def model_exists() -> bool:
    """Return True if both the model file and the label map are present on disk."""
    return (os.path.exists(config.MODEL_PATH) and
            os.path.exists(_LABEL_MAP_PATH))
