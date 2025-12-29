
# Because ////
# main.py
# └── expense-tracker-mcp (1)
#     └── servers (2)
#         └── MCP (3)
#             └── Advanced-ChatBot (PROJECT ROOT)
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))


from fastmcp import FastMCP
from db.database import AsyncSessionLocal
from db.models import Expense, ExpenseSubCategory, ExpenseType
from services.expense_helpers import (
    get_or_create_category,
    get_or_create_subcategory,
)
from db.models import ExpenseCategory
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

# -----  REMOVE MODULES FROM GLOBALS  -----
del sys, Path, PROJECT_ROOT      # ←  crucial

mcp = FastMCP("ExpenseTrackerMCP")



@mcp.tool
async def record_expense(
    user_id: str | None = None,
    date: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    note: str | None = None,
    type: str | None = None,
    expense_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    # *,
    # context: dict | None = None,
) -> dict:
    """
    Record a user expense or credit.
    - Always succeeds
    - Auto-creates category/subcategory
    - Defaults to 'miscellaneous' / 'other'
    - User got from state 
    """

    # user_id = context.get("user_id") if isinstance(context, dict) else None

    if not user_id:
        return {
            "status": "ERROR",
            "message": "Missing user identity. Operation aborted.",
        }

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                cat = await get_or_create_category(db, category)
                sub = await get_or_create_subcategory(db, cat.id, subcategory)

                # default type
                expense_type = ExpenseType.debit
                if type is not None and type in ExpenseType.__members__:
                    expense_type = ExpenseType[type]

                date = date or "today"
                expense = Expense(
                    user_id=int(user_id),
                    date= date,
                    amount=amount,
                    category_id=cat.id,
                    subcategory_id=sub.id,
                    note=note,
                    type=expense_type,
                )

                db.add(expense)
                await db.flush()  # ensures expense.id

            return {
                "status": "SUCCESS",
                "expense_id": expense.id,
                "category": cat.name,
                "subcategory": sub.name,
                "amount": float(amount),
                "date": date,
                "note": note,
                "type": expense_type.name,
            }

    except Exception as exc:
        return {
            "status": "ERROR",
            "message": "Failed to record expense. Please retry.",
            "reason": str(exc),
        }
record_expense.__qualname__ = "record_expense"
    

@mcp.tool
async def list_cat_subcat_expense(
    user_id: str | None = None,
    date: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    note: str | None = None,
    type: str | None = None,
    expense_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    # *,
    # context: dict | None = None,
):
    """
    List all categories with their subcategories.
    Eg:-> Format:
    {
        "education": ["tuition_fees", "books", "other"],
        "food_and_dining": ["groceries", "restaurants", "other"],
        ...
    }
    """
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(ExpenseCategory)
                .options(selectinload(ExpenseCategory.subcategories))
                .order_by(ExpenseCategory.name.asc())
            )

            result = await db.execute(stmt)
            categories = result.scalars().all()

            data: dict[str, list[str]] = {}

            for cat in categories:
                subs = [s.name for s in cat.subcategories]
                if "other" not in subs:
                    subs.append("other")
                data[cat.name] = sorted(subs)

            return {
                "status": "SUCCESS",
                "data": data,
            }

    except Exception as exc:
        return {
            "status": "ERROR",
            "message": "Failed to load categories",
            "reason": str(exc),
        }
list_cat_subcat_expense.__qualname__ = "list_cat_subcat_expense"


