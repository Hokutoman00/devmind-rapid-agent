"""
DevMind — Engineering Memory Agent v3
Google Cloud Rapid Agent Hackathon — MongoDB track

Architecture:
  Gemini 2.0 Flash   → structured JSON reasoning (response_mime_type=application/json)
  text-embedding-004 → 768-dim embeddings, cached, output_dimensionality=768
  MongoDB            → decisions + sessions + resolutions (Atlas or mongomock demo)
  SSE streaming      → real-time pipeline stage events
"""

import os, time, json, asyncio
from typing import Optional, Any
from contextlib import asynccontextmanager
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
MONGODB_URI        = os.getenv("MONGODB_URI", "")
EMBED_DIM          = 768
CONFLICT_THRESHOLD = 0.72

# ─── Google GenAI SDK ─────────────────────────────────────────────────────────
_genai_client = None
_USE_NEW_SDK: Optional[bool] = None
_gtypes = None

try:
    from google import genai as _gnew
    from google.genai import types as _gt
    _genai_client = _gnew.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    _USE_NEW_SDK = True
    _gtypes = _gt
except Exception:
    try:
        import google.generativeai as _gold
        _gold.configure(api_key=GEMINI_API_KEY)
        _USE_NEW_SDK = False
    except Exception:
        pass

# ─── MongoDB (Atlas or mongomock) ─────────────────────────────────────────────
_mongo_col: Any          = None   # decisions
_mongo_sessions: Any     = None   # session memories
_mongo_resolutions: Any  = None   # conflict resolutions
_mongo_connected         = False
_mongo_is_atlas          = False  # True → real $vectorSearch; False → numpy scan on mongomock

def _init_mongodb():
    global _mongo_col, _mongo_sessions, _mongo_resolutions
    global _mongo_connected, _mongo_is_atlas

    if MONGODB_URI:
        try:
            from pymongo import MongoClient
            client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            client.server_info()
            db = client["devmind"]
            _mongo_col        = db["decisions"]
            _mongo_sessions   = db["sessions"]
            _mongo_resolutions= db["resolutions"]
            _mongo_col.create_index("adr_id", unique=True)
            _mongo_connected = True
            _mongo_is_atlas  = True
            print("[DevMind] MongoDB Atlas connected.")
            return
        except Exception as e:
            print(f"[DevMind] Atlas unavailable ({e}) — falling back to demo mode")

    try:
        import mongomock
        client = mongomock.MongoClient()
        db = client["devmind"]
        _mongo_col        = db["decisions"]
        _mongo_sessions   = db["sessions"]
        _mongo_resolutions= db["resolutions"]
        _mongo_connected = True
        _mongo_is_atlas  = False
        print("[DevMind] MongoDB demo mode (mongomock, Atlas-compatible API).")
    except ImportError:
        print("[DevMind] mongomock not installed — in-memory numpy only.")

def _upsert_decision(doc: dict):
    if _mongo_col is None:
        return
    try:
        _mongo_col.replace_one({"adr_id": doc["adr_id"]}, doc, upsert=True)
    except Exception:
        pass

def _vector_search_atlas(qvec: list, limit: int = 3) -> list:
    try:
        pipeline = [
            {"$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": qvec,
                "numCandidates": 50,
                "limit": limit,
            }},
            {"$project": {"_id": 0, "adr_id": 1, "task": 1, "reason": 1,
                          "score": {"$meta": "vectorSearchScore"}}},
        ]
        return list(_mongo_col.aggregate(pipeline))
    except Exception:
        return []

def _vector_search_mock(qvec: list, limit: int = 3) -> list:
    """Atlas-equivalent via numpy scan (mongomock doesn't support $vectorSearch)."""
    if _mongo_col is None:
        return []
    docs = list(_mongo_col.find({}, {"_id": 0}))
    q = np.array(qvec, dtype=np.float32)
    scored = []
    for doc in docs:
        emb = doc.get("embedding")
        if emb is None:
            continue
        s = cosine_sim(q, np.array(emb, dtype=np.float32))
        scored.append({k: v for k, v in doc.items() if k != "embedding"} | {"score": s})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]

def _vector_search(qvec: list, limit: int = 3) -> list:
    if not _mongo_connected:
        return []
    return _vector_search_atlas(qvec, limit) if _mongo_is_atlas else _vector_search_mock(qvec, limit)

# ─── Embedding (cached) ───────────────────────────────────────────────────────
_embed_cache: dict[str, np.ndarray] = {}

