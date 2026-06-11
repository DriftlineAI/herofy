import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { Users, AlertCircle, CheckCircle2, Clock, ArrowRight, LogIn } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth';
import { useWorkspace } from '@/lib/workspace';

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

interface InvitationDetails {
  workspace_name: string;
  role: string;
  invited_by_name: string | null;
  invited_by_email: string;
  email: string;
  expires_at: string;
  is_expired: boolean;
  status: string;
}

interface AcceptResult {
  workspace_id: string;
  workspace_slug: string;
  workspace_name: string;
  role: string;
}

// Role badge component
function RoleBadge({ role }: { role: string }) {
  const roleStyles: Record<string, string> = {
    owner: 'bg-rust-500/20 text-rust-400 border-rust-500/30',
    admin: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    member: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  };

  const roleLabels: Record<string, string> = {
    owner: 'Owner',
    admin: 'Admin',
    member: 'Member',
  };

  return (
    <span className={cn(
      'text-xs font-mono uppercase tracking-wider px-2 py-1 rounded border',
      roleStyles[role] || roleStyles.member
    )}>
      {roleLabels[role] || role}
    </span>
  );
}

export default function InviteAccept() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const { setWorkspaceId } = useWorkspace();

  const [invitation, setInvitation] = useState<InvitationDetails | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAccepting, setIsAccepting] = useState(false);
  const [acceptSuccess, setAcceptSuccess] = useState(false);
  const [acceptResult, setAcceptResult] = useState<AcceptResult | null>(null);

  // Fetch invitation details
  useEffect(() => {
    async function fetchInvitation() {
      if (!token) {
        setError('Invalid invitation link');
        setIsLoading(false);
        return;
      }

      try {
        const response = await fetch(`${PYTHON_URL}/api/invitations/${token}`);
        if (!response.ok) {
          const errData = await response.json().catch(() => ({ detail: 'Invitation not found' }));
          throw new Error(errData.detail || 'Failed to load invitation');
        }
        const data = await response.json();
        setInvitation(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load invitation');
      } finally {
        setIsLoading(false);
      }
    }

    fetchInvitation();
  }, [token]);

  // Accept the invitation
  async function handleAccept() {
    if (!token || !user) return;

    setIsAccepting(true);
    setError(null);

    try {
      const idToken = await user.getIdToken();
      const response = await fetch(`${PYTHON_URL}/api/invitations/${token}/accept`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${idToken}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: 'Failed to accept invitation' }));
        throw new Error(errData.detail || 'Failed to accept invitation');
      }

      const result: AcceptResult = await response.json();
      setAcceptResult(result);
      setAcceptSuccess(true);

      // Set the workspace context
      setWorkspaceId(result.workspace_id);

      // Redirect to app after a short delay
      setTimeout(() => {
        navigate('/app');
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept invitation');
    } finally {
      setIsAccepting(false);
    }
  }

  // Loading state
  if (isLoading || authLoading) {
    return (
      <div className="min-h-screen bg-charcoal-900 flex items-center justify-center">
        <div className="animate-pulse text-fg-400">Loading invitation...</div>
      </div>
    );
  }

  // Error state
  if (error && !invitation) {
    return (
      <div className="min-h-screen bg-charcoal-900 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-8 max-w-md w-full text-center"
        >
          <div className="w-12 h-12 rounded-full bg-rust-500/20 flex items-center justify-center mx-auto mb-4">
            <AlertCircle className="w-6 h-6 text-rust-400" />
          </div>
          <h1 className="text-xl font-bold text-fg-100 mb-2">Invalid Invitation</h1>
          <p className="text-fg-400 mb-6">{error}</p>
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-4 py-2 bg-charcoal-700 hover:bg-charcoal-600 text-fg-200 rounded transition-colors"
          >
            Go to Home
          </Link>
        </motion.div>
      </div>
    );
  }

  // Expired invitation
  if (invitation?.is_expired) {
    return (
      <div className="min-h-screen bg-charcoal-900 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-8 max-w-md w-full text-center"
        >
          <div className="w-12 h-12 rounded-full bg-amber-500/20 flex items-center justify-center mx-auto mb-4">
            <Clock className="w-6 h-6 text-amber-400" />
          </div>
          <h1 className="text-xl font-bold text-fg-100 mb-2">Invitation Expired</h1>
          <p className="text-fg-400 mb-6">
            This invitation has expired. Ask your admin to send a new one.
          </p>
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-4 py-2 bg-charcoal-700 hover:bg-charcoal-600 text-fg-200 rounded transition-colors"
          >
            Go to Home
          </Link>
        </motion.div>
      </div>
    );
  }

  // Success state
  if (acceptSuccess && acceptResult) {
    return (
      <div className="min-h-screen bg-charcoal-900 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="bg-charcoal-800 border border-emerald-500/30 rounded-lg p-8 max-w-md w-full text-center"
        >
          <div className="w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center mx-auto mb-4">
            <CheckCircle2 className="w-6 h-6 text-emerald-400" />
          </div>
          <h1 className="text-xl font-bold text-fg-100 mb-2">Welcome to {acceptResult.workspace_name}!</h1>
          <p className="text-fg-400 mb-4">
            You've joined as {acceptResult.role === 'admin' ? 'an' : 'a'} <RoleBadge role={acceptResult.role} />
          </p>
          <p className="text-fg-500 text-sm">Redirecting to your workspace...</p>
        </motion.div>
      </div>
    );
  }

  // Not logged in - show login prompt
  if (!user) {
    const redirectUrl = encodeURIComponent(`/invite/${token}`);
    return (
      <div className="min-h-screen bg-charcoal-900 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-8 max-w-md w-full"
        >
          <div className="text-center mb-6">
            <div className="w-12 h-12 rounded-full bg-rust-500/20 flex items-center justify-center mx-auto mb-4">
              <Users className="w-6 h-6 text-rust-400" />
            </div>
            <h1 className="text-xl font-bold text-fg-100 mb-2">Join {invitation?.workspace_name}</h1>
            <p className="text-fg-400">
              {invitation?.invited_by_name || invitation?.invited_by_email} invited you to join as{' '}
              {invitation?.role === 'admin' ? 'an' : 'a'} <RoleBadge role={invitation?.role || 'member'} />
            </p>
          </div>

          <div className="bg-charcoal-900/50 border border-charcoal-700 rounded-lg p-4 mb-6">
            <p className="text-sm text-fg-400 mb-1">Invitation sent to:</p>
            <p className="text-fg-200 font-mono text-sm">{invitation?.email}</p>
          </div>

          <div className="space-y-3">
            <Link
              to={`/login?redirect=${redirectUrl}`}
              className="flex items-center justify-center gap-2 w-full px-4 py-3 bg-rust-500 hover:bg-rust-600 text-white font-medium rounded transition-colors"
            >
              <LogIn className="w-4 h-4" />
              Sign in to Accept
            </Link>
            <p className="text-center text-fg-500 text-xs">
              Don't have an account?{' '}
              <Link to={`/login?redirect=${redirectUrl}`} className="text-rust-400 hover:text-rust-300">
                Sign up
              </Link>
            </p>
          </div>
        </motion.div>
      </div>
    );
  }

  // Logged in - show accept confirmation
  return (
    <div className="min-h-screen bg-charcoal-900 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-charcoal-800 border border-charcoal-700 rounded-lg p-8 max-w-md w-full"
      >
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-full bg-rust-500/20 flex items-center justify-center mx-auto mb-4">
            <Users className="w-6 h-6 text-rust-400" />
          </div>
          <h1 className="text-xl font-bold text-fg-100 mb-2">Join {invitation?.workspace_name}</h1>
          <p className="text-fg-400">
            {invitation?.invited_by_name || invitation?.invited_by_email} invited you to join as{' '}
            {invitation?.role === 'admin' ? 'an' : 'a'} <RoleBadge role={invitation?.role || 'member'} />
          </p>
        </div>

        <div className="bg-charcoal-900/50 border border-charcoal-700 rounded-lg p-4 mb-6 space-y-3">
          <div>
            <p className="text-xs text-fg-500 mb-0.5">Logged in as</p>
            <p className="text-fg-200 font-mono text-sm">{user.email}</p>
          </div>
          {invitation?.email !== user.email && (
            <div className="pt-2 border-t border-charcoal-700">
              <p className="text-xs text-amber-400 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                Note: Invitation was sent to {invitation?.email}
              </p>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-4 p-3 bg-rust-500/10 border border-rust-500/30 rounded text-rust-400 text-sm">
            {error}
          </div>
        )}

        <div className="space-y-3">
          <button
            onClick={handleAccept}
            disabled={isAccepting}
            className={cn(
              'flex items-center justify-center gap-2 w-full px-4 py-3 font-medium rounded transition-colors',
              isAccepting
                ? 'bg-charcoal-700 text-fg-500 cursor-not-allowed'
                : 'bg-rust-500 hover:bg-rust-600 text-white cursor-pointer'
            )}
          >
            {isAccepting ? (
              <>
                <div className="w-4 h-4 border-2 border-fg-500 border-t-transparent rounded-full animate-spin" />
                Accepting...
              </>
            ) : (
              <>
                Accept Invitation
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
          <Link
            to="/"
            className="flex items-center justify-center w-full px-4 py-2 text-fg-400 hover:text-fg-200 text-sm transition-colors"
          >
            Cancel
          </Link>
        </div>
      </motion.div>
    </div>
  );
}
