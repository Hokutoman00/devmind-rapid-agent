# DevMind — Engineering Memory Agent

> **Google Cloud Rapid Agent Hackathon — MongoDB Track**
> An AI agent that prevents costly architecture regressions by detecting when a new task conflicts with prior team decisions — powered by **Gemini 2.0 Flash + text-embedding-004 + MongoDB Atlas Vector Search**.

---

## The Problem

Engineering teams make architectural decisions (ADRs), but those decisions live in docs nobody reads. Months later, a developer proposes adding Redis for session storage — unaware the team decided on stateless JWT six months ago. The result: wasted sprint capacity, merge conflicts, and regressions.

**DevMind answers: "Before you build this — has the team already decided something that conflicts?"**

---

## Architecture

```
Developer Input
      │
      ▼
 SSE streaming        ← real-time pipeline stage events
      │
 text-embedding-004   ← 768-dim vector (output_dimensionality=768, cached)
      │
 MongoDB Atlas        ← $vectorSearch (cosine, index: vector_index, threshold: 0.72)
 (mongomock demo)     ← Atlas-compatible API when no URI provided
      │
 Gemini 2.0 Flash     ← structured JSON analysis (response_mime_type=application/json)
  response_schema:    ← summary + implications[] + tags[] + risk: LOW|MEDIUM|HIGH|CRITICAL
      │
 Conflict Modal       ← severity badge + override-with-reason + MongoDB resolution store
 + Live Memory Patch  ← diff view of evolving team knowledge
```

### Agent Pipeline (SSE streamed)

1. **`embedding`** — Gemini text-embedding-004 embeds the task (768-dim, cached)
2. **`search`** — MongoDB Atlas `$vectorSearch` scans the ADR collection (cosine ≥ 0.72)
3. **`reasoning`** — Gemini 2.0 Flash returns structured JSON: summary, implications, tags, risk
4. **`complete`** — Conflict modal with CRITICAL/HIGH/MEDIUM severity, or clear result

---

## Google Cloud + MongoDB Integration

| Component | Technology |
|-----------|-----------|
| Agent LLM | **Gemini 2.0 Flash** (`gemini-2.0-flash`) |
| Embeddings | **Gemini text-embedding-004** (768-dim, `output_dimensionality=768`) |
| Structured output | `response_mime_type="application/json"` + `response_schema` |
| Vector DB | **MongoDB Atlas Vector Search** (cosine, index: `vector_index`) |
| Demo mode | **mongomock** (Atlas-compatible pymongo API, numpy vector scan) |
| Decision store | MongoDB `decisions` + `sessions` + `resolutions` collections |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/run` | Agent analysis + conflict detection (JSON) |
| `POST` | `/run/stream` | Same — SSE streaming with staged progress events |
| `POST` | `/decisions` | Add new ADR from natural language (Gemini extracts structure) |
| `POST` | `/conflicts/resolve` | Record accept/override resolution in MongoDB |
| `GET`  | `/health` | Backend mode, decision count, Gemini status |
| `GET`  | `/memory/{session_id}` | Session decisions + MongoDB session entries |
| `GET`  | `/decisions` | List all stored ADRs |

---

## Demo Scenarios

**Scenario 1 — Conflict detection**
Type: `"Add Redis for session storage"` → SSE streams 3 stages → HIGH severity conflict modal → ADR-007 surfaces → user acknowledges or overrides with reason (stored in MongoDB)

**Scenario 2 — Team learning**
Click "Add ADR" → type: `"We decided to use Redis as our caching layer for hot reads"` → Gemini extracts structured ADR → stored in MongoDB with 768-dim embedding → future "Add Redis for caching" queries will resolve cleanly (different use case)

**Scenario 3 — Conflict resolution audit**
Override scenario 1 with reason → `POST /conflicts/resolve` stores `{adr_id, resolution: "overridden", reason: "...", ts}` in `devmind.resolutions` — full audit trail

---

## Setup

### MongoDB Atlas (optional — mongomock is used automatically without a URI)

1. Create free M0 cluster at [cloud.mongodb.com](https://cloud.mongodb.com)
2. Database: `devmind` / Collection: `decisions`
3. Create Vector Search Index named `vector_index`:
   ```json
   {
     "fields": [{
       "type": "vector",
       "path": "embedding",
       "numDimensions": 768,
       "similarity": "cosine"
     }]
   }
   ```
4. Add to `.env`: see `.credentials/` for connection string

### Backend (FastAPI — port 8080)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env: add GEMINI_API_KEY (optional: MONGODB_URI for Atlas)
python main.py
```

Startup log shows active mode: `Atlas+Gemini`, `Demo+Gemini`, `Demo+keyword`, or `numpy+keyword`

### Frontend (React + Vite — port 5173)

```bash
cd frontend
npm install
npm run dev
```

---

## Technical Stack

| Layer | Technology |
|-------|-----------|
| Agent | Python 3.12 + FastAPI (port 8080) |
| LLM | Gemini 2.0 Flash (`google-genai` SDK) |
| Structured output | `response_mime_type=application/json`, `response_schema` |
| Embeddings | Gemini text-embedding-004 (768-dim, cached) |
| Vector Store | MongoDB Atlas `$vectorSearch` / mongomock numpy scan |
| Streaming | SSE (`POST /run/stream`) — 3 stage events before result |
| Frontend | React 18 + Vite 6 |

---

## What Makes This Novel

1. **Decision memory, not just search**: DevMind tracks *why* decisions were made — the constraint propagates into conflict warnings with full Gemini-generated implications
2. **Always-on MongoDB**: mongomock provides Atlas-compatible storage without requiring Atlas credentials — `decisions`, `sessions`, and `resolutions` are always written to MongoDB collections
3. **ADR from natural language**: `POST /decisions` uses Gemini structured extraction to turn free-form text into searchable ADRs, embedding them in real time
4. **Conflict resolution audit trail**: Override decisions are stored in `devmind.resolutions` with the developer's rationale — full governance chain
5. **SSE streaming**: The 3-stage pipeline (embed → search → reason) is streamed live, making the AI reasoning process visible
6. **Severity levels**: CRITICAL / HIGH / MEDIUM — cosine similarity score maps to operational impact

---

## Repository Structure

```
backend/
├── main.py              # FastAPI agent — /run, /run/stream, /decisions, /conflicts/resolve
├── requirements.txt     # google-genai + pymongo[srv] + mongomock + fastapi
└── .env.example         # GEMINI_API_KEY + MONGODB_URI (both optional for demo)

frontend/
├── src/
│   ├── App.jsx          # React UI — SSE streaming, analysis panel, severity, Add ADR
│   └── index.css        # GCP dark theme + severity badges + risk display
├── package.json
└── vite.config.js
```
