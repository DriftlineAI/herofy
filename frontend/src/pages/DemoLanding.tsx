import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { signInAnon } from '@/lib/firebase';
import { syncWorkspaceClaims } from '@/lib/claims';
import { isDemoHost } from '@/lib/demo';
import { useWorkspace } from '@/lib/workspace';

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

/**
 * `/demo` — the anonymous-sandbox entry point. Signs the visitor in anonymously, asks the backend
 * to provision + seed an isolated `demo-*` workspace, mints their `ws` claim, then drops them into
 * the live app. Only runs on the demo host (see isDemoHost); bounces elsewhere.
 */
export default function DemoLanding() {
  const navigate = useNavigate();
  const { setWorkspaceId } = useWorkspace();
  const [status, setStatus] = useState('Spinning up your demo…');
  const [failed, setFailed] = useState(false);
  const ranRef = useRef(false);

  useEffect(() => {
    if (!isDemoHost()) {
      window.location.href = '/';
      return;
    }
    if (ranRef.current) return; // StrictMode double-invoke guard
    ranRef.current = true;

    (async () => {
      try {
        setStatus('Signing you in…');
        const cred = await signInAnon();
        setStatus('Building your demo workspace…');
        const token = await cred.user.getIdToken();
        const res = await fetch(`${PYTHON_URL}/demo/provision`, {
          method: 'POST',
          // Hosting's Cloud Run rewrite replaces Authorization, so duplicate the token in the
          // fallback header the backend also accepts (see middleware/auth.py get_current_user).
          headers: {
            Authorization: `Bearer ${token}`,
            'X-Firebase-ID-Token': token,
            'Content-Type': 'application/json',
          },
        });
        if (!res.ok) throw new Error(`provision failed: ${res.status}`);
        const data = await res.json();
        setStatus('Loading your customers…');
        // Mint the `ws` claim (Firestore tenant isolation) + force-refresh the token so it lands.
        await syncWorkspaceClaims();
        setWorkspaceId(data.workspace_id);
        navigate('/app', { replace: true });
      } catch (err) {
        console.error('[demo] provisioning failed', err);
        setFailed(true);
        setStatus('Could not start the demo. Please refresh to try again.');
      }
    })();
  }, [navigate, setWorkspaceId]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-charcoal-900">
      <div className="text-center max-w-md px-6">
        {!failed && (
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-rust-500 mx-auto mb-4" />
        )}
        <p className="text-cream-400 font-mono uppercase tracking-widest text-sm">{status}</p>
      </div>
    </div>
  );
}
