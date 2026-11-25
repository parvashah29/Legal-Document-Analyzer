import { useState, useEffect } from 'react';
import UploadZone from './components/UploadZone';
import RiskDashboard from './components/RiskDashboard';
import ChatPanel from './components/ChatPanel';
import SourceViewer from './components/SourceViewer';
import LandingPage from './components/LandingPage';
import AuthPanel from './components/AuthPanel';
import { getRisks, getHealth } from './api';
import { ShieldAlert, RefreshCw, FileCheck, Sun, Moon, Keyboard, Layout, History, LogOut, ChevronDown, AlertTriangle } from 'lucide-react';

export default function App() {
  const [docId, setDocId] = useState(null);
  const [fileName, setFileName] = useState('');
  const [risks, setRisks] = useState(null);
  const [sources, setSources] = useState([]);
  const [activeChunkIndex, setActiveChunkIndex] = useState(null);
  const [isLoadingRisks, setIsLoadingRisks] = useState(false);
  const [risksError, setRisksError] = useState('');
  const [isRefining, setIsRefining] = useState(false);
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(false);
  const [view, setView] = useState('landing'); // 'landing' or 'app'
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('lda-theme') || 'dark';
  });

  // Authentication State
  const readJson = (key, fallback) => {
    try {
      const v = localStorage.getItem(key);
      return v ? JSON.parse(v) : fallback;
    } catch {
      return fallback;
    }
  };
  const [user, setUser] = useState(() => readJson('lda-session', null)); // null = not logged in, 'guest' = skipped login, object = logged in user
  const [showAuth, setShowAuth] = useState(false);
  const [showHistoryDropdown, setShowHistoryDropdown] = useState(false);
  const [userHistory, setUserHistory] = useState(() => {
    const u = readJson('lda-session', null);
    return u?.email ? readJson(`lda-history-${u.email}`, []) : [];
  });

  // Apply theme on mount and change
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('lda-theme', theme);
  }, [theme]);

  // Show which backends (vector store / LLM) the server is actually using
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      getHealth()
        .then((h) => { if (!cancelled) { setHealth(h); setHealthError(false); } })
        .catch(() => { if (!cancelled) setHealthError(true); });
    load();
    const t = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  const loadUserHistory = (email) => {
    try {
      const historyData = localStorage.getItem(`lda-history-${email}`);
      setUserHistory(historyData ? JSON.parse(historyData) : []);
    } catch {
      setUserHistory([]);
    }
  };

  const handleLogin = (userData) => {
    setUser(userData);
    localStorage.setItem('lda-session', JSON.stringify(userData));
    loadUserHistory(userData.email);
    setShowAuth(false);
    setView('app');
  };

  const handleGuestLogin = () => {
    setUser('guest');
    setShowAuth(false);
    setView('app');
  };

  const handleLogout = () => {
    setUser(null);
    localStorage.removeItem('lda-session');
    setUserHistory([]);
    setShowHistoryDropdown(false);
    handleReset();
    setView('landing');
  };

  const saveAuditToHistory = (id, name, score) => {
    if (!user || user === 'guest') return;

    const newAudit = {
      docId: id,
      fileName: name,
      score: score,
      date: new Date().toISOString(),
    };

    const updatedHistory = [newAudit, ...userHistory];
    setUserHistory(updatedHistory);
    localStorage.setItem(`lda-history-${user.email}`, JSON.stringify(updatedHistory));
  };

  // Fast rule-based analysis first, then (if an LLM is running) a second pass that rewrites the wording.
  const runAnalysis = async (id, name, { saveHistory = false } = {}) => {
    setDocId(id);
    setFileName(name);
    setIsLoadingRisks(true);
    setRisksError('');
    setRisks(null);
    setSources([]);

    try {
      const data = await getRisks(id);
      setRisks(data);
      if (saveHistory) saveAuditToHistory(id, name, data.summary?.overall_score || 0);
      if (data.flags && data.flags.length > 0) {
        setSources(data.flags.map((f) => ({ text: f.raw_text, chunk_index: f.chunk_index, score: 1.0 })));
      }
      setIsLoadingRisks(false);
      if (health?.llm?.active && health.llm.active !== 'none' && data.flags?.length) {
        setIsRefining(true);
        try {
          setRisks(await getRisks(id, true));
        } catch (err) {
          console.warn('LLM refinement skipped', err);
        } finally {
          setIsRefining(false);
        }
      }
    } catch (err) {
      console.error('Failed to load risk analysis', err);
      setRisksError(
        err.response?.data?.detail ||
          (err.response ? 'The risk analysis failed.' : 'Cannot reach the backend. Is it running?')
      );
    } finally {
      setIsLoadingRisks(false);
    }
  };

  const loadHistoricalAudit = (audit) => {
    setShowHistoryDropdown(false);
    setView('app');
    return runAnalysis(audit.docId, audit.fileName);
  };

  const handleIngested = (id, name) => runAnalysis(id, name, { saveHistory: !!user && user !== 'guest' });

  const handleReset = () => {
    setDocId(null);
    setFileName('');
    setRisks(null);
    setSources([]);
    setActiveChunkIndex(null);
    setRisksError('');
    setIsRefining(false);
  };

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'u') {
        e.preventDefault();
        if (docId) {
          handleReset();
        }
      }
      if (e.key === 'Escape') {
        document.activeElement?.blur();
        setShowHistoryDropdown(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [docId]);

  const handleSelectChunk = (idx) => {
    setActiveChunkIndex(idx);
    const panel = document.querySelector('.sources-panel');
    if (panel) {
      panel.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const handleGetStartedClick = () => {
    if (!user) {
      setShowAuth(true);
    } else {
      setView('app');
    }
  };

  return (
    <div className="app-container">
      {/* Dynamic Header */}
      <header className="glass-panel" style={{ padding: '1.25rem 2rem' }}>
        <div 
          className="logo-container" 
          style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}
          onClick={() => setView('landing')}
          title="Go to Product Overview"
        >
          <div className="logo-icon-wrapper">
            <ShieldAlert size={28} color="var(--accent)" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.6rem' }}>Legal Agreement Diagnostics</h1>
            <p>Contract red-flag scanner & grounded Q&A (not legal advice)</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {/* View switcher */}
          {view === 'landing' ? (
            <button 
              onClick={handleGetStartedClick} 
              className="header-action-btn"
              style={{ background: 'var(--primary)', color: 'white', border: 'none' }}
              title="Open Diagnostics Workspace Console"
            >
              <Layout size={12} />
              <span>Workspace Console</span>
            </button>
          ) : (
            <button 
              onClick={() => setView('landing')} 
              className="header-action-btn"
              title="Go back to Landing Page"
            >
              <Layout size={12} />
              <span>Product Overview</span>
            </button>
          )}

          {docId && view === 'app' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <div className="active-file-badge">
                <FileCheck size={14} color="var(--low-risk)" />
                <span style={{ fontWeight: '500' }}>{fileName}</span>
              </div>
              <button onClick={handleReset} className="header-action-btn" title="Analyze a new document (⌘U)">
                <RefreshCw size={12} /> Analyze New
              </button>
            </div>
          )}

          {/* User Menu / Saved Audits */}
          {user && user !== 'guest' ? (
            <div className="user-menu-container">
              <button 
                className="user-profile-btn"
                onClick={() => setShowHistoryDropdown(!showHistoryDropdown)}
              >
                <div className="user-avatar">
                  {user.email.charAt(0).toUpperCase()}
                </div>
                <span className="user-email-text">{user.email}</span>
                <ChevronDown size={14} color="var(--text-muted)" />
              </button>

              {showHistoryDropdown && (
                <div className="history-dropdown">
                  <div className="history-header">
                    <h4><History size={16} /> Saved Audits</h4>
                    <button onClick={handleLogout} className="logout-btn" title="Sign Out">
                      <LogOut size={14} />
                    </button>
                  </div>
                  
                  {userHistory.length === 0 ? (
                    <div className="history-empty">
                      No saved audits yet.<br/>Upload a contract to start analyzing.
                    </div>
                  ) : (
                    <div className="history-list">
                      {userHistory.map((audit, i) => (
                        <div key={i} className="history-item" onClick={() => loadHistoricalAudit(audit)}>
                          <div className="history-item-icon">
                            <FileCheck size={16} color="var(--accent)" />
                          </div>
                          <div className="history-item-details">
                            <p className="history-item-title" title={audit.fileName}>{audit.fileName}</p>
                            <div className="history-item-meta">
                              <span>{new Date(audit.date).toLocaleDateString()}</span>
                              <span style={{ 
                                color: audit.score >= 50 ? 'var(--high-risk)' : audit.score >= 25 ? 'var(--med-risk)' : 'var(--low-risk)',
                                fontWeight: 600 
                              }}>
                                Score: {audit.score}/100
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : !user ? (
            <button 
              className="header-action-btn" 
              onClick={() => setShowAuth(true)}
              style={{ padding: '0.4rem 1rem' }}
            >
              Sign In
            </button>
          ) : (
             <button 
              className="header-action-btn" 
              onClick={handleLogout}
              style={{ padding: '0.4rem 1rem' }}
              title="Exit Guest Mode"
            >
              Exit Guest
            </button>
          )}

          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            className="theme-toggle-btn"
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
      </header>

      <div className="status-strip" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', padding: '0.5rem 0.25rem' }}>
        <span title={health ? JSON.stringify({ vector_store: health.vector_store, llm: health.llm }, null, 1) : ''}>
          {healthError ? (
            <strong style={{ color: 'var(--high-risk)' }}>Backend unreachable</strong>
          ) : health ? (
            <>
              Vector store: <strong>{health.vector_store.backend}</strong> | Language model:{' '}
              <strong>
                {health.llm.active === 'none' ? 'none (rule-based analysis; Q&A shows excerpts only)' : `${health.llm.active}${health.llm[health.llm.active]?.model ? ` (${health.llm[health.llm.active].model})` : ''}`}
              </strong>
            </>
          ) : 'Connecting to backend...'}
        </span>
        <span style={{ display: 'inline-flex', gap: '0.35rem', alignItems: 'center' }}>
          <AlertTriangle size={12} /> Automated analysis, not legal advice. Consult a qualified attorney.
        </span>
      </div>

      {/* Main Workflow View */}
      {view === 'landing' ? (
        <LandingPage onEnterHub={handleGetStartedClick} docId={docId} fileName={fileName} />
      ) : !docId ? (
        <UploadZone onIngested={handleIngested} />
      ) : (
        <main style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          <div className="main-workspace-vertical">
            {/* Top Section: Dashboard Report */}
            <div className="glass-panel full-width-dashboard" style={{ width: '100%' }}>
              {isLoadingRisks ? (
                <div className="loading-state" style={{ minHeight: '300px' }}>
                  <div className="loading-pulse">
                    <div className="spinner" style={{ width: '40px', height: '40px' }} />
                  </div>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                    Analyzing legal text clauses...
                  </p>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.75rem', opacity: 0.6 }}>
                    Scanning clauses with the rule engine
                  </p>
                </div>
              ) : (
                <RiskDashboard risks={risks} error={risksError} isRefining={isRefining} onSelectChunk={handleSelectChunk} />
              )}
            </div>

            {/* Bottom Section: Chat and Citations Split */}
            <div className="chat-citations-workspace">
              <div className="chat-side-panel">
                <ChatPanel docId={docId} onSourcesFetched={setSources} />
              </div>
              <div className="citations-side-panel glass-panel">
                <SourceViewer sources={sources} activeChunkIndex={activeChunkIndex} />
              </div>
            </div>
          </div>
        </main>
      )}

      {showAuth && (
        <AuthPanel 
          onLogin={handleLogin} 
          onGuest={handleGuestLogin} 
          onClose={() => setShowAuth(false)} 
        />
      )}

      <footer>
        <div className="footer-content">
          <p>© 2026 Legal Document Analyzer. Not legal advice.</p>
          <div className="footer-shortcuts">
            <Keyboard size={12} />
            <span>⌘K Chat</span>
            <span>⌘U Upload</span>
            <span>Esc Clear</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
