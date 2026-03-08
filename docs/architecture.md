# Sentinel K8s - Architecture Diagram

## High-Level System Architecture

```
                                   EXTERNAL SOURCES
                    +------------------------------------------+
                    |                                          |
                    |   Kubernetes Cluster     Alertmanager    |
                    |   (Event Exporter)       (Prometheus)    |
                    |        |                      |          |
                    +--------|----------------------|----------+
                             |                      |
                   POST /webhook/event    POST /webhook/alert
                             |                      |
                    +--------v----------------------v----------+
                    |          WEBHOOK RECEIVER (:8000)         |
                    |          webhook_receiver.py              |
                    |                                          |
                    |  /webhook/event     Classify severity    |
                    |  /webhook/admission SHA-256 event ID     |
                    |  /webhook/alert     Store to MySQL       |
                    |  /health                                 |
                    +---------------------|--------------------+
                                          |
                                          v
+-------------------------+     +-------------------+     +-------------------------+
|   MCP SERVER (stdio)    |     |     MySQL 8       |     |  BACKEND API (:8001)    |
|   mcp_server.py         |---->|   sentinel_k8s    |<----|  chat_ui/backend/       |
|                         |     |                   |     |                         |
|  10 Tools for Claude    |     |  k8s_events       |     |  FastAPI + CORS         |
|  Desktop via MCP        |     |  app_config       |     |  Bearer + TOTP Auth     |
|                         |     |  users            |     |  Session Management     |
+------|------------------+     |  sessions         |     +------|------------------+
       |                        +-------------------+            |
       |                                                         |
       +--------------------+------------------------------------+
                            |
                            v
              +----------------------------+
              |    Kubernetes API Server    |
              |    (via kubectl subprocess) |
              +----------------------------+


                    +------------------------------------------+
                    |          FRONTEND (:5173/80)              |
                    |          chat_ui/frontend/                |
                    |                                          |
                    |   React 19 + TypeScript + Vite           |
                    |   Nginx reverse proxy in production      |
                    |                                          |
                    |   Communicates with Backend API (:8001)  |
                    +------------------------------------------+


                    +------------------------------------------+
                    |          CLAUDE DESKTOP                   |
                    |                                          |
                    |   Connects to MCP Server via stdio       |
                    |   Uses 10 tools for event analysis       |
                    +------------------------------------------+
```

## Detailed Component Diagram

```
+===========================================================================+
|                         SENTINEL K8S PROJECT                               |
+===========================================================================+
|                                                                           |
|  webhook/                          chat_ui/backend/                       |
|  +-------------------------------+ +-----------------------------------+ |
|  |                               | |                                   | |
|  | database.py (SHARED MODULE)   | | main.py                          | |
|  |   MySQL connection pool (5)   | |   FastAPI app entry              | |
|  |   get_db() / get_cursor()     | |   Lifespan: init DB, seed admin  | |
|  |   wait_for_db() / init_db()   | |   Session cleanup loop (60s)     | |
|  |   ConfigStore (60s TTL cache) | |                                   | |
|  |   User CRUD (bcrypt)          | | auth.py                          | |
|  |   Session CRUD                | |   POST /api/auth/login           | |
|  |   seed_admin_user()           | |   POST /api/auth/verify-totp     | |
|  |                               | |   require_auth() dependency      | |
|  | mcp_server.py                 | |   QR code generation (pyotp)     | |
|  |   FastMCP "k8s-event-analyzer"| |                                   | |
|  |   10 tools (see below)        | | events_api.py                    | |
|  |   Runs as stdio MCP server    | |   GET  /api/events               | |
|  |                               | |   GET  /api/events/stats         | |
|  | webhook_receiver.py           | |   GET  /api/events/stream (SSE)  | |
|  |   POST /webhook/event         | |   GET  /api/events/{id}          | |
|  |   POST /webhook/admission     | |                                   | |
|  |   POST /webhook/alert         | | cluster_api.py                   | |
|  |   GET  /health                | |   GET  /api/cluster/nodes        | |
|  |   Severity classification     | |   GET  /api/cluster/namespaces   | |
|  |                               | |   GET  /api/cluster/pods         | |
|  +-------------------------------+ |   GET  /api/cluster/logs         | |
|                                     |   GET  /api/cluster/resources    | |
|                                     |   GET  /api/cluster/resources/   | |
|                                     |        trace (LLM analysis)     | |
|                                     |   GET  /api/cluster/jvm          | |
|                                     |   GET  /api/cluster/network      | |
|                                     |                                   | |
|                                     | chat_handler.py                  | |
|                                     |   Multi-turn LLM chat            | |
|                                     |   Skill expansion                | |
|                                     |   Tool call loop (max 10 rounds) | |
|                                     |                                   | |
|                                     | tool_executor.py                 | |
|                                     |   Maps tool names to mcp_server  | |
|                                     |   functions (10 tools)           | |
|                                     |                                   | |
|                                     | llm_client.py                    | |
|                                     |   OpenAI-compatible client       | |
|                                     |   Via LiteLLM proxy              | |
|                                     |                                   | |
|                                     | config.py                        | |
|                                     |   Reads LLM config from DB       | |
|                                     |   (litellm_base_url, model, key) | |
|                                     +-----------------------------------+ |
|                                                                           |
|  chat_ui/frontend/                                                        |
|  +-----------------------------------+                                    |
|  |                                   |                                    |
|  | React 19 + TypeScript + Vite      |                                    |
|  |                                   |                                    |
|  | Pages:                            |                                    |
|  |   /login        LoginPage         |                                    |
|  |   /             DashboardPage     |                                    |
|  |   /events       EventExplorerPage |                                    |
|  |   /nodes        NodesPage         |                                    |
|  |   /logs         LogsPage          |                                    |
|  |   /resources    ResourceAllocation |                                    |
|  |   /jvm          JvmDetailsPage    |                                    |
|  |   /network      NetworkLatencyPage|                                    |
|  |   /ai-insights  AIInsightsPage    |                                    |
|  |                                   |                                    |
|  | Context Providers:                |                                    |
|  |   AuthContext (token management)  |                                    |
|  |   ChatContext (AI chat state)     |                                    |
|  |                                   |                                    |
|  | Production: Nginx serves static   |                                    |
|  | files + reverse proxy to backend  |                                    |
|  +-----------------------------------+                                    |
|                                                                           |
+===========================================================================+
```

