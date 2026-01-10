# db/models.py
from sqlalchemy import (
    Column, Index, Integer, BigInteger, String, Text, DateTime, Enum, ForeignKey,
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
    mcp_servers = relationship(
        "MCPServer",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all,delete")
    episodic_memories = relationship("EpisodicMemory", back_populates="user", cascade="all, delete-orphan")
    semantic_memories = relationship("SemanticMemory", back_populates="user", cascade="all, delete-orphan")
    procedural_rules = relationship("ProceduralMemory", back_populates="user", cascade="all, delete-orphan")
    semantic_embeddings = relationship("SemanticEmbedding", back_populates="user", cascade="all, delete-orphan")
    user_memory_settings = relationship("UserMemorySetting", back_populates="user", cascade="all, delete-orphan", uselist=False)

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
    episodic_memories = relationship("EpisodicMemory", back_populates="thread", cascade="all,delete")
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
    image_url = Column(String(512), nullable=True)
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
    description = Column(Text, nullable=True)
    status = Column(
        Enum('active', 'inactive', name="tool_status"),
        nullable=False,
        server_default="active",
    )
    scope = Column(
        Enum('global', 'mcp', name="tool_scope"),
        nullable=False,
        server_default="global",
        index=True,
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
    mcp_links = relationship(
        "MCPServerUserTool",
        back_populates="user_tool",
        cascade="all, delete-orphan",
    )

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


class MCPServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    name = Column(String(100), nullable=False)
    transport = Column(String(50), nullable=False)

    command = Column(Text, nullable=True)
    args = Column(JSON, nullable=True)
    url = Column(String(500), nullable=True)
    extra = Column(JSON, nullable=True)

    owner_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    user = relationship("User", back_populates="mcp_servers")
    user_tool_links = relationship(
        "MCPServerUserTool",
        cascade="all, delete-orphan",
        back_populates="mcp_server",
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_user_mcp_name"),
    )

class MCPServerUserTool(Base):
    __tablename__ = "mcp_server_user_tools"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    mcp_server_id = Column(
        BigInteger,
        ForeignKey("mcp_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_tool_id = Column(
        BigInteger,
        ForeignKey("user_tools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime, server_default=func.now())

    mcp_server = relationship("MCPServer", back_populates="user_tool_links")
    user_tool = relationship(
        "UserTool",
        back_populates="mcp_links",
    )

    __table_args__ = (
        UniqueConstraint(
            "mcp_server_id",
            "user_tool_id",
            name="uq_mcp_user_tool",
        ),
    )



# ***********************  Memory system ***********************************
class EpisodicMemory(Base):
    __tablename__ = "episodic_memories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id = Column(String(64), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(10), nullable=False)          # user / assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_user_thread_time", "user_id", "thread_id", "created_at"),)

    user = relationship("User", back_populates="episodic_memories")
    thread = relationship("Thread", back_populates="episodic_memories")

class ProceduralMemory(Base):
    __tablename__ = "procedural_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    rules = Column(Text, nullable=False)               # json list of strings
    confidence = Column(Float, nullable=True)
    fingerprint = Column(String(32), nullable=False, index=True)
    active = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        Index("ix_procedural_fp", "user_id", "fingerprint"),  # <-- fast dedup lookup
    )
    user = relationship("User", back_populates="procedural_rules")

class SemanticMemory(Base):
    __tablename__ = "semantic_memories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fact = Column(Text, nullable=False)                # human-readable sentence
    embedding_id = Column(String(64), nullable=False, unique=True)  # faiss vector id
    fingerprint = Column(String(128), nullable=True, index=True)  # normalized + hashed
    confidence = Column(Float, nullable=True)
    active        = Column(Boolean, default=True, index=True)
    retention_until = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("ix_semantic_dedup", "user_id", "fingerprint"),
        Index("ix_semantic_created", "user_id", "created_at"),
    )

    embedding = relationship(
        "SemanticEmbedding",
        back_populates="memory",
        cascade="all, delete",          # <--  if you delete the embedding, delete the fact too
        uselist=False,
    )
    user = relationship("User", back_populates="semantic_memories")

class SemanticEmbedding(Base):
    __tablename__ = "semantic_embeddings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vector_id = Column(
        String(255), nullable=False, unique=True
    )
    embedding_model = Column(String(128), nullable=False)
    created_at = Column(
        DateTime(timezone=False), server_default=func.now()
    )
    semantic_memory_id = Column(
        Integer,
        ForeignKey("semantic_memories.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,     # enforces 1-to-1
        index=True,
    )
    memory = relationship(
        "SemanticMemory",
        back_populates="embedding",
        cascade="all, delete",          # <--  when SemanticMemory row is deleted, this row auto-vanishes
        uselist=False,                  # 1-to-1
    )
    user = relationship("User", back_populates="semantic_embeddings")
    __table_args__ = (
        Index("idx_semantic_user_vector", "user_id", "vector_id"),
    )

class UserMemorySetting(Base):
    __tablename__ = "user_memory_settings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    allow_episodic = Column(Boolean, default=True)
    allow_semantic = Column(Boolean, default=True)
    allow_procedural = Column(Boolean, default=True)
    allow_long_conversation_memory = Column(Boolean, default=True)
    semantic_retention_days = Column(Integer, default=90)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="user_memory_settings")




# ***********************  Admin system ***********************************
# class Admin(Base):
#     __tablename__ = "admins"
#     id = Column(BigInteger, primary_key=True)
#     email = Column(String(255), unique=True, nullable=False)
#     password_hash = Column(String(255), nullable=False)
#     role = Column(Enum("super_admin", "ops", "support", name="admin_roles"))
#     active = Column(Boolean, default=True)
#     created_at = Column(DateTime, server_default=func.now())


# class GlobalMemoryPolicy(Base):
#     __tablename__ = "global_memory_policies"
#     id = Column(Integer, primary_key=True)
#     max_semantic_days = Column(Integer)
#     episodic_enabled = Column(Boolean)
#     semantic_enabled = Column(Boolean)
#     procedural_enabled = Column(Boolean)
#     updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# class SystemEvent(Base):
#     __tablename__ = "system_events"
#     id = Column(BigInteger, primary_key=True)
#     level = Column(Enum("info","warning","error","critical"))
#     service = Column(String(100))
#     message = Column(Text)
#     metadata = Column(JSON)
#     created_at = Column(DateTime, server_default=func.now())


# class AuditLog(Base):
#     __tablename__ = "audit_logs"
#     id = Column(BigInteger, primary_key=True)
#     actor_type = Column(Enum("admin","system"))
#     actor_id = Column(BigInteger)
#     action = Column(String(255))
#     target_type = Column(String(100))
#     target_id = Column(BigInteger)
#     metadata = Column(JSON)
#     created_at = Column(DateTime, server_default=func.now())


class MessageFeedback(Base):
    __tablename__ = "message_feedback"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)

    rating = Column(Enum("up", "down", name="feedback_rating"), nullable=False)
    reason = Column(String(255), nullable=True)   # optional user text / enum later

    model = Column(String(128), nullable=True)    # which model generated this
    tool_used = Column(String(128), nullable=True)  # tool name if any
    latency_ms = Column(Float, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_feedback_message", "message_id"),
        Index("ix_feedback_user", "user_id"),
    )


