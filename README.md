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
 Gemini 2.0 Flash          ← reasoning agent
      │
      ▼
 text-embedding-004         ← 768-dim vector embedding
 (google-genai SDK)
      │
      ▼
 MongoDB Atlas              ← $vectorSearch (cosine similarity)
 Vector Search              ← index: vector_index | threshold: 0.72
      │
      ▼
 Conflict Modal             ← surfaces conflicting ADR to developer
 + Live Memory Patch        ← diff view of evolving team knowledge
```

### Agent Pipeline

1. **Input**: Developer describes a new task or technical decision
2. **Gemini Agent** (`gemini-2.0-flash`): Analyzes architectural implications
3. **Embedding** (`text-embedding-004`, 768-dim): Embeds task into vector space
4. **MongoDB Atlas Vector Search**: Cosine similarity against stored team ADRs
5. **Conflict Detection**: similarity ≥ 0.72 → surface the conflicting ADR
6. **Session Memory**: `GET /memory/{session_id}` — exposes agent's accumulated knowledge

---

## Google Cloud + MongoDB Integration

| Component | Technology |
|-----------|-----------|
| Agent LLM | **Gemini 2.0 Flash** (`gemini-2.0-flash`) |
| Embeddings | **Gemini text-embedding-004** (768-dim) |
| Vector DB | **MongoDB Atlas Vector Search** (cosine, index: `vector_index`) |
| SDK | `google-genai` (new SDK) with `google-generativeai` fallback |

---

## Demo

**Golden path** — type "Add Redis for session storage":

1. DevMind analyzes the architectural implications via Gemini 2.0 Flash
2. Vector search detects high similarity with ADR-007 (JWT stateless auth decision)
3. Conflict modal surfaces: "Avoid Redis — team decided on stateless JWT 3 months ago"
4. Live Memory Patching panel shows the diff updating team knowledge

The backend also exposes three endpoints:
- `POST /run` — agent + conflict detection
- `GET /health` — shows MongoDB connection status + conflict mode
- `GET /memory/{session_id}` — exposes all decisions the agent has learned per session
- `GET /decisions` — lists all stored ADRs (Atlas or in-memory)

---

## Setup

### MongoDB Atlas (Required for full MongoDB Track demo)

1. Create a free M0 cluster at [cloud.mongodb.com](https://cloud.mongodb.com)
2. Database: `devmind` / Collection: `decisions`
3. Create a **Vector Search Index** named `vector_index`:
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
4. Add the connection string to `.env`:
   ```
   MONGODB_URI=mongodb+srv://USER:PASS@cluster.mongodb.net/
   ```

### Backend (FastAPI — port 8080)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env: add GEMINI_API_KEY and MONGODB_URI
python main.py
```

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
| Embeddings | Gemini text-embedding-004 (768-dim) |
| Vector Store | **MongoDB Atlas Vector Search** (cosine, dim=768) |
| Fallback | numpy cosine similarity (if Atlas unavailable) |
| Frontend | React 18 + Vite 6 |

---

## What Makes This Novel

1. **Decision memory, not just search**: DevMind tracks *why* decisions were made, not just what was decided — the reasoning propagates into conflict warnings
2. **Session memory API**: `GET /memory/{session_id}` exposes what the agent has learned — the agent is observable, not a black box
3. **Live patching visualization**: Every task submission shows a real-time diff of how team memory evolves
4. **Graceful degradation**: keyword fallback → numpy cosine → Atlas vector search (three-tier)

---

## Repository Structure

```
backend/
├── main.py              # FastAPI agent (POST /run, GET /memory, GET /decisions)
├── requirements.txt     # google-genai + pymongo[srv] + fastapi
└── .env.example         # GEMINI_API_KEY + MONGODB_URI

frontend/
├── src/
│   └── App.jsx          # React UI — agent chat + conflict modal + live patch
├── package.json
└── vite.config.js
```
