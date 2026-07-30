import { useUser } from '@clerk/clerk-react';
import { Zap } from 'lucide-react';
import type { Theme } from '../types';
import type { AuthState } from '../hooks/useAuth';

interface Props {
  authState: AuthState;
  theme: Theme;
  onUpgradeClick: () => void;
  onSignInClick: () => void;
  onPortalClick: () => void;
}

const PLAN_LABELS: Record<string, string> = {
  anonymous: 'Guest',
  free:      'Free',
  explorer:  'Explorer',
  unlimited: 'Unlimited',
};

// Vite sets this true under `npm run dev`; pairs with the backend DEV_MODE flag.
const DEV_UNLIMITED = import.meta.env.DEV;

export default function UsageCounter({
  authState,
  theme,
  onUpgradeClick,
  onSignInClick,
  onPortalClick,
}: Props) {
  const { isSignedIn } = useUser();
  const { plan, searchesUsed, searchesLimit, searchesRemaining } = authState;
  const pct = Math.min(100, (searchesUsed / searchesLimit) * 100);
  const isPaid = plan === 'explorer' || plan === 'unlimited';
  const isLow = searchesRemaining <= 2 && searchesRemaining > 0;
  const isOut  = searchesRemaining === 0;

  const barColor = isOut ? '#ef4444' : isLow ? '#f59e0b' : theme.accent;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      {/* Usage pill */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '8px',
        backgroundColor: theme.inputBg,
        border: `1px solid ${isOut ? '#ef4444' : theme.border}`,
        borderRadius: '9999px',
        padding: '6px 12px',
        fontSize: '12px',
        color: isOut ? '#ef4444' : theme.textMuted,
      }}>
        <Zap size={12} style={{ color: barColor }} />
        <span>
          {DEV_UNLIMITED
            ? 'Dev · unlimited'
            : isSignedIn
            ? `${searchesRemaining} / ${searchesLimit} left · ${PLAN_LABELS[plan] ?? plan}`
            : `${Math.max(0, searchesLimit - searchesUsed)} free search${searchesLimit - searchesUsed !== 1 ? 'es' : ''} left`}
        </span>
        {/* Mini progress bar (hidden in dev mode — there's no quota to show) */}
        {!DEV_UNLIMITED && (
          <div style={{ width: '40px', height: '4px', backgroundColor: theme.border, borderRadius: '9999px', overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', backgroundColor: barColor, borderRadius: '9999px', transition: 'width 0.3s' }} />
          </div>
        )}
      </div>

      {/* CTA button */}
      {!isSignedIn && (
        <button onClick={onSignInClick} style={{
          padding: '7px 14px', borderRadius: '9999px',
          backgroundColor: theme.accent, color: theme.accentText,
          border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 600,
        }}>
          Sign in
        </button>
      )}
      {isSignedIn && !isPaid && (
        <button onClick={onUpgradeClick} style={{
          padding: '7px 14px', borderRadius: '9999px',
          backgroundColor: theme.accent, color: theme.accentText,
          border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 600,
        }}>
          Upgrade
        </button>
      )}
      {isSignedIn && isPaid && (
        <button onClick={onPortalClick} style={{
          padding: '7px 14px', borderRadius: '9999px',
          backgroundColor: theme.inputBg, color: theme.textMuted,
          border: `1px solid ${theme.border}`, cursor: 'pointer', fontSize: '12px',
        }}>
          Manage plan
        </button>
      )}
    </div>
  );
}
