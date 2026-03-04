"""
Admin Router - Tenant Management Endpoints

This module provides API endpoints for managing tenants in the iDone Chatbot System.
All endpoints require admin authentication via X-Admin-Key header.

Usage:
    - Create new tenants with unique API keys
    - Update tenant configurations (system prompts, LLM settings)
    - List all tenants with usage statistics
    - Delete tenants and all associated data (CASCADE)
"""

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from app.database import get_db
from app.schemas import TenantCreate, TenantUpdate, TenantResponse, TenantListResponse
from app.services.tenant_service import TenantService
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
