## Architecture
- **Frontend**: HTML5 semantic structure, Vanilla CSS (Glassmorphism, Dark mode, custom variables), Vanilla JS (EventSource SSE streaming, dynamic UI).
- **Backend**: Python (FastAPI, Uvicorn, SQLAlchemy async).
- **LLM Runner**: Native C++ `llama-server` (copied from official `ghcr.io/ggerganov/llama.cpp:server`), managed as a Python subprocess.
- **Database**: PostgreSQL (production via Railway) with automatic fallback to SQLite (`chats.db`) for local developer testing.

## Module Registry
| Module | Path | Responsibility | Depends on | Depended on by |
|--------|------|----------------|------------|----------------|
| Database | [database.py](file:///d:/centy_gguf_q4_gguf-20260528T164811Z-3-001/centy_gguf_q4_gguf/backend/database.py) | Database schemas, connections, pool initialization | SQLAlchemy, asyncpg | main.py |
| LLM Manager | [llm_manager.py](file:///d:/centy_gguf_q4_gguf-20260528T164811Z-3-001/centy_gguf_q4_gguf/backend/llm_manager.py) | Spawns, monitors, and stops the `llama-server` process | subprocess, httpx | main.py |
| Main API | [main.py](file:///d:/centy_gguf_q4_gguf-20260528T164811Z-3-001/centy_gguf_q4_gguf/backend/main.py) | API endpoints, static assets serving, streaming logic | FastAPI, database.py, llm_manager.py | - |
| Web Layout | [index.html](file:///d:/centy_gguf_q4_gguf-20260528T164811Z-3-001/centy_gguf_q4_gguf/frontend/index.html) | HTML5 structure, links to assets, starter prompts | - | main.py |
| Styling | [styles.css](file:///d:/centy_gguf_q4_gguf-20260528T164811Z-3-001/centy_gguf_q4_gguf/frontend/styles.css) | Premium glassmorphism design, dark mode, animations | - | index.html |
| App Logic | [app.js](file:///d:/centy_gguf_q4_gguf-20260528T164811Z-3-001/centy_gguf_q4_gguf/frontend/app.js) | Chat session management, EventSource stream reader, DOM rendering | - | index.html |
| Docker Config | [Dockerfile](file:///d:/centy_gguf_q4_gguf-20260528T164811Z-3-001/centy_gguf_q4_gguf/Dockerfile) | Multi-stage Docker packaging with pre-compiled `llama-server` | - | - |
| Startup Script | [start.sh](file:///d:/centy_gguf_q4_gguf-20260528T164811Z-3-001/centy_gguf_q4_gguf/start.sh) | Execution entry point for container, starts Uvicorn | - | Dockerfile |

## Decisions Log
| # | Date | Decision | Context | Alternatives rejected | Reversal cost |
|---|------|----------|---------|-----------------------|---------------|
| 1 | 2026-05-28 | Subprocess `llama-server` | Compiling `llama-cpp-python` in Docker takes 5-10 minutes and often crashes on Railway build limits. | Python C-bindings (`llama-cpp-python`) | Low |
| 2 | 2026-05-28 | SQLite fallback | Enable local testing without running a PostgreSQL instance. | Hard Postgres requirement | None |
| 3 | 2026-05-28 | Parent Process Lifespan | Python FastAPI manages subprocess lifecycle of `llama-server` to avoid orphaned background processes. | Background shell script launching | Medium |
| 4 | 2026-05-29 | Model download during Docker build via `gdown` | File size (~400MB) exceeds comfortable Git limits. Downloading during container build avoids cold-start latency. | Downloading at runtime in `start.sh` | Low |

## Task Log
| # | Task | Mode | Status | Files | Goals satisfied (G1–G4) | Notes |
|---|------|------|--------|-------|-------------------------|-------|
| 1 | Create lightweight chat application with PostgreSQL, GGUF running on CPU, and a modern frontend | Feature | Completed | All | G1, G2, G3, G4 | Initial task complete, verified locally |
| 2 | Add script to download Qwen2.5 GGUF model from Google Drive folder | Feature | Completed | [download_model.py](file:///f:/llm_centy/download_model.py) | G1, G2, G3 | Setup automatic model downloading via gdown |
| 3 | Fix Docker base image registry and binary path for llama.cpp due to migration to ggml-org | Fix | Completed | [Dockerfile](file:///f:/llm_centy/Dockerfile) | G2, G3 | Update image registry to ghcr.io/ggml-org/llama.cpp:server and binary source path to /app/llama-server |
| 4 | Fix gdown arguments in Dockerfile for gdown v6 compliance | Fix | Completed | [Dockerfile](file:///f:/llm_centy/Dockerfile) | G2, G3 | Remove deprecated --id flag and pass file ID as positional argument |
| 5 | Copy shared libraries (.so) and versioned libraries (.so*) for llama-server and run ldconfig in Dockerfile | Fix | Completed | [Dockerfile](file:///f:/llm_centy/Dockerfile) | G2, G3 | Add COPY instruction for /app/*.so* to /usr/lib/ and run ldconfig |
| 6 | Fix NameErrors in backend/main.py | Fix | Completed | [backend/main.py](file:///f:/llm_centy/backend/main.py) | G2, G3 | Import AsyncSessionLocal and func |






## Known Issues & Technical Debt
| Issue | Severity | Location | Impact on G1 / G3 / G4 | Owner | Plan |
|---|---|---|---|---|---|
| Model loading time | Low | startup | G1 (delays first response slightly at cold start) | - | Resolved via pre-warming check |

## Build & Test Commands
- **Install packages (local)**: `.\venv\Scripts\pip.exe install -r requirements.txt`
- **Run local server**: `$env:USE_MOCK_LLM='true'; .\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
- **Build Container**: `docker build -t centy-ai .`
- **Download Model**: `python download_model.py`
