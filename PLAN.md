# iDone Chatbot Manager - Implementation Plan

## Executive Summary

This document outlines the complete implementation plan for a production-ready Multi-Tenant RAG (Retrieval-Augmented Generation) Chatbot System for the "iDone" agency. The system provides isolated, custom-knowledge chatbots for various business clients with strict data isolation.

---

## 1. Technology Stack

### 1.1 Backend
- **Framework:** Python 3.11 with FastAPI
- **Async Support:** Uvicorn with ASGI
- **Database:** PostgreSQL 15 (Relational data)
- **ORM:** SQLAlchemy 2.0 with async support

### 1.2 Vector Database
- **Solution:** Qdrant v1.7.4 (Local/Containerized)
- **Reasoning:** Supports metadata filtering for tenant isolation, easy Docker deployment

### 1.3 LLM Integration
- **Framework:** LangChain
- **Provider:** OpenAI API (GPT-4o Mini default)
- **Embeddings:** OpenAI text-embedding-3-small

### 1.4 Frontend
- **Type:** Vanilla JavaScript + HTML
- **Styling:** TailwindCSS (via CDN)
- **Deployment:** Nginx Alpine

### 1.5 DevOps
- **Containerization:** Docker + Docker Compose
- **Orchestration:** Single docker-compose.yml for all services

---

## 2. Architecture & Multi-Tenancy Logic

### 2.1 Core Principle
**One codebase, one deployment, handling multiple clients with strict data isolation.**

### 2.2 Tenant Isolation Strategy

| Layer | Isolation Method |
|-------|-----------------|
| **API Key** | Each tenant receives unique 64-character API key |
| **PostgreSQL** | `tenant_id` foreign key on all tables with CASCADE delete |
| **Qdrant** | `tenant_id` stored in payload metadata, filtered on every query |
| **Application** | API key → tenant_id lookup on every request |

### 2.3 Data Flow

```
Client Request (API Key)
       ↓
FastAPI validates API key → retrieves tenant_id
       ↓
LangChain generates query embedding
       ↓
Qdrant searches with tenant_id filter (MUST match)
       ↓
Context retrieved, LLM generates response
       ↓
Chat saved to PostgreSQL with tenant_id
       ↓
Response returned to client
```

---

## 3. API Endpoints Specification

### 3.1 Admin/Tenant Management

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/admin/tenants` | Create new tenant | Admin Key |
| GET | `/admin/tenants` | List all tenants | Admin Key |
| GET | `/admin/tenants/{tenant_id}` | Get tenant details | Admin Key |
| PUT | `/admin/tenants/{tenant_id}` | Update tenant settings | Admin Key |
| DELETE | `/admin/tenants/{tenant_id}` | Delete tenant & all data | Admin Key |

### 3.2 Knowledge Base (Ingestion)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/ingest/{tenant_id}/text` | Ingest text content | Tenant API Key |
| POST | `/api/ingest/{tenant_id}/file` | Upload PDF/DOCX/TXT | Tenant API Key |

### 3.3 Chat/Inference

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/chat` | Main webhook endpoint | Tenant API Key |
| GET | `/api/chat/history/{user_id}` | Get user chat history | Tenant API Key |

### 3.4 System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/docs` | API documentation |
| GET | `/` | API root info |

---

## 4. Database Schema

### 4.1 Tables

