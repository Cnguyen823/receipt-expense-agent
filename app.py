import hashlib
import sys
from pathlib import Path

sys.path.insert(0, "src")

import streamlit as st
from sqlalchemy.orm import Session

from agent import ask
from ocr import extract_text
from parse import CATEGORIES, parse_receipt
from storage import Receipt, engine, init_db, receipt_exists, save_receipt

init_db()

st.set_page_config(page_title="Receipt Expense Agent", page_icon="🧾")

page = st.sidebar.radio("Navigate", ["Upload Receipt", "Browse Receipts", "Ask a Question"])


# Converts a blank string back to None, so an empty field is stored as
# genuinely unknown rather than defaulting to 0 or "".
def _blank_to_none(value):
    return value.strip() if value and value.strip() else None


def _blank_to_none_float(value):
    value = _blank_to_none(value)
    return float(value) if value is not None else None


if page == "Upload Receipt":
    st.title("Upload a Receipt")
    uploaded = st.file_uploader("Choose a receipt image", type=["jpg", "jpeg", "png"])

    if uploaded is not None:
        content_bytes = uploaded.getvalue()
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        if receipt_exists(content_hash):
            st.info("This exact receipt has already been processed and saved.")
        else:
            # Only run OCR/parsing once per uploaded file, not on every
            # widget interaction -- Streamlit reruns this whole script on
            # every rerun, so we cache the result in session_state keyed
            # by the file's hash.
            if st.session_state.get("current_hash") != content_hash:
                image_path = Path("data/receipts") / f"{content_hash[:16]}.jpg"
                image_path.write_bytes(content_bytes)

                with st.spinner("Reading receipt text..."):
                    text = extract_text(str(image_path))
                with st.spinner("Extracting structured data..."):
                    data = parse_receipt(text)

                st.session_state["current_hash"] = content_hash
                st.session_state["current_path"] = str(image_path)
                st.session_state["current_data"] = data

            data = st.session_state["current_data"]

            st.image(content_bytes, caption="Uploaded receipt", width=280)
            st.subheader("Review & correct before saving")
            st.caption("Leave a field blank if it's genuinely unknown -- don't guess.")

            merchant = st.text_input("Merchant", value=data.get("merchant") or "")

            category_options = [""] + CATEGORIES
            current_category = data.get("category") or ""
            category = st.selectbox(
                "Category",
                options=category_options,
                index=category_options.index(current_category)
                if current_category in category_options
                else 0,
            )

            date_str = st.text_input(
                "Date (YYYY-MM-DD)", value=data.get("date") or ""
            )
            total_str = st.text_input(
                "Total", value=str(data["total"]) if data.get("total") is not None else ""
            )
            subtotal_str = st.text_input(
                "Subtotal",
                value=str(data["subtotal"]) if data.get("subtotal") is not None else "",
            )
            tax_str = st.text_input(
                "Tax", value=str(data["tax"]) if data.get("tax") is not None else ""
            )

            st.write("Line items:")
            edited_items = st.data_editor(
                data.get("line_items", []),
                num_rows="dynamic",
                use_container_width=True,
            )

            if st.button("Save Receipt", type="primary"):
                corrected = {
                    "merchant": _blank_to_none(merchant),
                    "category": _blank_to_none(category),
                    "date": _blank_to_none(date_str),
                    "total": _blank_to_none_float(total_str),
                    "subtotal": _blank_to_none_float(subtotal_str),
                    "tax": _blank_to_none_float(tax_str),
                    "line_items": edited_items,
                }
                receipt_id = save_receipt(
                    corrected,
                    source_file=Path(st.session_state["current_path"]).name,
                    content_hash=content_hash,
                )
                st.success(f"Saved as receipt #{receipt_id}")
                del st.session_state["current_hash"]
                del st.session_state["current_data"]
                del st.session_state["current_path"]

elif page == "Browse Receipts":
    st.title("Your Receipts")
    with Session(engine) as session:
        receipts = session.query(Receipt).order_by(Receipt.date.desc()).all()
        rows = [
            {
                "ID": r.id,
                "Merchant": r.merchant or "—",
                "Category": r.category or "—",
                "Date": str(r.date) + (" (est.)" if r.date_is_estimated else ""),
                "Total": f"${r.total:.2f}" if r.total is not None else "—",
            }
            for r in receipts
        ]
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No receipts yet -- upload one to get started.")

elif page == "Ask a Question":
    st.title("Ask About Your Spending")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    for role, message in st.session_state["chat_history"]:
        with st.chat_message(role):
            st.write(message)

    question = st.chat_input("Ask a question about your receipts...")
    if question:
        st.session_state["chat_history"].append(("user", question))
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = ask(question)
            st.write(answer)
        st.session_state["chat_history"].append(("assistant", answer))
