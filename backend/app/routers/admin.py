"""
Admin Router - Tenant Management Endpoints

This module provides API endpoints for managing tenants in the iDone Chatbot System.
All endpoints require admin authentication via X-Admin-Key header.

Usage:
    - Create new tenants with unique API keys
    - Update tenant configurations (system prompts, LLM settings)
    - List all tenants with usage statistics
    - Delete tenants and all associated data (CASCADE)
    - Manage tenant documents (list, delete, update)
"""

from fastapi import APIRouter, Depends, HTTPException, Header, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
import uuid
from app.database import get_db
from app.schemas import (
    TenantCreate, TenantUpdate, TenantResponse, TenantListResponse,
    DocumentListResponse, MultiIngestResponse, DocumentUpdateRequest
)
from app.models import Document
from app.services.tenant_service import TenantService
from app.services.rag_service import rag_service
from app.services.vector_service import vector_service
from app.utils.helpers import process_file_content, clean_text
from app.config import settings
from loguru import logger


router = APIRouter(
    prefix="/admin",
    tags=["Admin - Tenant Management"],
    responses={
        401: {"description": "Invalid or missing admin API key"},
        403: {"description": "Forbidden - invalid admin key"},
        404: {"description": "Tenant not found"}
    }
)


def verify_admin_key(x_admin_key: Optional[str] = Header(None)):
    """
    Verify admin API key from X-Admin-Key header.
    
    Args:
        x_admin_key: Admin API key passed in header
        
    Returns:
        True if valid
        
    Raises:
        HTTPException: 401 if key is invalid
    """
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid admin API key"
        )
    return True


@router.post(
    "/tenants",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Tenant",
    description="""
Create a new tenant with a unique API key.
    
The tenant will have:
- A unique UUID identifier
- A 64-character randomly generated API key
- Default LLM settings (GPT-4o Mini, temperature 0.7)

Use the returned API key to authenticate tenant requests.
    """,
    response_description="Created tenant with generated API key"
)
async def create_tenant(
    tenant_data: TenantCreate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Create a new tenant in the system.
    
    **Request Body:**
    - name: Tenant/business name (required)
    - system_prompt: Custom system prompt for the LLM
    - llm_model: LLM model to use (default: gpt-4o-mini)
    - temperature: LLM temperature (0-2, default: 0.7)
    - max_tokens: Max tokens in response (default: 2000)
    
    **Returns:**
    - Full tenant object including the generated API key
    """
    service = TenantService(db)
    tenant = await service.create_tenant(tenant_data)
    logger.info(f"Created new tenant: {tenant.name} ({tenant.id})")
    return tenant


@router.get(
    "/tenants",
    response_model=List[TenantListResponse],
    summary="List All Tenants",
    description="""
Get a list of all tenants with their basic information.
    
Includes document count and chat count for each tenant.
    """,
    response_description="List of all tenants"
)
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Retrieve all tenants in the system.
    
    **Returns:**
    - Array of tenant objects with:
      - id, name, is_active, created_at
      - document_count: Number of uploaded documents
      - chat_count: Number of chat interactions
    """
    service = TenantService(db)
    tenants = await service.list_tenants()
    return tenants


@router.get(
    "/tenants/{tenant_id}",
    response_model=TenantResponse,
    summary="Get Tenant Details",
    description="""
Get detailed information about a specific tenant.
    
Includes the full API key (only shown once on creation).
    """,
    response_description="Detailed tenant information"
)
async def get_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Get details of a specific tenant by ID.
    
    **Path Parameters:**
    - tenant_id: UUID of the tenant
    
    **Returns:**
    - Full tenant object including API key
    """
    service = TenantService(db)
    tenant = await service.get_tenant_by_id(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Tenant not found"
        )
    return tenant


@router.put(
    "/tenants/{tenant_id}",
    response_model=TenantResponse,
    summary="Update Tenant",
    description="""
Update tenant settings including:
- Name
- System prompt
- LLM model and parameters
- Active status
    """,
    response_description="Updated tenant information"
)
async def update_tenant(
    tenant_id: str,
    tenant_data: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Update an existing tenant's configuration.
    
    **Path Parameters:**
    - tenant_id: UUID of the tenant
    
    **Request Body:**
    - name: Updated name (optional)
    - system_prompt: Updated system prompt (optional)
    - llm_model: Updated LLM model (optional)
    - temperature: Updated temperature 0-2 (optional)
    - max_tokens: Updated max tokens (optional)
    - is_active: Active status (optional)
    
    **Returns:**
    - Updated tenant object
    """
    service = TenantService(db)
    tenant = await service.update_tenant(tenant_id, tenant_data)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Tenant not found"
        )
    logger.info(f"Updated tenant: {tenant.name} ({tenant.id})")
    return tenant


