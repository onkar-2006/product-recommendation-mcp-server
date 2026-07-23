# E-Commerce MCP Server

A production-grade, highly concurrent Model Context Protocol (MCP) Server for search, price comparison, and details extraction from major Indian e-commerce platforms: **Amazon.in**, **Flipkart**, **Meesho**, and **Myntra**.

This server is designed for dual deployment modes:
1. **Local Mode (STDIO)**: Integrates directly with local LLM clients like Claude Desktop, Cursor, or VS Code.
2. **Deployed Server Mode (SSE/HTTP)**: Runs as an isolated web service inside Docker, hosted on cloud providers (Render, Railway, Fly.io, AWS) with API Key authentication.

---

## 🛠️ Features

*   **Dual Protocol Support**: Instantly switch between STDIO (local) and SSE (Server-Sent Events over HTTP).
*   **Dynamic Browser Context Pooling**: Uses a semaphore-throttled pool of incognito browser contexts via Playwright to maximize search concurrency while capping RAM/CPU usage.
*   **Embedded SQLite WAL Caching**: Zero-overhead local database (`data/mcp_cache.db`) operating in WAL (Write-Ahead Logging) mode. Caches platform searches (10-min TTL) and product specs (24-hour TTL).
*   **Stateful Cookie Preservation**: Saves browser session cookies to minimize the frequency of anti-bot login challenges.
*   **Advanced Anti-Bot Evasion**: Spoofs languages, plugins, WebGL graphics renderers, masks `navigator.webdriver` flags, and utilizes human-like mouse/scroll patterns.
*   **Self-Correcting Prices**: Parses pricing grids intelligently, sorting current selling prices and original MRPs without depending on specific character encoding symbols.
*   **JSON Script Extraction**: Reads Myntra and Meesho search and PDP values straight from React scripts (`window.__myx`) utilizing multiline regex patterns (`re.DOTALL`).

---

## 📂 Project Structure

```text
ecommerce-mcp/
├── Dockerfile                   # Production container definition (pre-loaded Playwright)
├── requirements.txt             # Application dependencies
├── pyproject.toml               # Pytest configurations
├── .env.example                 # Configuration template
├── .gitignore
│
├── config/
│   └── settings.py              # Configuration schemas via Pydantic Settings
│
├── data/                        # Persistent SQLite cache storage directory
├── logs/                        # Persistent application logs directory
│
├── src/                         # Core codebase
│   ├── main.py                  # Primary server CLI entrypoint
│   ├── core/                    # Low-level systems (Browser Pool, WAL Cache, DB, Logger, Auth)
│   ├── schemas/                 # Pydantic data contracts (Product, CompareResult, Details)
│   ├── scrapers/                # Extractor submodules (Amazon, Flipkart, Meesho, Myntra)
│   └── tools/                   # MCP protocol actions (Search, Compare, Details)
│
└── tests/                       # Test suite (using mock routers for 100% offline runs)
```

---

## 🚀 Local Installation & Setup

### 1. Prerequisites
Ensure you have Python 3.12+ installed.

### 2. Install Dependencies
Clone the repository and set up a virtual environment:
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows PowerShell)
& .venv/Scripts/Activate.ps1

# Activate virtual environment (macOS/Linux)
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Install Playwright Chromium binaries
playwright install chromium
```

### 3. Configure Settings
Copy `.env.example` to `.env` and fill in any rotating residential proxy credentials (highly recommended for production servers to prevent datacenter IP blocks).
```bash
cp .env.example .env
```

---

## 🖥️ Running Locally

### A. Local STDIO Transport (Default)
In STDIO mode, logs write strictly to `logs/mcp.log` and `sys.stderr` to keep `stdout` clean for JSON-RPC messages.

To launch or debug locally using the MCP Inspector:
```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m src.main --transport stdio
# (On Windows, replace with .venv/Scripts/python -m src.main --transport stdio)
```

To integrate with **Claude Desktop**, add the following block to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "ecommerce-mcp": {
      "command": "python",
      "args": ["-m", "src.main", "--transport", "stdio"],
      "cwd": "C:/path/to/ecommerce-mcp",
      "env": {
        "HEADLESS": "true"
      }
    }
  }
}
```

### B. Deployed SSE/HTTP Transport
Launches an HTTP server (Uvicorn) hosting the SSE endpoint at `http://localhost:8000/sse`.

```bash
python -m src.main --transport sse --port 8000
```
Verify the server status:
```bash
curl http://localhost:8000/health
```

---

## 🐳 Production Container Deployment (Docker)

To deploy to cloud services like Render, Railway, or AWS:

### 1. Build Docker Image
```bash
docker build -t ecommerce-mcp .
```

### 2. Run Container
Pass your secure `API_KEY` token and optional proxy gateway as environment variables:
```bash
docker run -d \
  -p 8000:8000 \
  -e TRANSPORT=sse \
  -e API_KEY=my_secure_secret_token_123 \
  -e PROXY_SERVER=http://myproxyprovider.com:8000 \
  -e PROXY_USERNAME=user \
  -e PROXY_PASSWORD=pass \
  --name ecommerce-mcp-server \
  ecommerce-mcp
```

### 3. Connect to Deployed SSE Server
MCP clients connecting to your deployed server will send request frames subscribing to the server stream:
*   Endpoint: `http://<your-domain>/sse`
*   Header auth (if `API_KEY` is set): `Authorization: Bearer my_secure_secret_token_123`

---

## ☁️ Deploying to FastMCP Cloud (Prefect Horizon)

Prefect Horizon is the managed platform built by the FastMCP team for hosting MCP servers. It uses Git-driven deployments:

1. **Commit and Push**: Ensure all changes and `fastmcp.json` are committed and pushed to your GitHub repository.
2. **Connect to Horizon**:
   - Go to your Prefect Horizon/FastMCP Cloud Dashboard.
   - Click "Deploy Server" and authorize your GitHub account.
   - Select your `ecommerce-mcp` repository.
3. **Trigger Build**: FastMCP Cloud will parse the `fastmcp.json` config, automatically install Pytest/Playwright requirements, launch Chromium under the hood, and deploy the server as a secure HTTPS endpoint.

---

## 🔧 MCP Tools Schema

The server registers 3 actions to the LLM:

1.  `search_products`: Queries select platforms concurrently and returns aggregated listings.
    *   Parameters: `query` (str), `platforms` (list[str], default: all), `limit` (int, default: 5).
2.  `compare_prices`: Scrapes platforms, aggregates items, sorts them by price, and tags the cheapest product.
    *   Parameters: `query` (str), `platforms` (list[str], default: all).
3.  `get_product_details`: Fetches full product descriptions, specifications, image URLs, stock status, and merchant selling names.
    *   Parameters: `url` (str), `platform` (str).

---

## 🧪 Running Tests
All tests route network calls locally via Playwright's `route` interceptor, letting the suite run completely offline.

```bash
# Run all tests
pytest -vv
```
