"""
LLM Factory Service - Dynamic LLM Client Instantiation

This module provides a factory for creating LLM clients based on the provider.
It supports BYOK (Bring Your Own Key) by using tenant-specific API keys
with fallback to global environment variables.
"""

from typing import Optional, Any
from app.config import settings
from loguru import logger


class LLMFactory:
    """Factory class for creating LLM clients based on provider"""

    # Mapping of providers to their required environment variable keys
    PROVIDER_ENV_KEYS = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
        "groq": "groq_api_key",
        "deepseek": "deepseek_api_key",
        "grok": "xai_api_key",
        "cohere": "cohere_api_key",
    }

    def __init__(self):
        # Cache for global API keys
        self._global_keys = {}

    def _get_global_api_key(self, provider: str) -> Optional[str]:
        """Get global API key from environment variables"""
        if provider in self._global_keys:
            return self._global_keys[provider]

        env_key = self.PROVIDER_ENV_KEYS.get(provider)
        if env_key:
            api_key = getattr(settings, env_key, None) or ""
            self._global_keys[provider] = api_key if api_key else None
            return self._global_keys[provider]
        return None

    def _get_effective_api_key(self, tenant_api_key: Optional[str], provider: str) -> Optional[str]:
        """
        Get the effective API key, with BYOK taking precedence over global.
        """
        # If tenant provided their own key, use it
        if tenant_api_key and tenant_api_key.strip():
            return tenant_api_key.strip()
        
        # Fall back to global API key
        return self._get_global_api_key(provider)

    def create_llm_client(
        self,
        provider: str,
        model: str,
        tenant_api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Any:
        """
        Create and return an LLM client based on the provider.
        
        Args:
            provider: LLM provider (openai, anthropic, gemini, groq, deepseek, grok, cohere)
            model: Model name for the provider
            tenant_api_key: Tenant-specific API key (BYOK). If None/empty, uses global fallback.
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            LangChain LLM client instance
            
        Raises:
            ValueError: If provider is not supported or API key is missing
        """
        provider = provider.lower().strip() if provider else "groq"
        
        # Get effective API key (BYOK takes precedence)
        api_key = self._get_effective_api_key(tenant_api_key, provider)
        
        if not api_key:
            logger.warning(f"No API key found for provider '{provider}'. Using global fallback.")
        
        # Create the appropriate LLM client
        if provider == "openai":
            return self._create_openai_client(model, api_key, temperature, max_tokens)
        elif provider == "anthropic":
            return self._create_anthropic_client(model, api_key, temperature, max_tokens)
        elif provider == "gemini":
            return self._create_gemini_client(model, api_key, temperature, max_tokens)
        elif provider == "groq":
            return self._create_groq_client(model, api_key, temperature, max_tokens)
        elif provider == "deepseek":
            return self._create_deepseek_client(model, api_key, temperature, max_tokens)
        elif provider == "grok":
            return self._create_grok_client(model, api_key, temperature, max_tokens)
        elif provider == "cohere":
            return self._create_cohere_client(model, api_key, temperature, max_tokens)
        else:
            # Default to Groq
            logger.warning(f"Unknown provider '{provider}', defaulting to Groq")
            return self._create_groq_client(
                model or "llama-3.3-70b-versatile",
                api_key,
                temperature,
                max_tokens
            )

    def _create_openai_client(self, model: str, api_key: Optional[str], temperature: float, max_tokens: int):
        """Create OpenAI LLM client"""
        from langchain_openai import ChatOpenAI
        
        return ChatOpenAI(
            model=model or "gpt-4o-mini",
            api_key=api_key or settings.openai_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _create_anthropic_client(self, model: str, api_key: Optional[str], temperature: float, max_tokens: int):
        """Create Anthropic LLM client"""
        from langchain_anthropic import ChatAnthropic
        
        # Map model names to Anthropic format
        model_mapping = {
            "claude-3-7-sonnet-20250219": "claude-sonnet-3-7-20250219",
            "claude-3-5-sonnet-20241022": "claude-3-5-sonnet-20241022",
        }
        anthropic_model = model_mapping.get(model, model or "claude-3-5-sonnet-20241022")
        
        return ChatAnthropic(
            model=anthropic_model,
            anthropic_api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _create_gemini_client(self, model: str, api_key: Optional[str], temperature: float, max_tokens: int):
        """Create Google Gemini LLM client"""
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        return ChatGoogleGenerativeAI(
            model=model or "gemini-1.5-flash",
            google_api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _create_groq_client(self, model: str, api_key: Optional[str], temperature: float, max_tokens: int):
        """Create Groq LLM client"""
        from langchain_groq import ChatGroq
        
        return ChatGroq(
            model=model or "llama-3.3-70b-versatile",
            groq_api_key=api_key or settings.groq_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _create_deepseek_client(self, model: str, api_key: Optional[str], temperature: float, max_tokens: int):
        """Create DeepSeek LLM client (uses OpenAI-compatible API)"""
        from langchain_openai import ChatOpenAI
        
        return ChatOpenAI(
            model=model or "deepseek-chat",
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _create_grok_client(self, model: str, api_key: Optional[str], temperature: float, max_tokens: int):
        """Create xAI Grok LLM client (uses OpenAI-compatible API)"""
        from langchain_openai import ChatOpenAI
        
        return ChatOpenAI(
            model=model or "grok-2",
            api_key=api_key,
            base_url="https://api.x.ai/v1",
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _create_cohere_client(self, model: str, api_key: Optional[str], temperature: float, max_tokens: int):
        """Create Cohere LLM client"""
        from langchain_cohere import ChatCohere
        
        return ChatCohere(
            model=model or "command-r-plus",
            cohere_api_key=api_key or settings.cohere_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )


# Singleton instance
llm_factory = LLMFactory()
