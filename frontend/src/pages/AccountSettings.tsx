import React from 'react';
import { motion } from 'motion/react';
import { ArrowLeft, Save, RefreshCw, Users, Zap, CreditCard, Check, Link2, ExternalLink, AlertCircle, CheckCircle2, UserPlus, X, Clock, Mail, Copy, Trash2, Edit2 } from 'lucide-react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth';
import { useWorkspace } from '@/lib/workspace';
import { getAuth } from 'firebase/auth';
import {
  useIntegrations,
  useConnectIntegration,
  useDisconnectIntegration,
  usePendingJoinRequests,
  useTeamMembers,
  useApproveJoinRequest,
  useRejectJoinRequest,
  type JoinRequest,
} from '@/lib/dataconnect-hooks';
import type { AutonomyLevel, WorkspaceRole, IntegrationType, Integration } from '@/lib/api';
import NotionConfigModal from '@/components/NotionConfigModal';

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

// Types for invitation management
interface PendingInvitation {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  created_at: string;
  invited_by_name: string | null;
  invited_by_email: string;
}

interface InviteMemberResponse {
  invitation_id: string;
  invite_link: string;
  email: string;
  role: string;
  expires_at: string;
}

// Autonomy level descriptions
const AUTONOMY_OPTIONS: {
  value: AutonomyLevel;
  label: string;
  description: string;
  recommended?: boolean;
}[] = [
  {
    value: 'full_auto',
    label: 'Full Auto',
    description: 'Agents never pause, always produce best-effort output',
  },
  {
    value: 'smart_auto',
    label: 'Smart Auto',
    description: 'Pause only when confidence is low',
    recommended: true,
  },
  {
    value: 'supervised',
    label: 'Supervised',
    description: 'Always pause for human review',
  },
];

// Role badge component - updated for new role names (owner/admin/member)
function RoleBadge({ role }: { role: WorkspaceRole | string }) {
  const roleStyles: Record<string, string> = {
    owner: 'bg-accent/20 text-accent border-accent/30',
    admin: 'bg-signal-warn/20 text-signal-warn border-signal-warn/30',
    member: 'bg-signal-ok/20 text-signal-ok border-signal-ok/30',
    // Legacy role mappings for backwards compatibility
    csm: 'bg-signal-warn/20 text-signal-warn border-signal-warn/30',
    viewer: 'bg-signal-ok/20 text-signal-ok border-signal-ok/30',
  };

  const roleLabels: Record<string, string> = {
    owner: 'Owner',
    admin: 'Admin',
    member: 'Member',
    // Legacy role mappings
    csm: 'Admin',
    viewer: 'Member',
  };

  return (
    <span className={cn(
      'text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded border',
      roleStyles[role] || roleStyles.member
    )}>
      {roleLabels[role] || role}
    </span>
  );
}

// Generate DiceBear avatar URL
function getAvatarUrl(seed: string): string {
  return `https://api.dicebear.com/7.x/adventurer/svg?seed=${encodeURIComponent(seed)}`;
}

// Integration configuration
const INTEGRATIONS: {
  type: IntegrationType;
  name: string;
  description: string;
  icon: React.ReactNode;
}[] = [
  {
    type: 'gmail',
    name: 'Gmail & Calendar',
    description: 'One connection covers both Gmail and Google Calendar, so Herofy can follow customer email threads and the meetings tied to them. This is how we surface what needs a reply and prep you for upcoming calls.',
    icon: (
      <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457z"/>
      </svg>
    ),
  },
  {
    type: 'slack',
    name: 'Slack',
    description: 'Herofy watches the channels and DMs you share with customers to catch requests and risk signals early. You choose which conversations to connect — internal channels stay private.',
    icon: (
      <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"/>
      </svg>
    ),
  },
  {
    type: 'notion',
    name: 'Notion (CRM)',
    description: 'Herofy uses your Notion workspace as the CRM — it\'s where customer accounts, handoff docs, and onboarding trackers live. Connecting it lets us read those records and keep customer context in sync.',
    icon: (
      <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 1.968c-.42-.326-.98-.7-2.055-.607L3.01 2.295c-.466.046-.56.28-.374.466zm.793 3.08v13.904c0 .747.373 1.027 1.214.98l14.523-.84c.841-.046.935-.56.935-1.167V6.354c0-.606-.233-.933-.748-.887l-15.177.887c-.56.047-.747.327-.747.933zm14.337.745c.093.42 0 .84-.42.888l-.7.14v10.264c-.608.327-1.168.514-1.635.514-.748 0-.935-.234-1.495-.933l-4.577-7.186v6.952l1.448.327s0 .84-1.168.84l-3.22.186c-.094-.187 0-.653.327-.746l.84-.233V9.854L7.822 9.76c-.094-.42.14-1.026.793-1.073l3.456-.233 4.764 7.279v-6.44l-1.215-.14c-.093-.514.28-.887.747-.933zM1.936 1.035l13.31-.98c1.634-.14 2.055-.047 3.082.7l4.249 2.986c.7.513.933.653.933 1.213v16.378c0 1.026-.373 1.634-1.68 1.726l-15.458.934c-.98.047-1.448-.093-1.962-.747l-3.129-4.06c-.56-.747-.793-1.306-.793-1.96V2.667c0-.839.374-1.54 1.448-1.632z"/>
      </svg>
    ),
  },
];

