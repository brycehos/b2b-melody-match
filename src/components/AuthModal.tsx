import { SignIn, SignUp } from '@clerk/clerk-react';
import { X, Music } from 'lucide-react';
import { useState } from 'react';
import type { Theme } from '../types';

interface Props {
  onClose: () => void;
  theme: Theme;
  /** If true, open on the sign-up tab by default */
  defaultSignUp?: boolean;
}

export default function AuthModal({ onClose, theme, defaultSignUp = true }: Props) {
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>(defaultSignUp ? 'sign-up' : 'sign-in');

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        backgroundColor: 'rgba(0,0,0,0.7)',
        backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
        padding: '16px',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        backgroundColor: theme.surface,
        borderRadius: '20px',
        padding: '32px',
        maxWidth: '420px',
        width: '100%',
        position: 'relative',
        border: `1px solid ${theme.border}`,
      }}>
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: '16px', right: '16px',
            background: 'none', border: 'none', cursor: 'pointer',
            color: theme.textMuted, padding: '4px',
          }}
        >
          <X size={18} />
        </button>

        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <div style={{
            width: '48px', height: '48px', borderRadius: '50%',
            backgroundColor: theme.accent,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 12px',
          }}>
            <Music size={22} color={theme.accentText} />
          </div>
          <h2 style={{ color: theme.text, fontSize: '22px', fontWeight: 700, margin: '0 0 8px' }}>
            {mode === 'sign-up' ? 'Create your free account' : 'Welcome back'}
          </h2>
          <p style={{ color: theme.textMuted, fontSize: '14px', margin: 0 }}>
            {mode === 'sign-up'
              ? 'Get 10 free searches per month. No credit card required.'
              : 'Sign in to continue your searches.'}
          </p>
        </div>

        {/* Mode toggle */}
        <div style={{
          display: 'flex', backgroundColor: theme.inputBg,
          borderRadius: '9999px', padding: '3px', marginBottom: '20px',
          border: `1px solid ${theme.border}`,
        }}>
          {(['sign-up', 'sign-in'] as const).map((m) => (
            <button key={m} onClick={() => setMode(m)} style={{
              flex: 1, padding: '8px',
              borderRadius: '9999px', border: 'none', cursor: 'pointer',
              fontSize: '13px', fontWeight: mode === m ? 600 : 400,
              backgroundColor: mode === m ? theme.accent : 'transparent',
              color: mode === m ? theme.accentText : theme.textMuted,
              transition: 'all 0.15s',
            }}>
              {m === 'sign-up' ? 'Sign up' : 'Sign in'}
            </button>
          ))}
        </div>

        {/* Clerk-hosted form — appearance prop customizes colors */}
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          {mode === 'sign-up'
            ? <SignUp routing="hash" afterSignUpUrl="/" />
            : <SignIn routing="hash" afterSignInUrl="/" />
          }
        </div>
      </div>
    </div>
  );
}