@router.delete(
    "/tenants/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Tenant",
    description="""
Delete a tenant and ALL associated data.

⚠️ **WARNING**: This action is irreversible!

This will CASCADE delete:
- All uploaded documents
- All chat histories
- All vector embeddings in Qdrant
    """,
    response_description="Tenant successfully deleted"
)
async def delete_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Permanently delete a tenant and all their data.
    
    **Path Parameters:**
    - tenant_id: UUID of the tenant to delete
    
    **Returns:**
    - 204 No Content on success
    """
    service = TenantService(db)
    success = await service.delete_tenant(tenant_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Tenant not found"
        )
    logger.warning(f"Deleted tenant: {tenant_id}")
    return None


# ==================== Document Management Endpoints ====================

@router.get(
    "/tenants/{tenant_id}/documents",
    response_model=List[DocumentListResponse],
    summary="List Tenant Documents",
    description="""
    Get a list of all documents for a specific tenant.
    
    Returns document ID, filename, file type, chunk count, and creation date.
    """,
    response_description="List of tenant documents"
)
async def list_tenant_documents(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Retrieve all documents for a specific tenant.
    
    **Path Parameters:**
    - tenant_id: UUID of the tenant
    
    **Returns:**
    - Array of document objects
    """
    result = await db.execute(
        select(Document)
        .where(Document.tenant_id == tenant_id)
        .order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()
    return documents


@router.delete(
    "/tenants/{tenant_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Document",
    description="""
    Delete a specific document from the tenant's knowledge base.
    
    This will:
    - Remove the document record from PostgreSQL
    - Delete all vector embeddings from Qdrant
    """,
    response_description="Document successfully deleted"
)
async def delete_document(
    tenant_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Delete a specific document and its vectors.
    
    **Path Parameters:**
    - tenant_id: UUID of the tenant
    - document_id: UUID of the document to delete
    
    **Returns:**
    - 204 No Content on success
    """
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.tenant_id == tenant_id)
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    vector_service.delete_by_document_id(tenant_id, document_id)
    
    await db.delete(document)
    await db.commit()
    
    logger.info(f"Deleted document {document_id} for tenant {tenant_id}")
    return None


@router.put(
    "/tenants/{tenant_id}/documents/{document_id}",
    response_model=DocumentListResponse,
    summary="Update Text Document",
    description="""
    Update a text document's content.
    
    This will:
    - Delete existing vectors from Qdrant
    - Re-ingest the new text content
    - Update the document record in PostgreSQL
    
    Note: Only works for .txt file types.
    """,
    response_description="Updated document"
)
async def update_document(
    tenant_id: str,
    document_id: str,
    update_data: DocumentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Update a text document's content.
    
    **Path Parameters:**
    - tenant_id: UUID of the tenant
    - document_id: UUID of the document to update
    
    **Request Body:**
    - text: New text content
    
    **Returns:**
    - Updated document object
    """
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.tenant_id == tenant_id)
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    if document.file_type != 'txt' and document.file_type != 'text':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only text documents (.txt) can be edited"
        )
    
    vector_service.delete_by_document_id(tenant_id, document_id)
    
    content = clean_text(update_data.text)
    
    ingest_result = await rag_service.ingest_document(
        tenant_id=tenant_id,
        document_id=document_id,
        text=content,
        filename=document.filename
    )
    
    document.content = content[:5000]
    document.chunk_count = ingest_result["chunks_created"]
    document.is_indexed = ingest_result["success"]
    
    await db.commit()
    await db.refresh(document)
    
    logger.info(f"Updated document {document_id} for tenant {tenant_id}")
    return document


@router.post(
    "/tenants/{tenant_id}/documents",
    response_model=MultiIngestResponse,
    summary="Upload Multiple Files",
    description="""
    Upload multiple files to the tenant's knowledge base.
    
    Accepts multiple files in a single request.
    Each file will be processed, chunked, and indexed.
    """,
    response_description="Upload results for multiple files"
)
async def upload_multiple_files(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    files: List[UploadFile] = File(...),
    _: bool = Depends(verify_admin_key)
):
    """
    Upload and ingest multiple files.
    
    **Path Parameters:**
    - tenant_id: UUID of the tenant
    
    **Form Data:**
    - files: Multiple files to upload (PDF, DOCX, TXT)
    
    **Returns:**
    - Summary of successful/failed uploads
    """
    tenant_service = TenantService(db)
    tenant = await tenant_service.get_tenant_by_id(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )
    
    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is inactive"
        )
    
    results = []
    successful = 0
    failed = 0
    
    for file in files:
        try:
            content = await file.read()
            
            if not content:
                results.append({"filename": file.filename, "success": False, "error": "Empty file"})
                failed += 1
                continue
                
            if len(content) > 10 * 1024 * 1024:
                results.append({"filename": file.filename, "success": False, "error": "File too large (max 10MB)"})
                failed += 1
                continue
            
            text_content = process_file_content(file.filename or "unknown.txt", content)
            
            if not text_content or not text_content.strip():
                results.append({"filename": file.filename or "unknown", "success": False, "error": "Could not extract text"})
                failed += 1
                continue
            
            text_content = clean_text(text_content)
            document_id = str(uuid.uuid4())
            filename = file.filename or "unknown_file"
            
            result = await rag_service.ingest_document(
                tenant_id=tenant.id,
                document_id=document_id,
                text=text_content,
                filename=filename
            )
            
            file_type = filename.lower().split('.')[-1] if '.' in filename else 'unknown'
            
            document = Document(
                id=document_id,
                tenant_id=tenant.id,
                filename=file.filename,
                file_type=file_type,
                content=text_content[:5000],
                chunk_count=result["chunks_created"],
                is_indexed=result["success"]
            )
            db.add(document)
            
            results.append({
                "filename": file.filename,
                "success": result["success"],
                "document_id": document_id,
                "chunks_created": result["chunks_created"]
            })
            
            if result["success"]:
                successful += 1
            else:
                failed += 1
                
        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {e}")
            results.append({"filename": file.filename, "success": False, "error": str(e)})
            failed += 1
    
    await db.commit()
    
    return MultiIngestResponse(
        success=failed == 0,
        total_files=len(files),
        successful=successful,
        failed=failed,
        results=results
    )
