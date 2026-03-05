"""
Analytics Router - Dashboard Analytics Endpoints

Provides analytics data for the admin dashboard including:
- Summary statistics
- Usage by tenant
- Activity timeline
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import aliased
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from app.database import get_db
from app.routers.admin import verify_admin_key
from app.models import Tenant, Document, ChatHistory
from loguru import logger


router = APIRouter(
    prefix="/admin/analytics",
    tags=["Admin - Analytics"],
)


# Response Models
class SummaryResponse(BaseModel):
    total_tenants: int
    active_tenants: int
    total_users: int
    total_messages: int
    total_documents: int
    estimated_tokens: int
    avg_messages_per_user: float


class TenantUsageResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    message_count: int
    user_count: int
    document_count: int
    estimated_tokens: int


class TimelineResponse(BaseModel):
    date: str
    message_count: int
    user_count: int
    token_count: int


@router.get(
    "/summary",
    response_model=SummaryResponse,
    summary="Get Analytics Summary",
    description="Returns global counters for the dashboard summary cards"
)
async def get_analytics_summary(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Get global analytics summary.
    
    Returns:
    - Total tenants (active and all)
    - Total unique users
    - Total messages
    - Total documents
    - Estimated tokens
    - Average messages per user
    """
    try:
        # Count tenants
        tenant_result = await db.execute(
            select(
                func.count(Tenant.id).label('total'),
                func.sum(func.cast(Tenant.is_active, sqlalchemy.Integer)).label('active')
            )
        )
        tenant_data = tenant_result.first()
        total_tenants = tenant_data.total or 0
        active_tenants = tenant_data.active or 0
        
        # Count unique users
        user_result = await db.execute(
            select(func.count(func.distinct(ChatHistory.user_id)))
        )
        total_users = user_result.scalar() or 0
        
        # Count messages
        message_result = await db.execute(
            select(func.count(ChatHistory.id))
        )
        total_messages = message_result.scalar() or 0
        
        # Count documents
        doc_result = await db.execute(
            select(func.count(Document.id))
        )
        total_documents = doc_result.scalar() or 0
        
        # Sum tokens (if column exists, otherwise estimate)
        try:
            token_result = await db.execute(
                select(func.sum(ChatHistory.token_count))
            )
            estimated_tokens = token_result.scalar() or 0
        except:
            # Fallback: estimate from message length
            msg_result = await db.execute(
                select(ChatHistory.message, ChatHistory.response)
            )
            messages = msg_result.all()
            estimated_tokens = sum(
                (len(msg.message or '') + len(msg.response or '')) // 4
                for msg in messages
            )
        
        # Calculate average
        avg_messages = (total_messages / total_users) if total_users > 0 else 0.0
        
        return SummaryResponse(
            total_tenants=total_tenants,
            active_tenants=active_tenants,
            total_users=total_users,
            total_messages=total_messages,
            total_documents=total_documents,
            estimated_tokens=estimated_tokens,
            avg_messages_per_user=round(avg_messages, 2)
        )
        
    except Exception as e:
        logger.error(f"Error getting analytics summary: {e}")
        raise


@router.get(
    "/usage-by-tenant",
    response_model=List[TenantUsageResponse],
    summary="Get Usage by Tenant",
    description="Returns message and token counts grouped by tenant"
)
async def get_usage_by_tenant(
    limit: int = Query(10, ge=1, le=100, description="Number of tenants to return"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Get usage statistics grouped by tenant.
    
    Returns:
    - List of tenants with their usage metrics
    - Sorted by message count (descending)
    """
    try:
        # Query to get usage by tenant
        result = await db.execute(
            select(
                Tenant.id.label('tenant_id'),
                Tenant.name.label('tenant_name'),
                func.count(ChatHistory.id).label('message_count'),
                func.count(func.distinct(ChatHistory.user_id)).label('user_count'),
                func.sum(ChatHistory.token_count).label('estimated_tokens')
            )
            .outerjoin(ChatHistory, ChatHistory.tenant_id == Tenant.id)
            .group_by(Tenant.id, Tenant.name)
            .order_by(func.count(ChatHistory.id).desc())
            .limit(limit)
        )
        
        # Get document counts separately
        doc_counts_result = await db.execute(
            select(
                Document.tenant_id,
                func.count(Document.id).label('doc_count')
            )
            .group_by(Document.tenant_id)
        )
        doc_counts = {row.tenant_id: row.doc_count for row in doc_counts_result.all()}
        
        # Build response
        usage_data = []
        for row in result.all():
            usage_data.append(TenantUsageResponse(
                tenant_id=row.tenant_id,
                tenant_name=row.tenant_name,
                message_count=row.message_count or 0,
                user_count=row.user_count or 0,
                document_count=doc_counts.get(row.tenant_id, 0),
                estimated_tokens=row.estimated_tokens or 0
            ))
        
        return usage_data
        
    except Exception as e:
        logger.error(f"Error getting usage by tenant: {e}")
        raise


@router.get(
    "/activity-timeline",
    response_model=List[TimelineResponse],
    summary="Get Activity Timeline",
    description="Returns daily message counts for the specified number of days"
)
async def get_activity_timeline(
    days: int = Query(7, ge=1, le=90, description="Number of days to include"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin_key)
):
    """
    Get activity timeline showing daily message counts.
    
    Args:
    - days: Number of days to include (default: 7, max: 90)
    
    Returns:
    - List of daily statistics
    - Sorted by date (ascending)
    """
    try:
        # Calculate date range
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days - 1)
        
        # Query daily stats
        result = await db.execute(
            select(
                func.date(ChatHistory.created_at).label('date'),
                func.count(ChatHistory.id).label('message_count'),
                func.count(func.distinct(ChatHistory.user_id)).label('user_count'),
                func.sum(ChatHistory.token_count).label('token_count')
            )
            .where(func.date(ChatHistory.created_at) >= start_date)
            .where(func.date(ChatHistory.created_at) <= end_date)
            .group_by(func.date(ChatHistory.created_at))
            .order_by(func.date(ChatHistory.created_at).asc())
        )
        
        # Build response with all dates (fill missing dates with zeros)
        date_stats = {row.date: row for row in result.all()}
        
        timeline_data = []
        current_date = start_date
        while current_date <= end_date:
            if current_date in date_stats:
                row = date_stats[current_date]
                timeline_data.append(TimelineResponse(
                    date=current_date.isoformat(),
                    message_count=row.message_count or 0,
                    user_count=row.user_count or 0,
                    token_count=row.token_count or 0
                ))
            else:
                timeline_data.append(TimelineResponse(
                    date=current_date.isoformat(),
                    message_count=0,
                    user_count=0,
                    token_count=0
                ))
            current_date += timedelta(days=1)
        
        return timeline_data
        
    except Exception as e:
        logger.error(f"Error getting activity timeline: {e}")
        raise


# Import sqlalchemy for cast function
import sqlalchemy
