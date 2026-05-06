# AI Document & Multimedia Q&A

A full-stack web application that lets users upload **PDFs, audio, and video files**, then ask questions, get summaries, and jump to specific timestamps in media — all powered by an LLM with retrieval-augmented generation (RAG).

> **Built for the SDE-1 Programming Assignment.**
> 100% of core requirements + bonus features (vector search, streaming responses, JWT auth) implemented.

---

## ✨ Features

### Core
- 📤 **Upload PDFs, audio (mp3/wav/m4a/ogg), and video (mp4/mov/webm)** — chunked upload with size limits.
- 🤖 **AI chatbot** — ask any question about an uploaded file. Answers are grounded in the document via RAG (won't hallucinate beyond the source).
- 📝 **Auto summarization** — every uploaded file gets a 4–7 sentence summary.
- ⏱️ **Timestamp extraction** — for audio/video, the chatbot returns the exact start/end times of the segments it used.
- ▶️ **"Play" button on every citation** — jumps the audio/video player to the relevant moment.
- 📜 **Full transcript view** with click-to-seek.

### Bonus
- 🔎 **Semantic vector search** — ChromaDB + OpenAI embeddings for high-recall retrieval.
- ⚡ **Real-time streaming chat responses** — tokens stream in via Server-Sent Events.
- 🔐 **JWT-based authentication** — multi-user, scoped data (you can only see your own files).
- 🚦 **Redis rate-limiting + caching** — per-user limits on uploads (10/min) and chat (30/min); embedding cache cuts repeat-query cost.
- 🧪 **99% backend test coverage** (137 tests) — unit + integration with mocked OpenAI, fakeredis for Redis paths.
- 🎬 **Automatic format conversion** — supports any video format (`.mov`, `.mkv`, etc.) by transcoding to mp3 via ffmpeg before transcription.
- 🐳 **Fully containerized** — `docker-compose up` and you're running.
- 🤖 **GitHub Actions CI/CD** — runs tests, builds images, and **auto-deploys to Render** on push to main.
- ☁️ **One-click cloud deploy** via Render Blueprint (`render.yaml`) — Postgres + backend + frontend provisioned automatically.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  React + Vite + Tailwind  (port 3000, served by nginx)      │
│  ─ Login / Register                                         │
│  ─ File upload, list, summary, transcript                   │
│  ─ Chat with streaming (SSE) + Play-at-timestamp            │
└──────────────────┬──────────────────────────────────────────┘
                   │  /api/v1/* (proxied through nginx)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Backend (port 8000)                                │
│  ┌────────────┐  ┌──────────────────┐  ┌────────────────┐   │
│  │   Auth     │  │   File pipeline  │  │   Chat / RAG   │   │
│  │   (JWT)    │  │ PDF / Whisper /  │  │  Stream + cite │   │
│  │            │  │ chunk / index    │  │                │   │
│  └────────────┘  └──────────────────┘  └────────────────┘   │
└────┬─────────────────────┬───────────────────────┬──────────┘
     │                     │                       │
     ▼                     ▼                       ▼
┌─────────┐         ┌──────────────┐        ┌──────────────┐
│Postgres │         │   ChromaDB   │        │  OpenAI API  │
│(users,  │         │ (embeddings, │        │  Whisper +   │
│ files,  │         │  per-file    │        │  GPT + emb.  │
│ chats)  │         │  collection) │        │              │
└─────────┘         └──────────────┘        └──────────────┘
```

### Processing pipeline
1. User uploads a file → backend saves it, creates a `File` row with status `pending`.
2. A FastAPI **background task** picks it up:
   - **PDF**: pypdf extracts page-by-page text.
   - **Audio/Video**: OpenAI Whisper produces text + per-segment timestamps.
3. Text is **chunked** (PDFs page-aware, media in ~30s windows) and **embedded** with `text-embedding-3-small`.
4. Embeddings are stored in **ChromaDB** in a per-file collection with metadata (page numbers / timestamps).
5. A summary is generated with `gpt-4o-mini`.
6. File status flips to `ready`.

### RAG flow on a question
1. User asks question → embed the question → top-k semantic search in the file's Chroma collection.
2. Build a context block tagged with `[chunk N, page X]` or `[chunk N, 12.5s-25.0s]`.
3. Stream the LLM response via SSE; emit a `citations` event up-front so the UI can show source pills with **Play** buttons.

---

## 🚀 Quick start

### Prerequisites
- Docker & Docker Compose
- An OpenAI API key with at least ~$3 of credit (Whisper costs $0.006/min; GPT-4o-mini is very cheap)

### 1. Clone and configure
```bash
git clone <your-repo-url> ai-qa-app
cd ai-qa-app
cp .env.example .env
# edit .env and set OPENAI_API_KEY
```

### 2. Run everything
```bash
docker compose up --build
```

### 3. Open the app
- **Frontend:** http://localhost:3000
- **API docs (Swagger UI):** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

Register a new account, upload a PDF or short audio file, wait a few seconds for processing, then ask away.

---

## 🧑‍💻 Local development (without Docker)

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Use a local SQLite DB if you don't want Postgres:
export DATABASE_URL="sqlite:///./dev.db"
export OPENAI_API_KEY="sk-..."
export SECRET_KEY="$(openssl rand -hex 32)"
export UPLOAD_DIR="./storage/uploads"
export CHROMA_DIR="./storage/chroma"

uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# Vite proxies /api → http://localhost:8000 automatically
```

---

## 📚 API Documentation

Swagger UI auto-generated at **`/docs`**, ReDoc at **`/redoc`**.

### Auth
| Method | Path                  | Purpose                                    |
|--------|-----------------------|--------------------------------------------|
| POST   | `/api/v1/auth/register` | Create an account, returns JWT           |
| POST   | `/api/v1/auth/login`    | Returns JWT on valid credentials         |
| GET    | `/api/v1/auth/me`       | Current user (requires Bearer token)     |

### Files
| Method | Path                          | Purpose                                  |
|--------|-------------------------------|------------------------------------------|
| POST   | `/api/v1/files`               | Multipart upload (`file` field)          |
| GET    | `/api/v1/files`               | List your files                          |
| GET    | `/api/v1/files/{id}`          | File detail with transcript segments     |
| DELETE | `/api/v1/files/{id}`          | Delete file + its vector index           |
| GET    | `/api/v1/files/{id}/media`    | Stream raw media bytes for `<audio>/<video>` |

### Chat
| Method | Path                              | Purpose                                  |
|--------|-----------------------------------|------------------------------------------|
| POST   | `/api/v1/chat/sessions`           | Create a session (optionally bind a file)|
| GET    | `/api/v1/chat/sessions`           | List your sessions                       |
| GET    | `/api/v1/chat/sessions/{id}`      | Session detail with messages + citations |
| POST   | `/api/v1/chat/ask`                | Ask, get full answer (non-streaming)     |
| POST   | `/api/v1/chat/ask/stream`         | Ask, get **SSE-streamed** answer         |

#### Streaming event format
```
event: session
data: {"session_id": 12}

event: citations
data: [{"file_id":1,"filename":"x.mp3","snippet":"...","start":12.5,"end":24.0}]

event: token
data: Hello

event: token
data:  world

event: done
data: ok
```

---

## 🧪 Testing

```bash
cd backend
pytest --cov=app --cov-config=.coveragerc --cov-report=term
```

**Current results: 103 tests, 99% coverage** ✅

```
Name                                    Stmts   Miss  Cover
---------------------------------------------------------------------
app/api/auth.py                            30      0   100%
app/api/chat.py                           116      1    99%
app/api/deps.py                            23      0   100%
app/api/files.py                          110      2    98%
app/core/config.py                         26      0   100%
app/core/security.py                       22      0   100%
app/services/llm_service.py                65      1    98%
app/services/pdf_service.py                16      0   100%
app/services/processing_service.py         40      0   100%
app/services/transcription_service.py      15      0   100%
app/services/vector_service.py            112      0   100%
---------------------------------------------------------------------
TOTAL                                     740      8    99%
```

OpenAI is mocked everywhere — no real API calls during tests.

---

## 🔐 Security notes

- Passwords hashed with **bcrypt** (passlib).
- JWT signed with HS256; `SECRET_KEY` must be set in production.
- Per-user data isolation: every file/session/message is scoped by `owner_id`.
- File size capped (configurable via `MAX_UPLOAD_SIZE_MB`, default 100MB).
- CORS origins explicitly allowlisted.
- Streaming endpoint authenticated via Bearer header (not EventSource cookie magic).

---

## 🗂️ Project structure

```
ai-qa-app/
├── backend/
│   ├── app/
│   │   ├── api/              FastAPI routers (auth, files, chat)
│   │   ├── core/             config, db, security
│   │   ├── models/           SQLAlchemy ORM
│   │   ├── schemas/          Pydantic
│   │   └── services/         pdf / transcription / vector / llm / processing
│   ├── tests/                pytest, 99% coverage
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/              fetch client + SSE parsing
│   │   ├── components/       FileUpload, FileList, ChatPanel, MediaPlayer, SummaryCard
│   │   ├── hooks/            useAuth
│   │   └── pages/            Login, Register, Dashboard
│   ├── Dockerfile            multi-stage (build → nginx)
│   └── nginx.conf            SPA fallback + /api proxy with SSE-friendly buffering
├── .github/workflows/ci.yml  tests + builds
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🛠️ Tech stack

| Layer        | Choice                                      | Why                                                      |
|--------------|---------------------------------------------|----------------------------------------------------------|
| Backend      | **FastAPI** + Uvicorn                       | Async-native, auto OpenAPI, type-safe                    |
| ORM / DB     | **SQLAlchemy 2.0** + **PostgreSQL**         | Industry-standard, scalable                              |
| Auth         | JWT (python-jose) + bcrypt                  | Stateless, easy to extend                                |
| Vector store | **ChromaDB** (persistent local mode)        | Zero-ops vs Pinecone/FAISS, fine for SMB scale           |
| LLM          | OpenAI **gpt-4o-mini** + **whisper-1**      | Cheap, fast, accurate                                    |
| Frontend     | **React 18** + **Vite** + **Tailwind CSS**  | Fast HMR, tiny bundle, clean design                      |
| Streaming    | Server-Sent Events                          | Simpler than WebSockets, fits one-way LLM token flow     |
| CI           | GitHub Actions                              | Free, native to repo                                     |
| Container    | Docker Compose                              | Reproducible local + simple deploy                       |

---

## 🚦 Trade-offs and what I'd do next

- **No Redis cache / rate-limiting** — skipped due to 48h timebox. Trivial to add: a `slowapi` dependency on the ask endpoint plus Redis for embedding response cache.
- **In-process background tasks** — using FastAPI `BackgroundTasks`. For heavy production load I'd switch to Celery or RQ.
- **Single-tenant ChromaDB** — fine for thousands of files. For real scale, swap for Pinecone / Qdrant Cloud (the abstraction in `vector_service.py` makes this a one-file change).
- **No frontend tests** — backend has 99% coverage; frontend would benefit from Vitest + Testing Library if given more time.
---

## 📜 License

MIT — feel free to use as a reference.
