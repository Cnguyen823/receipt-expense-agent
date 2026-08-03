import sys

import cv2
import numpy as np
import pytesseract
from PIL import Image

# Phone photos from this setup come out rotated 90 degrees clockwise from
# upright. Tesseract's OSD (automatic orientation detection) was tested and
# found unreliable here: the receipt only fills part of the frame, and the
# wood-grain clipboard background is enough visual noise to tank its
# confidence to near-zero and produce wrong answers. Falling back to a fixed
# manual rotation for now; revisit auto-detection in Step 4 (batch
# processing) once there's more real receipt photos to work from. See
# docs/decisions.md.
ROTATION_DEGREES = -90

# Tesseract's default page segmentation mode assumes normal paragraph text
# and struggles with a receipt's columnar item/qty/price/total table -- it
# drops the table rows entirely. --psm 6 (treat the image as one uniform
# block of text) was tested against several modes and was the only one that
# picked up table content at all. See docs/decisions.md.
TESSERACT_CONFIG = "--psm 6"

# Minimum contour area, as a fraction of total image area, to be treated as
# part of the receipt rather than background noise (e.g. wood grain).
MIN_CONTOUR_AREA_RATIO = 0.001


# Detects the receipt's boundary and crops out background clutter. Rather
# than requiring a single closed 4-point contour (tested and found brittle
# -- see docs/decisions.md), this takes every sufficiently large detected
# edge and computes one bounding box around all of them together. This also
# gracefully handles a photo where the receipt runs off the edge of the
# frame: the bounding box naturally extends to the image's own edge there,
# since that's as far as any detected content goes, with no special-case
# logic needed for it.
def crop_to_receipt(image):
    array = np.array(image)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    # Wider blur than the OCR pipeline uses -- here we want to suppress ALL
    # fine texture (wood grain), not preserve character detail, since we're
    # only looking for the receipt's overall shape, not reading text yet.
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    # Canny edge detection: finds pixels where brightness jumps sharply,
    # i.e. likely object boundaries. 50/150 are low/high sensitivity
    # thresholds -- strong gradients (>150) are kept as edges outright;
    # medium ones (50-150) are kept only if connected to a strong edge.
    edges = cv2.Canny(blurred, 50, 150)
    # Thicken the white edge pixels slightly to bridge small gaps left by
    # Canny, so nearby edge fragments read as one continuous shape.
    edges = cv2.dilate(edges, None, iterations=2)

    # Trace the edge map into distinct boundary shapes ("contours").
    # RETR_EXTERNAL = only outermost shapes (ignore nested ones, e.g.
    # individual letters). CHAIN_APPROX_SIMPLE = store straight lines as
    # just their endpoints instead of every pixel, to save memory.
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # Area cutoff as a % of image size (not a fixed pixel count) so it
    # scales sensibly across different photo resolutions.
    min_area = MIN_CONTOUR_AREA_RATIO * array.shape[0] * array.shape[1]
    # Keep only contours big enough to plausibly be real receipt content,
    # dropping small noise shapes like stray wood-grain squiggles.
    significant = [c for c in contours if cv2.contourArea(c) > min_area]

    if not significant:
        raise ValueError(
            "Could not detect a receipt in this photo. Please retake it, "
            "making sure all four edges of the receipt are visible in frame."
        )

    # Combine every remaining contour's points into one set, then find the
    # smallest straight rectangle that contains all of them -- this is what
    # lets us crop without needing one single closed 4-point shape.
    x, y, w, h = cv2.boundingRect(np.vstack(significant))
    # Plain numpy slicing: grab rows y..y+h and columns x..x+w -- this is
    # the actual crop. Convert back to a PIL Image for the rest of the
    # pipeline.
    return Image.fromarray(array[y : y + h, x : x + w])


# Rotates a PIL image to correct our phone camera's known orientation, crops
# out background clutter, converts to grayscale, lightly blurs it to smooth
# out fine background noise (wood grain, compression artifacts) without
# eroding character strokes, then applies adaptive thresholding to binarize
# it into clean black text on white -- locally, so uneven lighting/shadows
# in the photo don't get misread as text the way a single global cutoff
# would. Rotation angle, blur kernel, and threshold params were all tuned
# empirically against a real receipt photo; see docs/decisions.md.
def preprocess_image(image):
    image = image.rotate(ROTATION_DEGREES, expand=True)
    image = crop_to_receipt(image)
    # Note: this grayscale/blur is a separate pass from the one inside
    # crop_to_receipt() above -- that one was tuned for finding shapes,
    # this one is tuned for preparing text for OCR, so they intentionally
    # don't share a code path even though both start the same way.
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
