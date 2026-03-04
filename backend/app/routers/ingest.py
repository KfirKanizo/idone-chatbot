"""
Ingest Router - Document Upload & Knowledge Base Management

This module provides endpoints for uploading and indexing documents into the
tenant's knowledge base.

Documents are:
- Extracted (PDF, DOCX, TXT)
- Chunked into smaller pieces
- Embedded using OpenAI text-embedding-3-small
- Stored in Qdrant with tenant_id metadata filter

Supported file types:
- PDF (.pdf)
- Word Documents (.docx)
- Plain Text (.txt)
- Markdown (.md)
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.models import Document
from app.schemas import IngestResponse
from app.services.tenant_service import TenantService
from app.services.rag_service import rag_service
from app.utils.helpers import process_file_content, clean_text
from loguru import logger


router = APIRouter(
    prefix="/api",
    tags=["Knowledge Base - Ingest"],
    responses={
        400: {"description": "Bad request - invalid file or text"},
        401: {"description": "Invalid or missing API key"},
        403: {"description": "Tenant is inactive or key mismatch"},
        413: {"description": "File too large"},
        500: {"description": "Processing error"}
    }
)


async def verify_tenant_access(
    x_api_key: Optional[str] = Header(None, description="Tenant API key"),
    tenant_id: str = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify tenant API key and return tenant object.
    
    Validates:
    - API key is provided
    - API key is valid
    - Tenant is active
    - Tenant ID matches (if provided)
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="API key is required. Use X-API-Key header."
        )
    
    service = TenantService(db)
    tenant = await service.get_tenant_by_api_key(x_api_key)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid API key."
        )
    
    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Tenant is inactive."
        )
    
    if tenant_id and tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="API key does not match the specified tenant."
        )
    
    return tenant


@router.post(
    "/ingest/{tenant_id}/text",
    response_model=IngestResponse,
    summary="Ingest Text Content",
    description="""
## Upload Text to Knowledge Base

Add plain text content to the tenant's knowledge base.

### Use Cases
- Paste FAQ content
- Add product descriptions
- Upload policy documents
- Add custom responses

### Processing
1. Text is cleaned and normalized
2. Split into chunks (~1000 chars each, 200 char overlap)
3. Each chunk is embedded using OpenAI
4. Embeddings stored in Qdrant with tenant isolation

### Limits
- Max text size: ~1MB
- Each chunk is ~1000 characters
    """,
    response_description="Ingestion result with chunk count"
)
async def ingest_text(
    tenant_id: str,
    text: str = Form(..., description="Text content to ingest"),
    filename: str = Form("text_input.txt", description="Filename for reference"),
    db: AsyncSession = Depends(get_db),
    x_api_key: Optional[str] = Header(None)
):
    """
    Ingest text content into the tenant's knowledge base.
    
    **Path Parameters:**
    - tenant_id: UUID of the tenant
    
    **Form Data:**
    - text: The text content to ingest (required)
    - filename: Reference filename (default: text_input.txt)
    
    **Headers:**
    - X-API-Key: Tenant's API key
    
    **Returns:**
    - success: Boolean indicating success
    - document_id: Unique ID for the document
    - chunks_created: Number of chunks indexed
    - message: Status message
    
    **Example:**
    ```bash
    curl -X POST "https://chat.idone.co.il/api/ingest/{tenant_id}/text" \\
      -H "X-API-Key: your_api_key" \\
      -F "text=Your company was founded in 2020..." \\
      -F "filename=about_us.txt"
    ```
    """
    tenant = await verify_tenant_access(x_api_key, tenant_id, db)
    
    if not text or not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Text content is required and cannot be empty."
        )
    
    document_id = str(uuid.uuid4())
    content = clean_text(text)
    
    logger.info(f"Ingesting text for tenant {tenant.id}: {filename}")
    
    result = await rag_service.ingest_document(
        tenant_id=tenant.id,
        document_id=document_id,
        text=content,
        filename=filename
    )
    
    if result["success"]:
        document = Document(
            id=document_id,
            tenant_id=tenant.id,
            filename=filename,
            file_type="text",
            content=content[:5000],
            chunk_count=result["chunks_created"],
            is_indexed=True
        )
        db.add(document)
        await db.commit()
        logger.info(f"Text ingested successfully: {result['chunks_created']} chunks")
    
    return IngestResponse(
        success=result["success"],
        document_id=document_id,
        chunks_created=result["chunks_created"],
        message=result["message"]
    )


@router.post(
    "/ingest/{tenant_id}/file",
    response_model=IngestResponse,
    summary="Upload File",
    description="""
## Upload Document File

Upload a document file (PDF, DOCX, TXT) to the knowledge base.

### Supported File Types
- **PDF** (.pdf) - Extracted using PyPDF2
- **Word** (.docx) - Extracted using python-docx
- **Text** (.txt, .md) - Raw text extraction

### Processing
1. File is parsed based on type
2. Text is extracted
3. Split into chunks (~1000 chars each)
4. Each chunk embedded with OpenAI
5. Stored in Qdrant with tenant isolation

### Limits
- Max file size: 10MB
- Supported: .pdf, .docx, .doc, .txt, .md
    """,
    response_description="Upload result with chunk count"
)
async def ingest_file(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(..., description="File to upload (PDF, DOCX, TXT)"),
    x_api_key: Optional[str] = Header(None)
):
    """
    Upload and ingest a document file.
    
    **Path Parameters:**
    - tenant_id: UUID of the tenant
    
    **Form Data:**
    - file: The file to upload (required)
    
    **Headers:**
    - X-API-Key: Tenant's API key
    
    **Supported Formats:**
    - .pdf - PDF documents
    - .docx / .doc - Word documents
    - .txt / .md - Plain text
    
    **Returns:**
    - success: Boolean indicating success
    - document_id: Unique ID for the document
    - chunks_created: Number of chunks indexed
    - message: Status message
    
    **Example:**
    ```bash
    curl -X POST "https://chat.idone.co.il/api/ingest/{tenant_id}/file" \\
      -H "X-API-Key: your_api_key" \\
      -F "file=@document.pdf"
    ```
    """
    tenant = await verify_tenant_access(x_api_key, tenant_id, db)
    
    content = await file.read()
    
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Empty file uploaded."
        )
    
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, 
            detail="File too large. Maximum size is 10MB."
        )
    
    logger.info(f"Processing file for tenant {tenant.id}: {file.filename}")
    
    text_content = process_file_content(file.filename, content)
    
    if not text_content or not text_content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Could not extract text from file. Ensure file is not encrypted or corrupted."
        )
    
    text_content = clean_text(text_content)
    document_id = str(uuid.uuid4())
    
    result = await rag_service.ingest_document(
        tenant_id=tenant.id,
        document_id=document_id,
        text=text_content,
        filename=file.filename
    )
    
    file_type = file.filename.lower().split('.')[-1] if '.' in file.filename else 'unknown'
    
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
    await db.commit()
    
    logger.info(f"File ingested: {file.filename} -> {result['chunks_created']} chunks")
    
    return IngestResponse(
        success=result["success"],
        document_id=document_id,
        chunks_created=result["chunks_created"],
        message=result["message"]
    )
