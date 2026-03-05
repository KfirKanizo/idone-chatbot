-- Migration: Add BYOK (Bring Your Own Key) columns to Tenants table
-- Created: 2026-03-05
-- Description: Adds columns for tenants to configure their own LLM provider, model, and API key

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS llm_provider VARCHAR(50) DEFAULT 'groq';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS llm_model VARCHAR(100);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS llm_api_key VARCHAR(500);

-- Set default llm_model based on provider if not set
UPDATE tenants SET llm_model = 'llama-3.3-70b-versatile' WHERE llm_model IS NULL OR llm_model = '';

COMMENT ON COLUMN tenants.llm_provider IS 'LLM provider: openai, anthropic, gemini, groq, deepseek, grok, cohere';
COMMENT ON COLUMN tenants.llm_model IS 'Model name for the selected provider';
COMMENT ON COLUMN tenants.llm_api_key IS 'Tenant-specific API key for the LLM provider (BYOK)';