```sql
-- Tenants table
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    system_prompt TEXT DEFAULT 'You are a helpful assistant.',
    llm_model VARCHAR(50) DEFAULT 'gpt-4o-mini',
    temperature FLOAT DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 2000,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Documents table
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    chunk_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    is_indexed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Chat histories table
CREATE TABLE chat_histories (
    id UUID PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    response TEXT NOT NULL,
    context_used JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.2 Indexes

```sql
CREATE INDEX idx_tenants_api_key ON tenants(api_key);
CREATE INDEX idx_documents_tenant_id ON documents(tenant_id);
CREATE INDEX idx_chat_histories_tenant_id ON chat_histories(tenant_id);
CREATE INDEX idx_chat_histories_user_id ON chat_histories(user_id);
CREATE INDEX idx_chat_histories_created_at ON chat_histories(created_at);
```

---

## 5. Qdrant Vector Database

### 5.1 Collection Configuration

- **Collection Name:** `documents`
- **Vector Size:** 1536 (text-embedding-3-small)
- **Distance Metric:** Cosine

### 5.2 Point Structure

```python
{
    "id": "{document_id}_{chunk_index}",
    "vector": [embedding],
    "payload": {
        "tenant_id": "uuid",
        "document_id": "uuid",
        "chunk_index": 0,
        "text": "chunk content"
    }
}
```

### 5.3 Search Filter (CRITICAL)

Every search query MUST include:
```python
Filter(
    must=[
        FieldCondition(
            key="tenant_id",
            match=MatchValue(value=tenant_id)
        )
    ]
)
```

---

## 6. RAG Pipeline

### 6.1 Text Processing

1. **File Extraction:**
   - PDF → PyPDF2
   - DOCX → python-docx
   - TXT → UTF-8 decode

2. **Text Chunking:**
   - RecursiveCharacterTextSplitter
   - Chunk size: 1000 characters
   - Overlap: 200 characters

### 6.2 Embedding Generation

- **Model:** text-embedding-3-small
- **Dimensions:** 1536
- **Max Input:** 8191 tokens

### 6.3 Context Retrieval

1. Generate query embedding
2. Search Qdrant with tenant filter
3. Return top-k results (default: 5)
4. Build context string from results

### 6.4 LLM Response Generation

1. Build prompt with system prompt + context + user message
2. Call OpenAI Chat API with tenant-specific settings
3. Return response + context used

---

## 7. Admin Dashboard Specification

### 7.1 Features

| Feature | Description |
|---------|-------------|
| **Header** | "iDone Chatbot Manager" branding |
| **Tenant Table** | List all tenants with status, document count, chat count |
| **Add Tenant Form** | Name, System Prompt, LLM Model, Temperature |
| **Edit Tenant** | Modal with all tenant settings |
| **Upload Section** | Select tenant, paste text OR upload file |
| **System Status** | Health check indicator |

### 7.2 UI Components

- TailwindCSS for styling
- Font Awesome for icons
- Toast notifications for feedback
- Modal dialogs for editing
- Responsive grid layout

---

## 8. Deployment & Infrastructure

### 8.1 Domain Configuration

| Service | Domain | Description |
|---------|--------|-------------|
| **Chat API** | https://chat.idone.co.il | Main chatbot API |
| **Swagger UI** | https://chat.idone.co.il/docs | Interactive API docs |
| **ReDoc** | https://chat.idone.co.il/redoc | Alternative API docs |
| **n8n** | https://n8n.idone.co.il | Existing automation |

### 8.2 Nginx Proxy Manager (NPM) Setup

The system is configured to work with an existing NPM installation:

#### Container Configuration
```yaml
backend:
  container_name: idone_chat_api
  expose:
    - "8000"  # Internal only, NOT exposed to host
  networks:
    - idone_network
    - npm_network  # External network for NPM

frontend:
  container_name: idone_chat_frontend
  expose:
    - "80"
  networks:
    - idone_network
    - npm_network
```

#### NPM Proxy Host Configuration

**For API (idone_chat_api):**
- Domain: `chat.idone.co.il`
- Scheme: `https`
- Forward Hostname/IP: `idone_chat_api`
- Forward Port: `8000`
- Block Common Exploits: ✓

**For Frontend (idone_chat_frontend):**
- Domain: `chat.idone.co.il`
- Scheme: `https`
- Forward Hostname/IP: `idone_chat_frontend`
- Forward Port: `80`
- Advanced: Rewrite `/` to `/index.html`

### 8.3 Docker Network Setup

```bash
# Create external network if not exists
docker network create npm_network

# Or define custom network in .env
DOCKER_NETWORK=npm_network
```

### 8.4 Environment Variables for Production

```env
# Database
DB_HOST=postgres
DB_NAME=idone_chatbot
DB_USER=postgres
DB_PASSWORD=<secure_password>

# Qdrant
QDRANT_HOST=qdrant

# OpenAI
OPENAI_API_KEY=<openai_key>

# Admin
ADMIN_API_KEY=<secure_admin_key>

# CORS (your domains)
CORS_ORIGINS=https://chat.idone.co.il

