#!/bin/bash

# =============================================================================
# iDone Chatbot - Production Deployment Script
# =============================================================================
# Run as: sudo bash deploy_chatbot.sh
# =============================================================================

set -e

# =============================================================================
# CONFIGURATION SECTION - Edit these variables before deployment
# =============================================================================

# Database Configuration
DB_NAME="idone_chatbot"
DB_USER="postgres"
DB_PASSWORD="change_me_postgres_password"

# Admin Configuration
ADMIN_API_KEY="change_me_admin_api_key"

# LLM Configuration (Choose one: OpenAI OR Groq)
OPENAI_API_KEY=""
GROQ_API_KEY="change_me_groq_api_key"
GROQ_MODEL="llama-3.1-8b-instant"

# CORS Origins (comma-separated)
CORS_ORIGINS="https://chat.idone.co.il,https://n8n.idone.co.il,https://www.idone.co.il,https://idone.co.il"

# Docker Network (external network for Nginx Proxy Manager)
PROXY_NETWORK="proxy-network"

# =============================================================================
# DIRECTORY SETUP
# =============================================================================

echo "==> Creating directory structure..."

STACK_DIR="/opt/stacks/idone-chatbot"
APP_DATA_DIR="/opt/app-data/idone-chatbot"

mkdir -p "$STACK_DIR"
mkdir -p "$APP_DATA_DIR/postgres"
mkdir -p "$APP_DATA_DIR/qdrant"

echo "    Created: $STACK_DIR"
echo "    Created: $APP_DATA_DIR/postgres"
echo "    Created: $APP_DATA_DIR/qdrant"

# =============================================================================
# GENERATE ENVIRONMENT FILE
# =============================================================================

echo "==> Generating .env file..."

cat <<ENVEOF > "$STACK_DIR/.env"
# =============================================================================
# iDone Chatbot - Production Environment
# =============================================================================

# Application Settings
APP_NAME=iDone-Chatbot
APP_VERSION=1.0.0
DEBUG=false
SECRET_KEY=$(openssl rand -hex 32)

# Database (PostgreSQL)
DB_HOST=postgres
DB_PORT=5432
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD

# Vector Database (Qdrant)
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_GRPC_PORT=6334
QDRANT_API_KEY=

# LLM Configuration (OpenAI)
OPENAI_API_KEY=$OPENAI_API_KEY
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_TEMPERATURE=0.7
OPENAI_MAX_TOKENS=2000

# LLM Configuration (Groq)
GROQ_API_KEY=$GROQ_API_KEY
GROQ_MODEL=$GROQ_MODEL
GROQ_EMBEDDING_MODEL=text-embedding-3-small

# Admin Dashboard
ADMIN_API_KEY=$ADMIN_API_KEY

# CORS Settings
CORS_ORIGINS=$CORS_ORIGINS

# Logging
LOG_LEVEL=INFO

# Docker Network
DOCKER_NETWORK=$PROXY_NETWORK
ENVEOF

echo "    .env file created at: $STACK_DIR/.env"

# =============================================================================
# GENERATE DOCKER COMPOSE FILE
# =============================================================================

echo "==> Generating docker-compose.yml..."

cat <<COMPOSEEOF > "$STACK_DIR/docker-compose.yml"
version: '3.8'

