import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Union

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from loguru import logger
import os

from app.config import settings
from app.database import init_db
from app.routers import admin, ingest, chat, analytics, logs
from app.services.vector_service import vector_service


logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=settings.log_level
)


API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
ADMIN_HEADER = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def get_tenant_api_key(api_key: Union[str, None] = Depends(API_KEY_HEADER)) -> str:
    """
    Dependency to extract and validate tenant API key from header.
    Used for API documentation and testing.
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required. Add 'X-API-Key' header."
        )
    return api_key


async def get_admin_api_key(api_key: Union[str, None] = Depends(ADMIN_HEADER)) -> str:
    """
    Dependency to extract and validate admin API key from header.
    Used for admin endpoints in Swagger UI.
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key is required. Add 'X-Admin-Key' header."
        )
    if api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key"
        )
    return api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting iDone Chatbot System...")
    
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    
    try:
        if hasattr(vector_service, '_ensure_collection'):
            vector_service._ensure_collection()
        logger.info("Vector database ready")
    except Exception as e:
        logger.error(f"Vector database initialization failed: {e}")
    
    yield
    
    logger.info("Shutting down iDone Chatbot System...")


app = FastAPI(
    title="iDone Chatbot API",
    description="""
## Multi-Tenant RAG Chatbot System

Welcome to the iDone Chatbot API - a production-ready system for providing isolated, 
custom-knowledge chatbots for multiple business clients.

### Features

* **Multi-Tenant Isolation** - Each client has isolated data via unique API keys
* **RAG Pipeline** - Retrieval-Augmented Generation using LangChain and OpenAI
* **Document Ingestion** - Upload PDF, DOCX, or text files for knowledge base
* **Chat Webhooks** - Optimized for n8n/Make automation integration
* **Admin Dashboard** - Manage tenants, monitor usage

### Authentication

- **Tenant Endpoints**: Use `X-API-Key` header with tenant's API key
- **Admin Endpoints**: Use `X-Admin-Key` header with admin API key

### Base URL

Production: `https://chat.idone.co.il`
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    contact={
        "name": "iDone Agency",
        "url": "https://idone.co.il",
        "email": "support@idone.co.il"
    },
    license_info={
        "name": "Proprietary",
        "url": "https://idone.co.il/terms"
    }
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chat.idone.co.il",
        "https://admin.idone.co.il",
        "https://n8n.idone.co.il",
        "https://www.idone.co.il",
        "https://idone.co.il",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


app.include_router(admin.router)
app.include_router(ingest.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(logs.router)


@app.get(
    "/",
    summary="API Root",
    description="Get basic information about the iDone Chatbot API",
    tags=["System"]
)
async def root():
    """
    Returns basic API information including version and documentation links.
    """
    return {
        "name": "iDone Chatbot API",
        "version": "1.0.0",
        "description": "Multi-Tenant RAG Chatbot System",
        "documentation": "/docs",
        "redoc": "/redoc",
        "health": "/health"
    }


@app.get(
    "/health",
    response_model=dict,
    summary="Health Check",
    description="Check the health status of all system components",
    tags=["System"]
)
async def health_check():
    """
    Performs health checks on all dependencies:
    - PostgreSQL database connection
    - Qdrant vector database
    
    Returns overall system status and individual component health.
    """
    db_status = "unknown"
    qdrant_status = "unknown"
    
    try:
        from app.database import check_db_connection
        db_status = "healthy" if await check_db_connection() else "unhealthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"
    
    try:
        info = vector_service.get_collection_info()
        qdrant_status = "healthy" if info else "unhealthy"
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        qdrant_status = "error"
    
    return {
        "status": "healthy" if db_status == "healthy" and qdrant_status == "healthy" else "degraded",
        "database": db_status,
        "qdrant": qdrant_status,
        "timestamp": datetime.utcnow().isoformat()
    }


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
frontend_path = os.path.join(os.path.dirname(BASE_DIR), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