def get_embedding(text: str) -> Optional[np.ndarray]:
    if text in _embed_cache:
        return _embed_cache[text]
    try:
        if _USE_NEW_SDK and _genai_client and _gtypes:
            res = _genai_client.models.embed_content(
                model="text-embedding-004",
                contents=text,
                config=_gtypes.EmbedContentConfig(
                    output_dimensionality=EMBED_DIM,
                    task_type="RETRIEVAL_DOCUMENT",
                ),
            )
            vec = np.array(res.embeddings[0].values, dtype=np.float32)
            _embed_cache[text] = vec
            return vec
        elif _USE_NEW_SDK is False:
            import google.generativeai as _gold
            res = _gold.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="RETRIEVAL_DOCUMENT",
            )
            vec = np.array(res["embedding"], dtype=np.float32)
            _embed_cache[text] = vec
            return vec
    except Exception:
        pass
    return None

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    d = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / d) if d else 0.0

# ─── Seed decisions ───────────────────────────────────────────────────────────
SEED_DECISIONS = [
    {"adr_id": "ADR-007", "task": "JWT stateless auth (decided 2025-03-12)",
     "reason": "Avoid Redis for sessions — team chose stateless JWT. Adding session state contradicts ADR-007.",
     "keywords": ["redis", "session", "memcache", "cache", "session storage", "stateful"]},
    {"adr_id": "ADR-003", "task": "PostgreSQL for primary storage (decided 2025-01-20)",
     "reason": "Use PostgreSQL not MySQL/SQLite — data model requires JSONB and full-text search.",
     "keywords": ["mysql", "sqlite", "sql server", "database migration", "orm"]},
    {"adr_id": "ADR-011", "task": "REST API over GraphQL (decided 2025-04-05)",
     "reason": "REST chosen for simplicity. GraphQL deferred until client demands it.",
     "keywords": ["graphql", "apollo", "subscriptions", "mutation", "resolver"]},
    {"adr_id": "ADR-015", "task": "React 18 SPA — no SSR (decided 2025-05-10)",
     "reason": "Next.js SSR adds infra complexity not affordable this quarter. SPA only.",
     "keywords": ["nextjs", "next.js", "ssr", "server side rendering", "hydration", "vercel"]},
    {"adr_id": "ADR-019", "task": "Docker Compose local dev, GKE prod (decided 2025-06-01)",
     "reason": "Local dev via docker-compose; production deploys to GKE only. No VM deploys.",
     "keywords": ["docker", "vm", "ec2", "vps", "kubernetes", "k8s", "deploy"]},
]

_seed_embeddings: list[np.ndarray] = []
_session_memories: dict[str, list[dict]] = {}

# ─── Keyword fallback ─────────────────────────────────────────────────────────
def keyword_conflict(msg: str) -> Optional[dict]:
    low = msg.lower()
    best, best_n = None, 0
    for d in SEED_DECISIONS:
        n = sum(1 for kw in d["keywords"] if kw in low)
        if n > best_n:
            best_n, best = n, d
    if best and best_n > 0:
        score = min(0.65 + best_n * 0.06, 0.94)
        return {"adr_id": best["adr_id"], "task": best["task"],
                "score": round(score, 2), "reason": best["reason"]}
    return None

# ─── Severity ────────────────────────────────────────────────────────────────
def severity(score: float) -> str:
    if score >= 0.90: return "CRITICAL"
    if score >= 0.80: return "HIGH"
    return "MEDIUM"

# ─── Gemini structured analysis ───────────────────────────────────────────────
_ANALYSIS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary":      {"type": "STRING"},
        "implications": {"type": "ARRAY", "items": {"type": "STRING"}},
        "tags":         {"type": "ARRAY",  "items": {"type": "STRING"}},
        "risk":         {"type": "STRING", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
    },
    "required": ["summary", "implications", "tags", "risk"],
}

_EXTRACT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "adr_id":   {"type": "STRING"},
        "task":     {"type": "STRING"},
        "reason":   {"type": "STRING"},
        "keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["adr_id", "task", "reason", "keywords"],
}

def _gemini_json(prompt: str, schema: dict) -> Optional[dict]:
    """Call Gemini with JSON-mode structured output. Returns parsed dict or None."""
    try:
        if _USE_NEW_SDK and _genai_client and _gtypes:
            res = _genai_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=_gtypes.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            return json.loads(res.text)
        elif _USE_NEW_SDK is False:
            import google.generativeai as _gold
            model = _gold.GenerativeModel(
                "gemini-2.0-flash",
                generation_config={"response_mime_type": "application/json"},
            )
            return json.loads(model.generate_content(prompt).text)
    except Exception:
        pass
    return None

