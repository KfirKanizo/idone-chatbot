-- Migration: Add token_count column to chat_histories table
-- Run this SQL on your PostgreSQL database to add the token_count column

-- Add token_count column with default value 0
ALTER TABLE chat_histories 
ADD COLUMN IF NOT EXISTS token_count INTEGER DEFAULT 0;

-- Update existing records with estimated token counts (optional)
-- This estimates tokens based on character count (roughly 4 chars per token)
UPDATE chat_histories 
SET token_count = (LENGTH(COALESCE(message, '')) + LENGTH(COALESCE(response, ''))) / 4
WHERE token_count = 0 OR token_count IS NULL;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_chat_histories_token_count ON chat_histories(token_count);
