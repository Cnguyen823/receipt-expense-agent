import sys

import cv2
import numpy as np
import pytesseract
from PIL import Image

# Direction to rotate a sideways photo. Only validated on one real example
# so far -- assumes future sideways photos need the same direction. See
# docs/decisions.md.
SIDEWAYS_ROTATION_DEGREES = -90

# --psm 6 (uniform block of text) recovers table content that Tesseract's
# default mode drops. See docs/decisions.md.
TESSERACT_CONFIG = "--psm 6"

# Min contour area (as a % of image area) to count as real receipt content
# vs. background noise. Tuned empirically across two photos with different
# backgrounds. See docs/decisions.md.
MIN_CONTOUR_AREA_RATIO = 0.00025


# Crops out background clutter by finding all sufficiently large edges and
# boxing them together, rather than requiring one closed 4-point shape
# (tested, too brittle -- see docs/decisions.md). Also handles a receipt
# that runs off the edge of the frame for free: the box just extends to the
# image boundary there.
def crop_to_receipt(image):
    array = np.array(image)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    # Blur to suppress background texture before edge detection.
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    # Find edges (sharp brightness changes = likely object boundaries).
    edges = cv2.Canny(blurred, 50, 150)
    # Bridge small gaps in the detected edges.
    edges = cv2.dilate(edges, None, iterations=2)

    # Trace edges into shapes, keep only the outermost ones.
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = MIN_CONTOUR_AREA_RATIO * array.shape[0] * array.shape[1]
    significant = [c for c in contours if cv2.contourArea(c) > min_area]

    if not significant:
        raise ValueError(
            "Could not detect a receipt in this photo. Please retake it, "
            "making sure all four edges of the receipt are visible in frame."
        )

    # Box around every remaining shape combined, then crop to it.
    x, y, w, h = cv2.boundingRect(np.vstack(significant))
    return Image.fromarray(array[y : y + h, x : x + w])


# Fixes sideways photos using a receipt's known shape: right-side-up, it's
# always taller than wide. Must run after crop_to_receipt() -- background
# clutter could otherwise make an upright receipt look wider than tall.
def correct_orientation(image):
    width, height = image.size
    if width > height:
        image = image.rotate(SIDEWAYS_ROTATION_DEGREES, expand=True)
    return image


# Crops, fixes orientation, then binarizes into clean black text on white
# for OCR: grayscale -> light blur (smooths noise, keeps character strokes)
# -> adaptive threshold (binarizes using local, not global, contrast so
# uneven lighting doesn't get misread as text). Params tuned empirically
# against real photos; see docs/decisions.md.
def preprocess_image(image):
    image = crop_to_receipt(image)
    image = correct_orientation(image)
    array = np.array(image)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    thresholded = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 15
    )
    return Image.fromarray(thresholded)


# Opens an image file, preprocesses it, and returns the raw OCR text.
def extract_text(image_path):
    image = Image.open(image_path)
    image = preprocess_image(image)
    return pytesseract.image_to_string(image, config=TESSERACT_CONFIG)


if __name__ == "__main__":
    text = extract_text(sys.argv[1])
    print(text)
