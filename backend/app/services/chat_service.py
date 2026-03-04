import uuid
from typing import Optional, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import ChatHistory
from loguru import logger


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_chat(
        self,
        tenant_id: str,
        user_id: str,
        message: str,
        response: str,
        context_used: List[str]
    ) -> ChatHistory:
        chat = ChatHistory(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            message=message,
            response=response,
            context_used=context_used
        )
        
        self.db.add(chat)
        await self.db.commit()
        await self.db.refresh(chat)
        
        logger.info(f"Saved chat {chat.id} for tenant {tenant_id}")
        return chat

    async def get_chat_history(
        self,
        tenant_id: str,
        user_id: str,
        limit: int = 50
    ) -> List[ChatHistory]:
        result = await self.db.execute(
            select(ChatHistory)
            .where(ChatHistory.tenant_id == tenant_id)
            .where(ChatHistory.user_id == user_id)
            .order_by(desc(ChatHistory.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent_chats(
        self,
        tenant_id: str,
        limit: int = 100
    ) -> List[ChatHistory]:
        result = await self.db.execute(
            select(ChatHistory)
            .where(ChatHistory.tenant_id == tenant_id)
            .order_by(desc(ChatHistory.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_chat(self, chat_id: str, tenant_id: str) -> bool:
        result = await self.db.execute(
            select(ChatHistory)
            .where(ChatHistory.id == chat_id)
            .where(ChatHistory.tenant_id == tenant_id)
        )
        chat = result.scalar_one_or_none()
        
        if not chat:
            return False
        
        await self.db.delete(chat)
        await self.db.commit()
        
        logger.info(f"Deleted chat {chat_id}")
        return True

    async def clear_user_history(self, tenant_id: str, user_id: str) -> int:
        result = await self.db.execute(
            select(ChatHistory)
            .where(ChatHistory.tenant_id == tenant_id)
            .where(ChatHistory.user_id == user_id)
        )
        chats = result.scalars().all()
        
        count = len(chats)
        for chat in chats:
            await self.db.delete(chat)
        
        await self.db.commit()
        
        logger.info(f"Cleared {count} chats for user {user_id} in tenant {tenant_id}")
        return count

    async def get_chat_stats(self, tenant_id: str) -> dict:
        from sqlalchemy import func
        
        result = await self.db.execute(
            select(
                func.count(ChatHistory.id).label('total_chats'),
                func.count(func.distinct(ChatHistory.user_id)).label('unique_users')
            )
            .where(ChatHistory.tenant_id == tenant_id)
        )
        
        row = result.one()
        return {
            "total_chats": row.total_chats or 0,
            "unique_users": row.unique_users or 0
        }