## Data Flow Diagrams

### 1. Event Ingestion Flow

```
Kubernetes Cluster
       |
       | kube-event-exporter / custom webhook
       |
       v
POST /webhook/event
       |
       v
+------------------+
| Classify severity |  SEVERITY_MAP: CrashLoopBackOff->critical,
| (reason-based)   |                OOMKilled->critical,
+------------------+                BackOff->warning, etc.
       |
       v
+------------------+
| Generate ID      |  SHA-256(kind:ns:name:reason:msg:timestamp)[:16]
+------------------+
       |
       v
+------------------+
| INSERT IGNORE    |  k8s_events table
| into MySQL       |  status='new', severity=classified
+------------------+
       |
       +-----> SSE stream (/api/events/stream) polls every 2s
       |
       +-----> Dashboard/Events pages query on demand
       |
       +-----> AI chat tools query via list_events/get_event
```

### 2. AI Chat Flow

```
User (Frontend)
       |
       | POST /api/chat  { messages: [...] }
       v
+------------------+
| Auth Check       |  Bearer token -> sessions table
+------------------+
       |
       v
+------------------+
| Skill Expansion  |  "[Cluster Health]" -> full prompt from skills.yaml
+------------------+
       |
       v
+--------------------+
| LLM API Call       |  OpenAI-compatible via LiteLLM proxy
| (system_prompt.md) |  Model configured in app_config table
+--------------------+
       |
       v
+--------------------+      +---------------------------+
| Tool Call?         |--yes->| Execute Tool              |
| (up to 10 rounds) |       |                           |
+--------------------+       | list_events     -> MySQL  |
       |                     | get_event       -> MySQL  |
       | no                  | analyze_event   -> MySQL  |
       v                     | get_event_summary-> MySQL |
+--------------------+       | mark_resolved   -> MySQL  |
| Return assistant   |       | get_cluster_info -> kubectl|
| message to user    |       | apply_fix       -> kubectl|
+--------------------+       | trace_resource  -> kubectl|
                             | get_jvm_details -> kubectl|
                             | get_network_status->kubectl|
                             +---------------------------+
                                        |
                                  result fed back
                                  to LLM for next
                                  round
```

### 3. Authentication Flow

```
User
  |
  | POST /api/auth/login { username, password }
  v
+------------------+
| Verify bcrypt    |  users table -> password_hash
+------------------+
  |
  v
+------------------+       +---------------------+
| TOTP configured? |--no-->| Generate TOTP secret|
+------------------+       | Return QR code PNG  |
  |                        | (base64) + secret   |
  | yes                    +---------------------+
  v                               |
+------------------+              |
| Create temp      |<-------------+
| session (5 min)  |  sessions table, is_temp=TRUE
+------------------+
  |
  | POST /api/auth/verify-totp { temp_token, code }
  v
+------------------+
| Verify TOTP code |  pyotp.TOTP.verify(code, valid_window=1)
+------------------+
  |
  v
+------------------+
| Delete temp      |
| session          |
+------------------+
  |
  v
+------------------+
| Create full      |  sessions table, is_temp=FALSE, TTL=24h
| session (24h)    |  Return bearer token
+------------------+
```

