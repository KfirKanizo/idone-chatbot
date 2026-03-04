from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== Tenant Schemas ====================

class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    system_prompt: Optional[str] = "You are a helpful assistant."
    llm_model: Optional[str] = "llama-3.1-8b-instant"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2000


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    system_prompt: Optional[str] = None
    llm_model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)
    is_active: Optional[bool] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    api_key: str
    system_prompt: str
    llm_model: str
    temperature: float
    max_tokens: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    id: str
    name: str
    is_active: bool
    created_at: datetime
    document_count: Optional[int] = 0
    chat_count: Optional[int] = 0

    class Config:
        from_attributes = True


# ==================== Document Schemas ====================

class DocumentCreate(BaseModel):
    filename: str
    file_type: str
    content: str
    metadata: Optional[Dict[str, Any]] = {}


class DocumentResponse(BaseModel):
    id: str
    tenant_id: str
    filename: str
    file_type: str
    chunk_count: int
    is_indexed: bool
    created_at: datetime

    class Config:
        from_attributes = True


class IngestRequest(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None


class IngestResponse(BaseModel):
    success: bool
    document_id: str
    chunks_created: int
    message: str


# ==================== Chat Schemas ====================

class ChatRequest(BaseModel):
    api_key: str
    user_id: str
    message: str


class ChatResponse(BaseModel):
    response: str
    context_used: List[str]
    user_id: str
    timestamp: datetime


# ==================== Error Schemas ====================

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    database: str
    qdrant: str
    timestamp: datetime