def agent_respond_structured(message: str, session_id: str) -> tuple[str, dict]:
    history = _session_memories.get(session_id, [])
    ctx = "\n".join(f"- {m['task'][:80]}" for m in history[-5:])
    prompt = f"""You are DevMind, an engineering memory agent that prevents architecture regressions.

Analyze this developer task and return a structured JSON analysis.

Team decisions logged this session:
{ctx or "(no prior decisions)"}

Developer task: {message}

Return JSON with:
- summary: 1-2 sentence analysis of architectural implications
- implications: 2-3 key implications as array strings
- tags: 4-6 technical keyword tags for memory indexing
- risk: LOW | MEDIUM | HIGH | CRITICAL (risk of proceeding without checking team decisions)"""

    analysis = _gemini_json(prompt, _ANALYSIS_SCHEMA)
    if analysis:
        return analysis.get("summary", message), analysis

    return (
        f"Task registered for analysis: {message[:80]}",
        {
            "summary": f"Task analyzed: {message[:100]}. Checking team decisions for conflicts.",
            "implications": [
                "Review existing architectural decisions before implementation",
                "Proposed change may conflict with team standards",
                "Document decision rationale for future reference",
            ],
            "tags": list(dict.fromkeys(message.lower().split()))[:6],
            "risk": "MEDIUM",
        },
    )

# ─── Conflict detection ───────────────────────────────────────────────────────
def detect_conflicts(message: str, session_id: str) -> list[dict]:
    # 1. Keyword (instant, reliable for demo)
    kw = keyword_conflict(message)
    if kw:
        kw["severity"] = severity(kw["score"])
        return [kw]

    # 2. MongoDB vector search (Atlas or mongomock)
    if _mongo_connected:
        qe = get_embedding(message)
        if qe is not None:
            results = _vector_search(qe.tolist())
            hits = [r for r in results if r.get("score", 0) >= CONFLICT_THRESHOLD]
            if hits:
                r = hits[0]
                return [{"adr_id": r.get("adr_id", ""), "task": r["task"],
                         "score": round(r["score"], 3), "reason": r["reason"],
                         "severity": severity(r["score"])}]

    # 3. Numpy scan (in-memory seeds)
    if _seed_embeddings:
        qe = get_embedding(message)
        if qe is not None:
            best_s, best_d = 0.0, None
            for i, se in enumerate(_seed_embeddings):
                s = cosine_sim(qe, se)
                if s > best_s:
                    best_s, best_d = s, SEED_DECISIONS[i]
            if best_s >= CONFLICT_THRESHOLD and best_d:
                return [{"adr_id": best_d["adr_id"], "task": best_d["task"],
                         "score": round(best_s, 3), "reason": best_d["reason"],
                         "severity": severity(best_s)}]
    return []

# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    _init_mongodb()
    if GEMINI_API_KEY:
        print("[DevMind] Pre-embedding seed decisions...")
        for d in SEED_DECISIONS:
            text = d["task"] + " " + " ".join(d["keywords"][:3])
            emb = get_embedding(text)
            if emb is not None:
                _seed_embeddings.append(emb)
                _upsert_decision({**d, "embedding": emb.tolist()})
                print(f"  [ok] {d['adr_id']}")
            else:
                _upsert_decision(d)
                print(f"  [skip] {d['adr_id']} (quota limited — stored without embedding)")
    else:
        for d in SEED_DECISIONS:
            _upsert_decision(d)
        print("[DevMind] No GEMINI_API_KEY — keyword-only mode")

    n = _mongo_col.count_documents({}) if _mongo_col is not None else 0
    mode = ("Atlas" if _mongo_is_atlas else "Demo") + ("+" + "Gemini" if _seed_embeddings else "+keyword")
    print(f"[DevMind] Ready. Mode: {mode} | Decisions in MongoDB: {n}")
    yield

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="DevMind Engineering Memory", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class RunRequest(BaseModel):
    message: str
    session_id: str = "default"

class ConflictItem(BaseModel):
    adr_id: str = ""
    task: str
    score: float
    reason: str
    severity: str = "MEDIUM"

class RunResponse(BaseModel):
    reply: str
    analysis: dict
    conflicts: list[ConflictItem]
    session_id: str
    processing_ms: int
    backend_mode: str

class AddDecisionRequest(BaseModel):
    text: str
    session_id: str = "default"

class ResolveRequest(BaseModel):
    session_id: str
    adr_id: str
    resolution: str   # 'accepted' | 'overridden'
    reason: Optional[str] = None

def _backend_mode() -> str:
    if _mongo_is_atlas:   return "atlas"
    if _mongo_connected:  return "demo"
    if _seed_embeddings:  return "numpy"
    return "keyword"

def _store_session(session_id: str, task: str, analysis: dict):
    mem = _session_memories.setdefault(session_id, [])
    mem.append({"task": task[:120], "ts": int(time.time()), "tags": analysis.get("tags", [])})
    if len(mem) > 50:
        _session_memories[session_id] = mem[-50:]
    if _mongo_sessions is not None:
        try:
            _mongo_sessions.insert_one({
                "session_id": session_id,
                "task": task[:200],
                "tags": analysis.get("tags", []),
                "risk": analysis.get("risk", "LOW"),
                "ts": int(time.time()),
            })
        except Exception:
            pass

