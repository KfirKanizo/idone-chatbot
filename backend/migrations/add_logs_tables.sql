-- Migration: Add Integration and Audit Logs Tables
-- Created: 2026-03-05
-- Description: Adds tables for tracking webhook/integration calls and administrative actions

-- Integration Logs: Track outbound webhook/API calls from the chat flow
CREATE TABLE IF NOT EXISTS integration_logs (
    id VARCHAR(36) PRIMARY KEY DEFAULT (replace(uuid_generate_v4()::text, '-', '')),
    tenant_id VARCHAR(36) REFERENCES tenants(id) ON DELETE CASCADE,
    target_url VARCHAR(2048) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER,
    payload JSONB,
    response_body TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_integration_logs_tenant_id ON integration_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_integration_logs_created_at ON integration_logs(created_at DESC);

-- Audit Logs: Track administrative actions and configuration changes
CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(36) PRIMARY KEY DEFAULT (replace(uuid_generate_v4()::text, '-', '')),
    tenant_id VARCHAR(36) REFERENCES tenants(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_id ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);

COMMENT ON TABLE integration_logs IS 'Tracks outbound webhook/API calls made by the chatbot (e.g., to n8n, CRM, external business logic)';
COMMENT ON TABLE audit_logs IS 'Tracks administrative actions like tenant creation, document uploads, configuration changes';