# class FeedbackReview(Base):
#     __tablename__ = "feedback_reviews"
#     id = Column(BigInteger, primary_key=True)
#     feedback_id = Column(BigInteger, ForeignKey("message_feedback.id"))
#     admin_id = Column(BigInteger, ForeignKey("admins.id"))
#     note = Column(Text)
#     created_at = Column(DateTime, server_default=func.now())


# class SystemConfig(Base):
#     __tablename__ = "system_config"

#     key = Column(String(100), primary_key=True)
#     value = Column(JSON, nullable=False)
#     value_type = Column(Enum(
#         "string", "int", "float", "bool", "json", name="config_types"
#     ), nullable=False)

#     description = Column(Text, nullable=True)
#     editable = Column(Boolean, default=True)
#     requires_restart = Column(Boolean, default=False)

#     updated_by_admin_id = Column(BigInteger, ForeignKey("admins.id"), nullable=True)
#     updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# class ConfigAuditLog(Base):
#     __tablename__ = "config_audit_logs"

#     id = Column(BigInteger, primary_key=True)
#     admin_id = Column(BigInteger, ForeignKey("admins.id"))
#     key = Column(String(100))
#     old_value = Column(JSON)
#     new_value = Column(JSON)
#     created_at = Column(DateTime, server_default=func.now())
