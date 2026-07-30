import { useState, useCallback, useEffect } from 'react';
import { Music, AudioWaveform, FileText, Search, X, Mic } from 'lucide-react';
import { useAuth as useClerkAuth } from '@clerk/clerk-react';

import { useSearch } from './hooks/useSearch';
import { useAuth } from './hooks/useAuth';
import { useBilling } from './hooks/useBilling';
import { themes } from './themes';
import { audioSearch } from './api/client';
import AgentThinking from './components/AgentThinking';
import AudioUpload from './components/AudioUpload';
import ResultCard from './components/ResultCard';
import ThemeToggle from './components/ThemeToggle';
import AuthModal from './components/AuthModal';
import UpgradeModal from './components/UpgradeModal';
import UsageCounter from './components/UsageCounter';
import type { SearchType, SongResult, ThemeName } from './types';

// In `npm run dev`, Vite sets import.meta.env.DEV = true. Dev mode bypasses all
// paid-tier gating (matches the backend DEV_MODE flag), so we also hide the
// quota counter and catalog-upgrade prompts that would otherwise be misleading.
const DEV_UNLIMITED = import.meta.env.DEV;

type InputMode = 'text' | 'audio';

export default function App() {
  const [themeName, setThemeName] = useState<ThemeName>('spotify');
  const [inputMode, setInputMode] = useState<InputMode>('text');
  const [inputValue, setInputValue] = useState('');
  const [searchType, setSearchType] = useState<SearchType>('both');
  const [hasSearched, setHasSearched] = useState(false);
  const [lastQuery, setLastQuery] = useState('');
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);

  // Audio search state (separate from agent streaming state)
  const [audioSongs, setAudioSongs] = useState<SongResult[]>([]);
  const [audioExplanation, setAudioExplanation] = useState('');
  const [audioLoading, setAudioLoading] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);

  const { getToken } = useClerkAuth();
  const { state, search, cancel } = useSearch();
  const { authState, canSearch, recordSearch, needsSignup, needsUpgrade } = useAuth();
  const { openBillingPortal } = useBilling();

  const theme = themes[themeName];

  // Show upgrade modal automatically when limit is hit after a search
  useEffect(() => {
    if (needsUpgrade && hasSearched) setShowUpgradeModal(true);
  }, [needsUpgrade, hasSearched]);

  // Check for post-Stripe redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('upgraded') === 'true') {
      window.history.replaceState({}, '', '/');
    }
  }, []);

  const handleSearch = useCallback(async () => {
    const q = inputValue.trim();
    if (!q) return;

    // Gate check
    if (needsSignup) { setShowAuthModal(true); return; }
    if (needsUpgrade) { setShowUpgradeModal(true); return; }
    if (!canSearch()) {
      if (!authState.isSignedIn) setShowAuthModal(true);
      else setShowUpgradeModal(true);
      return;
    }

    const token = authState.isSignedIn ? await getToken() : null;
    setLastQuery(q);
    setHasSearched(true);
    recordSearch();
    search(q, searchType, token);
  }, [inputValue, searchType, canSearch, needsSignup, needsUpgrade, authState, getToken, recordSearch, search]);

  const handleAudioSearch = useCallback(async (blob: Blob) => {
    // Gate check
    if (needsSignup) { setShowAuthModal(true); return; }
    if (needsUpgrade) { setShowUpgradeModal(true); return; }
    if (!canSearch()) {
      if (!authState.isSignedIn) setShowAuthModal(true);
      else setShowUpgradeModal(true);
      return;
    }

    setAudioLoading(true);
    setAudioError(null);
    setAudioSongs([]);
    setAudioExplanation('');
    setHasSearched(true);
    setLastQuery('audio clip');
    recordSearch();

    try {
      const token = authState.isSignedIn ? await getToken() : null;
      const result = await audioSearch(blob, token);
      setAudioSongs(result.songs);
      setAudioExplanation(result.explanation);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setAudioError(msg);
    } finally {
      setAudioLoading(false);
    }
  }, [needsSignup, needsUpgrade, canSearch, authState, getToken, recordSearch]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
  };

  const searchTypeOptions: {
    value: SearchType; label: string; icon: typeof AudioWaveform; desc: string
  }[] = [
    { value: 'melody', label: 'Melody & Sound', icon: AudioWaveform, desc: 'Match by musical feel, tempo, energy' },
    { value: 'lyrics', label: 'Lyrics & Theme', icon: FileText, desc: 'Match by meaning and lyrical content' },
    { value: 'both', label: 'Both', icon: Music, desc: 'Best overall match' },
  ];

  return (
    <div style={{ minHeight: '100vh', backgroundColor: theme.bg, color: theme.text, fontFamily: 'system-ui, -apple-system, sans-serif', transition: 'all 0.2s' }}>
      <div style={{ maxWidth: '860px', margin: '0 auto', padding: '32px 16px 64px' }}>

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px', marginBottom: '10px' }}>
            <div style={{ width: '44px', height: '44px', borderRadius: '50%', backgroundColor: theme.accent, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Music size={22} color={theme.accentText} />
            </div>
            <h1 style={{ fontSize: '32px', fontWeight: 800, color: theme.accent, margin: 0 }}>MelodyMatch</h1>
          </div>
          <p style={{ color: theme.textMuted, fontSize: '15px', margin: '0 0 16px' }}>
            Describe any musical feeling — our AI finds songs that match using vector search
          </p>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <ThemeToggle current={themeName} onChange={setThemeName} theme={theme} />
            <UsageCounter
              authState={authState}
              theme={theme}
              onUpgradeClick={() => setShowUpgradeModal(true)}
              onSignInClick={() => setShowAuthModal(true)}
              onPortalClick={openBillingPortal}
            />
          </div>
        </div>

        {/* Search card */}
        <div style={{ backgroundColor: theme.surface, border: `1px solid ${theme.border}`, borderRadius: theme.name === 'spotify' ? '16px' : theme.radius, padding: '28px', marginBottom: '24px' }}>

          {/* Input mode toggle (Text / Audio) */}
          <div style={{
            display: 'flex', backgroundColor: theme.inputBg,
            borderRadius: '9999px', padding: '3px', marginBottom: '20px',
            border: `1px solid ${theme.border}`,
          }}>
            {(['text', 'audio'] as const).map((mode) => (
              <button key={mode} onClick={() => setInputMode(mode)} style={{
                flex: 1, padding: '8px 12px',
                borderRadius: '9999px', border: 'none', cursor: 'pointer',
                fontSize: '13px', fontWeight: inputMode === mode ? 600 : 400,
                backgroundColor: inputMode === mode ? theme.accent : 'transparent',
                color: inputMode === mode ? theme.accentText : theme.textMuted,
                transition: 'all 0.15s',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
              }}>
                {mode === 'text' ? <Search size={13} /> : <Mic size={13} />}
                {mode === 'text' ? 'Text search' : 'Audio match'}
              </button>
            ))}
          </div>

          {inputMode === 'text' ? (
            <>
              <div style={{ position: 'relative', marginBottom: '16px' }}>
                <Search size={18} style={{ position: 'absolute', left: '16px', top: '50%', transform: 'translateY(-50%)', color: theme.textMuted }} />
                <input
                  type="text"
                  placeholder='e.g. "slow melancholic acoustic guitar like Elliott Smith" or "songs about resilience with an upbeat energy"'
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  style={{
                    width: '100%',
                    padding: '14px 48px 14px 46px',
                    backgroundColor: theme.inputBg,
                    border: `1px solid ${theme.border}`,
                    borderRadius: theme.radius,
                    color: theme.text,
                    fontSize: '15px',
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                  onFocus={(e) => (e.currentTarget.style.borderColor = theme.accent)}
                  onBlur={(e) => (e.currentTarget.style.borderColor = theme.border)}
                />
                {inputValue && (
                  <button
                    onClick={() => setInputValue('')}
                    style={{ position: 'absolute', right: '14px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: theme.textMuted }}
                  >
                    <X size={16} />
                  </button>
                )}
              </div>

              {/* Search type selector */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', marginBottom: '16px' }}>
                {searchTypeOptions.map(({ value, label, icon: Icon, desc }) => {
                  const active = searchType === value;
                  return (
                    <button key={value} onClick={() => setSearchType(value)} style={{
                      padding: '12px',
                      borderRadius: theme.name === 'spotify' ? '10px' : theme.radius,
                      border: `2px solid ${active ? theme.accent : theme.border}`,
                      backgroundColor: active ? theme.accentBg : theme.surface,
                      cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <Icon size={15} style={{ color: active ? theme.accent : theme.textMuted }} />
                        <span style={{ color: active ? theme.accent : theme.text, fontSize: '13px', fontWeight: 600 }}>{label}</span>
                      </div>
                      <div style={{ color: theme.textMuted, fontSize: '11px' }}>{desc}</div>
                    </button>
                  );
                })}
              </div>

              {/* Free catalog notice for gated users (hidden in dev mode) */}
              {!DEV_UNLIMITED && (!authState.isSignedIn || authState.plan === 'free') ? (
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 14px', marginBottom: '12px',
                  backgroundColor: theme.accentBg,
                  borderRadius: '8px',
                  fontSize: '12px',
                }}>
                  <span style={{ color: theme.textMuted }}>
                    🎵 Searching <strong style={{ color: theme.text }}>popular songs</strong> — upgrade to unlock the full catalog
                  </span>
                  <button onClick={() => authState.isSignedIn ? setShowUpgradeModal(true) : setShowAuthModal(true)} style={{
                    backgroundColor: theme.accent, color: theme.accentText,
                    border: 'none', borderRadius: '9999px', padding: '4px 10px',
                    fontSize: '11px', fontWeight: 600, cursor: 'pointer',
                  }}>
                    Unlock
                  </button>
                </div>
              ) : null}

              <button
                onClick={state.isLoading ? cancel : handleSearch}
                disabled={!inputValue.trim() && !state.isLoading}
                style={{
                  width: '100%', padding: '14px', borderRadius: theme.radius, border: 'none',
                  backgroundColor: state.isLoading ? theme.inputBg : (inputValue.trim() ? theme.accent : theme.border),
                  color: state.isLoading ? theme.textMuted : (inputValue.trim() ? theme.accentText : theme.textMuted),
                  fontSize: '15px', fontWeight: 700,
                  cursor: inputValue.trim() || state.isLoading ? 'pointer' : 'default',
                  transition: 'all 0.15s',
                }}
              >
                {state.isLoading ? 'Cancel search' : 'Find Similar Songs'}
              </button>
            </>
          ) : (
            /* Audio upload / record mode */
            <AudioUpload
              theme={theme}
              isSearching={audioLoading}
              onSearch={handleAudioSearch}
              onCancel={() => setInputMode('text')}
            />
          )}
        </div>

        {/* Results */}
        {hasSearched && (
          <div>
            {/* Text search results */}
            {inputMode === 'text' && (
              <>
                <AgentThinking steps={state.steps} isLoading={state.isLoading} theme={theme} />

                {state.error && (
                  <div style={{ backgroundColor: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '10px', padding: '16px', color: '#ef4444', marginBottom: '16px' }}>
                    {state.error}
                  </div>
                )}

                {state.songs.length > 0 && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', marginBottom: '16px' }}>
                      <Music size={18} style={{ color: theme.accent, marginTop: '2px', flexShrink: 0 }} />
                      <div>
                        <h2 style={{ color: theme.text, fontSize: '18px', fontWeight: 700, margin: '0 0 4px' }}>
                          Results for "{lastQuery}"
                        </h2>
                        {state.explanation && (
                          <p style={{ color: theme.textMuted, fontSize: '13px', margin: 0, lineHeight: '1.5' }}>
                            {state.explanation}
                          </p>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {state.songs.map((song, i) => (
                        <ResultCard key={song.song_id} song={song} rank={i + 1} theme={theme} />
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* Audio search results */}
            {inputMode === 'audio' && (
              <>
                {audioLoading && (
                  <div style={{
                    backgroundColor: theme.surface, border: `1px solid ${theme.border}`,
                    borderRadius: '12px', padding: '20px', marginBottom: '16px',
                    display: 'flex', alignItems: 'center', gap: '12px',
                  }}>
                    <div style={{
                      width: '20px', height: '20px', border: `2px solid ${theme.border}`,
                      borderTopColor: theme.accent, borderRadius: '50%',
                      animation: 'spin 0.8s linear infinite',
                    }} />
                    <span style={{ color: theme.textMuted, fontSize: '14px' }}>
                      Analyzing audio fingerprint…
                    </span>
                    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                  </div>
                )}

                {audioError && (
                  <div style={{ backgroundColor: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '10px', padding: '16px', color: '#ef4444', marginBottom: '16px' }}>
                    {audioError}
                  </div>
                )}

                {audioSongs.length > 0 && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', marginBottom: '16px' }}>
                      <Mic size={18} style={{ color: theme.accent, marginTop: '2px', flexShrink: 0 }} />
                      <div>
                        <h2 style={{ color: theme.text, fontSize: '18px', fontWeight: 700, margin: '0 0 4px' }}>
                          Songs matching your audio
                        </h2>
                        {audioExplanation && (
                          <p style={{ color: theme.textMuted, fontSize: '13px', margin: 0, lineHeight: '1.5' }}>
                            {audioExplanation}
                          </p>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {audioSongs.map((song, i) => (
                        <ResultCard key={song.song_id} song={song} rank={i + 1} theme={theme} />
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Modals */}
      {showAuthModal && (
        <AuthModal theme={theme} onClose={() => setShowAuthModal(false)} defaultSignUp />
      )}
      {showUpgradeModal && (
        <UpgradeModal theme={theme} currentPlan={authState.plan} onClose={() => setShowUpgradeModal(false)} />
      )}
    </div>
  );
}