## MCP Server Tools (Claude Desktop)

```
+-------------------------------------------------------------------+
|                    MCP Server: k8s-event-analyzer                  |
|                    Transport: stdio                                |
+-------------------------------------------------------------------+
|                                                                   |
|  DB Tools (MySQL)              K8s Tools (kubectl subprocess)     |
|  +-------------------------+   +-------------------------------+  |
|  | list_events             |   | get_cluster_info              |  |
|  |   Filter: status,       |   |   Read-only kubectl           |  |
|  |   severity, namespace   |   |   Allowed: get, describe,     |  |
|  |                         |   |   logs, top, version, events  |  |
|  | get_event               |   |   Blocks write operations     |  |
|  |   Full event + payload  |   |                               |  |
|  |                         |   | apply_fix                     |  |
|  | analyze_event           |   |   --dry-run=client by default |  |
|  |   Template-based        |   |   Blocks: delete ns, drain,   |  |
|  |   analysis + diagnostics|   |   cordon, taint               |  |
|  |   Marks status=analyzed |   |                               |  |
|  |                         |   | trace_resource_usage          |  |
|  | get_event_summary       |   |   describe + top + events     |  |
|  |   By severity + status  |   |   + logs for a pod            |  |
|  |   Latest 5 events       |   |                               |  |
|  |                         |   | get_jvm_details               |  |
|  | mark_resolved           |   |   Expected (env) vs Actual    |  |
|  |   Updates status +      |   |   (jcmd) JVM flags            |  |
|  |   resolution note       |   |                               |  |
|  +-------------------------+   | get_network_status            |  |
|                                |   Services, endpoints,         |  |
|                                |   network policies, issues     |  |
|                                +-------------------------------+  |
+-------------------------------------------------------------------+
```

## Infrastructure & Deployment

```
+===================================================================+
|                    Docker Compose Stack                             |
|                    (deploy/docker-compose.yml)                      |
+===================================================================+
|                                                                   |
|  +-------------+  +-------------------+  +---------+  +---------+ |
|  |   MySQL 8   |  | Webhook Receiver  |  | Backend |  | Frontend| |
|  |             |  |                   |  |         |  |         | |
|  | Port: 3008  |  | Port: 8000       |  | Port:   |  | Port:   | |
|  |  -> 3306    |  |                   |  | 8001    |  | 5173    | |
|  |             |  | Dockerfile.webhook|  |         |  |  -> 80  | |
|  | Volume:     |  |                   |  | Dockerfile| |         | |
|  | mysql_data  |  | Depends: mysql   |  | .backend|  | Dockerfile|
|  |             |  |                   |  |         |  | .frontend|
|  | Init:       |  |                   |  | Depends:|  |         | |
|  | config/     |  |                   |  | mysql   |  | Depends:| |
|  | init.sql    |  |                   |  |         |  | backend | |
|  |             |  |                   |  | Volume: |  |         | |
|  +-------------+  +-------------------+  | ~/.kube |  | Nginx   | |
|                                          | /config |  | reverse | |
|                                          +---------+  | proxy   | |
|                                                       +---------+ |
+===================================================================+
```

## Project Directory Structure