// Integration card component
function IntegrationCard({
  config,
  integration,
  onConnect,
  onDisconnect,
  onConfigure,
  isConnecting,
  isDisconnecting,
  secondary,
}: {
  config: typeof INTEGRATIONS[number];
  integration: Integration | undefined;
  onConnect: () => void;
  onDisconnect: () => void;
  onConfigure?: () => void;
  isConnecting: boolean;
  isDisconnecting: boolean;
  // Optional companion integration shown as a sub-status on the same card (e.g. Notion's
  // hosted MCP "AI deep-access", which is a separate OAuth connection from the REST/CRM one).
  secondary?: {
    label: string;
    integration: Integration | undefined;
    onConnect: () => void;
    isConnecting: boolean;
  };
}) {
  const isConnected = integration?.connected ?? false;
  const hasError = integration?.status === 'error';
  const isPending = isConnecting || isDisconnecting;
  const isConfigured = integration?.config && Object.keys(integration.config).length > 0;

  return (
    <div className={cn(
      'p-4 rounded-lg border transition-all',
      isConnected
        ? hasError
          ? 'bg-signal-bad/5 border-signal-bad/30'
          : 'bg-signal-ok/5 border-signal-ok/30'
        : 'bg-page/50 border-border hover:border-border-strong'
    )}>
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div className={cn(
            'p-2 rounded-lg',
            isConnected
              ? hasError
                ? 'bg-signal-bad/20 text-signal-bad'
                : 'bg-signal-ok/20 text-signal-ok'
              : 'bg-border text-fg-300'
          )}>
            {config.icon}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium text-fg-100">{config.name}</span>
              {isConnected && (
                hasError ? (
                  <span className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-signal-bad/20 text-signal-bad rounded">
                    <AlertCircle className="w-3 h-3" />
                    Error
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-signal-ok/20 text-signal-ok rounded">
                    <CheckCircle2 className="w-3 h-3" />
                    Connected
                  </span>
                )
              )}
              {isConnected && !isConfigured && onConfigure && (
                <span className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-signal-warn/20 text-signal-warn rounded">
                  Not configured
                </span>
              )}
            </div>
            <p className="text-sm text-fg-400 mt-0.5">{config.description}</p>
            {isConnected && integration?.last_sync_at && (
              <p className="text-xs text-fg-500 mt-1">
                Last synced: {new Date(integration.last_sync_at).toLocaleString()}
              </p>
            )}
            {hasError && integration?.last_error && (
              <p className="text-xs text-signal-bad mt-1">
                {integration.last_error}
              </p>
            )}
            {secondary && isConnected && (() => {
              const secConnected = secondary.integration?.connected ?? false;
              const secError = secondary.integration?.status === 'error';
              return (
                <div className="mt-2 flex items-center gap-2">
                  <span className={cn(
                    'w-1.5 h-1.5 rounded-full shrink-0',
                    secConnected ? (secError ? 'bg-signal-bad' : 'bg-signal-ok') : 'bg-fg-500'
                  )} />
                  <span className="text-xs text-fg-400">
                    {secondary.label}:{' '}
                    <span className={cn(
                      'font-medium',
                      secConnected ? (secError ? 'text-signal-bad' : 'text-signal-ok') : 'text-fg-500'
                    )}>
                      {secConnected ? (secError ? 'Error' : 'Connected') : 'Not connected'}
                    </span>
                  </span>
                  {!secConnected && (
                    <button
                      onClick={secondary.onConnect}
                      disabled={secondary.isConnecting}
                      className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border border-border-strong text-fg-300 hover:border-accent hover:text-accent transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {secondary.isConnecting ? 'Connecting…' : 'Enable'}
                    </button>
                  )}
                </div>
              );
            })()}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isConnected && onConfigure && (
            <button
              onClick={onConfigure}
              className="px-3 py-1.5 text-sm rounded border transition-colors cursor-pointer bg-transparent text-fg-300 border-border-strong hover:border-fg-400 hover:text-fg-200"
            >
              Configure
            </button>
          )}
          {isConnected ? (
            <button
              onClick={onDisconnect}
              disabled={isPending}
              className={cn(
                'px-3 py-1.5 text-sm rounded border transition-colors cursor-pointer',
                isPending
                  ? 'bg-border text-fg-400 border-border-strong cursor-not-allowed'
                  : 'bg-transparent text-fg-300 border-border-strong hover:border-signal-bad hover:text-signal-bad'
              )}
            >
              {isDisconnecting ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                'Disconnect'
              )}
            </button>
          ) : (
            <button
              onClick={onConnect}
              disabled={isPending}
              className={cn(
                'px-3 py-1.5 text-sm rounded transition-colors cursor-pointer flex items-center gap-1.5',
                isPending
                  ? 'bg-border text-fg-400 cursor-not-allowed'
                  : 'bg-accent hover:bg-accent-hover text-page'
              )}
            >
              {isConnecting ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <ExternalLink className="w-4 h-4" />
                  Connect
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Get workspace data from localStorage (saved when onboarding completes)
function getSavedWorkspaceData(): { name: string; valueProp?: string; importSource?: string; integrations?: Record<string, boolean> } {
  try {
    const saved = localStorage.getItem('herofy_workspace_data');
    if (saved) {
      return JSON.parse(saved);
    }
  } catch {}
  return { name: '' };
}

export default function AccountSettings() {
  const { user: firebaseUser, isStaff, hasCompletedSetup, loading } = useAuth();
  const { workspaceId } = useWorkspace();
  const [searchParams, setSearchParams] = useSearchParams();

  const [workspaceName, setWorkspaceName] = React.useState('');
  const [valueProp, setValueProp] = React.useState('');
  const [autonomyLevel, setAutonomyLevel] = React.useState<AutonomyLevel>('smart_auto');
  const [hasChanges, setHasChanges] = React.useState(false);
  const [isSaving, setIsSaving] = React.useState(false);
  const [saveSuccess, setSaveSuccess] = React.useState(false);
  const [saveError, setSaveError] = React.useState(false);

  // Original values for change detection
  const [originalName, setOriginalName] = React.useState('');
  const [originalValueProp, setOriginalValueProp] = React.useState('');
  const [originalAutonomy, setOriginalAutonomy] = React.useState<AutonomyLevel>('smart_auto');

  // Integrations
  const { data: integrations, isLoading: integrationsLoading, refetch: refetchIntegrations } = useIntegrations();
  const { connect, isPending: isConnecting } = useConnectIntegration();
  const { disconnect, isPending: isDisconnecting } = useDisconnectIntegration();
  const [connectingProvider, setConnectingProvider] = React.useState<IntegrationType | null>(null);
  const [disconnectingProvider, setDisconnectingProvider] = React.useState<IntegrationType | null>(null);
  const [integrationMessage, setIntegrationMessage] = React.useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showNotionConfig, setShowNotionConfig] = React.useState(false);

  // Team management
  const { data: pendingRequests, isLoading: requestsLoading, refetch: refetchRequests } = usePendingJoinRequests();
  const { data: teamMembersData, isLoading: membersLoading, refetch: refetchMembers } = useTeamMembers();
  const teamMembers = teamMembersData?.members || [];
  const { approve: approveRequest, isPending: isApproving } = useApproveJoinRequest();
  const { reject: rejectRequest, isPending: isRejecting } = useRejectJoinRequest();
  const [processingRequestId, setProcessingRequestId] = React.useState<string | null>(null);
  const [teamMessage, setTeamMessage] = React.useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Invitation management
  const [pendingInvitations, setPendingInvitations] = React.useState<PendingInvitation[]>([]);
  const [invitationsLoading, setInvitationsLoading] = React.useState(false);
  const [inviteEmail, setInviteEmail] = React.useState('');
  const [inviteRole, setInviteRole] = React.useState<'admin' | 'member'>('member');
  const [isInviting, setIsInviting] = React.useState(false);
  const [lastInviteLink, setLastInviteLink] = React.useState<string | null>(null);
  const [copiedLink, setCopiedLink] = React.useState(false);
  const [removingMemberId, setRemovingMemberId] = React.useState<string | null>(null);
  const [changingRoleMemberId, setChangingRoleMemberId] = React.useState<string | null>(null);

  // Get current user's role
  const currentUserRole = React.useMemo(() => {
    const member = teamMembers.find(m => m.user_id === firebaseUser?.uid);
    return member?.role || 'member';
  }, [teamMembers, firebaseUser?.uid]);

  // Can the current user manage team (admin or owner)
  const canManageTeam = currentUserRole === 'owner' || currentUserRole === 'admin';

  // Fetch pending invitations
  const fetchInvitations = React.useCallback(async () => {
    if (!workspaceId || !canManageTeam) return;

    setInvitationsLoading(true);
    try {
      const auth = getAuth();
      const user = auth.currentUser;
      if (!user) return;

      const token = await user.getIdToken();
      const response = await fetch(`${PYTHON_URL}/api/workspaces/${workspaceId}/invitations`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setPendingInvitations(data);
      }
    } catch (err) {
      console.error('Failed to fetch invitations:', err);
    } finally {
      setInvitationsLoading(false);
    }
  }, [workspaceId, canManageTeam]);

  // Fetch invitations when workspace loads
  React.useEffect(() => {
    fetchInvitations();
  }, [fetchInvitations]);

  // Send invitation
  const handleInvite = async () => {
    if (!workspaceId || !inviteEmail.trim()) return;

    setIsInviting(true);
    setLastInviteLink(null);

    try {
      const auth = getAuth();
      const user = auth.currentUser;
      if (!user) throw new Error('Not authenticated');

      const token = await user.getIdToken();
      const response = await fetch(`${PYTHON_URL}/api/workspaces/${workspaceId}/invitations`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: inviteEmail.trim(), role: inviteRole }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Failed to send invitation' }));
        throw new Error(err.detail || 'Failed to send invitation');
      }

      const result: InviteMemberResponse = await response.json();
      setLastInviteLink(result.invite_link);
      setInviteEmail('');
      setTeamMessage({ type: 'success', text: `Invitation sent to ${result.email}` });
      fetchInvitations();
    } catch (err) {
      setTeamMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to send invitation' });
    } finally {
      setIsInviting(false);
    }
  };

  // Revoke invitation
  const handleRevokeInvitation = async (invitationId: string) => {
    if (!workspaceId) return;

    try {
      const auth = getAuth();
      const user = auth.currentUser;
      if (!user) throw new Error('Not authenticated');

      const token = await user.getIdToken();
      const response = await fetch(`${PYTHON_URL}/api/workspaces/${workspaceId}/invitations/${invitationId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (!response.ok) throw new Error('Failed to revoke invitation');

      setTeamMessage({ type: 'success', text: 'Invitation revoked' });
      fetchInvitations();
    } catch (err) {
      setTeamMessage({ type: 'error', text: 'Failed to revoke invitation' });
    }
  };

  // Remove member
  const handleRemoveMember = async (memberId: string) => {
    if (!workspaceId) return;

    setRemovingMemberId(memberId);
    try {
      const auth = getAuth();
      const user = auth.currentUser;
      if (!user) throw new Error('Not authenticated');

      const token = await user.getIdToken();
      const response = await fetch(`${PYTHON_URL}/api/workspaces/${workspaceId}/members/${memberId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Failed to remove member' }));
        throw new Error(err.detail || 'Failed to remove member');
      }

      setTeamMessage({ type: 'success', text: 'Member removed' });
      refetchMembers();
    } catch (err) {
      setTeamMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to remove member' });
    } finally {
      setRemovingMemberId(null);
    }
  };

  // Change member role
  const handleChangeRole = async (memberId: string, newRole: string) => {
    if (!workspaceId) return;

    setChangingRoleMemberId(memberId);
    try {
      const auth = getAuth();
      const user = auth.currentUser;
      if (!user) throw new Error('Not authenticated');

      const token = await user.getIdToken();
      const response = await fetch(`${PYTHON_URL}/api/workspaces/${workspaceId}/members/${memberId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ role: newRole }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Failed to change role' }));
        throw new Error(err.detail || 'Failed to change role');
      }

      setTeamMessage({ type: 'success', text: 'Role updated' });
      refetchMembers();
    } catch (err) {
      setTeamMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to change role' });
    } finally {
      setChangingRoleMemberId(null);
    }
  };

  // Copy invite link to clipboard
  const copyInviteLink = async () => {
    if (!lastInviteLink) return;
    try {
      await navigator.clipboard.writeText(lastInviteLink);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = lastInviteLink;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    }
  };

  // Handle OAuth callback params
  React.useEffect(() => {
    const success = searchParams.get('success');
    const error = searchParams.get('error');
    const provider = searchParams.get('provider');

    const providerLabels: Record<string, string> = {
      notion: 'Notion',
      notion_mcp: 'Notion AI access',
      gmail: 'Gmail & Calendar',
      slack: 'Slack',
    };
    if (success === 'true' && provider) {
      const label = providerLabels[provider] || provider;
      setIntegrationMessage({ type: 'success', text: `${label} connected successfully!` });
      refetchIntegrations();
      // Clear the params
      setSearchParams({});
    } else if (error && provider) {
      const label = providerLabels[provider] || provider;
      const errorMessages: Record<string, string> = {
        invalid_state: 'OAuth session expired. Please try again.',
        oauth_failed: 'Failed to connect. Please try again.',
        oauth_start_failed: 'Failed to start OAuth flow. Please try again.',
      };
      setIntegrationMessage({ type: 'error', text: errorMessages[error] || `Failed to connect ${label}` });
      setSearchParams({});
    }
  }, [searchParams, setSearchParams, refetchIntegrations]);

  // Clear integration message after 5 seconds
  React.useEffect(() => {
    if (integrationMessage) {
      const timer = setTimeout(() => setIntegrationMessage(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [integrationMessage]);

  // Clear team message after 5 seconds
  React.useEffect(() => {
    if (teamMessage) {
      const timer = setTimeout(() => setTeamMessage(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [teamMessage]);

  const handleConnect = async (provider: IntegrationType) => {
    setConnectingProvider(provider);
    try {
      await connect(provider);
    } catch {
      setIntegrationMessage({ type: 'error', text: `Failed to connect ${provider}` });
    } finally {
      setConnectingProvider(null);
    }
  };

  const handleDisconnect = async (provider: IntegrationType) => {
    setDisconnectingProvider(provider);
    try {
      await disconnect(provider);
      // The Notion card represents both the REST/CRM connection and the hosted-MCP "AI
      // deep-access" connection, so disconnecting Notion tears down the MCP one too.
      if (provider === 'notion' && integrations.some(i => i.integration_type === 'notion_mcp' && i.connected)) {
        await disconnect('notion_mcp').catch(() => { /* best effort — REST already disconnected */ });
      }
      setIntegrationMessage({ type: 'success', text: `${provider} disconnected` });
      refetchIntegrations();
    } catch {
      setIntegrationMessage({ type: 'error', text: `Failed to disconnect ${provider}` });
    } finally {
      setDisconnectingProvider(null);
    }
  };

  // Check if user is owner (completed setup or is staff)
  const isOwner = hasCompletedSetup || isStaff;

  // Initialize form state
  React.useEffect(() => {
    const workspaceData = getSavedWorkspaceData();
    const savedName = workspaceData.name || 'My Workspace';
    const savedValueProp = workspaceData.valueProp || '';
    setWorkspaceName(savedName);
    setOriginalName(savedName);
    setValueProp(savedValueProp);
    setOriginalValueProp(savedValueProp);
    setAutonomyLevel('smart_auto');
    setOriginalAutonomy('smart_auto');
  }, []);

  // Track changes
  React.useEffect(() => {
    const changed =
      workspaceName !== originalName ||
      valueProp !== originalValueProp ||
      autonomyLevel !== originalAutonomy;
    setHasChanges(changed);
  }, [workspaceName, valueProp, autonomyLevel, originalName, originalValueProp, originalAutonomy]);

  const handleSave = async () => {
    setIsSaving(true);
    setSaveSuccess(false);
    setSaveError(false);

    try {
      // TODO: Save to backend when API is wired up
      // For now, persist workspace name and valueProp to localStorage
      const existingData = getSavedWorkspaceData();
      localStorage.setItem('herofy_workspace_data', JSON.stringify({
        ...existingData,
        name: workspaceName,
        valueProp: valueProp,
      }));

      await new Promise(r => setTimeout(r, 500));
      setOriginalName(workspaceName);
      setOriginalValueProp(valueProp);
      setOriginalAutonomy(autonomyLevel);
      setSaveSuccess(true);
      setHasChanges(false);
    } catch (error) {
      setSaveError(true);
    } finally {
      setIsSaving(false);
    }
  };

  // Redirect non-owners
  if (!loading && !isOwner) {
    return <Navigate to="/app/settings" replace />;
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-pulse text-fg-400">Loading settings...</div>
      </div>
    );
  }

  // Current user info
  const userEmail = firebaseUser?.email || '';
  const userDisplayName = firebaseUser?.displayName || userEmail.split('@')[0];
  const userAvatarUrl = firebaseUser?.photoURL || getAvatarUrl(firebaseUser?.uid || 'default');

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="max-w-2xl mx-auto"
    >
      {/* Header */}
      <div className="mb-8">
        <Link
          to="/app/settings"
          className="inline-flex items-center gap-2 text-fg-400 hover:text-fg-200 transition-colors text-sm mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to User Settings
        </Link>
        <h1 className="text-2xl font-bold text-fg-100">Account Settings</h1>
        <p className="text-fg-400 mt-1">Manage workspace settings and team</p>
      </div>

      {/* Workspace Section */}
      <section className="mb-10">
        <h2 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4">Workspace</h2>
        <div className="bg-surface-2/50 border border-border rounded-lg p-6">
          <div className="space-y-4">
            <div>
              <label htmlFor="workspaceName" className="block text-sm text-fg-300 mb-1.5">
                Workspace Name
              </label>
              <input
                id="workspaceName"
                type="text"
                value={workspaceName}
                onChange={(e) => setWorkspaceName(e.target.value)}
                placeholder="My Workspace"
                className="w-full bg-page border border-border-strong rounded px-3 py-2 text-fg-100 placeholder-fg-500 focus:outline-none focus:border-accent transition-colors"
              />
            </div>
            <div>
              <label htmlFor="valueProp" className="block text-sm text-fg-300 mb-1.5">
                Value Proposition
              </label>
              <textarea
                id="valueProp"
                value={valueProp}
                onChange={(e) => setValueProp(e.target.value.slice(0, 500))}
                placeholder="What value do you deliver to customers? (e.g., 'Analytics platform for marketing teams')"
                rows={3}
                className="w-full bg-page border border-border-strong rounded px-3 py-2 text-fg-100 placeholder-fg-500 focus:outline-none focus:border-accent transition-colors resize-none"
              />
              <p className="text-xs text-fg-500 mt-1">
                Helps AI understand your customers' goals during enrichment ({valueProp.length}/500)
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Agent Autonomy Section */}
      <section className="mb-10">
        <h2 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4 flex items-center gap-2">
          <Zap className="w-4 h-4" />
          Agent Autonomy Level
        </h2>
        <div className="bg-surface-2/50 border border-border rounded-lg p-6">
          <p className="text-fg-300 text-sm mb-4">
            Control how autonomous agents behave when they encounter uncertainty.
          </p>
          <div className="space-y-3">
            {AUTONOMY_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => setAutonomyLevel(option.value)}
                className={cn(
                  'w-full p-4 rounded-lg border text-left transition-all cursor-pointer',
                  autonomyLevel === option.value
                    ? 'bg-accent/10 border-accent/50'
                    : 'bg-page/50 border-border hover:border-border-strong'
                )}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        'font-medium',
                        autonomyLevel === option.value ? 'text-fg-100' : 'text-fg-200'
                      )}>
                        {option.label}
                      </span>
                      {option.recommended && (
                        <span className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 bg-signal-ok/20 text-signal-ok rounded">
                          Recommended
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-fg-400 mt-1">{option.description}</p>
                  </div>
                  <div className={cn(
                    'w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors',
                    autonomyLevel === option.value
                      ? 'border-accent bg-accent'
                      : 'border-border-strong'
                  )}>
                    {autonomyLevel === option.value && (
                      <Check className="w-3 h-3 text-white" />
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Integrations Section */}
      <section className="mb-10">
        <h2 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4 flex items-center gap-2">
          <Link2 className="w-4 h-4" />
          Integrations
        </h2>
        <div className="bg-surface-2/50 border border-border rounded-lg p-6">
          <p className="text-fg-300 text-sm mb-4">
            Connect your tools to let Herofy monitor customer communications and sync data.
          </p>

          {/* Integration status message */}
          {integrationMessage && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className={cn(
                'mb-4 p-3 rounded text-sm',
                integrationMessage.type === 'success'
                  ? 'bg-signal-ok/10 border border-signal-ok/30 text-signal-ok'
                  : 'bg-signal-bad/10 border border-signal-bad/30 text-signal-bad'
              )}
            >
              {integrationMessage.text}
            </motion.div>
          )}

          {integrationsLoading ? (
            <div className="text-fg-400 text-sm animate-pulse">Loading integrations...</div>
          ) : (
            <div className="space-y-3">
              {INTEGRATIONS.map((config) => {
                const integration = integrations.find(i => i.integration_type === config.type);
                // Notion's hosted-MCP "AI deep-access" is a separate OAuth connection; surface it
                // as a sub-status on the same Notion card (one tile, two connections).
                const mcpIntegration = config.type === 'notion'
                  ? integrations.find(i => i.integration_type === 'notion_mcp')
                  : undefined;
                return (
                  <IntegrationCard
                    key={config.type}
                    config={config}
                    integration={integration}
                    onConnect={() => handleConnect(config.type)}
                    onDisconnect={() => handleDisconnect(config.type)}
                    onConfigure={config.type === 'notion' ? () => setShowNotionConfig(true) : undefined}
                    isConnecting={connectingProvider === config.type && isConnecting}
                    isDisconnecting={disconnectingProvider === config.type && isDisconnecting}
                    secondary={config.type === 'notion' ? {
                      label: 'AI deep-access (MCP)',
                      integration: mcpIntegration,
                      onConnect: () => handleConnect('notion_mcp'),
                      isConnecting: connectingProvider === 'notion_mcp' && isConnecting,
                    } : undefined}
                  />
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* Pending Join Requests Section */}
      {pendingRequests.length > 0 && (
        <section className="mb-10">
          <h2 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4 flex items-center gap-2">
            <UserPlus className="w-4 h-4" />
            Pending Requests
            <span className="ml-1 px-1.5 py-0.5 text-[10px] bg-signal-warn/20 text-signal-warn rounded">
              {pendingRequests.length}
            </span>
          </h2>
          <div className="bg-surface-2/50 border border-border rounded-lg p-6">
            {/* Team message */}
            {teamMessage && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className={cn(
                  'mb-4 p-3 rounded text-sm',
                  teamMessage.type === 'success'
                    ? 'bg-signal-ok/10 border border-signal-ok/30 text-signal-ok'
                    : 'bg-signal-bad/10 border border-signal-bad/30 text-signal-bad'
                )}
              >
                {teamMessage.text}
              </motion.div>
            )}

            <p className="text-fg-300 text-sm mb-4">
              These users have requested to join your workspace.
            </p>
            <div className="space-y-3">
              {pendingRequests.map((request) => (
                <div
                  key={request.id}
                  className="flex items-center justify-between p-3 bg-page/50 rounded-lg border border-signal-warn/20"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-signal-warn/20 flex items-center justify-center">
                      <Mail className="w-4 h-4 text-signal-warn" />
                    </div>
                    <div>
                      <div className="text-fg-200 text-sm">{request.userEmail}</div>
                      <div className="text-fg-500 text-xs flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        Requested {new Date(request.createdAt).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={async () => {
                        if (!workspaceId) return;
                        setProcessingRequestId(request.id);
                        try {
                          await approveRequest(request, workspaceId);
                          setTeamMessage({ type: 'success', text: `${request.userEmail} has been added to the team` });
                          refetchRequests();
                          refetchMembers();
                        } catch {
                          setTeamMessage({ type: 'error', text: 'Failed to approve request' });
                        } finally {
                          setProcessingRequestId(null);
                        }
                      }}
                      disabled={processingRequestId === request.id}
                      className="flex items-center gap-1 px-3 py-1.5 text-xs font-mono uppercase tracking-wider bg-signal-ok hover:bg-signal-ok/80 text-page rounded transition-colors disabled:opacity-50"
                    >
                      {processingRequestId === request.id && isApproving ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        <Check className="w-3 h-3" />
                      )}
                      Approve
                    </button>
                    <button
                      onClick={async () => {
                        setProcessingRequestId(request.id);
                        try {
                          await rejectRequest(request.id);
                          setTeamMessage({ type: 'success', text: 'Request rejected' });
                          refetchRequests();
                        } catch {
                          setTeamMessage({ type: 'error', text: 'Failed to reject request' });
                        } finally {
                          setProcessingRequestId(null);
                        }
                      }}
                      disabled={processingRequestId === request.id}
                      className="flex items-center gap-1 px-3 py-1.5 text-xs font-mono uppercase tracking-wider border border-border-strong text-fg-400 hover:border-signal-bad hover:text-signal-bad rounded transition-colors disabled:opacity-50"
                    >
                      {processingRequestId === request.id && isRejecting ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        <X className="w-3 h-3" />
                      )}
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Team Members Section */}
      <section className="mb-10">
        <h2 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4 flex items-center gap-2">
          <Users className="w-4 h-4" />
          Team Members
          {teamMembers.length > 0 && (
            <span className="ml-1 text-fg-500">({teamMembers.length})</span>
          )}
        </h2>
        <div className="bg-surface-2/50 border border-border rounded-lg p-6">
          {/* Team message */}
          {teamMessage && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className={cn(
                'mb-4 p-3 rounded text-sm',
                teamMessage.type === 'success'
                  ? 'bg-signal-ok/10 border border-signal-ok/30 text-signal-ok'
                  : 'bg-signal-bad/10 border border-signal-bad/30 text-signal-bad'
              )}
            >
              {teamMessage.text}
            </motion.div>
          )}

          {/* Invite Form - only for admins/owners */}
          {canManageTeam && (
            <div className="mb-6 pb-6 border-b border-border">
              <h3 className="text-sm font-medium text-fg-200 mb-3 flex items-center gap-2">
                <UserPlus className="w-4 h-4" />
                Invite Team Member
              </h3>
              <div className="flex gap-2">
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="email@example.com"
                  className="flex-1 bg-page border border-border-strong rounded px-3 py-2 text-sm text-fg-100 placeholder-fg-500 focus:outline-none focus:border-accent transition-colors"
                />
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as 'admin' | 'member')}
                  className="bg-page border border-border-strong rounded px-3 py-2 text-sm text-fg-100 focus:outline-none focus:border-accent transition-colors"
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
                <button
                  onClick={handleInvite}
                  disabled={isInviting || !inviteEmail.trim()}
                  className={cn(
                    'px-4 py-2 text-sm rounded transition-colors flex items-center gap-2',
                    isInviting || !inviteEmail.trim()
                      ? 'bg-border text-fg-400 cursor-not-allowed'
                      : 'bg-accent hover:bg-accent-hover text-page cursor-pointer'
                  )}
                >
                  {isInviting ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <Mail className="w-4 h-4" />
                      Invite
                    </>
                  )}
                </button>
              </div>

              {/* Show invite link after successful invite */}
              {lastInviteLink && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-3 p-3 bg-page/50 border border-border rounded"
                >
                  <p className="text-xs text-fg-400 mb-2">Share this link with the invited user:</p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 text-xs text-fg-300 bg-page px-2 py-1 rounded truncate">
                      {lastInviteLink}
                    </code>
                    <button
                      onClick={copyInviteLink}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-border hover:bg-border-strong text-fg-300 rounded transition-colors"
                    >
                      {copiedLink ? (
                        <>
                          <Check className="w-3 h-3 text-signal-ok" />
                          Copied
                        </>
                      ) : (
                        <>
                          <Copy className="w-3 h-3" />
                          Copy
                        </>
                      )}
                    </button>
                  </div>
                </motion.div>
              )}
            </div>
          )}

          {/* Pending Invitations */}
          {canManageTeam && pendingInvitations.length > 0 && (
            <div className="mb-6 pb-6 border-b border-border">
              <h3 className="text-sm font-medium text-fg-200 mb-3 flex items-center gap-2">
                <Clock className="w-4 h-4" />
                Pending Invitations
                <span className="ml-1 px-1.5 py-0.5 text-[10px] bg-signal-warn/20 text-signal-warn rounded">
                  {pendingInvitations.length}
                </span>
              </h3>
              <div className="space-y-2">
                {pendingInvitations.map((invitation) => (
                  <div
                    key={invitation.id}
                    className="flex items-center justify-between p-3 bg-page/50 rounded-lg border border-signal-warn/20"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-signal-warn/20 flex items-center justify-center">
                        <Mail className="w-4 h-4 text-signal-warn" />
                      </div>
                      <div>
                        <div className="text-fg-200 text-sm flex items-center gap-2">
                          {invitation.email}
                          <RoleBadge role={invitation.role} />
                        </div>
                        <div className="text-fg-500 text-xs">
                          Expires {new Date(invitation.expires_at).toLocaleDateString()}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleRevokeInvitation(invitation.id)}
                      className="px-2 py-1 text-xs text-fg-400 hover:text-signal-bad transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Current Members */}
          {membersLoading ? (
            <div className="text-fg-400 text-sm animate-pulse">Loading team members...</div>
          ) : teamMembers.length === 0 ? (
            <div className="space-y-3">
              {/* Current user (owner) - fallback when no members loaded */}
              <div className="flex items-center justify-between p-3 bg-page/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <img
                    src={userAvatarUrl}
                    alt={userDisplayName}
                    className="w-8 h-8 rounded-full border border-border-strong object-cover"
                  />
                  <div>
                    <div className="text-fg-200 text-sm flex items-center gap-2">
                      {userDisplayName}
                      <span className="text-fg-500 text-xs">(you)</span>
                    </div>
                    <div className="text-fg-500 text-xs">{userEmail}</div>
                  </div>
                </div>
                <RoleBadge role="owner" />
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {teamMembers.map((member) => {
                const isCurrentUser = member.user_id === firebaseUser?.uid;
                const memberAvatarUrl = getAvatarUrl(member.user_id);
                const memberDisplayName = member.display_name || member.name || member.email.split('@')[0];
                const memberRole = member.role as string;
                const isOwner = memberRole === 'owner';

                // Determine if current user can modify this member
                const canModify = canManageTeam && !isCurrentUser && !isOwner &&
                  (currentUserRole === 'owner' || (currentUserRole === 'admin' && memberRole === 'member'));

                return (
                  <div
                    key={member.user_id}
                    className="flex items-center justify-between p-3 bg-page/50 rounded-lg group"
                  >
                    <div className="flex items-center gap-3">
                      <img
                        src={memberAvatarUrl}
                        alt={memberDisplayName}
                        className="w-8 h-8 rounded-full border border-border-strong object-cover"
                      />
                      <div>
                        <div className="text-fg-200 text-sm flex items-center gap-2">
                          {memberDisplayName}
                          {isCurrentUser && <span className="text-fg-500 text-xs">(you)</span>}
                        </div>
                        <div className="text-fg-500 text-xs">{member.email}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <RoleBadge role={member.role} />
                      {canModify && (
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          {/* Role change dropdown */}
                          <select
                            value={memberRole}
                            onChange={(e) => handleChangeRole(member.user_id, e.target.value)}
                            disabled={changingRoleMemberId === member.user_id}
                            className="bg-surface-2 border border-border-strong rounded px-2 py-1 text-xs text-fg-300 focus:outline-none focus:border-accent transition-colors"
                          >
                            <option value="member">Member</option>
                            <option value="admin">Admin</option>
                          </select>
                          {/* Remove button */}
                          <button
                            onClick={() => handleRemoveMember(member.user_id)}
                            disabled={removingMemberId === member.user_id}
                            className="p-1 text-fg-500 hover:text-signal-bad transition-colors disabled:opacity-50"
                            title="Remove member"
                          >
                            {removingMemberId === member.user_id ? (
                              <RefreshCw className="w-4 h-4 animate-spin" />
                            ) : (
                              <Trash2 className="w-4 h-4" />
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div className="mt-4 pt-4 border-t border-border">
            <p className="text-xs text-fg-500">
              {canManageTeam
                ? 'Invite team members by email. They will receive a link to join.'
                : 'Contact your workspace admin to invite new team members.'}
            </p>
          </div>
        </div>
      </section>

      {/* Billing Section (Placeholder) */}
      <section className="mb-10">
        <h2 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4 flex items-center gap-2">
          <CreditCard className="w-4 h-4" />
          Billing
        </h2>
        <div className="bg-surface-2/50 border border-border rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-fg-200 font-medium">Current Plan</div>
              <div className="text-fg-400 text-sm mt-1">Early Access (Free)</div>
            </div>
            <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-1 bg-signal-ok/20 text-signal-ok rounded border border-signal-ok/30">
              Active
            </span>
          </div>
          <p className="text-xs text-fg-500 mt-4">
            Billing and subscription management coming soon.
          </p>
        </div>
      </section>

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={!hasChanges || isSaving}
          className={cn(
            'inline-flex items-center gap-2 px-6 py-2.5 rounded font-medium transition-colors cursor-pointer',
            hasChanges
              ? 'bg-accent hover:bg-accent-hover text-page'
              : 'bg-border text-fg-400 cursor-not-allowed'
          )}
        >
          {isSaving ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save className="w-4 h-4" />
              Save Changes
            </>
          )}
        </button>
      </div>

      {/* Success/Error Messages */}
      {saveSuccess && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 p-3 bg-signal-ok/10 border border-signal-ok/30 rounded text-signal-ok text-sm text-center"
        >
          Settings saved successfully
        </motion.div>
      )}

      {saveError && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 p-3 bg-signal-bad/10 border border-signal-bad/30 rounded text-signal-bad text-sm text-center"
        >
          Failed to save settings. Please try again.
        </motion.div>
      )}

      {/* Notion Configuration Modal */}
      <NotionConfigModal
        isOpen={showNotionConfig}
        onClose={() => setShowNotionConfig(false)}
        onSave={() => {
          refetchIntegrations();
          setIntegrationMessage({ type: 'success', text: 'Notion configuration saved!' });
        }}
      />
    </motion.div>
  );
}
