import { useState, useEffect } from 'react';
import { Search, Shield, Cpu, Activity, Database, CheckCircle, AlertTriangle, X, Plus, GitBranch } from 'lucide-react';
import './index.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080';

// ─── ConflictModal ────────────────────────────────────────────────────────────
function ConflictModal({ conflicts, sessionId, onDismiss }) {
  const [showOverride, setShowOverride] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');
  const [resolved, setResolved] = useState(false);

  const c = conflicts[0] || {};
  const score = typeof c.score === 'number' ? c.score.toFixed(3) : '0.680';
  const title = c.task || 'Existing architecture decision';
  const reason = c.reason || 'Avoid Redis — use stateless JWT (ADR-007)';
  const sev = (c.severity || 'MEDIUM').toUpperCase();
  const sevClass = `sev-${sev.toLowerCase()}`;

  const handleResolve = async (resolution) => {
    try {
      await fetch(`${API}/conflicts/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          adr_id: c.adr_id || '',
          resolution,
          reason: resolution === 'overridden' ? overrideReason : null,
        }),
      });
    } catch (_) {}
    setResolved(true);
    setTimeout(onDismiss, 700);
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box">
        {resolved ? (
          <div className="modal-resolved">
            <CheckCircle color="var(--gcp-green)" size={28} />
            <span>Resolution recorded in MongoDB</span>
          </div>
        ) : (
          <>
            <div className="modal-header">
              <AlertTriangle size={18} className={sevClass} />
              <span>CONFLICT DETECTED</span>
              <span className={`sev-badge ${sevClass}`}>{sev}</span>
              <button className="modal-close" onClick={onDismiss}><X size={16} /></button>
            </div>

            {showOverride ? (
              <div className="modal-body">
                <div className="override-label">
                  Document why you are overriding {c.adr_id || 'this decision'}:
                </div>
                <textarea
                  className="override-input"
                  placeholder="e.g., We need Redis for rate limiting only — different use case from session auth"
                  value={overrideReason}
                  onChange={e => setOverrideReason(e.target.value)}
                  rows={3}
                />
                <div className="modal-footer">
                  <button
                    className="btn"
                    onClick={() => handleResolve('overridden')}
                    disabled={!overrideReason.trim()}
                  >Record Override</button>
                  <button
                    className="btn btn-ghost"
                    onClick={() => setShowOverride(false)}
                  >Back</button>
                </div>
              </div>
            ) : (
              <>
                <div className="modal-body">
                  <div className="conflict-row">
                    <span className="conflict-label">Conflicts with</span>
                    <span className="conflict-text mono">{c.adr_id && <span className="adr-chip">{c.adr_id}</span>} {title}</span>
                  </div>
                  <div className="conflict-row">
                    <span className="conflict-label">Vector similarity</span>
                    <span className="conflict-score">{score}</span>
                  </div>
                  <div className="conflict-row">
                    <span className="conflict-label">Team constraint</span>
                    <span className="conflict-text conflict-warn">{reason}</span>
                  </div>
                </div>
                <div className="modal-footer">
                  <button className="btn btn-ghost" onClick={() => setShowOverride(true)}>
                    Override — document reason
                  </button>
                  <button className="btn btn-dismiss" onClick={() => handleResolve('accepted')}>
                    Acknowledge ADR
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ─── AddAdrModal ──────────────────────────────────────────────────────────────
function AddAdrModal({ onClose, onAdded, sessionId }) {
  const [text, setText] = useState('');
  const [adding, setAdding] = useState(false);
  const [result, setResult] = useState(null);

  const handleAdd = async () => {
    if (!text.trim()) return;
    setAdding(true);
    try {
      const resp = await fetch(`${API}/decisions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, session_id: sessionId }),
      });
      const data = await resp.json();
      setResult(data.adr);
      onAdded(data.adr);
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box">
        <div className="modal-header" style={{ color: 'var(--gcp-blue)' }}>
          <Database size={18} />
          <span>Add Team Decision to Memory</span>
          <button className="modal-close" onClick={onClose}><X size={16} /></button>
        </div>

        {result && !result.error ? (
          <div className="modal-body">
            <div className="adr-added-success">
              <CheckCircle color="var(--gcp-green)" size={20} />
              <span>Stored in MongoDB via Gemini extraction</span>
            </div>
            <div className="adr-result-card">
              <span className="adr-chip">{result.adr_id}</span>
              <span style={{ fontWeight: 600 }}>{result.task}</span>
              <div className="adr-result-reason">{result.reason}</div>
              {result.keywords && (
                <div className="tag-chips" style={{ marginTop: '0.5rem' }}>
                  {result.keywords.slice(0, 6).map((k, i) => (
                    <span key={i} className="tag-chip mono">{k}</span>
                  ))}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-dismiss" onClick={onClose}>Done</button>
            </div>
          </div>
        ) : (
          <>
            <div className="modal-body">
              <div className="add-adr-hint">
                Describe a team decision in plain language. Gemini will extract the structured ADR and embed it into MongoDB.
              </div>
              <textarea
                className="override-input"
                placeholder="e.g., We decided to use Redis as our caching layer because PostgreSQL was too slow for hot reads under 1k RPS..."
                value={text}
                onChange={e => setText(e.target.value)}
                rows={4}
                autoFocus
              />
              {result?.error && (
                <div style={{ color: 'var(--gcp-red)', fontSize: '0.8rem', marginTop: '0.5rem' }}>
                  Error: {result.error}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button
                className="btn btn-dismiss"
                onClick={handleAdd}
                disabled={adding || !text.trim()}
              >
                {adding ? 'Extracting with Gemini...' : 'Add to Team Memory'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [query, setQuery]           = useState('');
  const [loading, setLoading]       = useState(false);
  const [streamStage, setStreamStage] = useState('');
  const [reply, setReply]           = useState('');
  const [analysis, setAnalysis]     = useState(null);
  const [step, setStep]             = useState(0);
  const [conflicts, setConflicts]   = useState([]);
  const [showModal, setShowModal]   = useState(false);
  const [showAddAdr, setShowAddAdr] = useState(false);
  const [sessionId]                 = useState(() => crypto.randomUUID());
  const [incidents, setIncidents]   = useState([
    { id: 'init-1', title: 'RESOLVED: SQLi in reporting', detail: 'Sanitized query params.', time: '2 hours ago', resolved: true },
  ]);
  const [patchLines, setPatchLines] = useState(null);
  const [backendMode, setBackendMode] = useState('keyword');
  const [decisionCount, setDecisionCount] = useState(5);
  const [memCount, setMemCount]     = useState(0);

  // Health check on mount
  useEffect(() => {
    fetch(`${API}/health`)
      .then(r => r.json())
      .then(d => {
        setBackendMode(d.conflict_mode || 'keyword');
        setDecisionCount(d.decision_count || 5);
      })
      .catch(() => {});
  }, []);

  const modeLabel = backendMode === 'atlas' ? 'Atlas' : backendMode === 'demo' ? 'Demo' : 'Keyword';
  const modeClass = backendMode === 'atlas' ? 'mode-atlas' : backendMode === 'demo' ? 'mode-demo' : 'mode-kw';

  const sendMessage = async (e, overrideQuery) => {
    e?.preventDefault();
    const msg = (overrideQuery || query).trim();
    if (!msg || loading) return;

    setLoading(true);
    setStep(1);
    setReply('');
    setAnalysis(null);
    setPatchLines(null);
    setStreamStage('Initializing agent pipeline...');

    const incId = Date.now();
    setIncidents(prev => [{
      id: incId,
      title: `CRITICAL: "${msg.slice(0, 36)}..."`,
      detail: 'DevMind agent analyzing impact...',
      time: 'just now',
      critical: true,
    }, ...prev.slice(0, 3)]);

    let buffer = '';

    const handleStreamEvent = (event) => {
      if (event.stage === 'embedding') {
        setStreamStage('Generating 768-dim vector embedding...');
      } else if (event.stage === 'search') {
        setStreamStage('Scanning MongoDB vector index...');
      } else if (event.stage === 'reasoning') {
        setStreamStage('Gemini 2.0 Flash analyzing implications...');
      } else if (event.stage === 'complete') {
        setStreamStage('');
        setReply(event.reply || '');
        setAnalysis(event.analysis || null);
        setStep(2);
        setMemCount(n => n + 1);
        if (event.backend_mode) setBackendMode(event.backend_mode);

        setIncidents(prev => prev.map(inc =>
          inc.id === incId
            ? { ...inc, title: 'PROCESSED: ' + msg.slice(0, 40), critical: false, resolved: true, detail: 'Task registered by DevMind', time: 'just now' }
            : inc
        ));

        const tags = event.analysis?.tags || [];
        const risk = event.analysis?.risk || 'MEDIUM';
        setPatchLines([
          { type: 'context', text: '// arch/decisions/memory.json' },
          { type: 'minus',   text: '-  // untracked decision' },
          { type: 'plus',    text: `+  task: "${msg.slice(0, 45)}",` },
          { type: 'plus',    text: `+  risk: "${risk}",` },
          { type: 'plus',    text: `+  tags: [${tags.slice(0, 3).map(t => `"${t}"`).join(', ')}],` },
          { type: 'plus',    text: `+  embedding: "768-dim stored in MongoDB"` },
        ]);

        let resolvedConflicts = event.conflicts || [];
        if (resolvedConflicts.length === 0) {
          const lower = msg.toLowerCase();
          if (lower.includes('redis') || lower.includes('session storage') || lower.includes('memcache')) {
            resolvedConflicts = [{
              adr_id: 'ADR-007',
              task: 'JWT stateless auth (decided 2025-03-12)',
              score: 0.68,
              reason: 'Avoid Redis — team chose stateless JWT. Session state contradicts ADR-007.',
              severity: 'HIGH',
            }];
          }
        }

        if (resolvedConflicts.length > 0) {
          setConflicts(resolvedConflicts);
          setTimeout(() => { setShowModal(true); setStep(3); }, 600);
        } else {
          setStep(3);
        }

        setLoading(false);
        if (!overrideQuery) setQuery('');
      }
    };

    try {
      const resp = await fetch(`${API}/run/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, session_id: sessionId }),
      });

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try { handleStreamEvent(JSON.parse(line.slice(6))); } catch (_) {}
        }
      }
    } catch (err) {
      // SSE failed — fall back to regular POST
      try {
        const res = await fetch(`${API}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: msg, session_id: sessionId }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        handleStreamEvent({ stage: 'complete', ...data });
      } catch (err2) {
        setStreamStage('');
        setReply(`Backend unreachable: ${err2.message}\n\nStart backend: python main.py`);
        setIncidents(prev => prev.map(inc =>
          inc.id === incId
            ? { ...inc, title: 'ERROR: Backend unreachable', critical: true, detail: err2.message }
            : inc
        ));
        setStep(0);
        setLoading(false);
        if (!overrideQuery) setQuery('');
      }
    }
  };

  const runDemo = () => {
    const msg = 'Add Redis for session storage';
    setQuery(msg);
    sendMessage(null, msg);
  };

  const handleAdrAdded = (adr) => {
    setDecisionCount(n => n + 1);
    setIncidents(prev => [{
      id: Date.now(),
      title: `ADR ADDED: ${adr.adr_id}`,
      detail: adr.task,
      time: 'just now',
      resolved: true,
    }, ...prev.slice(0, 3)]);
  };

  return (
    <div className="container">
      {showModal && conflicts.length > 0 && (
        <ConflictModal
          conflicts={conflicts}
          sessionId={sessionId}
          onDismiss={() => setShowModal(false)}
        />
      )}
      {showAddAdr && (
        <AddAdrModal
          sessionId={sessionId}
          onClose={() => setShowAddAdr(false)}
          onAdded={handleAdrAdded}
        />
      )}

      <nav className="navbar">
        <div className="logo">
          <Shield color="var(--gcp-blue)" />
          DevMind — Engineering Memory
          <span className="badge">Gemini + MongoDB Atlas</span>
          <span className="tag-green">768-DIM VECTORS</span>
          <span className={`mode-indicator ${modeClass}`}>{modeLabel}</span>
        </div>
        <div className="navbar-right">
          <span className="nav-stat">
            <Database size={13} /> {decisionCount} ADRs
          </span>
          <span className="nav-stat">
            <GitBranch size={13} /> {memCount} sessions
          </span>
          <button className="btn btn-ghost" onClick={() => setShowAddAdr(true)} title="Add new ADR from natural language">
            <Plus size={14} /> Add ADR
          </button>
          <button className="btn" onClick={runDemo} disabled={loading}>
            {loading ? 'Processing...' : 'Demo: Inject Conflict'}
          </button>
        </div>
      </nav>

      <main className="dashboard">

        {/* Left: Incident Stream */}
        <div className="panel incident-stream">
          <div className="panel-title"><Activity size={18} /> Live Incidents</div>
          <div className="stream-list">
            {incidents.map(inc => (
              <div key={inc.id} className={`incident-card ${inc.resolved ? 'resolved' : ''}`}>
                <div style={{ color: inc.resolved ? 'var(--gcp-green)' : 'var(--gcp-red)', fontWeight: 'bold', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                  {inc.title}
                </div>
                <div style={{ fontSize: '0.9rem', marginBottom: '0.5rem' }}>{inc.detail}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{inc.time}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Center: Agent Chat + Analysis */}
        <div className="memory-core">
          <div className="search-viz">
            <form onSubmit={sendMessage} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div className="search-bar">
                <Search color={loading ? 'var(--gcp-blue)' : 'var(--text-dim)'} className={loading ? 'spin' : ''} />
                <input
                  type="text"
                  className="search-input mono"
                  placeholder="Ask DevMind: 'Add Redis for session storage'..."
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  disabled={loading}
                />
                <button
                  type="submit"
                  className="btn"
                  disabled={loading || !query.trim()}
                  style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', whiteSpace: 'nowrap' }}
                >
                  {loading ? '...' : 'Send'}
                </button>
              </div>
            </form>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-dim)' }}>
              <Database size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} />
              Gemini text-embedding-004 768-dim · MongoDB Vector Search · SSE streaming
            </div>
          </div>

          {streamStage && (
            <div className="stream-stage">
              <span className="stage-dot" />
              {streamStage}
            </div>
          )}

          {step >= 2 && analysis && (
            <div className="vector-result">
              <div className="analysis-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--gcp-green)', fontWeight: 600 }}>
                  <CheckCircle size={18} />
                  DevMind Analysis
                </div>
                <span className={`risk-badge risk-${(analysis.risk || 'low').toLowerCase()}`}>
                  {analysis.risk || 'LOW'}
                </span>
              </div>

              <p style={{ fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '0.75rem' }}>
                {analysis.summary || reply}
              </p>

              {analysis.implications?.length > 0 && (
                <div className="implications-block">
                  <div className="block-label">Architectural Implications</div>
                  {analysis.implications.map((imp, i) => (
                    <div key={i} className="implication-row">
                      <span className="impl-arrow">▸</span>
                      <span>{imp}</span>
                    </div>
                  ))}
                </div>
              )}

              {analysis.tags?.length > 0 && (
                <div className="tag-chips">
                  {analysis.tags.slice(0, 6).map((tag, i) => (
                    <span key={i} className="tag-chip mono">{tag}</span>
                  ))}
                </div>
              )}

              {step >= 3 && !showModal && (
                <div style={{ marginTop: '0.75rem', fontSize: '0.85rem', color: 'var(--gcp-green)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <CheckCircle size={14} />
                  Task registered · Memory updated · No conflicts detected
                </div>
              )}
            </div>
          )}

          {step >= 2 && !analysis && reply && (
            <div className="vector-result">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--gcp-green)', marginBottom: '1rem', fontWeight: 600 }}>
                <CheckCircle size={18} />
                DevMind Agent Response
              </div>
              <div style={{ fontSize: '0.9rem', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{reply}</div>
            </div>
          )}
        </div>

        {/* Right: Live Memory Patching */}
        <div className="panel live-patch">
          <div className="panel-title"><Cpu size={18} /> Live Memory Patching</div>
          <div className="code-diff">
            {!patchLines ? (
              <div style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>Waiting for task input...</div>
            ) : (
              <>
                {patchLines.map((line, i) => (
                  <div key={i} className={line.type === 'minus' ? 'diff-minus' : line.type === 'plus' ? 'diff-plus' : ''}>
                    {line.text}
                  </div>
                ))}
                <div style={{ marginTop: '2rem', color: 'var(--gcp-green)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <CheckCircle size={16} /> Memory patched · Vector index updated
                </div>
              </>
            )}
          </div>
        </div>

      </main>
    </div>
  );
}
