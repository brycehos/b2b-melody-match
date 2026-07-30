import { useState, useRef, useCallback } from 'react';
import { streamSearch } from '../api/client';
import type { AgentEvent, SongResult, SearchType } from '../types';

export interface ThinkingStep {
  type: 'thinking' | 'tool_call' | 'tool_result';
  text: string;
}

export interface SearchState {
  isLoading: boolean;
  songs: SongResult[];
  explanation: string;
  steps: ThinkingStep[];
  error: string | null;
}

export function useSearch() {
  const [state, setState] = useState<SearchState>({
    isLoading: false,
    songs: [],
    explanation: '',
    steps: [],
    error: null,
  });

  const abortRef = useRef<AbortController | null>(null);

  const search = useCallback(async (query: string, searchType: SearchType, authToken?: string | null) => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setState({ isLoading: true, songs: [], explanation: '', steps: [], error: null });

    const handleEvent = (event: AgentEvent) => {
      setState((prev) => {
        switch (event.type) {
          case 'thinking':
            return {
              ...prev,
              steps: [...prev.steps, { type: 'thinking', text: event.text }],
            };

          case 'tool_call':
            return {
              ...prev,
              steps: [
                ...prev.steps,
                {
                  type: 'tool_call',
                  text: `${toolLabel(event.tool)}: "${event.query}"`,
                },
              ],
            };

          case 'tool_result':
            return {
              ...prev,
              steps: [
                ...prev.steps,
                {
                  type: 'tool_result',
                  text: `Found ${event.count} candidate songs`,
                },
              ],
            };

          case 'result':
            return {
              ...prev,
              isLoading: false,
              songs: event.songs,
              explanation: event.explanation ?? '',
            };

          case 'error':
            return {
              ...prev,
              isLoading: false,
              error: event.text ?? 'An unknown error occurred',
            };

          default:
            return prev;
        }
      });
    };

    try {
      await streamSearch(query, searchType, handleEvent, abortRef.current.signal, authToken);
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') return;
      setState((prev) => ({
        ...prev,
        isLoading: false,
        error: (err as Error).message ?? 'Search failed',
      }));
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({ ...prev, isLoading: false }));
  }, []);

  return { state, search: search as (q: string, t: SearchType, token?: string | null) => void, cancel };
}

function toolLabel(tool: string): string {
  switch (tool) {
    case 'search_by_audio_mood': return 'Searching audio characteristics';
    case 'search_by_lyrics_theme': return 'Searching lyrical themes';
    case 'search_combined': return 'Running combined search';
    default: return tool;
  }
}
