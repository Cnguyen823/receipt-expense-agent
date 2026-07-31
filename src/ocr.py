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


# Rotates a PIL image to correct our phone camera's known orientation, then
# converts to grayscale, lightly blurs it to smooth out fine background
# noise (wood grain, compression artifacts) without eroding character
# strokes, then applies adaptive thresholding to binarize it into clean
# black text on white -- locally, so uneven lighting/shadows in the photo
# don't get misread as text the way a single global cutoff would. Rotation
# angle, blur kernel, and threshold params were all tuned empirically
# against a real receipt photo; see docs/decisions.md.
def preprocess_image(image):
    image = image.rotate(ROTATION_DEGREES, expand=True)
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
