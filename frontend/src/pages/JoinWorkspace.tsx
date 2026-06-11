import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, ArrowRight, Loader2, CheckCircle } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { getEmailDomain } from '@/lib/validation';
import { useGetWorkspaceByDomain, useGetMyJoinRequest, useCreateJoinRequest } from '@/dataconnect-generated/react';

interface WorkspaceInfo {
  id: string;
  name: string;
  memberCount: number;
}

export default function JoinWorkspace() {
  const { user, completeSetup, signOut } = useAuth();
  const navigate = useNavigate();
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null);
  const [requestStatus, setRequestStatus] = useState<'idle' | 'requesting' | 'sent' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);

  const userDomain = user?.email ? getEmailDomain(user.email) : null;

  // Query for existing workspace by domain (DataConnect)
  const { data: workspaceData, isLoading } = useGetWorkspaceByDomain(
    { domain: userDomain || '' },
    { enabled: !!userDomain }
  );

  // Check for existing join request
  const { data: joinRequestData } = useGetMyJoinRequest(
    { workspaceId: workspace?.id || '' },
    { enabled: !!workspace?.id }
  );

  // Mutation for creating join request
  const createJoinRequest = useCreateJoinRequest();

  const existingRequest = joinRequestData?.workspaceJoinRequests?.[0];
  const hasPendingRequest = existingRequest?.status === 'pending';

  // Process workspace data when it loads
  useEffect(() => {
    if (isLoading || !userDomain) return;

    // Check if we've already processed a redirect check in this session
    const redirectCheckKey = `herofy_redirect_check_${user?.uid}`;
    const hasProcessedCheck = sessionStorage.getItem(redirectCheckKey);

    if (hasProcessedCheck) {
      // Already checked, but we're on /join so show the join screen if workspace exists
      const workspaceResult = workspaceData?.workspaces?.[0];
      if (workspaceResult) {
        const members = workspaceResult.workspaceMembers_on_workspace || [];
        setWorkspace({
          id: workspaceResult.id,
          name: workspaceResult.name,
          memberCount: members.length,
        });
      }
      return;
    }

    const workspaceResult = workspaceData?.workspaces?.[0];

    if (!workspaceResult) {
      // No workspace found for domain, redirect to setup to create one
      console.log('No workspace found, redirecting to /setup');
      sessionStorage.setItem(redirectCheckKey, 'true');
      navigate('/setup');
      return;
    }

    const members = workspaceResult.workspaceMembers_on_workspace || [];
    const currentMembership = members.find(m => m.user.id === user?.uid);
    const isCurrentUserMember = !!currentMembership;
    // Check per-user hasCompletedSetup, not workspace-level setupCompleted
    const userHasCompletedSetup = currentMembership?.hasCompletedSetup || false;

    console.log('Join page - workspace check:', {
      workspace_id: workspaceResult.id,
      is_member: isCurrentUserMember,
      user_has_completed_setup: userHasCompletedSetup,
      workspace_setup_completed: workspaceResult.setupCompleted,
    });

    // Mark as processed
    sessionStorage.setItem(redirectCheckKey, 'true');

    // If user is already a member AND has completed setup, go to app
    if (isCurrentUserMember && userHasCompletedSetup) {
      console.log('User is member with completed setup, redirecting to /app');
      completeSetup().then(() => {
        navigate('/app');
      });
      return;
    }

    // If user is a member but hasn't completed setup, go to setup wizard
    if (isCurrentUserMember && !userHasCompletedSetup) {
      console.log('User is member but setup incomplete, redirecting to /setup');
      navigate('/setup');
      return;
    }

    // User is not a member, show join screen
    setWorkspace({
      id: workspaceResult.id,
      name: workspaceResult.name,
      memberCount: members.length,
    });
  }, [workspaceData, isLoading, userDomain, user?.uid, navigate, completeSetup]);

  // If there's already a pending request, show it immediately
  useEffect(() => {
    if (hasPendingRequest) {
      console.log('✅ Existing pending join request found:', {
        request_id: existingRequest?.id,
        status: existingRequest?.status,
        created_at: existingRequest?.createdAt,
      });
      setRequestStatus('sent');
    }
  }, [hasPendingRequest, existingRequest]);

  const handleRequestJoin = async () => {
    if (!workspace || !user) return;

    setRequestStatus('requesting');
    setError(null);

    try {
      await createJoinRequest.mutateAsync({
        workspaceId: workspace.id,
        userId: user.uid,
        userEmail: user.email || '',
      });

      setRequestStatus('sent');
    } catch (err) {
      console.error('Failed to send join request:', err);
      setError(err instanceof Error ? err.message : 'Failed to send join request');
      setRequestStatus('error');
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-charcoal-800 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-8 h-8 text-rust-500 animate-spin mx-auto mb-4" />
          <p className="text-cream-400">Loading workspace information...</p>
        </div>
      </div>
    );
  }

  if (!workspace) {
    return (
      <div className="min-h-screen bg-charcoal-800 flex items-center justify-center">
        <div className="text-center max-w-md">
          <p className="text-cream-400 mb-4">No workspace found for your domain.</p>
          <button
            onClick={() => navigate('/setup')}
            className="text-rust-500 hover:text-rust-400 transition-colors"
          >
            Create a new workspace →
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-charcoal-800 flex items-center justify-center p-6">
      <div className="max-w-lg w-full">
        {requestStatus === 'sent' ? (
          // Request sent confirmation
          <div className="text-center">
            <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
              <CheckCircle className="w-8 h-8 text-emerald-500" />
            </div>
            <h1 className="font-serif text-3xl text-cream-100 mb-4">Request Sent</h1>
            <p className="text-cream-400 mb-6">
              We've notified the workspace admin at{' '}
              <span className="text-cream-200">{workspace.name}</span>.
              You'll receive an email when your request is approved.
            </p>
            <div className="space-y-2">
              <p className="text-xs text-charcoal-500">
                You can close this page. We'll email you when you're approved!
              </p>
              <button
                onClick={async () => {
                  await signOut();
                  navigate('/login');
                }}
                className="text-xs text-charcoal-400 hover:text-cream-100 transition-colors"
              >
                Sign out and log in as different user
              </button>
            </div>
          </div>
        ) : (
          // Request to join screen
          <>
            {/* Header */}
            <div className="mb-8">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 bg-rust-500/20 rounded-lg flex items-center justify-center">
                  <Building2 className="w-5 h-5 text-rust-500" />
                </div>
                <h1 className="font-serif text-3xl text-cream-100">Your team is already here</h1>
              </div>
              <p className="text-cream-400 text-lg">
                We found an existing workspace for{' '}
                <span className="text-cream-200">@{userDomain}</span>
              </p>
            </div>

            {/* Workspace Card */}
            <div className="border border-rust-500/30 bg-rust-500/5 p-6 mb-6">
              <div className="flex items-start gap-4">
                <div className="w-12 h-12 bg-charcoal-700 rounded-lg flex items-center justify-center">
                  <Building2 className="w-6 h-6 text-cream-300" />
                </div>
                <div className="flex-1">
                  <div className="font-medium text-cream-100 text-lg mb-1">
                    {workspace.name}
                  </div>
                  <div className="text-sm text-charcoal-400">
                    {workspace.memberCount} team member{workspace.memberCount !== 1 ? 's' : ''}
                  </div>
                </div>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}

            {/* Action */}
            <button
              onClick={handleRequestJoin}
              disabled={requestStatus === 'requesting'}
              className="w-full flex items-center justify-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-4 hover:bg-rust-400 transition-colors font-bold disabled:opacity-50"
            >
              {requestStatus === 'requesting' ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Sending Request...
                </>
              ) : (
                <>
                  Request to Join
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>

            <div className="mt-6 text-center space-y-2">
              <p className="text-xs text-charcoal-500">
                Your request will be sent to the workspace owner for approval.
              </p>
              <button
                onClick={async () => {
                  await signOut();
                  navigate('/login');
                }}
                className="text-xs text-charcoal-400 hover:text-cream-100 transition-colors"
              >
                Sign out and log in as different user
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
