import { useCallback, useState } from 'react';
import { useAuth as useClerkAuth } from '@clerk/clerk-react';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export function useBilling() {
  const { getToken } = useClerkAuth();
  const [isRedirecting, setIsRedirecting] = useState(false);

  const startCheckout = useCallback(async (plan: 'explorer' | 'unlimited') => {
    setIsRedirecting(true);
    try {
      const token = await getToken();
      const res = await fetch(`${API_URL}/api/billing/checkout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ plan }),
      });
      if (!res.ok) throw new Error('Failed to create checkout session');
      const { url } = await res.json();
      window.location.href = url;
    } catch (err) {
      console.error('Checkout error:', err);
      setIsRedirecting(false);
    }
  }, [getToken]);

  const openBillingPortal = useCallback(async () => {
    setIsRedirecting(true);
    try {
      const token = await getToken();
      const res = await fetch(`${API_URL}/api/billing/portal`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to open billing portal');
      const { url } = await res.json();
      window.location.href = url;
    } catch (err) {
      console.error('Portal error:', err);
      setIsRedirecting(false);
    }
  }, [getToken]);

  return { startCheckout, openBillingPortal, isRedirecting };
}
