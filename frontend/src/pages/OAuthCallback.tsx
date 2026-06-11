import { useEffect, useState, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { getAuth } from 'firebase/auth';

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

/**
 * OAuth Callback Page
 *
 * This page handles the OAuth callback from providers (Google, Slack, Notion).
 * It forwards the authorization code to the backend to complete the OAuth flow.
 */
export default function OAuthCallback() {
  const { provider } = useParams<{ provider: string }>();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<'loading' | 'error'>('loading');
  const [errorMessage, setErrorMessage] = useState<string>('');

  // Prevent double execution from React StrictMode
  const hasStarted = useRef(false);

  useEffect(() => {
    // Prevent double execution
    if (hasStarted.current) return;
    hasStarted.current = true;

    const completeOAuth = async () => {
      const code = searchParams.get('code');
      const state = searchParams.get('state');
      const error = searchParams.get('error');

      // Check if we should return to setup flow or settings
      // Read BEFORE any async operations to prevent race conditions
      const returnPath = sessionStorage.getItem('herofy_oauth_return') || '/app/settings/account';
      console.log('[OAuthCallback] Return path from sessionStorage:', returnPath);
      // Clear the return path after reading
      sessionStorage.removeItem('herofy_oauth_return');

      // Handle OAuth errors from provider
      if (error) {
        setStatus('error');
        setErrorMessage(`Authorization denied: ${error}`);
        setTimeout(() => {
          window.location.href = `${returnPath}?error=${error}&provider=${provider}`;
        }, 2000);
        return;
      }

      if (!code || !state) {
        setStatus('error');
        setErrorMessage('Missing authorization code or state');
        setTimeout(() => {
          window.location.href = `${returnPath}?error=missing_params&provider=${provider}`;
        }, 2000);
        return;
      }

      try {
        // Get Firebase token for authentication
        const auth = getAuth();
        const user = auth.currentUser;

        const headers: Record<string, string> = {};
        if (user) {
          const token = await user.getIdToken();
          headers['Authorization'] = `Bearer ${token}`;
        }

        // Forward to backend callback endpoint
        // Use manual redirect to properly handle the response
        const callbackUrl = `${PYTHON_URL}/integrations/${provider}/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`;

        const response = await fetch(callbackUrl, {
          method: 'GET',
          headers,
          redirect: 'manual', // Don't follow redirects, handle them ourselves
        });

        // Backend returns 302 redirect on success (Location unreadable due to CORS), or 200.
        const succeeded =
          response.type === 'opaqueredirect' ||
          response.status === 302 ||
          response.status === 0 ||
          response.ok;
        if (!succeeded) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data.detail || 'OAuth callback failed');
        }

        // Connecting Notion (REST/CRM) must also connect Notion's hosted MCP server, which is a
        // SEPARATE OAuth flow (different authorization server + PKCE). Chain straight into it so a
        // single "Connect Notion" authorizes both. If the MCP hop can't even start, the REST
        // connection still stands — we fall through to the return path and the settings card shows
        // MCP as "not connected" with a manual Enable action.
        if (provider === 'notion' && user) {
          try {
            const wsId =
              localStorage.getItem(`herofy_workspace_id_${user.uid}`) ||
              '11111111-1111-1111-1111-111111111111';
            const token = await user.getIdToken();
            const urlResp = await fetch(
              `${PYTHON_URL}/integrations/notion_mcp/auth/url?workspace_id=${encodeURIComponent(wsId)}`,
              { headers: { Authorization: `Bearer ${token}` } },
            );
            if (urlResp.ok) {
              const { authorization_url: mcpUrl } = await urlResp.json();
              if (mcpUrl) {
                // Preserve the return path for the MCP callback (the second hop).
                sessionStorage.setItem('herofy_oauth_return', returnPath);
                console.log('[OAuthCallback] Notion REST connected; chaining into Notion MCP');
                window.location.href = mcpUrl;
                return;
              }
            }
            console.warn('[OAuthCallback] Notion MCP auth/url unavailable; REST connected, MCP skipped');
          } catch (mcpErr) {
            console.warn('[OAuthCallback] Notion MCP chain failed; REST connected, MCP skipped', mcpErr);
          }
        }

        console.log('[OAuthCallback] Redirecting to:', `${returnPath}?success=true&provider=${provider}`);
        window.location.href = `${returnPath}?success=true&provider=${provider}`;
      } catch (err) {
        console.error('OAuth callback error:', err);
        setStatus('error');
        setErrorMessage(err instanceof Error ? err.message : 'Failed to complete authorization');
        setTimeout(() => {
          window.location.href = `${returnPath}?error=oauth_failed&provider=${provider}`;
        }, 2000);
      }
    };

    completeOAuth();
  }, [provider, searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-charcoal-900">
      <div className="text-center">
        {status === 'loading' ? (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-rust-500 mx-auto mb-4"></div>
            <h1 className="text-xl font-semibold text-cream-100 mb-2">
              Connecting {provider}...
            </h1>
            <p className="text-cream-400">
              Please wait while we complete the authorization.
            </p>
          </>
        ) : (
          <>
            <div className="w-12 h-12 rounded-full bg-rust-500/20 flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-rust-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1 className="text-xl font-semibold text-cream-100 mb-2">
              Connection Failed
            </h1>
            <p className="text-cream-400 mb-4">
              {errorMessage}
            </p>
            <p className="text-cream-500 text-sm">
              Redirecting...
            </p>
          </>
        )}
      </div>
    </div>
  );
}
