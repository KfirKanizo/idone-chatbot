"""
Logs Router - Integration and Audit Log Endpoints

Provides endpoints for viewing:
- Integration logs (webhook-triggered outbound calls)
- Audit logs (administrative actions)

Also provides helper functions for logging from other modules.
"""

from fastapi import APIRouter, Depends, Query, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from pydantic import BaseModel
from app.database import get_db
from app.models import IntegrationLog, AuditLog
from app.config import settings
from loguru import logger


router = APIRouter(
    prefix="/admin/logs",
    tags=["Admin - Logs"],
)


def verify_admin_key(x_admin_key: Optional[str] = Header(None)):
    """Verify admin API key from X-Admin-Key header."""
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key"
        )
    return True


# Response Models
class IntegrationLogResponse(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    target_url: str
    method: str
    status_code: Optional[int] = None
    payload: Optional[dict] = None
    response_body: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class AuditLogResponse(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    action: str
    details: Optional[dict] = None
    created_at: str

    class Config:
        from_attributes = True


# Helper function for audit logging
async def log_audit_action(
    db: AsyncSession,
    tenant_id: Optional[str],
    action: str,
    details: Optional[dict] = None
) -> AuditLog:
    """
    Helper function to log an audit action.
    
    Args:
        db: Database session
        tenant_id: Tenant ID (optional for global actions)
        action: Action type (e.g., 'CREATE_TENANT', 'UPDATE_PROMPT')
        details: Additional details as dict
    
    Returns:
        Created AuditLog instance
    """
    try:
        audit_log = AuditLog(
            tenant_id=tenant_id,
            action=action,
            details=details
        )
        db.add(audit_log)
        await db.commit()
        await db.refresh(audit_log)
        logger.info(f"Audit log created: {action} for tenant {tenant_id}")
        return audit_log
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
        await db.rollback()
        return None


async def log_integration_call(
    db: AsyncSession,
    tenant_id: Optional[str],
    target_url: str,
    method: str,
    status_code: Optional[int] = None,
    payload: Optional[dict] = None,
    response_body: Optional[str] = None
) -> IntegrationLog:
    """
    Helper function to log an integration (webhook) call.
    
    Args:
        db: Database session
        tenant_id: Tenant ID
        target_url: Webhook URL
        method: HTTP method
        status_code: Response status code
        payload: Request payload
        response_body: Response body
    
    Returns:
        Created IntegrationLog instance
    """
    try:
        integration_log = IntegrationLog(
            tenant_id=tenant_id,
            target_url=target_url,
            method=method,
            status_code=status_code,
            payload=payload,
            response_body=response_body
        )
        db.add(integration_log)
        await db.commit()
        await db.refresh(integration_log)
        logger.info(f"Integration log created: {method} {target_url} -> {status_code}")
        return integration_log
    except Exception as e:
        logger.error(f"Failed to create integration log: {e}")
        await db.rollback()
        return None


@router.get(
    "/integrations",
    response_model=List[IntegrationLogResponse],
    summary="Get Integration Logs",
    description="Returns recent integration/webhook logs, optionally filtered by tenant"
)
async def get_integration_logs(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    limit: int = Query(50, ge=1, le=500, description="Number of logs to return"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Get integration logs for debugging webhook calls.
    
    Args:
        tenant_id: Optional tenant filter
        limit: Max records to return (default 50)
    
    Returns:
        List of integration logs, newest first
    """
    try:
        query = select(IntegrationLog).order_by(desc(IntegrationLog.created_at))
        
        if tenant_id:
            query = query.where(IntegrationLog.tenant_id == tenant_id)
        
        query = query.limit(limit)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        return [
            IntegrationLogResponse(
                id=log.id,
                tenant_id=log.tenant_id,
                target_url=log.target_url,
                method=log.method,
                status_code=log.status_code,
                payload=log.payload,
                response_body=log.response_body,
                created_at=log.created_at.isoformat() if log.created_at else None
            )
            for log in logs
        ]
    except Exception as e:
        logger.error(f"Error fetching integration logs: {e}")
        raise


@router.get(
    "/audit",
    response_model=List[AuditLogResponse],
    summary="Get Audit Logs",
    description="Returns recent audit logs of administrative actions"
)
async def get_audit_logs(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(50, ge=1, le=500, description="Number of logs to return"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Get audit logs for tracking administrative changes.
    
    Args:
        tenant_id: Optional tenant filter
        action: Optional action type filter
        limit: Max records to return (default 50)
    
    Returns:
        List of audit logs, newest first
    """
    try:
        query = select(AuditLog).order_by(desc(AuditLog.created_at))
        
        if tenant_id:
            query = query.where(AuditLog.tenant_id == tenant_id)
        
        if action:
            query = query.where(AuditLog.action == action)
        
        query = query.limit(limit)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        return [
            AuditLogResponse(
                id=log.id,
                tenant_id=log.tenant_id,
                action=log.action,
                details=log.details,
                created_at=log.created_at.isoformat() if log.created_at else None
            )
            for log in logs
        ]
    except Exception as e:
        logger.error(f"Error fetching audit logs: {e}")
        raise
