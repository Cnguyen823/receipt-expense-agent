from pathlib import Path

from ocr import extract_text
from parse import parse_receipt
from storage import compute_file_hash, init_db, receipt_exists, save_receipt

RECEIPTS_DIR = Path("data/receipts")


# Loops the OCR -> parse -> store pipeline over every receipt photo in
# RECEIPTS_DIR. Skips files already saved (by content hash, not filename)
# before running OCR/LLM on them again. Catches per-receipt failures so one
# bad photo (e.g. crop_to_receipt() rejecting an unusable image) doesn't
# stop the rest of the batch.
def process_all_receipts():
    init_db()
    image_paths = sorted(RECEIPTS_DIR.glob("*.jpg"))

    processed = skipped = failed = 0

    for path in image_paths:
        content_hash = compute_file_hash(path)
        if receipt_exists(content_hash):
            print(f"Skipping {path.name} (already processed)")
            skipped += 1
            continue

        print(f"Processing {path.name}...")
        try:
            text = extract_text(str(path))
            data = parse_receipt(text)
            receipt_id = save_receipt(data, source_file=path.name, content_hash=content_hash)
            print(f"  Saved as receipt id {receipt_id}")
            processed += 1
        except Exception as e:
            print(f"  Failed: {e}")
            failed += 1

    print(f"\nDone. Processed: {processed}, skipped: {skipped}, failed: {failed}")


if __name__ == "__main__":
    process_all_receipts()
