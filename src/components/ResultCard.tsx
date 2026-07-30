import { useState, useRef } from 'react';
import { Play, Pause, Heart, ExternalLink, Music } from 'lucide-react';
import type { SongResult, Theme } from '../types';

interface Props {
  song: SongResult;
  rank: number;
  theme: Theme;
}

export default function ResultCard({ song, rank, theme }: Props) {
  const [liked, setLiked] = useState(false);
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const togglePlay = () => {
    if (!song.preview_url) return;
    if (!audioRef.current) {
      audioRef.current = new Audio(song.preview_url);
      audioRef.current.volume = 0.6;
      audioRef.current.onended = () => setPlaying(false);
    }
    if (playing) {
      audioRef.current.pause();
      setPlaying(false);
    } else {
      audioRef.current.play();
      setPlaying(true);
    }
  };

  const matchPct = Math.round(song.similarity * 100);
  const matchColor =
    matchPct >= 85 ? '#22c55e' : matchPct >= 70 ? theme.accent : theme.textMuted;

  return (
    <div
      style={{
        backgroundColor: theme.surface,
        border: `1px solid ${theme.border}`,
        borderRadius: theme.name === 'spotify' ? '10px' : theme.radius,
        padding: '16px',
        transition: 'background-color 0.15s',
      }}
      onMouseEnter={(e) =>
        ((e.currentTarget as HTMLDivElement).style.backgroundColor = theme.surfaceHover)
      }
      onMouseLeave={(e) =>
        ((e.currentTarget as HTMLDivElement).style.backgroundColor = theme.surface)
      }
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        {/* Rank */}
        <div
          style={{
            width: '28px',
            height: '28px',
            borderRadius: '50%',
            backgroundColor: theme.accent,
            color: theme.accentText,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '13px',
            fontWeight: 700,
            flexShrink: 0,
          }}
        >
          {rank}
        </div>

        {/* Album art / placeholder */}
        <div
          style={{
            width: '52px',
            height: '52px',
            borderRadius: theme.name === 'spotify' ? '4px' : '10px',
            overflow: 'hidden',
            flexShrink: 0,
            backgroundColor: theme.inputBg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {song.image_url ? (
            <img src={song.image_url} alt={song.album} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : (
            <Music size={22} style={{ color: theme.textMuted }} />
          )}
        </div>

        {/* Song info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: theme.text, fontWeight: 600, fontSize: '15px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {song.title}
          </div>
          <div style={{ color: theme.textMuted, fontSize: '13px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {song.artist} · {song.album}
          </div>
          <div style={{ display: 'flex', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
            <span style={{
              fontSize: '11px',
              padding: '2px 8px',
              borderRadius: '9999px',
              backgroundColor: theme.accentBg,
              color: theme.accent,
              fontWeight: 500,
            }}>
              {song.genre}
            </span>
            <span style={{ fontSize: '11px', color: theme.textMuted }}>{song.year} · {song.duration}</span>
          </div>
        </div>

        {/* Match % */}
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ color: matchColor, fontWeight: 700, fontSize: '18px' }}>
            {matchPct}%
          </div>
          <div style={{ color: theme.textMuted, fontSize: '11px' }}>match</div>
        </div>
      </div>

      {/* Match reason */}
      {song.match_reason && (
        <div style={{
          marginTop: '12px',
          padding: '10px 12px',
          backgroundColor: theme.inputBg,
          borderRadius: theme.name === 'spotify' ? '8px' : theme.radius,
          color: theme.textMuted,
          fontSize: '13px',
          lineHeight: '1.5',
          borderLeft: `3px solid ${theme.accent}`,
        }}>
          {song.match_reason}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
        {song.preview_url && (
          <button
            onClick={togglePlay}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '7px 14px',
              borderRadius: theme.radius,
              backgroundColor: theme.accent,
              color: theme.accentText,
              border: 'none',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: 600,
            }}
          >
            {playing ? <Pause size={14} /> : <Play size={14} />}
            {playing ? 'Pause' : 'Preview'}
          </button>
        )}

        <button
          onClick={() => setLiked((l) => !l)}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '34px',
            height: '34px',
            borderRadius: theme.radius,
            backgroundColor: theme.inputBg,
            border: `1px solid ${theme.border}`,
            cursor: 'pointer',
            color: liked ? '#e53e3e' : theme.textMuted,
          }}
        >
          <Heart size={15} fill={liked ? '#e53e3e' : 'none'} />
        </button>

        {song.spotify_url && (
          <a
            href={song.spotify_url}
            target="_blank"
            rel="noreferrer"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '34px',
              height: '34px',
              borderRadius: theme.radius,
              backgroundColor: theme.inputBg,
              border: `1px solid ${theme.border}`,
              color: theme.textMuted,
              textDecoration: 'none',
            }}
          >
            <ExternalLink size={15} />
          </a>
        )}
      </div>
    </div>
  );
}
