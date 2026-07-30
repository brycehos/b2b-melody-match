import { useEffect, useRef } from 'react';
import { Brain, Search, Music, CheckCircle } from 'lucide-react';
import type { Theme } from '../types';
import type { ThinkingStep } from '../hooks/useSearch';

interface Props {
  steps: ThinkingStep[];
  isLoading: boolean;
  theme: Theme;
}

const stepIcon = (type: ThinkingStep['type']) => {
  switch (type) {
    case 'thinking': return Brain;
    case 'tool_call': return Search;
    case 'tool_result': return CheckCircle;
  }
};

export default function AgentThinking({ steps, isLoading, theme }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [steps.length]);

  if (steps.length === 0 && !isLoading) return null;

  return (
    <div
      style={{
        backgroundColor: theme.surface,
        border: `1px solid ${theme.border}`,
        borderRadius: theme.name === 'spotify' ? '12px' : theme.radius,
        padding: '20px',
        marginBottom: '16px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
        <Music size={16} style={{ color: theme.accent }} />
        <span style={{ color: theme.textMuted, fontSize: '13px', fontWeight: 500 }}>
          Agent reasoning
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '220px', overflowY: 'auto' }}>
        {steps.map((step, i) => {
          const Icon = stepIcon(step.type);
          return (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '10px',
                animation: 'fadeIn 0.2s ease',
              }}
            >
              <Icon
                size={14}
                style={{
                  color: step.type === 'tool_result' ? theme.accent : theme.textMuted,
                  marginTop: '2px',
                  flexShrink: 0,
                }}
              />
              <span style={{ color: theme.textMuted, fontSize: '13px', lineHeight: '1.5' }}>
                {step.text}
              </span>
            </div>
          );
        })}

        {isLoading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ display: 'flex', gap: '4px' }}>
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: theme.accent,
                    display: 'inline-block',
                    animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
                  }}
                />
              ))}
            </div>
            <span style={{ color: theme.textMuted, fontSize: '13px' }}>Searching...</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); } 40% { opacity: 1; transform: scale(1); } }
      `}</style>
    </div>
  );
}