@mcp.tool
async def find_expenses(
    user_id: str | None = None,
    date: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    note: str | None = None,
    type: str | None = None,
    expense_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    # *,
    # context: dict | None = None,
) -> dict:
    """Find matching expenses for identification (read-only)."""

    # user_id = context.get("user_id") if isinstance(context, dict) else None
    if not user_id:
        return {"status": "ERROR", "message": "Missing user identity"}

    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(Expense)
                .where(Expense.user_id == int(user_id))
                .options(
                    selectinload(Expense.category),
                    selectinload(Expense.subcategory),
                )
            )

            if date:
                stmt = stmt.where(Expense.date == date)
            if category:
                stmt = stmt.where(Expense.category.has(name=category))
            if amount is not None:
                stmt = stmt.where(Expense.amount == amount)
            if note:
                stmt = stmt.where(Expense.note.ilike(f"%{note}%"))

            stmt = stmt.order_by(Expense.date.desc()).limit(5)

            result = await db.execute(stmt)
            expenses = result.scalars().all()

            return {
                "status": "SUCCESS",
                "results": [
                    {
                        "expense_id": e.id,
                        "date": e.date,
                        "amount": float(e.amount),
                        "category": e.category.name,
                        "subcategory": e.subcategory.name,
                        "note": e.note,
                        "type": e.type.value,
                    }
                    for e in expenses
                ],
            }

    except Exception as exc:
        return {
            "status": "ERROR",
            "message": "Failed to find expenses",
            "reason": str(exc),
        }
find_expenses.__qualname__ = "find_expenses"


@mcp.tool
async def update_expense(
    user_id: str | None = None,
    date: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    note: str | None = None,
    type: str | None = None,
    expense_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    # *,
    # context: dict | None = None,
) -> dict:
    """
    Update an existing expense by user_id + expense_id.
    """

    # ---------- HARD VALIDATION ----------
    try:
        expense_id = int(expense_id) if expense_id is not None else None
    except (TypeError, ValueError):
        return {
            "status": "ERROR",
            "message": "Invalid expense_id",
            "received": expense_id,
        }

    if not user_id or not expense_id:
        return {"status": "ERROR", "message": "Missing user_id or expense_id"}

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                expense = await db.get(Expense, expense_id)
                if not expense or expense.user_id != int(user_id):
                    return {"status": "NOT_FOUND", "expense_id": expense_id}

                # --- CATEGORY ---
                if category is not None:
                    cat = await get_or_create_category(db, category)
                    expense.category_id = cat.id
                else:
                    cat = await db.get(ExpenseCategory, expense.category_id)

                # --- SUBCATEGORY ---
                if subcategory is not None:
                    sub = await get_or_create_subcategory(
                        db, expense.category_id, subcategory
                    )
                    expense.subcategory_id = sub.id
                else:
                    sub = await db.get(ExpenseSubCategory, expense.subcategory_id)

                if date is not None:
                    expense.date = date
                if amount is not None:
                    expense.amount = amount
                if note is not None:
                    expense.note = note

                # default type
                expense_type = ExpenseType.debit
                if type is not None and type in ExpenseType.__members__:
                    expense_type = ExpenseType[type]

                expense.type = expense_type

            return {
                "status": "SUCCESS",
                "expense_id": expense.id,
                "amount": amount,
                "category": cat.name,
                "subcategory": sub.name,
                "type": expense_type.name,
                "date": date
            }

    except Exception as exc:
        # import traceback
        # traceback.print_exc()
        return {
            "status": "ERROR",
            "message": "Failed to update expense",
            "reason": str(exc),
        }
update_expense.__qualname__ = "update_expense"


@mcp.tool
async def remove_expense(
    user_id: str | None = None,
    date: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    note: str | None = None,
    type: str | None = None,
    expense_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    # *,
    # context: dict | None = None,
) -> dict:
    """
    Delete an expense by user_id + expense_id.
    """

    # ---------- HARD VALIDATION ----------
    try:
        expense_id = int(expense_id) if expense_id is not None else None
    except (TypeError, ValueError):
        return {
            "status": "ERROR",
            "message": "Invalid expense_id",
            "received": expense_id,
        }

    if not user_id or not expense_id:
        return {"status": "ERROR", "message": "Missing user_id or expense_id"}

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                expense = await db.get(Expense, expense_id)
                if not expense or expense.user_id != int(user_id):
                    return {"status": "NOT_FOUND", "expense_id": expense_id}

                await db.delete(expense)

            return {"status": "SUCCESS", "deleted_id": expense_id}

    except Exception as exc:
        return {
            "status": "ERROR",
            "message": "Failed to delete expense",
            "reason": str(exc),
        }
remove_expense.__qualname__ = "remove_expense"
    

