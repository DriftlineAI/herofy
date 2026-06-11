/**
 * Demo-mode detection. The per-visitor anonymous sandbox only runs on the demo host
 * (demo.herofy.ai). Set VITE_DEMO_ENABLED=true to force it on for local testing.
 */
export const DEMO_HOST = 'demo.herofy.ai';

export function isDemoHost(): boolean {
  if (typeof window === 'undefined') return false;
  return window.location.hostname === DEMO_HOST || import.meta.env.VITE_DEMO_ENABLED === 'true';
}
