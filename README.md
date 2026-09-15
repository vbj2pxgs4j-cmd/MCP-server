# Weekly App Review Pulse via MCP

Automated system that ingests Google Play Store reviews for **Groww**, clusters them into themes and extracts verbatim quotes & action ideas using a **LangChain AI Agent**, generates a structured one-page weekly pulse note, and delivers it via **Google Docs** and **Gmail** using **MCP (Model Context Protocol)** servers.

---

## Architecture Overview

```
Google Play Store
       │
       ▼
[Layer 1: Scraper & Normalizer]  ──► Cache: data/reviews/latest.json
       │
       ▼
[Layer 2: LangChain AI Agent]    ──► ThemeClustererTool, QuoteSelectorTool, ActionGeneratorTool
       │
       ▼
[Layer 3: Pulse Generator]       ──► Jinja2 Markdown & HTML rendering
       │
       ▼
[Layer 4: MCP Delivery]          ──► Google Docs MCP & Gmail MCP
```

---

## Project Structure

```
MCP-server/
├── doc/                             # System documentation & specifications
├── src/
│   ├── __init__.py
│   ├── config.py                    # Environment & configuration loader
│   ├── scraper/                     # Layer 1 — Play Store ingestion & normalization
│   ├── agent/                       # Layer 2 — LangChain AI Agent & custom tools
│   │   └── tools/
│   ├── pulse/                       # Layer 3 — Markdown/HTML template rendering
│   │   └── templates/
│   └── delivery/                    # Layer 4 — MCP delivery (Docs & Gmail)
├── data/
│   └── reviews/                     # Local review cache (gitignored)
├── config/
│   └── mcp_config.json              # MCP server configurations
├── tests/                           # Unit & integration test suite
├── .env.example                     # Environment template
├── .gitignore                       # Ignored secrets, cache, and virtualenvs
├── requirements.txt                 # Python dependencies
└── README.md
```

---

## Getting Started

### 1. Prerequisites
- Python 3.11+
- Node.js (for running MCP servers via `npx`)

### 2. Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

### 3. Verification Commands (Phase 1)
```bash
# Verify config loading
python3 -c "from src.config import TARGET_APP_ID; print(TARGET_APP_ID)"

# Verify subpackages importability
python3 -c "import src, src.scraper, src.agent, src.agent.tools, src.pulse, src.delivery, tests; print('All packages imported successfully')"
```
