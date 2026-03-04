import uuid
import secrets
import string
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Tenant, Document, ChatHistory
from app.schemas import TenantCreate, TenantUpdate, TenantResponse
from loguru import logger


def generate_api_key() -> str:
    """Generate a secure random API key"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))


class TenantService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_tenant(self, tenant_data: TenantCreate) -> Tenant:
        """Create a new tenant with a unique API key"""
        api_key = generate_api_key()
        
        tenant = Tenant(
            id=str(uuid.uuid4()),
            name=tenant_data.name,
            api_key=api_key,
            system_prompt=tenant_data.system_prompt or "You are a helpful assistant.",
            llm_model=tenant_data.llm_model or "gpt-4o-mini",
            temperature=tenant_data.temperature or 0.7,
            max_tokens=tenant_data.max_tokens or 2000,
        )
        
        self.db.add(tenant)
        await self.db.commit()
        await self.db.refresh(tenant)
        
        logger.info(f"Created tenant: {tenant.name} ({tenant.id})")
        return tenant

    async def get_tenant_by_id(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID"""
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_tenant_by_api_key(self, api_key: str) -> Optional[Tenant]:
        """Get tenant by API key - critical for authentication"""
        result = await self.db.execute(
            select(Tenant).where(Tenant.api_key == api_key)
        )
        return result.scalar_one_or_none()

    async def update_tenant(self, tenant_id: str, tenant_data: TenantUpdate) -> Optional[Tenant]:
        """Update tenant settings"""
        tenant = await self.get_tenant_by_id(tenant_id)
        if not tenant:
            return None
        
        update_data = tenant_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(tenant, field, value)
        
        await self.db.commit()
        await self.db.refresh(tenant)
        
        logger.info(f"Updated tenant: {tenant.name} ({tenant.id})")
        return tenant

    async def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant and all associated data"""
        tenant = await self.get_tenant_by_id(tenant_id)
        if not tenant:
            return False
        
        await self.db.delete(tenant)
        await self.db.commit()
        
        logger.info(f"Deleted tenant: {tenant_id}")
        return True

    async def list_tenants(self) -> List[dict]:
        """List all tenants with document and chat counts"""
        result = await self.db.execute(
            select(
                Tenant.id,
                Tenant.name,
                Tenant.is_active,
                Tenant.created_at,
                func.count(Document.id).label('document_count'),
                func.count(ChatHistory.id).label('chat_count')
            )
            .outerjoin(Document, Document.tenant_id == Tenant.id)
            .outerjoin(ChatHistory, ChatHistory.tenant_id == Tenant.id)
            .group_by(Tenant.id)
            .order_by(Tenant.created_at.desc())
        )
        
        rows = result.all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "is_active": row.is_active,
                "created_at": row.created_at,
                "document_count": row.document_count or 0,
                "chat_count": row.chat_count or 0
            }
            for row in rows
        ]

    async def get_tenant_stats(self, tenant_id: str) -> Optional[dict]:
        """Get statistics for a specific tenant"""
        tenant = await self.get_tenant_by_id(tenant_id)
        if not tenant:
            return None
        
        doc_result = await self.db.execute(
            select(func.count(Document.id)).where(Document.tenant_id == tenant_id)
        )
        doc_count = doc_result.scalar()
        
        chat_result = await self.db.execute(
            select(func.count(ChatHistory.id)).where(ChatHistory.tenant_id == tenant_id)
        )
        chat_count = chat_result.scalar()
        
        return {
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
            "document_count": doc_count or 0,
            "chat_count": chat_count or 0,
            "is_active": tenant.is_active
        }
