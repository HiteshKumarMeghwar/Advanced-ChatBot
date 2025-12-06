from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from core.config import ASYNC_DATABASE_URL # create this in your config, e.g. mysql+asyncmy://...


# Example ASYNC_DATABASE_URL for MySQL (asyncmy driver):
# mysql+asyncmy://username:password@host:port/chatbot_db


async_engine = create_async_engine(
ASYNC_DATABASE_URL,
echo=False,
future=True,
)


AsyncSessionLocal = async_sessionmaker(
bind=async_engine,
expire_on_commit=False,
class_=AsyncSession,
)


Base = declarative_base()