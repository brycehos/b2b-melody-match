export type SearchType = 'melody' | 'lyrics' | 'both';
export type ThemeName = 'spotify' | 'apple' | 'purple';
export type PlanName = 'anonymous' | 'free' | 'explorer' | 'unlimited';

export interface AudioFeatures {
  energy: number;
  tempo: number;
  valence: number;
  danceability: number;
  acousticness: number;
  instrumentalness: number;
  speechiness: number;
  loudness: number;
  key: number;
  mode: number;
  liveness: number;
}

export interface SongResult {
  song_id: string;
  title: string;
  artist: string;
  album: string;
  year: number;
  genre: string;
  duration: string;
  similarity: number;
  match_reason?: string;
  preview_url?: string;
  image_url?: string;
  spotify_url?: string;
  audio_features?: AudioFeatures;
}

export type AgentEvent =
  | { type: 'thinking'; text: string }
  | { type: 'tool_call'; tool: string; query: string }
  | { type: 'tool_result'; count: number }
  | { type: 'result'; songs: SongResult[]; explanation: string }
  | { type: 'error'; text: string };

export interface AudioSearchResult {
  songs: SongResult[];
  explanation: string;
  features: AudioFeatures;
}

export interface Theme {
  name: ThemeName;
  bg: string;
  surface: string;
  surfaceHover: string;
  border: string;
  accent: string;
  accentHover: string;
  accentText: string;
  accentBg: string;
  inputBg: string;
  text: string;
  textMuted: string;
  radius: string;
  toggleActive: string;
}
