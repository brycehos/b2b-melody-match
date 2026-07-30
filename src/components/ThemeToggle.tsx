import type { Theme, ThemeName } from '../types';

interface Props {
  current: ThemeName;
  onChange: (name: ThemeName) => void;
  theme: Theme;
}

const OPTIONS: { name: ThemeName; label: string }[] = [
  { name: 'spotify', label: 'Spotify' },
  { name: 'apple', label: 'Apple' },
  { name: 'purple', label: 'Classic' },
];

export default function ThemeToggle({ current, onChange, theme }: Props) {
  return (
    <div
      style={{
        display: 'inline-flex',
        backgroundColor: theme.inputBg,
        borderRadius: '9999px',
        padding: '3px',
        gap: '2px',
        border: `1px solid ${theme.border}`,
      }}
    >
      {OPTIONS.map(({ name, label }) => {
        const active = name === current;
        return (
          <button
            key={name}
            onClick={() => onChange(name)}
            style={{
              padding: '5px 14px',
              borderRadius: '9999px',
              border: 'none',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: active ? 600 : 400,
              backgroundColor: active ? theme.accent : 'transparent',
              color: active ? theme.accentText : theme.textMuted,
              transition: 'all 0.15s',
            }}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
