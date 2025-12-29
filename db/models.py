# db/models.py
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Enum, ForeignKey,
    JSON, Boolean, Float, func, UniqueConstraint, CHAR
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .database import Base
import enum


class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)
    auth_provider = Column(String(50), default="local")  # local | google
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    threads = relationship("Thread", back_populates="user", cascade="all,delete")
    documents = relationship("Document", back_populates="user", cascade="all,delete")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all,delete")
    tokens = relationship("AuthToken", back_populates="user", cascade="all,delete")
    tools = relationship("UserTool", back_populates="user", cascade="all,delete")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all,delete")

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="password_reset_tokens")

class Thread(Base):
    __tablename__ = "threads"
    id = Column(String(64), primary_key=True)  # allow UUID strings
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    user = relationship("User", back_populates="threads")
    messages = relationship("Message", back_populates="thread", cascade="all,delete")
    documents = relationship(
        "Document",
        back_populates="thread",
        cascade="all,delete"
    )

class Message(Base):
    __tablename__ = "messages"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    thread_id = Column(String(64), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum('user', 'assistant', 'system', name="message_roles"), nullable=False)
    content = Column(Text, nullable=True)
    json_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    thread = relationship("Thread", back_populates="messages")
    provenance = relationship("QueryProvenance", back_populates="message", cascade="all,delete")

class Document(Base):
    __tablename__ = "documents"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    thread_id = Column(String(64), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=True)
    sha256_hash = Column(CHAR(64), nullable=False)
    __table_args__ = (
        UniqueConstraint("thread_id", "sha256_hash", name="uq_thread_file"),
    )
    status = Column(Enum('uploaded','processing','indexed','failed', name="doc_status"), nullable=False, server_default="uploaded")
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    user = relationship("User", back_populates="documents")
    thread = relationship("Thread", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all,delete")
    ingestion_jobs = relationship("IngestionJob", back_populates="document", cascade="all,delete")

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    json_metadata = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="chunks")
    embedding = relationship("EmbeddingMetadata", back_populates="chunk", uselist=False, cascade="all,delete")
    provenance_links = relationship("QueryProvenance", back_populates="chunk", cascade="all,delete")

    __table_args__ = (
        UniqueConstraint('document_id', 'chunk_index', name='uq_document_chunk_index'),
    )
    __mapper_args__ = {"confirm_deleted_rows": False}

class EmbeddingMetadata(Base):
    __tablename__ = "embeddings_metadata"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    chunk_id = Column(BigInteger, ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, unique=True)
    vector_id = Column(String(255), nullable=False)  # id in vector DB
    embedding_model = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    chunk = relationship("DocumentChunk", back_populates="embedding")
    __mapper_args__ = {"confirm_deleted_rows": False}

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum('pending','running','completed','failed', name="job_status"), nullable=False, server_default="pending")
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=False), nullable=True)
    finished_at = Column(DateTime(timezone=False), nullable=True)

    document = relationship("Document", back_populates="ingestion_jobs")
    __mapper_args__ = {"confirm_deleted_rows": False}

class QueryProvenance(Base):
    __tablename__ = "query_provenance"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    message_id = Column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    chunk_id = Column(BigInteger, ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False)
    score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    message = relationship("Message", back_populates="provenance")
    chunk = relationship("DocumentChunk", back_populates="provenance_links")
    __mapper_args__ = {"confirm_deleted_rows": False}

class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now())
    expires_at = Column(DateTime(timezone=False), nullable=True)

    user = relationship("User", back_populates="tokens")
    
class Tool(Base):
    __tablename__ = "tools"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    status = Column(
        Enum('active', 'inactive', name="tool_status"),
        nullable=False,
        server_default="active"
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now())
    
    user_tools = relationship("UserTool", back_populates="tool")

class UserTool(Base):
    __tablename__ = "user_tools"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tool_id = Column(BigInteger, ForeignKey("tools.id", ondelete="CASCADE"), nullable=False)
    usage_limit = Column(Integer, nullable=True)  # how many times user can use it
    status = Column(
        Enum('allowed', 'denied', name="user_tool_status"),
        nullable=False,
        server_default="allowed"
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    user = relationship("User", back_populates="tools")
    tool = relationship("Tool", back_populates="user_tools")


class UserSettings(Base):
    __tablename__ = "user_settings"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    preferred_model = Column(String(255), nullable=True)
    theme = Column(String(50), nullable=True)
    notification_enabled = Column(Boolean, default=True)
    preferred_tools = Column(JSON, nullable=True)  # array of tool ids or names

    user = relationship("User", back_populates="settings")




# ***********************  EXPENSE-TRACKER-MCP ***********************************

class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    subcategories = relationship(
        "ExpenseSubCategory",
        back_populates="category",
        cascade="all, delete-orphan",
    )

class ExpenseSubCategory(Base):
    __tablename__ = "expense_subcategories"
    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_category_subcategory"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("expense_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    category = relationship("ExpenseCategory", back_populates="subcategories")


class ExpenseType(enum.Enum):
    debit = "debit"
    credit = "credit"

class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[BigInteger] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


    date: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)

    category_id: Mapped[int] = mapped_column(
        ForeignKey("expense_categories.id"), nullable=False
    )
    subcategory_id: Mapped[int] = mapped_column(
        ForeignKey("expense_subcategories.id"), nullable=False
    )

    note: Mapped[str] = mapped_column(String(255), default="")
    type: Mapped[ExpenseType] = mapped_column(
        Enum(ExpenseType), default=ExpenseType.debit
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    user = relationship("User")
    category = relationship("ExpenseCategory")
    subcategory = relationship("ExpenseSubCategory")