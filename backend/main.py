"""
DevMind — Engineering Memory Agent
FastAPI backend for Google Cloud Rapid Agent hackathon (MongoDB track)

Architecture:
- Gemini 2.0 Flash   → agent reasoning (LLM)
- text-embedding-004 → 768-dim decision embeddings
- MongoDB Atlas Vector Search (cosine, index: vector_index) → conflict detection
"""

import os, time, hashlib
from typing import Optional
from contextlib import asynccontextmanager
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
MONGODB_URI     = os.getenv("MONGODB_URI", "")   # mongodb+srv://...
EMBED_DIM       = 768                             # text-embedding-004 default
CONFLICT_THRESHOLD = 0.72

# ─── Google GenAI SDK ─────────────────────────────────────────────────────────
_genai_client = None
try:
    from google import genai as _genai_new
    _genai_client = _genai_new.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    _USE_NEW_SDK = True
except Exception:
    try:
        import google.generativeai as _genai_old
        _genai_old.configure(api_key=GEMINI_API_KEY)
        _USE_NEW_SDK = False
    except Exception:
        _USE_NEW_SDK = None

# ─── MongoDB Atlas client ─────────────────────────────────────────────────────
_mongo_col = None
_mongo_connected = False

def _init_mongodb():
    global _mongo_col, _mongo_connected
    if not MONGODB_URI:
        return
    try:
        from pymongo import MongoClient
        from pymongo.operations import SearchIndexModel
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # raises if unreachable
        db = client["devmind"]
        _mongo_col = db["decisions"]
        _mongo_col.create_index("adr_id", unique=True)
        _mongo_connected = True
        print("[DevMind] MongoDB Atlas connected.")
    except Exception as e:
        print(f"[DevMind] MongoDB Atlas unavailable: {e}  → numpy fallback active")

def _upsert_decision(doc: dict):
    if _mongo_col is None:
        return
    try:
        _mongo_col.replace_one({"adr_id": doc["adr_id"]}, doc, upsert=True)
    except Exception:
        pass

def _vector_search_atlas(query_vector: list[float], limit: int = 3) -> list[dict]:
    if _mongo_col is None:
        return []
    try:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": 50,
                    "limit": limit,
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "adr_id": 1,
                    "task": 1,
                    "reason": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        return list(_mongo_col.aggregate(pipeline))
    except Exception:
        return []

# ─── Seed decisions ───────────────────────────────────────────────────────────
SEED_DECISIONS = [
    {
        "adr_id": "ADR-007",
        "task": "JWT stateless auth (decided 2025-03-12)",
        "reason": "Avoid Redis — team decided on stateless JWT for session management. Adding session state contradicts ADR-007. See: arch/decisions/ADR-007.md",
        "keywords": ["redis", "session", "memcache", "cache", "session storage", "stateful"],
    },
    {
        "adr_id": "ADR-003",
        "task": "PostgreSQL for primary storage (decided 2025-01-20)",
        "reason": "Use PostgreSQL not MySQL/SQLite — our data model requires JSONB and full-text search. See: ADR-003.",
        "keywords": ["mysql", "sqlite", "sql server", "database migration", "orm"],
    },
    {
        "adr_id": "ADR-011",
        "task": "REST API over GraphQL (decided 2025-04-05)",
        "reason": "We chose REST for simplicity; GraphQL was deferred until client needs mandate it. See: ADR-011.",
        "keywords": ["graphql", "apollo", "subscriptions", "mutation", "resolver"],
    },
    {
        "adr_id": "ADR-015",
        "task": "React 18 SPA — no SSR (decided 2025-05-10)",
        "reason": "Next.js SSR adds infra complexity we can't afford this quarter. Decision: SPA only for now. See: ADR-015.",
        "keywords": ["nextjs", "next.js", "ssr", "server side rendering", "hydration", "vercel"],
    },
    {
        "adr_id": "ADR-019",
        "task": "Docker Compose for local dev, GKE for prod (decided 2025-06-01)",
        "reason": "Local dev uses docker-compose. Production deploys to GKE only. No direct VM deploys. See: ADR-019.",
        "keywords": ["docker", "vm", "ec2", "vps", "kubernetes", "k8s", "deploy"],
    },
]

_seed_embeddings: list[np.ndarray] = []
_session_memories: dict[str, list[dict]] = {}

# ─── Embedding ────────────────────────────────────────────────────────────────
def get_embedding(text: str) -> Optional[np.ndarray]:
    try:
        if _USE_NEW_SDK and _genai_client:
            res = _genai_client.models.embed_content(
                model="text-embedding-004",
                contents=text,
            )
            return np.array(res.embeddings[0].values, dtype=np.float32)
        elif _USE_NEW_SDK is False:
            import google.generativeai as _genai_old
            res = _genai_old.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="RETRIEVAL_DOCUMENT",
            )
            return np.array(res["embedding"], dtype=np.float32)
    except Exception:
        pass
    return None

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0

