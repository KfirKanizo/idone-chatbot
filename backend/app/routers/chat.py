"""
Chat Router - Chat & Conversation Endpoints

This module provides the main chatbot API endpoints.
These endpoints are used by tenant clients to interact with their chatbots.

Authentication:
- All endpoints require X-API-Key header with valid tenant API key
- API key is validated against the tenants table
- Inactive tenants will receive 403 Forbidden
"""

from fastapi import APIRouter, Depends, HTTPException, Header, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.schemas import ChatRequest, ChatResponse
from app.services.tenant_service import TenantService
from app.services.rag_service import rag_service
from app.services.chat_service import ChatService
from loguru import logger


router = APIRouter(
    prefix="/api",
    tags=["Chat & Conversation"],
    responses={
        400: {"description": "Bad request - invalid input"},
        401: {"description": "Invalid or missing API key"},
        403: {"description": "Tenant is inactive"},
        500: {"description": "Internal server error"}
    }
)


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send Chat Message",
    description="""
## Main Chat Webhook Endpoint

This is the primary endpoint for sending messages to a tenant's chatbot.
Optimized for integration with automation tools like n8n, Make, or Zapier.

### Request Format
```json
{
    "api_key": "tenant_api_key_here",
    "user_id": "user_identifier",
    "message": "Hello, how can you help me?"
}
```

### How It Works
1. Validates the API key and retrieves tenant configuration
2. Generates query embedding from the user message
3. Searches the tenant's knowledge base (Qdrant) for relevant context
4. Builds a prompt with system prompt + context + user message
5. Calls OpenAI LLM with tenant-specific settings
6. Saves the interaction to chat history
7. Returns the response with context used
    """,
    response_description="Chatbot response with context"
)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Process a chat message and return an AI-generated response.
    
    **Request Body:**
    - api_key: Your tenant's API key (required)
    - user_id: Unique identifier for the user (phone number, email, etc.)
    - message: The user's message (required)
    
    **Returns:**
    - response: The AI-generated response
    - context_used: Array of context chunks used for generation
    - user_id: The user ID passed in the request
    - timestamp: When the response was generated
    
    **Example with curl:**
    ```bash
    curl -X POST https://chat.idone.co.il/api/chat \\
      -H "Content-Type: application/json" \\
      -d '{
        "api_key": "your_tenant_api_key",
        "user_id": "phone_number",
        "message": "What are your business hours?"
      }'
    ```
    """
    if not request.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="API key is required. Include 'api_key' in request body."
        )
    
    if not request.message or not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Message is required and cannot be empty."
        )
    
    tenant_service = TenantService(db)
    tenant = await tenant_service.get_tenant_by_api_key(request.api_key)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid API key. Please check your tenant API key."
        )
    
    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Tenant is inactive. Contact administrator."
        )
    
    logger.info(f"Chat request from tenant {tenant.id}, user {request.user_id}")
    
    llm_response = await rag_service.generate_response(
        db=db,
        tenant_id=tenant.id,
        user_id=request.user_id,
        user_message=request.message,
        system_prompt=tenant.system_prompt,
        llm_provider=tenant.llm_provider,
        llm_model=tenant.llm_model,
        llm_api_key=tenant.llm_api_key,
        temperature=tenant.temperature,
        max_tokens=tenant.max_tokens
    )
    
    chat_service = ChatService(db)
    chat = await chat_service.save_chat(
        tenant_id=tenant.id,
        user_id=request.user_id,
        message=request.message,
        response=llm_response["response"],
        context_used=llm_response["context_used"]
    )
    
    return ChatResponse(
        response=llm_response["response"],
        context_used=llm_response["context_used"],
        user_id=request.user_id,
        timestamp=chat.created_at
    )


@router.get(
    "/chat/history/{user_id}",
    summary="Get Chat History",
    description="""
Retrieve chat history for a specific user.

Returns the most recent chat interactions for the specified user within the tenant.
    """,
    response_description="Chat history for the user"
)
async def get_chat_history(
    user_id: str,
    api_key: str = Header(..., description="Tenant API key"),
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """
    Get chat history for a specific user.
    
    **Path Parameters:**
    - user_id: The user's unique identifier
    
    **Query Parameters:**
    - limit: Maximum number of messages to return (default: 50)
    
    **Headers:**
    - X-API-Key: Your tenant's API key
    
    **Returns:**
    - Array of chat objects with message, response, and timestamp
    """
    tenant_service = TenantService(db)
    tenant = await tenant_service.get_tenant_by_api_key(api_key)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid API key"
        )
    
    chat_service = ChatService(db)
    history = await chat_service.get_chat_history(tenant.id, user_id, limit)
    
    return {
        "user_id": user_id,
        "chat_count": len(history),
        "chats": [
            {
                "id": chat.id,
                "message": chat.message,
                "response": chat.response,
                "created_at": chat.created_at.isoformat()
            }
            for chat in history
        ]
    }
