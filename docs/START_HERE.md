# Getting Started with KogniSync

Welcome to **KogniSync** — the multimodal journey intelligence and synchronized booking engine.

This guide provides developers, evaluators, and hackathon judges with a frictionless setup experience.

---

## ⚡ Quick Start: One Command

To start the entire application (infrastructure, database migrations, backend API, and frontend UI), open a terminal in the repository root and run:

```powershell
.\start.bat
```

That single command automatically:
1. **Validates prerequisites**: Checks for Python 3.10+, Node.js 18+, Git, and free ports (`8000`, `5173`).
2. **Bootstraps environment**: Creates `.env` from `.env.example` with generated cryptographic keys (or preserves existing `.env`).
3. **Manages dependencies**: Automatically bootstraps `.venv` and installs frontend packages (`npm ci`), caching dependency hashes for near-instant repeat boots.
4. **Orchestrates infrastructure**: Detects or starts PostgreSQL 16 on port `5434` and Redis 7 on port `6380` via Docker Compose.
5. **Applies database migrations**: Runs safe Alembic migrations (`scripts/migrate.py upgrade`).
6. **Launches services**: Spawns FastAPI backend (`http://127.0.0.1:8000`) and Vite frontend (`http://127.0.0.1:5173`).
7. **Verifies readiness**: Polls health endpoints before opening your default web browser to the application.

---

## 🛠️ Command-Line Options

You can pass options directly to `.\start.bat` or the underlying `scripts/start_kognisync.ps1`:

| Flag | Description |
| :--- | :--- |
| `-NoBrowser` | Suppress opening the default browser after readiness verification. |
| `-AllowOfflineFallback` | If Docker or PostgreSQL is unavailable, start in offline mode using resilient corridor estimation. |
| `-SkipInfrastructure` | Skip PostgreSQL and Redis detection and orchestration entirely. |
| `-DryRun` | Run all preflight checks and output the execution plan without starting services or containers. |
| `-TimeoutSeconds <int>` | Maximum seconds to wait for backend/frontend readiness (default: `60`). |
| `-ResetDemoState` | Automatically execute `scripts/reset_demo_state.py` after readiness is achieved. |
| `-Help` | Display help and usage instructions. |

### Examples

```powershell
# Run preflight validation without launching services
.\start.bat -DryRun

# Run in presentation/offline mode without requiring Docker
.\start.bat -AllowOfflineFallback

# Start in headless mode (e.g. for CI or automated scripts)
.\start.bat -NoBrowser

# Start with a fresh demo state
.\start.bat -ResetDemoState
```

---

## 📋 System Prerequisites

| Dependency | Minimum Version | Notes |
| :--- | :--- | :--- |
| **OS** | Windows 10/11 or Linux / macOS | Tested on Windows 11 with PowerShell 5.1 & PowerShell 7. |
| **Python** | 3.10+ (tested with 3.12, 3.13) | Standard Python installed and accessible via PATH or `py` launcher. |
| **Node.js** | 18+ (tested with 20, 22) | Includes `npm` and `npx`. |
| **Git** | Any modern version | Required for version control and workspace verification. |
| **Docker Desktop** | Recommended | Required for PostgreSQL 16 & Redis 7 containers. (If absent, use `-AllowOfflineFallback`). |

---

## 🌐 Application Endpoints

Once KogniSync has finished starting, the following endpoints are available:

- **Frontend Web UI**: [http://127.0.0.1:5173](http://127.0.0.1:5173)
- **Backend API**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive OpenAPI Docs (Swagger)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Backend Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **Database Health**: [http://127.0.0.1:8000/health/db](http://127.0.0.1:8000/health/db)
- **Redis Health**: [http://127.0.0.1:8000/health/redis](http://127.0.0.1:8000/health/redis)

---

## 🗄️ PostgreSQL Canonical Schema Initialization

KogniSync enforces strict database schema integrity and lifecycle separation:

### 1. Fresh Installation Lifecycle
When `.\start.bat` is executed on a machine with a newly created PostgreSQL container:
1. **Empty State Detection**: The launcher inspects `public` schema tables. If `0` tables exist, it detects a fresh database.
2. **Safe Schema Application**: It applies the immutable canonical schema (`BookingInventory/data/schema.sql`) in a single transaction, creating all 20 canonical tables without modifying or dropping any schemas.
3. **Reference Data Population**: It loads canonical reference seed data (`BookingInventory/data/csv/`) in foreign-key dependency order via high-performance `COPY`.
4. **Baseline Migration**: It executes Alembic migration `0001_canonical_baseline`, structurally verifying all tables, primary keys, and foreign keys before recording the baseline in `alembic_version`.

### 2. Protection of Existing Databases
- If an existing database already has the 20 canonical tables, the initializer detects `DatabaseState.INITIALIZED` and **preserves the database untouched**. Existing bookings, holds, user records, and custom data are never overwritten, dropped, or re-inserted.
- If a database contains a partial or corrupted schema (e.g. only 5 of 20 tables exist), the initializer **fails closed** immediately to prevent data corruption.

### 3. Recovery Steps for Failed Initialization
If an unexpected connection drop or external error interrupts initialization:
- All DDL and seed loads are executed within an atomic database transaction. Any error triggers an immediate `ROLLBACK`, leaving the database clean and empty for a safe re-run.
- To inspect database state manually:
  ```powershell
  .venv\Scripts\python scripts/init_canonical_db.py --check-only
  ```
- To verify migration baseline compatibility:
  ```powershell
  .venv\Scripts\python scripts/migrate.py check
  ```

---

## 🛑 Stopping KogniSync

To stop the running application:
1. Return to the terminal where `.\start.bat` is running.
2. Press `Ctrl + C`.

### Safety Guarantees
- **Strict Process Isolation**: Only the specific backend and frontend processes spawned by the launcher are terminated.
- **Unrelated Process Protection**: Any external applications or services running on your machine are left completely untouched.
- **Data Preservation**: Database volumes and the canonical organizer SQLite database (`BookingInventory/data/APS-05.db`) are **never** truncated, pruned, or dropped.

---

## 🔍 Logs & Troubleshooting

Logs are written to the `logs/` directory at the project root:
- `logs/backend.log` & `logs/backend_err.log`: FastAPI Uvicorn server logs.
- `logs/frontend.log` & `logs/frontend_err.log`: Vite dev server logs.

### Common Troubleshooting Scenarios

#### 1. "Port 8000 or 5173 is already occupied"
- Cause: A previous instance of KogniSync or an unrelated service is using the port.
- Resolution: Stop the existing process holding the port. KogniSync fails closed and will never kill existing processes automatically.

#### 2. "PostgreSQL is not running on port 5434 and Docker is not available"
- Cause: Docker Desktop is stopped or not installed, and no native PostgreSQL instance is listening on port 5434.
- Resolution: Start Docker Desktop, or run with `.\start.bat -AllowOfflineFallback` to use offline corridor estimation.

#### 3. Database Reset for Demos
- To reset ephemeral demo data while preserving canonical tables:
  ```powershell
  .venv\Scripts\python scripts/reset_demo_state.py
  ```