# ─── Keyword fallback ─────────────────────────────────────────────────────────
def keyword_conflict(message: str) -> Optional[dict]:
    low = message.lower()
    best, best_count = None, 0
    for d in SEED_DECISIONS:
        n = sum(1 for kw in d["keywords"] if kw in low)
        if n > best_count:
            best_count, best = n, d
    if best and best_count > 0:
        score = min(0.65 + best_count * 0.06, 0.94)
        return {"task": best["task"], "score": round(score, 2), "reason": best["reason"]}
    return None

# ─── Agent reasoning ─────────────────────────────────────────────────────────
def agent_respond(message: str, session_id: str) -> str:
    history = _session_memories.get(session_id, [])
    context = "\n".join(
        f"- {m['task'][:80]}" for m in history[-5:]
    )
    prompt = f"""You are DevMind, an engineering memory agent that helps teams avoid repeating costly architecture mistakes.

When a developer describes a task:
1. Briefly acknowledge (1 sentence)
2. Identify key architectural implications (2-3 bullets)
3. Note any patterns for memory tracking

Team's recent decisions this session:
{context if context else "(no prior decisions)"}

Developer task: {message}

Reply concisely in 3-4 sentences."""

    try:
        if _USE_NEW_SDK and _genai_client:
            response = _genai_client.models.generate_content(
                model="gemini-2.0-flash", contents=prompt
            )
            return response.text.strip()
        elif _USE_NEW_SDK is False:
            import google.generativeai as _genai_old
            model = _genai_old.GenerativeModel("gemini-2.0-flash")
            return model.generate_content(prompt).text.strip()
    except Exception:
        pass
    return (
        f"DevMind analyzed: \"{message[:80]}\". "
        "Task registered for vector indexing. "
        "Checking team decisions for architectural conflicts..."
    )

# ─── Conflict detection ───────────────────────────────────────────────────────
def detect_conflicts(message: str, session_id: str) -> list[dict]:
    # 1. Fast keyword match
    kw = keyword_conflict(message)
    if kw:
        return [kw]

    # 2. MongoDB Atlas vector search
    if _mongo_connected:
        qe = get_embedding(message)
        if qe is not None:
            results = _vector_search_atlas(qe.tolist())
            hits = [r for r in results if r.get("score", 0) >= CONFLICT_THRESHOLD]
            if hits:
                r = hits[0]
                return [{"task": r["task"], "score": round(r["score"], 3), "reason": r["reason"]}]

    # 3. Numpy cosine fallback
    if _seed_embeddings:
        qe = get_embedding(message)
        if qe is not None:
            best_score, best_seed = 0.0, None
            for idx, se in enumerate(_seed_embeddings):
                s = cosine_sim(qe, se)
                if s > best_score:
                    best_score, best_seed = s, SEED_DECISIONS[idx]
            if best_score >= CONFLICT_THRESHOLD and best_seed:
                return [{"task": best_seed["task"], "score": round(best_score, 3), "reason": best_seed["reason"]}]

    return []

# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    _init_mongodb()
    if GEMINI_API_KEY:
        print("[DevMind] Pre-embedding seed decisions...")
        for d in SEED_DECISIONS:
            emb = get_embedding(d["task"] + " " + " ".join(d["keywords"][:3]))
            if emb is not None:
                _seed_embeddings.append(emb)
                if _mongo_connected:
                    doc = {**d, "embedding": emb.tolist()}
                    _upsert_decision(doc)
                print(f"  [ok] {d['adr_id']}")
            else:
                print(f"  [skip] {d['adr_id']} (embedding unavailable - keyword fallback)")
    else:
        print("[DevMind] No GEMINI_API_KEY - keyword-only conflict detection active")
    mode = "Atlas+Gemini" if _mongo_connected else ("numpy+Gemini" if _seed_embeddings else "keyword-only")
    print(f"[DevMind] Ready. Mode: {mode} | Seeds: {len(_seed_embeddings)}/{len(SEED_DECISIONS)}")
    yield

# ─── FastAPI ──────────────────────────────────────────────────────────────────
app = FastAPI(title="DevMind Engineering Memory", version="2.0.0", lifespan=lifespan)
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
    return {
        "status": "ok",
        "mongodb_connected": _mongo_connected,
        "seed_embeddings": len(_seed_embeddings),
        "conflict_mode": "atlas" if _mongo_connected else ("numpy" if _seed_embeddings else "keyword"),
    }

@app.post("/run", response_model=RunResponse)
def run_agent(req: RunRequest):
    t0 = time.time()
    reply = agent_respond(req.message, req.session_id)
    conflicts = detect_conflicts(req.message, req.session_id)
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

@app.get("/memory/{session_id}")
def get_memory(session_id: str):
    entries = _session_memories.get(session_id, [])
    return {
        "session_id": session_id,
        "decision_count": len(entries),
        "decisions": entries[-20:],
    }

@app.get("/decisions")
def list_decisions():
    if _mongo_connected and _mongo_col is not None:
        docs = list(_mongo_col.find({}, {"_id": 0, "embedding": 0}))
        return {"source": "mongodb_atlas", "count": len(docs), "decisions": docs}
    return {
        "source": "in_memory",
        "count": len(SEED_DECISIONS),
        "decisions": [{k: v for k, v in d.items() if k != "keywords"} for d in SEED_DECISIONS],
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)
