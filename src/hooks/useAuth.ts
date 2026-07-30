/**
 * useAuth — wraps Clerk auth + tracks anonymous search usage in localStorage.
 *
 * Anonymous flow:  3 searches stored in localStorage → show signup modal
 * Authenticated:   usage comes from the backend (/api/billing/me)
 */

import { useCallback, useEffect, useState } from 'react';
import { useUser, useAuth as useClerkAuth } from '@clerk/clerk-react';

const ANON_KEY = 'mm_anon_searches';
const ANON_LIMIT = 3;

// In `npm run dev`, Vite sets import.meta.env.DEV = true. We use it to bypass
// all client-side search gating so local testing has unlimited queries. This
// pairs with the backend's DEV_MODE flag, which bypasses server-side quota.
const DEV_UNLIMITED = import.meta.env.DEV;

export interface AuthState {
  isLoaded: boolean;
  isSignedIn: boolean;
  plan: string;            // 'anonymous' | 'free' | 'explorer' | 'unlimited'
  searchesUsed: number;
  searchesLimit: number;
  searchesRemaining: number;
}

export function useAuth() {
  const { isLoaded, isSignedIn, user } = useUser();
  const { getToken } = useClerkAuth();

  const [authState, setAuthState] = useState<AuthState>({
    isLoaded: false,
    isSignedIn: false,
    plan: 'anonymous',
    searchesUsed: 0,
    searchesLimit: ANON_LIMIT,
    searchesRemaining: ANON_LIMIT,
  });

  // Load backend usage info when signed in
  useEffect(() => {
    if (!isLoaded) return;

    if (!isSignedIn) {
      const used = getAnonCount();
      setAuthState({
        isLoaded: true,
        isSignedIn: false,
        plan: 'anonymous',
        searchesUsed: used,
        searchesLimit: ANON_LIMIT,
        searchesRemaining: Math.max(0, ANON_LIMIT - used),
      });
      return;
    }

    // Fetch usage from backend
    fetchUsage(getToken).then((info) => {
      if (info) {
        setAuthState({
          isLoaded: true,
          isSignedIn: true,
          plan: info.plan,
          searchesUsed: info.searches_used,
          searchesLimit: info.searches_limit,
          searchesRemaining: info.searches_remaining,
        });
      }
    });
  }, [isLoaded, isSignedIn, user?.id]);

  const getAnonCount = (): number => {
    try {
      return parseInt(localStorage.getItem(ANON_KEY) ?? '0', 10);
    } catch {
      return 0;
    }
  };

  const incrementAnonCount = useCallback((): number => {
    const next = getAnonCount() + 1;
    try { localStorage.setItem(ANON_KEY, String(next)); } catch { /* */ }
    return next;
  }, []);

  /** Call before every search. Returns true if the search is allowed. */
  const canSearch = useCallback((): boolean => {
    if (DEV_UNLIMITED) return true;
    if (!isLoaded) return false;
    if (isSignedIn) return authState.searchesRemaining > 0;
    return getAnonCount() < ANON_LIMIT;
  }, [isLoaded, isSignedIn, authState.searchesRemaining]);

  /** Call after a search completes to keep the local counter accurate. */
  const recordSearch = useCallback(() => {
    if (!isSignedIn) {
      const used = incrementAnonCount();
      setAuthState((prev) => ({
        ...prev,
        searchesUsed: used,
        searchesRemaining: Math.max(0, ANON_LIMIT - used),
      }));
    } else {
      setAuthState((prev) => ({
        ...prev,
        searchesUsed: prev.searchesUsed + 1,
        searchesRemaining: Math.max(0, prev.searchesRemaining - 1),
      }));
    }
  }, [isSignedIn, incrementAnonCount]);

  /** True when the anonymous limit has been hit (not yet signed in) */
  const needsSignup = !DEV_UNLIMITED && !isSignedIn && getAnonCount() >= ANON_LIMIT;

  /** True when a signed-in user has exhausted their plan quota */
  const needsUpgrade = !DEV_UNLIMITED && isSignedIn && authState.searchesRemaining === 0;

  return { authState, canSearch, recordSearch, needsSignup, needsUpgrade, getToken };
}

async function fetchUsage(
  getToken: (opts?: { template?: string }) => Promise<string | null>
): Promise<{ plan: string; searches_used: number; searches_limit: number; searches_remaining: number } | null> {
  try {
    const token = await getToken();
    // Clerk may return null while still initializing — skip the request to
    // avoid a guaranteed 401 with "Bearer null" in the Authorization header.
    if (!token) return null;
    const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
    const res = await fetch(`${apiUrl}/api/billing/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