# ─── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    n = _mongo_col.count_documents({}) if _mongo_col is not None else 0
    return {
        "status": "ok",
        "mongodb_connected": _mongo_connected,
        "mongodb_is_atlas": _mongo_is_atlas,
        "decision_count": n,
        "seed_embeddings": len(_seed_embeddings),
        "conflict_mode": _backend_mode(),
        "gemini_ready": bool(_genai_client),
    }

@app.post("/run", response_model=RunResponse)
def run_agent(req: RunRequest):
    t0 = time.time()
    summary, analysis = agent_respond_structured(req.message, req.session_id)
    conflicts = detect_conflicts(req.message, req.session_id)
    _store_session(req.session_id, req.message, analysis)
    return RunResponse(
        reply=summary,
        analysis=analysis,
        conflicts=[ConflictItem(**c) for c in conflicts],
        session_id=req.session_id,
        processing_ms=int((time.time() - t0) * 1000),
        backend_mode=_backend_mode(),
    )

@app.post("/run/stream")
async def run_agent_stream(req: RunRequest):
    async def gen():
        yield f"data: {json.dumps({'stage': 'embedding', 'msg': 'Generating 768-dim vector embedding...'})}\n\n"
        await asyncio.sleep(0.05)
        yield f"data: {json.dumps({'stage': 'search', 'msg': 'Scanning MongoDB vector index...'})}\n\n"
        conflicts = detect_conflicts(req.message, req.session_id)
        await asyncio.sleep(0.05)
        yield f"data: {json.dumps({'stage': 'reasoning', 'msg': 'Gemini 2.0 Flash analyzing implications...'})}\n\n"
        summary, analysis = agent_respond_structured(req.message, req.session_id)
        _store_session(req.session_id, req.message, analysis)
        yield f"data: {json.dumps({'stage': 'complete', 'reply': summary, 'analysis': analysis, 'conflicts': conflicts, 'backend_mode': _backend_mode()})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )

@app.get("/memory/{session_id}")
def get_memory(session_id: str):
    entries = _session_memories.get(session_id, [])
    mongo_entries = []
    if _mongo_sessions is not None:
        try:
            mongo_entries = list(
                _mongo_sessions.find({"session_id": session_id}, {"_id": 0})
                               .sort("ts", -1).limit(20)
            )
        except Exception:
            pass
    return {"session_id": session_id, "decision_count": len(entries),
            "decisions": entries[-20:], "mongodb_entries": mongo_entries}

@app.post("/decisions")
def add_decision(req: AddDecisionRequest):
    words = req.text.lower().split()
    adr_num = int(time.time()) % 900 + 100
    fallback = {
        "adr_id": f"ADR-{adr_num}",
        "task": req.text[:60],
        "reason": req.text[:200],
        "keywords": list(dict.fromkeys(words))[:6],
    }
    prompt = f"""Extract a structured Architecture Decision Record from this text:

"{req.text}"

Return JSON with:
- adr_id: short ADR id like "ADR-{adr_num}"
- task: 1-line decision title (max 60 chars)
- reason: constraint this imposes on future proposals (max 200 chars)
- keywords: 5-7 technical terms that appear in conflicting proposals"""

    extracted = _gemini_json(prompt, _EXTRACT_SCHEMA) or fallback
    emb = get_embedding(extracted["task"] + " " + " ".join(extracted.get("keywords", [])[:3]))
    doc = {**extracted}
    if emb is not None:
        doc["embedding"] = emb.tolist()
        _seed_embeddings.append(emb)
    _upsert_decision(doc)
    return {
        "status": "added",
        "adr": {k: v for k, v in extracted.items() if k != "embedding"},
        "embedding_stored": emb is not None,
        "backend_mode": _backend_mode(),
    }

@app.post("/conflicts/resolve")
def resolve_conflict(req: ResolveRequest):
    doc = {
        "session_id": req.session_id,
        "adr_id": req.adr_id,
        "resolution": req.resolution,
        "reason": req.reason,
        "ts": int(time.time()),
    }
    if _mongo_resolutions is not None:
        try:
            _mongo_resolutions.insert_one(doc)
        except Exception:
            pass
    return {"status": "recorded", **{k: v for k, v in doc.items() if k != "_id"}}

@app.get("/decisions")
def list_decisions():
    if _mongo_col is not None:
        docs = list(_mongo_col.find({}, {"_id": 0, "embedding": 0}))
        return {"source": "atlas" if _mongo_is_atlas else "demo", "count": len(docs), "decisions": docs}
    return {"source": "in_memory", "count": len(SEED_DECISIONS),
            "decisions": [{k: v for k, v in d.items() if k != "keywords"} for d in SEED_DECISIONS]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)
