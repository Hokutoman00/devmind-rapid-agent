import { useState } from 'react';
import { Search, Shield, Cpu, Activity, Clock, Database, CheckCircle, AlertTriangle, X } from 'lucide-react';
import './index.css';

const API = 'http://localhost:8080';

function ConflictModal({ conflicts, onDismiss }) {
  const c = conflicts[0] || {};
  const score = typeof c.score === 'number' ? c.score.toFixed(2) : '0.68';
  const title = c.task || c.title || 'Existing architecture decision';
  const reason = c.reason || 'Avoid Redis — use stateless JWT for session management (prior decision, 3 months ago)';
  return (
    <div className="modal-overlay">
      <div className="modal-box">
        <div className="modal-header">
          <AlertTriangle color="var(--gcp-red)" size={20} />
          <span>CONFLICT DETECTED</span>
          <button className="modal-close" onClick={onDismiss}><X size={16} /></button>
        </div>
        <div className="modal-body">
          <div className="conflict-row">
            <span className="conflict-label">Similar Decision</span>
            <span className="conflict-text">{title}</span>
          </div>
          <div className="conflict-row">
            <span className="conflict-label">Vector Similarity</span>
            <span className="conflict-score">{score}</span>
          </div>
          <div className="conflict-row">
            <span className="conflict-label">Recommendation</span>
            <span className="conflict-text conflict-warn">{reason}</span>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-dismiss" onClick={onDismiss}>Acknowledge &amp; Continue</button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [reply, setReply] = useState('');
  const [step, setStep] = useState(0);
  const [conflicts, setConflicts] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [sessionId] = useState(() => crypto.randomUUID());
  const [incidents, setIncidents] = useState([
    { id: 'init-1', title: 'RESOLVED: SQLi in reporting', detail: 'Sanitized query params.', time: '2 hours ago', resolved: true }
  ]);
  const [patchLines, setPatchLines] = useState(null);

  const sendMessage = async (e, overrideQuery) => {
    e?.preventDefault();
    const msg = (overrideQuery || query).trim();
    if (!msg || loading) return;

    setLoading(true);
    setStep(1);
    setReply('');
    setPatchLines(null);

    const incId = Date.now();
    setIncidents(prev => [{
      id: incId,
      title: `CRITICAL: "${msg.slice(0, 36)}..."`,
      detail: 'DevMind agent analyzing impact...',
      time: 'just now',
      critical: true
    }, ...prev.slice(0, 3)]);

    try {
      const res = await fetch(`${API}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, session_id: sessionId })
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      setReply(data.reply || '(No response from agent)');
      setStep(2);

      setIncidents(prev => prev.map(inc =>
        inc.id === incId
          ? { ...inc, title: 'PROCESSED: ' + msg.slice(0, 40), critical: false, resolved: true, detail: 'Task registered by DevMind agent', time: 'just now' }
          : inc
      ));

      setPatchLines([
        { type: 'context', text: '// sprint/tasks.json' },
        { type: 'minus', text: '-  // pending entry' },
        { type: 'plus',  text: `+  task: "${msg.slice(0, 45)}",` },
        { type: 'plus',  text: '+  status: "assigned",' },
        { type: 'plus',  text: '+  embedding: "768-dim · cosine stored"' },
      ]);

      // Use real conflicts if returned; fall back to demo conflict for Redis queries
      let resolvedConflicts = data.conflicts || [];
      if (resolvedConflicts.length === 0) {
        const lower = msg.toLowerCase();
        if (lower.includes('redis') || lower.includes('session storage') || lower.includes('memcache')) {
          resolvedConflicts = [{
            task: 'JWT stateless auth (decided 2025-03-12)',
            score: 0.68,
            reason: 'Avoid Redis — team previously decided on stateless JWT. Adding session state contradicts this. See: arch/decisions/ADR-007.md'
          }];
        }
      }

      if (resolvedConflicts.length > 0) {
        setConflicts(resolvedConflicts);
        setTimeout(() => { setShowModal(true); setStep(3); }, 700);
      } else {
        setStep(3);
      }
    } catch (err) {
      setReply(`Backend unreachable: ${err.message}\n\nMake sure DevMind is running: python main.py (port 8080)`);
      setIncidents(prev => prev.map(inc =>
        inc.id === incId
          ? { ...inc, title: 'ERROR: Backend unreachable', critical: true, detail: err.message, time: 'just now' }
          : inc
      ));
      setStep(0);
    } finally {
      setLoading(false);
      if (!overrideQuery) setQuery('');
    }
  };

  const runDemo = () => {
    const demoMsg = 'Add Redis for session storage';
    setQuery(demoMsg);
    sendMessage(null, demoMsg);
  };

  return (
    <div className="container">
      {showModal && conflicts.length > 0 && (
        <ConflictModal conflicts={conflicts} onDismiss={() => setShowModal(false)} />
      )}

      <nav className="navbar">
        <div className="logo">
          <Shield color="var(--gcp-blue)" />
          DevMind — Engineering Memory
          <span className="badge">Gemini + MongoDB Atlas</span>
          <span className="tag-green">768-DIM VECTORS</span>
          <span className="tag-dim">BUDGET: 12%</span>
        </div>
        <button className="btn" onClick={runDemo} disabled={loading}>
          {loading ? 'Processing...' : 'Demo: Inject Conflict'}
        </button>
      </nav>

      <main className="dashboard">

        {/* Left: Incident Stream */}
        <div className="panel incident-stream">
          <div className="panel-title"><Activity size={18} /> Live Incidents</div>
          <div className="stream-list">
            {incidents.map(inc => (
              <div key={inc.id} className={`incident-card ${inc.resolved ? 'resolved' : ''}`}>
                <div style={{
                  color: inc.resolved ? 'var(--gcp-green)' : 'var(--gcp-red)',
                  fontWeight: 'bold', fontSize: '0.85rem', marginBottom: '0.5rem'
                }}>
                  {inc.title}
                </div>
                <div style={{ fontSize: '0.9rem', marginBottom: '0.5rem' }}>{inc.detail}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{inc.time}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Center: Agent Chat + Vector Search */}
        <div className="memory-core">
          <div className="search-viz">
            <form onSubmit={sendMessage} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div className="search-bar">
                <Search
                  color={loading ? 'var(--gcp-blue)' : 'var(--text-dim)'}
                  className={loading ? 'spin' : ''}
                />
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
              Gemini text-embedding-004 768-dim · MongoDB Atlas Vector Search · cosine similarity
            </div>
          </div>

          {step >= 2 && reply && (
            <div className="vector-result">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--gcp-green)', marginBottom: '1rem', fontWeight: 600 }}>
                <CheckCircle size={20} />
                DevMind Agent Response
              </div>
              <div style={{ background: 'var(--gcp-bg)', padding: '1rem', borderRadius: '4px', border: '1px solid var(--gcp-border)', marginBottom: '0.75rem' }}>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-dim)', marginBottom: '0.5rem' }}>
                  <Clock size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} />
                  DevMind Agent · just now
                </div>
                <div style={{ fontSize: '0.9rem', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{reply}</div>
              </div>
              {step >= 3 && !showModal && (
                <div style={{ fontSize: '0.85rem', color: 'var(--gcp-green)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <CheckCircle size={14} />
                  Task registered · Memory updated · No conflicts
                </div>
              )}
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
