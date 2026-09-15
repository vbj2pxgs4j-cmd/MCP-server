import os
from dotenv import load_dotenv

load_dotenv()

# Phase 2 LLM Config (Groq)
PHASE2_LLM_PROVIDER: str = os.getenv("PHASE2_LLM_PROVIDER", "groq")
GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", os.getenv("LLM_MODEL", "openai/gpt-oss-120b"))

# Groq Rate Limits (openai/gpt-oss-120b)
GROQ_RPM_LIMIT: int = int(os.getenv("GROQ_RPM_LIMIT", "30"))       # 30 requests / minute
GROQ_RPD_LIMIT: int = int(os.getenv("GROQ_RPD_LIMIT", "1000"))     # 1,000 requests / day
GROQ_TPM_LIMIT: int = int(os.getenv("GROQ_TPM_LIMIT", "8000"))     # 8,000 tokens / minute
GROQ_TPD_LIMIT: int = int(os.getenv("GROQ_TPD_LIMIT", "200000"))   # 200,000 tokens / day

# Phase 3 LLM Config (Gemini)
PHASE3_LLM_PROVIDER: str = os.getenv("PHASE3_LLM_PROVIDER", "gemini")
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("LLM_API_KEY")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Generic / Backward Compatibility Aliases
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", PHASE3_LLM_PROVIDER)
LLM_API_KEY: str | None = GEMINI_API_KEY or GROQ_API_KEY
LLM_MODEL: str = os.getenv("LLM_MODEL", GEMINI_MODEL)

# Target App Config
TARGET_APP_ID: str = os.getenv("TARGET_APP_ID", "com.nextbillion.groww")
REVIEW_WINDOW_WEEKS: int = int(os.getenv("REVIEW_WINDOW_WEEKS", "8"))
PULSE_RECIPIENT_EMAIL: str | None = os.getenv("PULSE_RECIPIENT_EMAIL")

# Google Workspace & MCP Server Delivery (Phase 5)
MCP_SERVER_URL: str = os.getenv("MCP_SERVER_URL", "https://mcp-server-1-production-7ea1.up.railway.app/sse")
GOOGLE_DOC_ID: str | None = os.getenv("GOOGLE_DOC_ID")
GOOGLE_CLIENT_ID: str | None = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET: str | None = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN: str | None = os.getenv("GOOGLE_REFRESH_TOKEN")