services:
  # -----------------------------------------------------------------------------
  # PostgreSQL Database
  # -----------------------------------------------------------------------------
  postgres:
    image: postgres:15-alpine
    container_name: idone_postgres
    environment:
      POSTGRES_DB: ${DB_NAME:-idone_chatbot}
      POSTGRES_USER: ${DB_USER:-postgres}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - ${APP_DATA_DIR}/postgres:/var/lib/postgresql/data
    expose:
      - "5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-postgres}"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - idone_network
    restart: unless-stopped

  # -----------------------------------------------------------------------------
  # Qdrant Vector Database
  # -----------------------------------------------------------------------------
  qdrant:
    image: qdrant/qdrant:v1.7.4
    container_name: idone_qdrant
    environment:
      QDRANT__SERVICE__GRPC_PORT: 6334
    volumes:
      - ${APP_DATA_DIR}/qdrant:/qdrant/storage
    expose:
      - "6333"
      - "6334"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - idone_network
    restart: unless-stopped

  # -----------------------------------------------------------------------------
  # FastAPI Backend (NPM managed)
  # -----------------------------------------------------------------------------
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: idone_chat_api
    env_file:
      - ./.env
    environment:
      DATABASE_URL: postgresql+asyncpg://${DB_USER:-postgres}:${DB_PASSWORD}@postgres:5432/${DB_NAME:-idone_chatbot}
      QDRANT_HOST: qdrant
      QDRANT_PORT: 6333
    expose:
      - "8000"
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - idone_network
      - proxy_network
    restart: unless-stopped

  # -----------------------------------------------------------------------------
  # Frontend (NPM managed)
  # -----------------------------------------------------------------------------
  frontend:
    image: nginx:alpine
    container_name: idone_chat_frontend
    volumes:
      - ./frontend:/usr/share/nginx/html:ro
    expose:
      - "80"
    depends_on:
      - backend
    networks:
      - idone_network
      - proxy_network
    restart: unless-stopped

# -----------------------------------------------------------------------------
# Networks
# -----------------------------------------------------------------------------
networks:
  idone_network:
    driver: bridge
  proxy_network:
    external: true
    name: ${PROXY_NETWORK:-proxy-network}

# -----------------------------------------------------------------------------
# Volumes (using host paths for persistence)
# -----------------------------------------------------------------------------
volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${APP_DATA_DIR}/postgres
  qdrant_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${APP_DATA_DIR}/qdrant
COMPOSEEOF

# Fix the volume paths in docker-compose.yml to use the actual paths
sed -i "s|\${APP_DATA_DIR}|$APP_DATA_DIR|g" "$STACK_DIR/docker-compose.yml"

echo "    docker-compose.yml created at: $STACK_DIR/docker-compose.yml"

# =============================================================================
# CHECK FOR EXTERNAL NETWORK
# =============================================================================

echo "==> Checking for external Docker network..."

if docker network ls | grep -q "$PROXY_NETWORK"; then
    echo "    Network '$PROXY_NETWORK' exists"
else
    echo "    WARNING: Network '$PROXY_NETWORK' does not exist!"
    echo "    Creating network..."
    docker network create "$PROXY_NETWORK" || echo "    Failed to create network. Please create it manually:"
    echo "        docker network create $PROXY_NETWORK"
fi

# =============================================================================
# DEPLOY STACK
# =============================================================================

echo "==> Deploying iDone Chatbot stack..."

cd "$STACK_DIR"

# Check if docker-compose or docker compose
if command -v docker-compose &> /dev/null; then
    docker-compose up -d
else
    docker compose up -d
fi

# =============================================================================
# VERIFICATION
# =============================================================================

echo ""
echo "==> Checking container status..."
sleep 5

docker ps --filter "name=idone" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "==> Checking health endpoints..."

# Check backend health
BACKEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "failed")
echo "    Backend health: $BACKEND_HEALTH"

echo ""
echo "================================================================================"
echo "  iDone Chatbot deployment complete!"
echo "================================================================================"
echo ""
echo "  Stack Directory:  $STACK_DIR"
echo "  Data Directory:   $APP_DATA_DIR"
echo "  Backend API:      http://localhost:8000 (internal)"
echo "  Swagger Docs:     http://localhost:8000/docs (internal)"
echo ""
echo "  Next steps:"
echo "    1. Configure Nginx Proxy Manager to proxy chat.idone.co.il -> backend:8000"
echo "    2. Configure Nginx Proxy Manager to proxy admin.idone.co.il -> frontend:80"
echo "    3. Test the API: curl -X POST http://chat.idone.co.il/api/chat \\"
echo "                        -H 'Content-Type: application/json' \\"
echo "                        -d '{\"api_key\":\"YOUR_TENANT_KEY\",\"user_id\":\"test\",\"message\":\"Hello\"}'"
echo ""
echo "================================================================================"
