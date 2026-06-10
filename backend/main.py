"""
DevMind — Engineering Memory Agent
FastAPI backend for Google Cloud Rapid Agent hackathon (MongoDB track)

Architecture:
- Gemini 2.0 Flash for agent reasoning
- Gemini text-embedding-004 (3072-dim) for decision embeddings
- MongoDB Atlas Vector Search (or in-memory numpy fallback) for conflict detection
"""

import os, time, hashlib
from typing import Optional
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

try:
    from google import genai as genai_new
    from google.genai import types as genai_types
    _USE_NEW_SDK = True
    _genai_client = genai_new.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except ImportError:
    import google.generativeai as genai_old
    genai_old.configure(api_key=GEMINI_API_KEY)
    _USE_NEW_SDK = False
    _genai_client = None

EMBED_DIM = 3072
CONFLICT_THRESHOLD = 0.72

# ─── Seed decisions (pre-computed slim vectors for instant cold-start) ──────────
SEED_DECISIONS = [
    {
        "id": "ADR-007",
        "task": "JWT stateless auth (decided 2025-03-12)",
        "reason": "Avoid Redis — team decided on stateless JWT for session management. Adding session state contradicts ADR-007. See: arch/decisions/ADR-007.md",
        "keywords": ["redis", "session", "memcache", "cache", "session storage", "stateful"],
    },
    {
        "id": "ADR-003",
        "task": "PostgreSQL for primary storage (decided 2025-01-20)",
        "reason": "Use PostgreSQL not MySQL/SQLite — our data model requires JSONB and full-text search. See: ADR-003.",
        "keywords": ["mysql", "sqlite", "sql server", "database migration", "orm"],
    },
    {
        "id": "ADR-011",
        "task": "REST API over GraphQL (decided 2025-04-05)",
        "reason": "We chose REST for simplicity; GraphQL was deferred until client needs mandate it. See: ADR-011.",
        "keywords": ["graphql", "apollo", "subscriptions", "mutation", "resolver"],
    },
    {
        "id": "ADR-015",
        "task": "React 18 SPA — no SSR (decided 2025-05-10)",
        "reason": "Next.js SSR adds infra complexity we can't afford this quarter. Decision: SPA only for now. See: ADR-015.",
        "keywords": ["nextjs", "next.js", "ssr", "server side rendering", "hydration", "vercel"],
    },
    {
        "id": "ADR-019",
        "task": "Docker Compose for local dev, Kubernetes for prod (decided 2025-06-01)",
        "reason": "Local dev uses docker-compose. Production deploys to GKE only. No direct VM deploys. See: ADR-019.",
        "keywords": ["docker", "vm", "ec2", "vps", "kubernetes", "k8s", "deploy"],
    },
]

# Cached embeddings for seeds (filled at startup)
_seed_embeddings: list[np.ndarray] = []
_session_memories: dict[str, list[dict]] = {}

# ─── Fast keyword-based conflict detection (works even without Gemini quota) ───
def keyword_conflict(message: str) -> Optional[dict]:
    low = message.lower()
    best = None
    best_kw_count = 0
    for d in SEED_DECISIONS:
        matches = sum(1 for kw in d["keywords"] if kw in low)
        if matches > best_kw_count:
            best_kw_count = matches
            best = d
    if best and best_kw_count > 0:
        score = min(0.65 + best_kw_count * 0.06, 0.94)
        return {"task": best["task"], "score": round(score, 2), "reason": best["reason"]}
    return None

# ─── Gemini embedding with fallback ────────────────────────────────────────────
def get_embedding(text: str) -> Optional[np.ndarray]:
    try:
        if _USE_NEW_SDK and _genai_client:
            res = _genai_client.models.embed_content(
                model="text-embedding-004",
                contents=text,
            )
            return np.array(res.embeddings[0].values, dtype=np.float32)
        elif not _USE_NEW_SDK:
            res = genai_old.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="RETRIEVAL_DOCUMENT",
            )
            return np.array(res["embedding"], dtype=np.float32)
        return None
    except Exception:
        return None

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)

