import uuid
import datetime
from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    api_key = Column(String(64), unique=True, nullable=False, index=True)
    system_prompt = Column(Text, default="You are a helpful assistant.")
    llm_model = Column(String(50), default="llama-3.1-8b-instant")
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2000)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    chat_histories = relationship("ChatHistory", back_populates="tenant", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="tenant", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tenant {self.name} ({self.id})>"


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    chunk_count = Column(Integer, default=0)
    extra_data = Column(JSON, default={})
    is_indexed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant", back_populates="documents")

    def __repr__(self):
        return f"<Document {self.filename} ({self.id})>"


class ChatHistory(Base):
    __tablename__ = "chat_histories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    context_used = Column(JSON, default=[])
    extra_data = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="chat_histories")

    def __repr__(self):
        return f"<ChatHistory {self.id} - Tenant: {self.tenant_id}>"
