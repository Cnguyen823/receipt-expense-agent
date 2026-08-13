from datetime import date as date_type

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from sqlalchemy import func
from sqlalchemy.orm import Session

from parse import CATEGORIES
from storage import Receipt, engine


# Applies the optional merchant/category/date filters shared by both tools
# to a SQLAlchemy query. merchant uses a case-insensitive partial match
# (ilike) since the agent's guess at a name may not match capitalization
# or the exact stored string exactly.
def _apply_filters(query, merchant, category, start_date, end_date):
    if merchant:
        query = query.filter(Receipt.merchant.ilike(f"%{merchant}%"))
    if category:
        query = query.filter(Receipt.category == category)
    if start_date:
        query = query.filter(Receipt.date >= date_type.fromisoformat(start_date))
    if end_date:
        query = query.filter(Receipt.date <= date_type.fromisoformat(end_date))
    return query


@tool
def sum_spending(
    merchant: str | None = None,
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> float:
    """Sum total spending across receipts, optionally filtered by merchant
    name (partial match), category, and/or date range. Dates must be in
    YYYY-MM-DD format."""
    with Session(engine) as session:
        query = _apply_filters(
            session.query(func.sum(Receipt.total)), merchant, category, start_date, end_date
        )
        return query.scalar() or 0.0


@tool
def lookup_receipts(
    merchant: str | None = None,
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Look up individual receipts, optionally filtered by merchant name
    (partial match), category, and/or date range. Dates must be in
    YYYY-MM-DD format. Returns up to `limit` results."""
    with Session(engine) as session:
        query = _apply_filters(
            session.query(Receipt), merchant, category, start_date, end_date
        )
        results = query.limit(limit).all()
        return [
            {
                "id": r.id,
                "merchant": r.merchant,
                "category": r.category,
                "date": str(r.date),
                "total": r.total,
            }
            for r in results
        ]


# Today's date is computed fresh each run (not hardcoded) so the agent can
# correctly resolve relative questions like "this month" into real date
# ranges when calling the tools above.
SYSTEM_PROMPT = (
    f"Today's date is {date_type.today().isoformat()}. Use this to resolve "
    "relative date references like 'this month' or 'last week' into actual "
    "start_date/end_date values when calling tools.\n\n"
    f"Valid categories are: {', '.join(CATEGORIES)}.\n\n"
    "If a question can't be confidently answered with the available tools "
    "-- e.g. it's ambiguous, or asks about data that isn't tracked -- ask "
    "the user for clarification instead of guessing."
)

model = ChatAnthropic(model="claude-sonnet-5")
agent = create_agent(model, tools=[sum_spending, lookup_receipts], system_prompt=SYSTEM_PROMPT)


# Sends a natural-language question through the agent and returns its
# final text answer.
def ask(question):
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    content = result["messages"][-1].content
    if isinstance(content, str):
        return content
    # content can be a list of typed blocks (e.g. a "thinking" block
    # alongside a "text" block) rather than a plain string -- extract just
    # the actual text, same underlying concept as parse.py's tool_use loop.
    return "".join(block["text"] for block in content if block.get("type") == "text")


if __name__ == "__main__":
    import sys

    print(ask(" ".join(sys.argv[1:])))