```
k8s_webhook/
|
+-- .dockerignore
|
+-- config/                          Configuration
|   +-- .env                           MySQL credentials, admin password
|   +-- claude_desktop_config.json     MCP server config for Claude Desktop
|   +-- init.sql                       MySQL schema seed
|
+-- deploy/                          Deployment
|   +-- docker-compose.yml             4-service stack (mysql, webhook, backend, frontend)
|   +-- Dockerfile.webhook             Python 3.12 slim
|   +-- Dockerfile.backend             Python 3.12 slim + kubectl
|   +-- Dockerfile.frontend            Node 20 build + Nginx serve
|   +-- k8s-manifests.yaml             Kubernetes Namespace + Deployment + Service
|
+-- docs/                            Documentation
|   +-- About.html                     Project overview page
|   +-- about_db.html                  Database documentation
|   +-- Questions.md                   Learning notes
|   +-- architecture.md               This file
|
+-- webhook/                         Core Services (shared Python modules)
|   +-- database.py                    MySQL pool, helpers, ConfigStore, auth helpers
|   +-- mcp_server.py                  MCP tools (10 tools for Claude Desktop)
|   +-- webhook_receiver.py            FastAPI webhook endpoints
|   +-- requirements.txt               Python dependencies
|
+-- chat_ui/                         Dashboard Application
    +-- __init__.py
    +-- .env.example
    |
    +-- backend/                     FastAPI Dashboard API
    |   +-- __init__.py
    |   +-- main.py                    App entry, lifespan, route registration
    |   +-- auth.py                    Login + TOTP 2FA + session management
    |   +-- events_api.py              Event list, stats, stream (SSE), detail
    |   +-- cluster_api.py             Nodes, pods, logs, resources, JVM, network
    |   +-- chat_handler.py            Multi-turn LLM chat with tool calls
    |   +-- tool_executor.py           Maps tool names to mcp_server functions
    |   +-- tool_registry.py           OpenAI function-calling tool definitions
    |   +-- llm_client.py              OpenAI client via LiteLLM proxy
    |   +-- config.py                  DB-backed LLM config (ConfigStore)
    |   +-- models.py                  Pydantic request/response models
    |   +-- system_prompt.md           LLM system prompt
    |   +-- skills.yaml                Chat skill definitions
    |   +-- requirements.txt           Backend Python dependencies
    |
    +-- frontend/                    React Dashboard UI
        +-- src/
        |   +-- App.tsx                Router: 9 pages + auth guard
        |   +-- main.tsx               React entry point
        |   +-- context/               AuthContext, ChatContext
        |   +-- components/            Layout, shared UI components
        |   +-- pages/                 Dashboard, Events, Nodes, Logs,
        |                              Resources, JVM, Network, AI Insights, Login
        +-- index.html
        +-- vite.config.ts
        +-- package.json
        +-- nginx.conf                 Production reverse proxy config
```

## Technology Stack

```
+-------------------+--------------------------------------------------+
| Layer             | Technology                                        |
+-------------------+--------------------------------------------------+
| Frontend          | React 19, TypeScript, Vite, React Router          |
| Backend API       | FastAPI (Python 3.12), Uvicorn                    |
| AI/LLM            | OpenAI-compatible API via LiteLLM proxy           |
| MCP Server        | FastMCP (Python), stdio transport                 |
| Database          | MySQL 8, mysql-connector-python, connection pool  |
| Auth              | bcrypt (passwords), pyotp + QR (TOTP 2FA)         |
| K8s Integration   | kubectl subprocess calls (read-only + dry-run)    |
| Containerization  | Docker, Docker Compose                            |
| K8s Deployment    | Namespace + Deployment + Service manifests         |
| Web Server        | Nginx (frontend static + reverse proxy)           |
+-------------------+--------------------------------------------------+
```

## Port Map

```
+----------+---------------------------+------------------+
| Port     | Service                   | Protocol         |
+----------+---------------------------+------------------+
| 3008     | MySQL (mapped from 3306)  | MySQL            |
| 8000     | Webhook Receiver          | HTTP (FastAPI)   |
| 8001     | Backend Dashboard API     | HTTP (FastAPI)   |
| 5173     | Frontend (mapped from 80) | HTTP (Nginx)     |
+----------+---------------------------+------------------+
```

## Security Boundaries

```
                          UNAUTHENTICATED
                    +-------------------------+
                    | POST /webhook/event     |
                    | POST /webhook/admission |  Webhook Receiver
                    | POST /webhook/alert     |  (cluster-internal)
                    | GET  /health            |
                    +-------------------------+
                    | POST /api/auth/login    |
                    | POST /api/auth/verify-  |  Backend API
                    |       totp              |  (public auth endpoints)
                    | GET  /api/health        |
                    +-------------------------+

                          AUTHENTICATED
                    (Bearer token + TOTP 2FA)
                    +-------------------------+
                    | GET  /api/events/*      |
                    | GET  /api/cluster/*     |  Backend API
                    | POST /api/chat          |  (protected endpoints)
                    | GET  /api/skills        |
                    | POST /api/reload        |
                    +-------------------------+

                         WRITE SAFETY
                    +-------------------------+
                    | get_cluster_info:       |
                    |   Only get/describe/    |  MCP + cluster_api.py
                    |   logs/top/version      |
                    |                         |
                    | apply_fix:              |
                    |   --dry-run=client      |
                    |   default               |
                    |   Blocks: delete ns,    |
                    |   drain, cordon, taint  |
                    +-------------------------+
```