# Docker Network
DOCKER_NETWORK=npm_network
```

---

## 9. API Documentation Standards

### 9.1 Swagger UI Configuration

- **URL:** `/docs`
- **Title:** iDone Chatbot API
- **Version:** 1.0.0
- **Description:** Comprehensive multi-tenant RAG chatbot system

### 9.2 Documentation Features

All endpoints include:
- ✨ Summary and description
- 📝 Detailed parameter documentation
- 📋 Request/response schemas
- 🔒 Authentication requirements
- 💡 Usage examples (curl)
- ⚠️ Warnings for destructive actions

### 9.3 Authentication in Swagger

| Header | Description | Used By |
|--------|-------------|---------|
| `X-Admin-Key` | Admin API key | All `/admin/*` endpoints |
| `X-API-Key` | Tenant API key | All `/api/*` endpoints |

---

## 10. Security Considerations

### 10.1 API Key Management
- 64-character random API keys
- Stored in database (consider bcrypt for future)
- Required for all tenant operations

### 10.2 Admin Authentication
- Separate admin API key
- Passed via `X-Admin-Key` header

### 10.3 Tenant Isolation
- Every vector query filters by tenant_id
- No cross-tenant data access possible
- CASCADE deletes ensure cleanup

### 10.4 Network Security
- Services NOT exposed to host (using `expose` instead of `ports`)
- Only accessible through NPM reverse proxy
- Internal Docker network for service-to-service communication

---

## 11. Implementation Status

### ✅ Completed

| Component | Status | Notes |
|-----------|--------|-------|
| Database Schema | ✅ Complete | PostgreSQL with SQLAlchemy |
| Core Backend | ✅ Complete | FastAPI with async |
| Tenant Service | ✅ Complete | CRUD operations |
| Vector Service | ✅ Complete | Qdrant with tenant filtering |
| RAG Pipeline | ✅ Complete | LangChain integration |
| Chat Service | ✅ Complete | History management |
| API Endpoints | ✅ Complete | Admin, Ingest, Chat |
| API Documentation | ✅ Complete | Comprehensive docstrings |
| Admin Dashboard | ✅ Complete | TailwindCSS UI |
| Docker Setup | ✅ Complete | NPM-ready configuration |

### 📋 Deployment Pending

| Component | Status | Notes |
|-----------|--------|-------|
| Production Deploy | ⏳ Pending | Requires NPM setup |
| Domain DNS | ⏳ Pending | Point to NPM |
| SSL Certificates | ⏳ Pending | Handled by NPM |
| Monitoring | ⏳ Pending | Optional enhancement |

---

## 12. Quick Start Commands

```bash
# 1. Clone and navigate to project
cd iDone-Chatbot

# 2. Configure environment
cp backend/.env.example backend/.env
# Edit .env with your values

# 3. Create Docker network (if not exists)
docker network create npm_network

# 4. Start all services
docker-compose up --build

# 5. Verify health
curl https://chat.idone.co.il/health

# 6. Access Swagger documentation
# Open https://chat.idone.co.il/docs
```

---

## 13. Testing Checklist

### 13.1 Tenant Management
- [ ] Create tenant via API
- [ ] Create tenant via Dashboard
- [ ] List all tenants
- [ ] Update tenant settings
- [ ] Delete tenant (verify cascade delete)

### 13.2 Document Ingestion
- [ ] Upload text content
- [ ] Upload PDF file
- [ ] Upload DOCX file
- [ ] Verify chunks created
- [ ] Verify vectors in Qdrant

### 13.3 Chat Functionality
- [ ] Send chat message
- [ ] Verify response generation
- [ ] Check chat history
- [ ] Test with different tenants

### 13.4 Isolation Verification
- [ ] Create 2 tenants
- [ ] Ingest different docs for each
- [ ] Query both - ensure no cross-contamination

---

## 14. Future Enhancements

| Feature | Priority | Description |
|---------|----------|-------------|
| API Key Rotation | Medium | Allow regenerating API keys |
| Webhook Notifications | Medium | Alert on errors |
| Usage Analytics | Low | Track API usage per tenant |
| Custom Embeddings | Low | Support for self-hosted models |
| SSO Integration | Low | OAuth for admin dashboard |

---

*Document Version: 2.0*
*Last Updated: 2026-03-03*
*Author: AI Developer*
