
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import ExpenseCategory, ExpenseSubCategory


async def get_or_create_category(
    db: AsyncSession,
    category_name: str | None,
):
    category_name = category_name or "miscellaneous"

    res = await db.execute(
        select(ExpenseCategory).where(ExpenseCategory.name == category_name)
    )
    category = res.scalar_one_or_none()

    if not category:
        category = ExpenseCategory(name=category_name)
        db.add(category)
        await db.flush()

    return category


async def get_or_create_subcategory(
    db: AsyncSession,
    category_id: int,
    sub_name: str | None,
):
    sub_name = sub_name or "other"

    res = await db.execute(
        select(ExpenseSubCategory)
        .where(
            ExpenseSubCategory.category_id == category_id,
            ExpenseSubCategory.name == sub_name,
        )
    )
    sub = res.scalar_one_or_none()

    if not sub:
        sub = ExpenseSubCategory(
            category_id=category_id,
            name=sub_name,
        )
        db.add(sub)
        await db.flush()

    return sub
