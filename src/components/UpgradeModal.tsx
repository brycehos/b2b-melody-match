import { X, Zap, Infinity, Check } from 'lucide-react';
import type { Theme } from '../types';
import { useBilling } from '../hooks/useBilling';

interface Props {
  onClose: () => void;
  theme: Theme;
  currentPlan: string;
}

const PLANS = [
  {
    key: 'explorer' as const,
    name: 'Explorer',
    price: '$4.99',
    period: '/month',
    icon: Zap,
    tagline: 'Perfect for regular music discovery',
    features: [
      '75 searches per month',
      'Full catalog (1,000+ songs)',
      'All genres including jazz, classical, folk, metal',
      'Save & favorite songs',
      'Match explanations from Claude AI',
    ],
  },
  {
    key: 'unlimited' as const,
    name: 'Unlimited',
    price: '$9.99',
    period: '/month',
    icon: Infinity,
    tagline: 'For music obsessives and professionals',
    features: [
      '300 searches per month',
      'Full catalog (1,000+ songs)',
      'Priority response queue',
      'All Explorer features',
      'Early access to new features',
    ],
    highlighted: true,
  },
];

export default function UpgradeModal({ onClose, theme, currentPlan }: Props) {
  const { startCheckout, isRedirecting } = useBilling();

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        backgroundColor: 'rgba(0,0,0,0.75)',
        backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: '16px',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        backgroundColor: theme.surface,
        borderRadius: '20px',
        padding: '32px',
        maxWidth: '580px',
        width: '100%',
        border: `1px solid ${theme.border}`,
        position: 'relative',
      }}>
        <button onClick={onClose} style={{
          position: 'absolute', top: '16px', right: '16px',
          background: 'none', border: 'none', cursor: 'pointer',
          color: theme.textMuted,
        }}>
          <X size={18} />
        </button>

        <div style={{ textAlign: 'center', marginBottom: '28px' }}>
          <h2 style={{ color: theme.text, fontSize: '24px', fontWeight: 800, margin: '0 0 8px' }}>
            Unlock the full catalog
          </h2>
          <p style={{ color: theme.textMuted, fontSize: '14px', margin: 0 }}>
            You've used all your {currentPlan === 'free' ? '10 free' : 'monthly'} searches.
            Upgrade to keep discovering music.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          {PLANS.map(({ key, name, price, period, icon: Icon, tagline, features, highlighted }) => (
            <div key={key} style={{
              border: `2px solid ${highlighted ? theme.accent : theme.border}`,
              borderRadius: '16px',
              padding: '20px',
              backgroundColor: highlighted ? theme.accentBg : theme.inputBg,
              position: 'relative',
            }}>
              {highlighted && (
                <div style={{
                  position: 'absolute', top: '-12px', left: '50%', transform: 'translateX(-50%)',
                  backgroundColor: theme.accent, color: theme.accentText,
                  fontSize: '11px', fontWeight: 700, padding: '3px 12px', borderRadius: '9999px',
                }}>
                  MOST POPULAR
                </div>
              )}

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <Icon size={18} style={{ color: theme.accent }} />
                <span style={{ color: theme.text, fontWeight: 700, fontSize: '16px' }}>{name}</span>
              </div>

              <div style={{ marginBottom: '6px' }}>
                <span style={{ color: theme.text, fontSize: '28px', fontWeight: 800 }}>{price}</span>
                <span style={{ color: theme.textMuted, fontSize: '13px' }}>{period}</span>
              </div>

              <p style={{ color: theme.textMuted, fontSize: '12px', margin: '0 0 16px' }}>{tagline}</p>

              <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {features.map((f) => (
                  <li key={f} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '13px', color: theme.textMuted }}>
                    <Check size={13} style={{ color: theme.accent, marginTop: '2px', flexShrink: 0 }} />
                    {f}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => startCheckout(key)}
                disabled={isRedirecting}
                style={{
                  width: '100%', padding: '11px',
                  borderRadius: '9999px', border: 'none', cursor: isRedirecting ? 'default' : 'pointer',
                  backgroundColor: highlighted ? theme.accent : theme.surface,
                  color: highlighted ? theme.accentText : theme.accent,
                  outline: highlighted ? 'none' : `2px solid ${theme.accent}`,
                  fontWeight: 700, fontSize: '14px',
                  opacity: isRedirecting ? 0.7 : 1,
                  transition: 'all 0.15s',
                } as React.CSSProperties}
              >
                {isRedirecting ? 'Redirecting…' : `Get ${name}`}
              </button>
            </div>
          ))}
        </div>

        <p style={{ color: theme.textMuted, fontSize: '12px', textAlign: 'center', marginTop: '20px', marginBottom: 0 }}>
          Cancel anytime · Secure payment via Stripe · No hidden fees
        </p>
      </div>
    </div>
  );
}
