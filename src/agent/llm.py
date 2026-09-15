import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

from src import config

logger = logging.getLogger(__name__)


def get_phase3_llm(**kwargs: Any) -> BaseChatModel:
    """
    Factory creating the configured LLM for Phase 3 (Analysis Layer).
    Defaults to Gemini (gemini-2.5-flash).
    
    Tries:
    1. ChatGoogleGenerativeAI (native langchain-google-genai)
    2. ChatOpenAI (via Google Gemini OpenAI-compatible endpoint)
    3. Fallback to ChatGroq if provider is explicitly set to groq or gemini is unavailable.
    """
    provider = (config.PHASE3_LLM_PROVIDER or "gemini").lower().strip()
    temperature = kwargs.pop("temperature", 0.3)

    if provider == "gemini":
        gemini_api_key = config.GEMINI_API_KEY
        if gemini_api_key in ("your-gemini-api-key", "your-api-key-here", None, ""):
            gemini_api_key = None

        if gemini_api_key:
            gemini_model = config.GEMINI_MODEL or "gemini-2.5-flash"

            # 1. Native langchain-google-genai
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI

                logger.debug("Initializing ChatGoogleGenerativeAI with model=%s", gemini_model)
                return ChatGoogleGenerativeAI(
                    model=gemini_model,
                    google_api_key=gemini_api_key,
                    temperature=temperature,
                    **kwargs,
                )
            except ImportError:
                logger.debug("langchain-google-genai not found, attempting OpenAI-compatible Gemini endpoint")

            # 2. Gemini via OpenAI-compatible endpoint (using langchain-openai)
            try:
                from langchain_openai import ChatOpenAI

                logger.debug("Initializing ChatOpenAI for Gemini with model=%s", gemini_model)
                return ChatOpenAI(
                    model=gemini_model,
                    api_key=gemini_api_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    temperature=temperature,
                    **kwargs,
                )
            except Exception as exc:
                logger.warning("Could not initialize Gemini via OpenAI client: %s", exc)

    # Fallback to Groq if provider is groq or gemini initialization was bypassed
    try:
        from langchain_groq import ChatGroq

        groq_api_key = config.GROQ_API_KEY or config.LLM_API_KEY
        groq_model = config.GROQ_MODEL
        logger.debug("Initializing ChatGroq fallback with model=%s", groq_model)
        return ChatGroq(
            api_key=groq_api_key,
            model=groq_model,
            temperature=temperature,
            **kwargs,
        )
    except Exception as exc:
        logger.error("Failed to initialize any LLM provider: %s", exc)
        raise