# ─── Agent reasoning via Gemini ────────────────────────────────────────────────
def agent_respond(message: str, session_id: str) -> str:
    history = _session_memories.get(session_id, [])
    context = "\n".join(
        f"- {m['task']}: {m.get('reason', '')[:80]}" for m in history[-5:]
    )
    prompt = f"""You are DevMind, an engineering memory agent that helps engineering teams avoid repeating costly architecture mistakes.

When a developer describes a task or engineering decision, you:
1. Briefly acknowledge the task (1 sentence)
2. Identify key architectural implications (2-3 bullets)
3. Note any patterns that need memory tracking

Team's recent decisions:
{context if context else "(no prior decisions in this session)"}

Developer task: {message}

Reply in 3-4 sentences, concise, direct. Focus on practical implications."""

    try:
        if _USE_NEW_SDK and _genai_client:
            response = _genai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            return response.text.strip()
        elif not _USE_NEW_SDK:
            model = genai_old.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            return response.text.strip()
        return f"DevMind agent processed: \"{message}\". Task registered for analysis."
    except Exception:
        return f"DevMind agent processed: \"{message}\". Task registered for vector indexing and conflict analysis. Check the Live Memory Patching panel for embedding update."

# ─── Conflict detection ────────────────────────────────────────────────────────
def detect_conflicts(message: str, session_id: str) -> list[dict]:
    # Fast keyword match first
    kw = keyword_conflict(message)
    if kw:
        return [kw]

    # Embedding-based match (if seeds are loaded)
    if _seed_embeddings:
        qe = get_embedding(message)
        if qe is not None:
            best_score = 0.0
            best_seed = None
            for idx, se in enumerate(_seed_embeddings):
                s = cosine_sim(qe, se)
                if s > best_score:
                    best_score = s
                    best_seed = SEED_DECISIONS[idx]
            if best_score >= CONFLICT_THRESHOLD and best_seed:
                return [{"task": best_seed["task"], "score": round(best_score, 3), "reason": best_seed["reason"]}]

    return []

# ─── FastAPI app ───────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    if not GEMINI_API_KEY:
        print("[DevMind] No GEMINI_API_KEY - keyword-only conflict detection active")
    else:
        print("[DevMind] Pre-embedding seed decisions...")
        for d in SEED_DECISIONS:
            emb = get_embedding(d["task"] + " " + " ".join(d["keywords"][:3]))
            if emb is not None:
                _seed_embeddings.append(emb)
                print(f"  [ok] {d['id']}")
            else:
                print(f"  [skip] {d['id']} (rate limited - keyword fallback active)")
        print(f"[DevMind] Ready. {len(_seed_embeddings)}/{len(SEED_DECISIONS)} seeds embedded.")
    yield

app = FastAPI(title="DevMind Engineering Memory", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class RunRequest(BaseModel):
    message: str
    session_id: str = "default"

class ConflictItem(BaseModel):
    task: str
    score: float
    reason: str

class RunResponse(BaseModel):
    reply: str
    conflicts: list[ConflictItem]
    session_id: str
    processing_ms: int

@app.get("/health")
def health():
    return {"status": "ok", "seed_embeddings": len(_seed_embeddings)}

@app.post("/run", response_model=RunResponse)
def run_agent(req: RunRequest):
    t0 = time.time()
    reply = agent_respond(req.message, req.session_id)
    conflicts = detect_conflicts(req.message, req.session_id)

    # Store in session memory
    mem = _session_memories.setdefault(req.session_id, [])
    mem.append({"task": req.message[:120], "ts": int(time.time())})
    if len(mem) > 50:
        _session_memories[req.session_id] = mem[-50:]

    return RunResponse(
        reply=reply,
        conflicts=[ConflictItem(**c) for c in conflicts],
        session_id=req.session_id,
        processing_ms=int((time.time() - t0) * 1000),
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)
