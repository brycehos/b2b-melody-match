import type { AgentEvent, AudioSearchResult, SearchType } from '../types';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export async function streamSearch(
  query: string,
  searchType: SearchType,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
  authToken?: string | null,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const response = await fetch(`${API_URL}/api/search`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query, search_type: searchType }),
    signal,
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`Search failed: ${detail}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      try {
        const event = JSON.parse(raw) as AgentEvent;
        onEvent(event);
      } catch {
        // Malformed SSE line — skip
      }
    }
  }
}

/**
 * Upload an audio blob and get back song matches.
 * The blob can be WAV (from MediaRecorder) or any common audio format.
 */
export async function audioSearch(
  blob: Blob,
  authToken?: string | null,
  signal?: AbortSignal,
): Promise<AudioSearchResult> {
  const headers: Record<string, string> = {};
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const formData = new FormData();
  // Extension must match the actual content so soundfile/ffmpeg can decode it.
  // AudioUpload always converts to WAV before calling this function, so the
  // extension here will almost always be .wav. Fall back based on MIME type
  // for any raw blob that bypasses conversion.
  const ext = blob.type.includes('wav') ? '.wav'
    : blob.type.includes('ogg') ? '.ogg'
    : blob.type.includes('mp4') || blob.type.includes('m4a') ? '.m4a'
    : blob.type.includes('mpeg') ? '.mp3'
    : '.webm';
  formData.append('file', blob, `audio${ext}`);

  const response = await fetch(`${API_URL}/api/audio-search`, {
    method: 'POST',
    headers,
    body: formData,
    signal,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body?.detail ?? detail;
    } catch { /* ignore */ }
    throw new Error(`Audio search failed: ${detail}`);
  }

  return response.json() as Promise<AudioSearchResult>;
}
