from db.database import async_engine, AsyncSessionLocal, Base
import logging


logger = logging.getLogger(__name__)


# -------------------------------
# Async DB Init (create tables)
# -------------------------------
async def init_db():
    """
    Run at startup to create tables if they don't exist.
    In production, Alembic is recommended for migrations.
    """
    try:
        async with async_engine.begin() as conn:
            logger.info("Creating all tables (if not exist)...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Async DB initialization complete.")
    except Exception as exc:
        logger.exception("Async DB init failed: %s", exc)

# -------------------------------
# Async dependency for FastAPI
# -------------------------------
async def get_db():
    """
    Yield an async session for request-handling.
    Closes automatically after request.
    """
    async with AsyncSessionLocal() as session:
        yield session