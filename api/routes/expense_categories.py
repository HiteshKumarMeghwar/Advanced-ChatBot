from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
from pathlib import Path

from core.database import get_db
from core.config import BASE_DIR
from db.models import ExpenseCategory, ExpenseSubCategory

router = APIRouter(
    prefix="/expense-categories",
    tags=["Expense Categories"]
)

CATEGORIES_PATH = BASE_DIR / "MCP" / "servers" / "expense-tracker-mcp" / "categories.json"


@router.post("/seed", summary="Seed expense categories & subcategories from JSON")
async def seed_expense_categories(
    db: AsyncSession = Depends(get_db),
):
    if not CATEGORIES_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="categories.json file not found"
        )

    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    inserted_categories = 0
    inserted_subcategories = 0

    for category_name, subcategories in data.items():

        # Check / create category
        result = await db.execute(
            select(ExpenseCategory)
            .where(ExpenseCategory.name == category_name)
        )
        category = result.scalar_one_or_none()

        if not category:
            category = ExpenseCategory(name=category_name)
            db.add(category)
            await db.flush()  # ensures category.id is available
            inserted_categories += 1

        # Always include "other"
        for sub in set(subcategories + ["other"]):

            sub_result = await db.execute(
                select(ExpenseSubCategory)
                .where(
                    ExpenseSubCategory.category_id == category.id,
                    ExpenseSubCategory.name == sub,
                )
            )

            if sub_result.scalar_one_or_none():
                continue

            db.add(
                ExpenseSubCategory(
                    category_id=category.id,
                    name=sub,
                )
            )
            inserted_subcategories += 1

    await db.commit()

    return {
        "message": "Expense categories seeded successfully",
        "categories_added": inserted_categories,
        "subcategories_added": inserted_subcategories,
    }