@mcp.tool
async def record_credit(
    user_id: str | None = None,
    date: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    note: str | None = None,
    type: str | None = None,
    expense_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    # *,
    # context: dict | None = None,
) -> dict:
    """
    Record a credit (incoming money).
    """

    # user_id = context.get("user_id") if isinstance(context, dict) else None
    if not user_id:
        return {"status": "ERROR", "message": "Missing user identity"}

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                cat = await get_or_create_category(db, category)
                sub = await get_or_create_subcategory(db, cat.id, subcategory)

                # default type
                expense_type = ExpenseType.debit
                if type is not None and type in ExpenseType.__members__:
                    expense_type = ExpenseType[type]

                expense = Expense(
                    user_id=int(user_id),
                    date=date,
                    amount=amount,
                    category_id=cat.id,
                    subcategory_id=sub.id,
                    note=note,
                    type=expense_type,
                )

                db.add(expense)
                await db.flush()

            return {
                "status": "SUCCESS",
                "expense_id": expense.id,
                "category": cat.name,
                "subcategory": sub.name,
                "type": "credit",
            }

    except Exception as exc:
        return {
            "status": "ERROR",
            "message": "Failed to record credit",
            "reason": str(exc),
        }
record_credit.__qualname__ = "record_credit"


@mcp.tool
async def list_user_expenses(
    user_id: str | None = None,
    date: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    note: str | None = None,
    type: str | None = None,
    expense_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    # *,
    # context: dict | None = None,
) -> dict:
    """
    List user expenses with optional date filtering.
    """

    # user_id = context.get("user_id") if isinstance(context, dict) else None
    if not user_id:
        return {"status": "ERROR", "message": "Missing user identity"}

    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(Expense)
                .where(Expense.user_id == int(user_id))
                .options(
                    selectinload(Expense.category),
                    selectinload(Expense.subcategory),
                )
            )

            if start_date and end_date:
                stmt = stmt.where(Expense.date.between(start_date, end_date))

            stmt = stmt.order_by(Expense.date.desc())

            result = await db.execute(stmt)
            expenses = result.scalars().all()

            return {
                "status": "SUCCESS",
                "expenses": [
                    {
                        "id": e.id,
                        "date": e.date,
                        "amount": float(e.amount),
                        "category": e.category.name,
                        "subcategory": e.subcategory.name,
                        "note": e.note,
                        "type": e.type.value,
                    }
                    for e in expenses
                ],
            }

    except Exception as exc:
        return {
            "status": "ERROR",
            "message": "Failed to list expenses",
            "reason": str(exc),
        }
list_user_expenses.__qualname__ = "list_user_expenses"



@mcp.tool
async def summarize_user_expenses(
    user_id: str | None = None,
    date: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    note: str | None = None,
    type: str | None = None,
    expense_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    # *,
    # context: dict | None = None,
) -> dict:
    """
    Summarize expenses grouped by category.
    """

    # user_id = context.get("user_id") if isinstance(context, dict) else None
    if not user_id:
        return {"status": "ERROR", "message": "Missing user identity"}

    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(
                    ExpenseCategory.name.label("category"),
                    func.sum(Expense.amount).label("total_amount"),
                )
                .join(Expense, Expense.category_id == ExpenseCategory.id)
                .where(Expense.user_id == int(user_id))
                .group_by(ExpenseCategory.name)
                .order_by(ExpenseCategory.name.asc())
            )

            if start_date and end_date:
                stmt = stmt.where(Expense.date.between(start_date, end_date))

            if category:
                stmt = stmt.where(ExpenseCategory.name == category)

            result = await db.execute(stmt)

            return {
                "status": "SUCCESS",
                "summary": [
                    {
                        "category": row.category,
                        "total_amount": float(row.total_amount),
                    }
                    for row in result
                ],
            }

    except Exception as exc:
        return {
            "status": "ERROR",
            "message": "Failed to summarize expenses",
            "reason": str(exc),
        }
summarize_user_expenses.__qualname__ = "summarize_user_expenses"



if __name__ == "__main__":
    mcp.run()
