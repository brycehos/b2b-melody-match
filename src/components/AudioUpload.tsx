/**
 * AudioUpload — Shazam-style audio input component.
 *
 * Two input modes:
 *   1. Record — tap the mic button to capture up to 15 seconds of audio via
 *      the MediaRecorder API (WAV preferred, Opus fallback).
 *   2. Upload — drag-and-drop or file picker for any audio file ≤ 10 MB.
 *
 * Calls `onSearch(blob)` when audio is ready, leaving network logic to the parent.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, MicOff, Upload, X, AudioWaveform } from 'lucide-react';
import type { Theme } from '../types';

interface Props {
  theme: Theme;
  isSearching: boolean;
  onSearch: (blob: Blob) => void;
  onCancel: () => void;
}

type RecordState = 'idle' | 'requesting' | 'recording' | 'processing';

const MAX_RECORD_SECONDS = 15;
const MIME_PREFERENCE = [
  'audio/wav',
  'audio/webm;codecs=pcm',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/ogg',
];

function getSupportedMime(): string {
  for (const mime of MIME_PREFERENCE) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return '';
}

/**
 * Convert any audio blob to a proper WAV blob using the Web Audio API.
 * This is necessary because MediaRecorder outputs webm/opus in Chrome,
 * which soundfile on the server cannot read without ffmpeg. Converting to
 * raw PCM WAV here means the server only ever receives a format it can
 * handle natively, with no external dependencies.
 */
async function toWav(blob: Blob): Promise<Blob> {
  const arrayBuffer = await blob.arrayBuffer();
  const audioCtx = new AudioContext();
  let audioBuffer: AudioBuffer;
  try {
    audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
  } finally {
    await audioCtx.close();
  }

  const numChannels = Math.min(audioBuffer.numberOfChannels, 2); // max stereo
  const sampleRate  = audioBuffer.sampleRate;
  const numFrames   = audioBuffer.length;
  const numSamples  = numFrames * numChannels;
  const dataBytes   = numSamples * 2;           // 16-bit PCM
  const buf         = new ArrayBuffer(44 + dataBytes);
  const view        = new DataView(buf);

  const str = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };

  // RIFF/WAVE header
  str(0, 'RIFF');
  view.setUint32(4,  36 + dataBytes, true);
  str(8, 'WAVE');
  str(12, 'fmt ');
  view.setUint32(16, 16, true);                        // PCM chunk size
  view.setUint16(20, 1,  true);                        // PCM format
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * 2, true);  // byte rate
  view.setUint16(32, numChannels * 2, true);           // block align
  view.setUint16(34, 16, true);                        // bits/sample
  str(36, 'data');
  view.setUint32(40, dataBytes, true);

  // Interleaved 16-bit PCM samples
  let off = 44;
  for (let i = 0; i < numFrames; i++) {
    for (let ch = 0; ch < numChannels; ch++) {
      const s = Math.max(-1, Math.min(1, audioBuffer.getChannelData(ch)[i]));
      view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      off += 2;
    }
  }

  return new Blob([buf], { type: 'audio/wav' });
}

