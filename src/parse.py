import json
import sys

import anthropic
from dotenv import load_dotenv

from ocr import extract_text

load_dotenv()

MODEL = "claude-sonnet-5"

# Persistent instructions for how to behave on every call, kept separate
# from the actual per-call OCR text passed in as the user message.
SYSTEM_PROMPT = (
    "Extract structured data from raw OCR text of a receipt. The text may "
    "contain noise or errors from the OCR process -- stray characters or "
    "words that aren't part of the receipt's real content. Use your "
    "judgment to exclude that noise from extracted values (e.g. item "
    "names).\n\n"
    "If a field's value isn't actually present in the text or can't be "
    "confidently determined, the field must be left out of your response "
    "entirely -- do not include it with any kind of default or "
    "placeholder value. This means: no assuming a missing quantity is 1, "
    "no using 0 as a stand-in for an unknown price (0 means free, not "
    "unknown), and no placeholder strings like \"UNKNOWN\" or \"N/A\". An "
    "unknown field should be genuinely absent from the output, not "
    "represented by any value at all.\n\n"
    "Only populate subtotal, tax, and total from text that is actually "
    "labeled as that specific field. Do not substitute a different "
    "labeled amount into one of these fields just because the field "
    "you're looking for isn't present (e.g. don't use a surcharge amount "
    "as the tax, or a cash total as the credit card total, even if "
    "they're the only nearby numbers available).\n\n"
    "merchant and total are always required in your response, unlike "
    "other fields. If you genuinely cannot determine either from the "
    "text, set it to null -- never a placeholder string like \"UNKNOWN\", "
    "and never a guessed value."
)

# A tool schema, not meant to be actually executed -- we use it purely to
# force Claude's response into a guaranteed, schema-validated JSON shape
# instead of free text we'd have to parse ourselves. See docs/decisions.md.
RECEIPT_TOOL = {
    "name": "record_receipt",
    "description": "Records structured data extracted from a receipt's raw OCR text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "merchant": {
                "type": ["string", "null"],
                "description": (
                    "Business name. Required in your response, but the "
                    "value itself may be null if genuinely undetermined."
                ),
            },
            "date": {
                "type": "string",
                "description": (
                    "Date of purchase, normalized to YYYY-MM-DD format "
                    "regardless of how it appears in the source text."
                ),
            },
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit_price": {"type": "number"},
                        "total_price": {"type": "number"},
                    },
                    "required": ["name"],
                },
            },
            "subtotal": {"type": "number"},
            "tax": {"type": "number"},
            "total": {
                "type": ["number", "null"],
                "description": (
                    "Grand total charged. Required in your response, but "
                    "the value itself may be null if genuinely undetermined."
                ),
            },
        },
        "required": ["merchant", "line_items", "total"],
    },
}


# Sends raw OCR text to Claude and returns structured receipt data as a
# Python dict, using tool use (forced via tool_choice) so the response is
# guaranteed to match RECEIPT_TOOL's schema rather than needing to parse
# free-form text.
def parse_receipt(ocr_text):
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[RECEIPT_TOOL],
        tool_choice={"type": "tool", "name": "record_receipt"},
        messages=[{"role": "user", "content": ocr_text}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise ValueError("No tool_use block in Claude's response")


if __name__ == "__main__":
    ocr_text = extract_text(sys.argv[1])
    receipt_data = parse_receipt(ocr_text)
    print(json.dumps(receipt_data, indent=2))
