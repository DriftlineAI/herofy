import { getAuth } from 'firebase/auth';

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

/**
 * Sync the signed-in user's workspace-membership custom claims (`ws`) on the backend, then
 * force-refresh the ID token so the new claim is visible to Firestore security rules
 * (tenant isolation on notifications/setup_progress). Best-effort and idempotent — safe to call
 * after provisioning, after joining a workspace, or on login when the claim is missing.
 */
export async function syncWorkspaceClaims(): Promise<void> {
  const user = getAuth().currentUser;
  if (!user) return;
  try {
    const token = await user.getIdToken();
    const res = await fetch(`${PYTHON_URL}/api/auth/sync-claims`, {
      method: 'POST',
      // Hosting's Cloud Run rewrite replaces Authorization, so duplicate the token in the
      // fallback header the backend also accepts (see middleware/auth.py get_current_user).
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Firebase-ID-Token': token,
        'Content-Type': 'application/json',
      },
    });
    if (!res.ok) {
      console.warn('[claims] sync-claims failed:', res.status);
      return;
    }
    // Force a token refresh so the freshly-written `ws` claim lands in the token Firestore sees.
    await user.getIdToken(true);
  } catch (err) {
    console.warn('[claims] sync-claims error:', err);
  }
}

/** Does the current token already carry a `ws` membership claim? (skip a redundant sync if so) */
export async function hasWorkspaceClaim(): Promise<boolean> {
  const user = getAuth().currentUser;
  if (!user) return false;
  try {
    const res = await user.getIdTokenResult();
    return Array.isArray((res.claims as Record<string, unknown>).ws);
  } catch {
    return false;
  }
}
