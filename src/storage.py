import hashlib
from datetime import date as date_type

from sqlalchemy import Date, Float, ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

DB_PATH = "sqlite:///data/receipts.db"


class Base(DeclarativeBase):
    pass


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # SHA-256 of the source image's bytes, not its filename -- lets us
    # detect an already-processed receipt even if it's renamed or
    # re-uploaded under a different name later (e.g. via a future UI).
    # source_file is kept only for human-readable reference.
    content_hash: Mapped[str] = mapped_column(String, unique=True)
    source_file: Mapped[str] = mapped_column(String)
    merchant: Mapped[str | None] = mapped_column(String, nullable=True)
    # One of parse.py's CATEGORIES, or null if genuinely unclear. Left for
    # a human to fill in later via a future correction UI rather than
    # guessed. See docs/decisions.md.
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    # date_is_estimated distinguishes a real extracted date from a fallback
    # to today's date, so future date-range queries don't silently treat
    # the two as equally reliable. See docs/decisions.md.
    date: Mapped[date_type] = mapped_column(Date)
    date_is_estimated: Mapped[bool] = mapped_column(default=False)
    subtotal: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Nullable: parse.py's schema requires this key be present in its
    # response, but the value itself may be null when genuinely
    # undeterminable from a badly OCR'd receipt. See docs/decisions.md.
    total: Mapped[float | None] = mapped_column(Float, nullable=True)

    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"))
    name: Mapped[str] = mapped_column(String)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    receipt: Mapped["Receipt"] = relationship(back_populates="line_items")


engine = create_engine(DB_PATH)


# Creates the receipts.db file and tables if they don't already exist.
# Safe to call every run -- does nothing if tables are already present.
def init_db():
    Base.metadata.create_all(engine)


# Hashes a file's actual bytes (not its name), so the same image is
# recognized as a duplicate even if it's renamed.
def compute_file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# Checks whether a receipt with this content hash has already been saved,
# so the batch pipeline can skip it before paying for OCR/LLM calls again.
def receipt_exists(content_hash):
    with Session(engine) as session:
        existing = session.query(Receipt).filter_by(content_hash=content_hash).first()
        return existing is not None


# Takes a parsed receipt dict (parse.py's output shape) and persists it as
# a Receipt row with related LineItem rows. Falls back to today's date,
# flagged via date_is_estimated, when parse.py couldn't extract one.
def save_receipt(receipt_data, source_file, content_hash):
    date_str = receipt_data.get("date")
    if date_str:
        parsed_date = date_type.fromisoformat(date_str)
        date_is_estimated = False
    else:
        parsed_date = date_type.today()
        date_is_estimated = True

    receipt = Receipt(
        content_hash=content_hash,
        source_file=source_file,
        merchant=receipt_data.get("merchant"),
        category=receipt_data.get("category"),
        date=parsed_date,
        date_is_estimated=date_is_estimated,
        subtotal=receipt_data.get("subtotal"),
        tax=receipt_data.get("tax"),
        total=receipt_data["total"],
        line_items=[
            LineItem(
                name=item["name"],
                quantity=item.get("quantity"),
                unit_price=item.get("unit_price"),
                total_price=item.get("total_price"),
            )
            for item in receipt_data.get("line_items", [])
        ],
    )

    with Session(engine) as session:
        session.add(receipt)
        session.commit()
        return receipt.id