export default function AudioUpload({ theme, isSearching, onSearch, onCancel }: Props) {
  const [recordState, setRecordState] = useState<RecordState>('idle');
  const [secondsLeft, setSecondsLeft] = useState(MAX_RECORD_SECONDS);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

  const mediaRef   = useRef<MediaRecorder | null>(null);
  const chunksRef  = useRef<Blob[]>([]);
  const timerRef   = useRef<ReturnType<typeof setInterval> | null>(null);
  const streamRef  = useRef<MediaStream | null>(null);

  // Cleanup on unmount
  useEffect(() => () => {
    timerRef.current && clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach(t => t.stop());
  }, []);

  const stopRecording = useCallback(() => {
    timerRef.current && clearInterval(timerRef.current);
    if (mediaRef.current && mediaRef.current.state !== 'inactive') {
      mediaRef.current.stop();
    }
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
    setRecordState('processing');
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    setFileName(null);
    setRecordState('requesting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mime = getSupportedMime();
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      mediaRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        const raw = new Blob(chunksRef.current, { type: mime || 'audio/webm' });
        setRecordState('processing');
        try {
          const wav = await toWav(raw);
          onSearch(wav);
        } catch {
          // If WAV conversion fails (e.g. very short clip), send raw and let
          // the server try its best with ffmpeg.
          onSearch(raw);
        } finally {
          setRecordState('idle');
          setSecondsLeft(MAX_RECORD_SECONDS);
        }
      };

      recorder.onerror = () => {
        setError('Recording error — please try again.');
        setRecordState('idle');
        setSecondsLeft(MAX_RECORD_SECONDS);
      };

      recorder.start(250); // collect chunks every 250 ms
      setRecordState('recording');
      setSecondsLeft(MAX_RECORD_SECONDS);

      // Auto-stop countdown
      timerRef.current = setInterval(() => {
        setSecondsLeft(prev => {
          if (prev <= 1) {
            stopRecording();
            return MAX_RECORD_SECONDS;
          }
          return prev - 1;
        });
      }, 1000);

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('Permission') || msg.includes('denied')) {
        setError('Microphone access denied. Please allow microphone permissions and try again.');
      } else {
        setError(`Could not start recording: ${msg}`);
      }
      setRecordState('idle');
    }
  }, [onSearch, stopRecording]);

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    if (!file.type.startsWith('audio/') && !file.name.match(/\.(mp3|wav|ogg|m4a|flac|aac|opus)$/i)) {
      setError('Please upload an audio file (MP3, WAV, OGG, M4A, etc.)');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('File too large. Maximum size is 10 MB.');
      return;
    }
    setFileName(file.name);
    // WAV files are sent as-is (soundfile reads them natively).
    // All other formats are decoded and re-encoded to WAV in-browser so the
    // server never needs ffmpeg.
    if (file.type === 'audio/wav' || file.name.endsWith('.wav')) {
      onSearch(file);
    } else {
      try {
        const wav = await toWav(file);
        onSearch(wav);
      } catch {
        onSearch(file);   // fallback: send raw and hope for ffmpeg
      }
    }
  }, [onSearch]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = '';
  }, [handleFile]);

  const isRecording = recordState === 'recording';
  const isRequesting = recordState === 'requesting' || recordState === 'processing';
  const isBusy = isSearching || isRequesting;

  // Progress arc for countdown
  const radius = 26;
  const circumference = 2 * Math.PI * radius;
  const progress = isRecording ? (secondsLeft / MAX_RECORD_SECONDS) * circumference : circumference;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

      {/* ── Mic recorder ────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
        <div style={{ position: 'relative', width: '72px', height: '72px' }}>
          {/* SVG countdown ring */}
          {isRecording && (
            <svg
              style={{ position: 'absolute', inset: 0, transform: 'rotate(-90deg)' }}
              width="72" height="72"
            >
              <circle
                cx="36" cy="36" r={radius}
                fill="none"
                stroke={theme.border}
                strokeWidth="3"
              />
              <circle
                cx="36" cy="36" r={radius}
                fill="none"
                stroke={theme.accent}
                strokeWidth="3"
                strokeDasharray={circumference}
                strokeDashoffset={circumference - progress}
                strokeLinecap="round"
                style={{ transition: 'stroke-dashoffset 1s linear' }}
              />
            </svg>
          )}

          <button
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isBusy}
            style={{
              position: 'absolute', inset: '6px',
              borderRadius: '50%',
              border: 'none',
              cursor: isBusy ? 'not-allowed' : 'pointer',
              backgroundColor: isRecording ? '#ef4444' : theme.accent,
              color: theme.accentText,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.2s',
              boxShadow: isRecording ? '0 0 0 4px rgba(239,68,68,0.25)' : 'none',
            }}
          >
            {isRecording
              ? <MicOff size={22} />
              : isRequesting
                ? <AudioWaveform size={22} style={{ opacity: 0.5 }} />
                : <Mic size={22} />
            }
          </button>
        </div>

        <div style={{ textAlign: 'center' }}>
          {isRecording ? (
            <p style={{ color: '#ef4444', fontSize: '13px', margin: 0, fontWeight: 600 }}>
              Recording… {secondsLeft}s — tap to stop
            </p>
          ) : isSearching ? (
            <p style={{ color: theme.textMuted, fontSize: '13px', margin: 0 }}>
              Analyzing audio…
            </p>
          ) : (
            <p style={{ color: theme.textMuted, fontSize: '13px', margin: 0 }}>
              Tap to record up to {MAX_RECORD_SECONDS} seconds
            </p>
          )}
        </div>
      </div>

      {/* ── Divider ─────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{ flex: 1, height: '1px', backgroundColor: theme.border }} />
        <span style={{ color: theme.textMuted, fontSize: '12px' }}>or upload a file</span>
        <div style={{ flex: 1, height: '1px', backgroundColor: theme.border }} />
      </div>

      {/* ── File drop zone ───────────────────────────────────────────────── */}
      <label
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          gap: '8px', padding: '20px 16px',
          border: `2px dashed ${dragOver ? theme.accent : theme.border}`,
          borderRadius: theme.radius,
          backgroundColor: dragOver ? theme.accentBg : theme.inputBg,
          cursor: isBusy ? 'not-allowed' : 'pointer',
          transition: 'all 0.15s',
          opacity: isBusy ? 0.6 : 1,
        }}
      >
        <input
          type="file"
          accept="audio/*"
          style={{ display: 'none' }}
          onChange={handleFileInput}
          disabled={isBusy}
        />
        <Upload size={20} style={{ color: dragOver ? theme.accent : theme.textMuted }} />
        {fileName ? (
          <span style={{ color: theme.text, fontSize: '13px', fontWeight: 500 }}>{fileName}</span>
        ) : (
          <>
            <span style={{ color: theme.text, fontSize: '13px', fontWeight: 500 }}>
              Drop audio file here
            </span>
            <span style={{ color: theme.textMuted, fontSize: '11px' }}>
              MP3, WAV, M4A, OGG — max 10 MB
            </span>
          </>
        )}
      </label>

      {/* ── Error ───────────────────────────────────────────────────────── */}
      {error && (
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: '8px',
          padding: '10px 12px',
          backgroundColor: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: '8px',
          color: '#ef4444', fontSize: '13px',
        }}>
          <X size={14} style={{ marginTop: '1px', flexShrink: 0, cursor: 'pointer' }} onClick={() => setError(null)} />
          {error}
        </div>
      )}

      {/* ── Cancel ──────────────────────────────────────────────────────── */}
      <button
        onClick={() => {
          if (isRecording) stopRecording();
          onCancel();
        }}
        style={{
          background: 'none', border: `1px solid ${theme.border}`,
          borderRadius: theme.radius, padding: '8px',
          color: theme.textMuted, fontSize: '13px',
          cursor: 'pointer',
        }}
      >
        Switch to text search
      </button>
    </div>
  );
}
