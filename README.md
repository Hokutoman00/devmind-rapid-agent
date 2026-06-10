# DevMind — Engineering Memory Agent

> **Google Cloud Rapid Agent Hackathon — MongoDB Track**
> An AI agent that prevents costly architecture regressions by detecting when a new task conflicts with the team's prior decisions — powered by **Gemini Embedding (3072-dim) + MongoDB Atlas Vector Search**.

---

## The Problem

Engineering teams make architectural decisions (ADRs), but those decisions live in docs nobody reads. Months later, a developer proposes adding Redis for session storage — unaware the team decided on stateless JWT six months ago. The result: wasted sprint capacity, merge conflicts, and regressions.

**DevMind answers: "Before you build this — has the team already decided something that conflicts?"**

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Developer Input  →  Gemini Agent  →  Conflict Detection │
│  (task description)    (reasoning)    MongoDB Vector Search│
│                                       3072-dim embeddings │
│                    ↓                                      │
│           Live Memory Patching Panel                      │
│           (diff view of architecture decisions)           │
└──────────────────────────────────────────────────────────┘
```

### Agent Pipeline

1. **Input**: Developer describes a new task or technical decision
2. **Gemini Agent** (`gemini-2.0-flash`): Analyzes architectural implications
3. **Embedding** (`text-embedding-004`, 3072-dim): Embeds task into vector space
4. **MongoDB Atlas Vector Search**: Cosine similarity against stored team decisions
5. **Conflict Detection**: If similarity ≥ 0.72 → surface the conflicting ADR
6. **Live Memory Patching**: Visual diff showing how this decision updates team memory

---

## Google Cloud Integration

| Component | Technology |
|-----------|-----------|
| Agent LLM | **Gemini 2.0 Flash** (generative reasoning) |
| Embeddings | **Gemini text-embedding-004** (3072-dim output) |
| Vector DB | **MongoDB Atlas Vector Search** (cosine similarity) |
| Agent Infra | **Google Cloud Agent Builder** (orchestration layer) |

---

## Demo

**Golden path** — type "Add Redis for session storage":
- DevMind agent analyzes the architectural implications
- Vector search detects similarity with ADR-007 (JWT stateless auth decision)
- Conflict modal surfaces: "Avoid Redis — team decided on stateless JWT 3 months ago"
- Live Memory Patching panel shows the diff updating team knowledge

---

## Setup

### Backend (FastAPI — port 8080)

```bash
cd backend
pip install -r requirements.txt
# Add GEMINI_API_KEY to .env (see .env.example)
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
| LLM | Gemini 2.0 Flash (`google.genai`) |
| Embeddings | Gemini text-embedding-004 (3072-dim) |
| Vector Store | MongoDB Atlas Vector Search (local: numpy cosine fallback) |
| Frontend | React 18 + Vite 6 |
| CORS | Fully open for local demo |

---

## What Makes This Novel

1. **Decision memory, not just search**: DevMind tracks *why* decisions were made, not just what was decided — the reasoning propagates into conflict warnings
2. **3072-dim precision**: Full Gemini embedding dimensionality maximizes semantic discrimination between similar-sounding but distinct architectural concerns
3. **Live patching visualization**: Every task submission shows a real-time diff of how team memory evolves — the agent is observable, not a black box
4. **Graceful degradation**: Keyword fallback ensures reliable demo behavior even under API rate limits

---

## Repository Structure

```
backend/
├── main.py              # FastAPI agent server (POST /run, GET /health)
├── requirements.txt
└── .env.example

frontend/
├── src/
│   └── App.jsx          # React UI — agent chat + conflict modal + live patch panel
├── package.json
└── vite.config.js
```
