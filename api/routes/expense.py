from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from core.database import get_db
from db.models import Expense, ExpenseType, User
from api.dependencies import get_current_user
from sqlalchemy.orm import selectinload
from typing import Optional
from fastapi import Query

router = APIRouter(prefix="/expenses", tags=["Expenses"])


@router.get("/list")
async def list_expenses(
    type: Optional[ExpenseType] = Query(None),
    category_id: Optional[int] = Query(None),
    date: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(Expense)
        .options(
            selectinload(Expense.category),
            selectinload(Expense.subcategory),
        )
        .where(Expense.user_id == user.id)
    )

    if type:
        query = query.where(Expense.type == type)
    if category_id:
        query = query.where(Expense.category_id == category_id)
    if date:
        query = query.where(Expense.date == date)
    if start_date:
        query = query.where(Expense.date >= start_date)
    if end_date:
        query = query.where(Expense.date <= end_date)

    result = await db.execute(query)
    expenses = result.scalars().all()

    items = [
        {
            "id": e.id,
            "date": e.date,
            "amount": e.amount,
            "type": e.type.value,
            "note": e.note,
            "category": {
                "id": e.category.id,
                "name": e.category.name,
            },
            "subcategory": {
                "id": e.subcategory.id,
                "name": e.subcategory.name,
            },
        }
        for e in expenses
    ]

    debit_total = sum(e.amount for e in expenses if e.type == ExpenseType.debit)
    credit_total = sum(e.amount for e in expenses if e.type == ExpenseType.credit)

    by_category = {}
    for e in expenses:
        name = e.category.name
        by_category[name] = by_category.get(name, 0) + e.amount

    return {
        "items": items,
        "summary": {
            "monthly_total": debit_total - credit_total,
            "debit_total": debit_total,
            "credit_total": credit_total,
            "by_category": [
                {"name": k, "total": v} for k, v in by_category.items()
            ],
        },
    }

