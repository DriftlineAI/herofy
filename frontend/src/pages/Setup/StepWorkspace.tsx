import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, X, Check } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { useWorkspace } from '@/lib/workspace';
import { useGetWorkspaceByDomain } from '@/dataconnect-generated/react';
import {
  validateWorkspaceName,
  sanitizeString,
  getEmailDomain,
  isPersonalEmailDomain,
  MAX_WORKSPACE_NAME_LENGTH,
} from '@/lib/validation';
import type { OnboardingData, UpdateDataFn } from './index';

interface StepWorkspaceProps {
  data: OnboardingData;
  updateData: UpdateDataFn;
  onComplete: () => void;
}

type TeamSize = 'solo' | 'small' | 'growing';

interface InviteRow {
  email: string;
  role: 'owner' | 'admin' | 'csm';
}

// Generate slug from name
function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 50);
}

export function StepWorkspace({ data, updateData, onComplete }: StepWorkspaceProps) {
  const { user, completeSetup } = useAuth();
  const { setWorkspaceId } = useWorkspace();

  // Form state
  const [name, setName] = useState(data.workspace.name || '');
  const [slug, setSlug] = useState(data.workspace.slug || '');
  const [valueProp, setValueProp] = useState(data.workspace.valueProp || '');
  const [teamSize, setTeamSize] = useState<TeamSize>(data.workspace.teamSize || 'small');
  const [invites, setInvites] = useState<InviteRow[]>(
    data.workspace.invites || [{ email: user?.email || '', role: 'owner' }]
  );
  const [error, setError] = useState<string | null>(null);
  const [slugStatus, setSlugStatus] = useState<'idle' | 'checking' | 'available' | 'taken'>('idle');

  const userDomain = user?.email ? getEmailDomain(user.email) : null;
  const isPersonalEmail = userDomain ? isPersonalEmailDomain(userDomain) : false;

  // Query for existing workspace by domain (DataConnect)
  const { data: workspaceData, isLoading: isChecking } = useGetWorkspaceByDomain(
    { domain: userDomain || '' },
    { enabled: !!userDomain && !isPersonalEmail }
  );

  // Auto-generate slug from name
  useEffect(() => {
    if (name && !data.workspace.slug) {
      const newSlug = generateSlug(name);
      setSlug(newSlug);
      setSlugStatus('idle');
    }
  }, [name, data.workspace.slug]);

  // Debounced slug availability check
  useEffect(() => {
    if (!slug || slug.length < 3) {
      setSlugStatus('idle');
      return;
    }

    setSlugStatus('checking');
    const timer = setTimeout(async () => {
      // TODO: Call actual slug check mutation
      // For now, simulate availability
      setSlugStatus('available');
    }, 500);

    return () => clearTimeout(timer);
  }, [slug]);

  // Process workspace data when it loads
  useEffect(() => {
    // Skip if no workspace data or personal email
    if (!workspaceData?.workspaces?.[0] || isPersonalEmail) return;

    // Check if we've already processed a redirect check in this session
    const redirectCheckKey = `herofy_redirect_check_${user?.uid}`;
    const hasProcessedCheck = sessionStorage.getItem(redirectCheckKey);

    if (hasProcessedCheck) {
      // Already checked, don't redirect again
      return;
    }

    const workspace = workspaceData.workspaces[0];
    const members = workspace.workspaceMembers_on_workspace || [];
    const isCurrentUserMember = members.some(m => m.user.id === user?.uid);
    const setupCompleted = workspace.setupCompleted || false;

    // Mark as processed to prevent redirect loop
    sessionStorage.setItem(redirectCheckKey, 'true');

    // If user is already a member AND workspace setup is complete
    if (isCurrentUserMember && setupCompleted) {
      completeSetup().then(() => {
        window.location.href = '/app';
      });
      return;
    }

    // If user is a member but workspace setup NOT complete
    // Only auto-navigate if workspace data is NOT already loaded (first visit to this step)
    if (isCurrentUserMember && !setupCompleted && !data.workspaceId) {
      setWorkspaceId(workspace.id);
      updateData({
        workspace: { name: workspace.name, slug: workspace.slug },
        workspaceId: workspace.id
      });
      onComplete();
      return;
    }

    // User is NOT a member, redirect to dedicated join page
    window.location.href = '/join';
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceData, user?.uid, isPersonalEmail, userDomain]);

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setName(value);
    setError(null);
  };

  const handleSlugChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '');
    setSlug(value);
  };

  const addInviteRow = () => {
    setInvites([...invites, { email: '', role: 'csm' }]);
  };

  const removeInviteRow = (index: number) => {
    if (invites.length > 1) {
      setInvites(invites.filter((_, i) => i !== index));
    }
  };

  const updateInvite = (index: number, field: 'email' | 'role', value: string) => {
    const updated = [...invites];
    updated[index] = { ...updated[index], [field]: value };
    setInvites(updated);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validate name
    const validation = validateWorkspaceName(name);
    if (!validation.valid) {
      setError(validation.error || 'Invalid workspace name');
      return;
    }

    // Validate slug
    if (!slug || slug.length < 3) {
      setError('Workspace URL must be at least 3 characters');
      return;
    }

    if (slugStatus === 'taken') {
      setError('This URL is already taken. Please choose another.');
      return;
    }

    const sanitizedName = sanitizeString(name.trim());

    updateData({
      workspace: {
        ...data.workspace,
        name: sanitizedName,
        slug,
        valueProp: valueProp.trim(),
        teamSize,
        invites: invites.filter(i => i.email.trim() !== ''),
      },
    });
    onComplete();
  };

  // Show loading state while checking
  if (isChecking) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 text-rust-500 animate-spin" />
      </div>
    );
  }

  return (
    <>
      {/* Header */}
      <div className="setup__head">
        <div>
          <h1>Let's setup your <em>workspace</em>.</h1>
          <p className="lede">
            Two minutes. Then we'll connect Notion, Gmail, and Slack so Sidekick can start reading your customer conversations.
          </p>
        </div>
        <div className="setup__head-aside">
          <div className="label">SIDEKICK NEEDS</div>
          <p>A workspace name, a URL, and one or two teammates worth inviting. Everything else can wait.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="setup__form">
          {/* LEFT COLUMN — workspace details */}
          <div>
            {/* Workspace name */}
            <div className="setup-field">
              <div className="setup-field__label">Workspace name</div>
              <input
                type="text"
                className="setup-field__input"
                value={name}
                onChange={handleNameChange}
                placeholder="e.g. Acme Customer Success"
                maxLength={MAX_WORKSPACE_NAME_LENGTH}
                autoFocus
              />
            </div>

            {/* Workspace URL */}
            <div className="setup-field">
              <div className="setup-field__label">
                Workspace URL
                <span className="hint">letters, numbers, hyphens</span>
              </div>
              <div className="setup-field__row">
                <span className="prefix">herofy.ai/</span>
                <input
                  type="text"
                  className="setup-field__input"
                  value={slug}
                  onChange={handleSlugChange}
                  style={{ flex: 1 }}
                />
                {slugStatus === 'checking' && (
                  <span className="suffix checking">checking...</span>
                )}
                {slugStatus === 'available' && slug.length >= 3 && (
                  <span className="suffix">✓ available</span>
                )}
                {slugStatus === 'taken' && (
                  <span className="suffix error">taken</span>
                )}
              </div>
            </div>

            {/* Value Prop */}
            <div className="setup-field">
              <div className="setup-field__label">
                What do you provide clients?
                <span className="hint">Makes Sidekick smarter.</span>
              </div>
              <textarea
                className="setup-field__input"
                value={valueProp}
                onChange={(e) => setValueProp(e.target.value)}
                placeholder="e.g. Customer success platform that monitors conversations and surfaces what needs attention"
                rows={3}
                style={{ resize: 'vertical', minHeight: '80px', fontSize: 'inherit', lineHeight: 'inherit' }}
              />
            </div>

            {/* Team size */}
            <div className="setup-field">
              <div className="setup-field__label">Team size</div>
              <div className="setup-radio-group">
                <button
                  type="button"
                  className={`setup-radio ${teamSize === 'solo' ? 'is-on' : ''}`}
                  onClick={() => setTeamSize('solo')}
                >
                  <div className="label">Just me</div>
                  <div className="sub">Solo CSM or founder doing CS</div>
                </button>
                <button
                  type="button"
                  className={`setup-radio ${teamSize === 'small' ? 'is-on' : ''}`}
                  onClick={() => setTeamSize('small')}
                >
                  <div className="label">2–5</div>
                  <div className="sub">Small team, shared portfolio</div>
                </button>
                <button
                  type="button"
                  className={`setup-radio ${teamSize === 'growing' ? 'is-on' : ''}`}
                  onClick={() => setTeamSize('growing')}
                >
                  <div className="label">5+</div>
                  <div className="sub">Multiple CSMs, named accounts</div>
                </button>
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN — invite team */}
          <div>
            <div className="setup-field">
              <div className="setup-field__label">
                Invite teammates
                <span className="hint">optional — can do this later</span>
              </div>

              {invites.map((invite, index) => (
                <div key={index} className="invite-row">
                  <input
                    type="email"
                    placeholder="name@yourteam.com"
                    value={invite.email}
                    onChange={(e) => updateInvite(index, 'email', e.target.value)}
                    disabled={index === 0 && invite.email === user?.email}
                  />
                  <select
                    value={invite.role}
                    onChange={(e) => updateInvite(index, 'role', e.target.value as InviteRow['role'])}
                    disabled={index === 0}
                  >
                    <option value="owner">OWNER</option>
                    <option value="admin">ADMIN</option>
                    <option value="csm">CSM</option>
                  </select>
                  <button
                    type="button"
                    className="remove"
                    onClick={() => removeInviteRow(index)}
                    disabled={index === 0}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}

              <button type="button" className="invite-add" onClick={addInviteRow}>
                + Add another
              </button>
            </div>

            <div className="setup-sidekick-note">
              <span className="tag">SIDEKICK</span>
              Teammates can answer HITL questions and edit playbooks. <em>First-wins concurrency</em> handles it gracefully when two people answer the same one.
            </div>
          </div>
        </div>

        {/* Error message */}
        {error && (
          <div className="text-red-400 text-sm mt-4 font-sans">
            {error}
          </div>
        )}

        {/* Footer */}
        <div className="setup__footer">
          <span className="font-mono text-[10px] text-charcoal-400 tracking-[0.2em] uppercase">
            Step 1 of 5
          </span>
          <button
            type="submit"
            className="sk-btn sk-btn--primary"
            disabled={!name.trim() || slug.length < 3 || slugStatus === 'taken'}
          >
            Continue · connect tools →
          </button>
        </div>
      </form>
    </>
  );
}
