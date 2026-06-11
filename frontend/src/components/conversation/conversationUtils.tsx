// Shared, mock-free helpers for the Conversation interface (Track A).
// All grouping/severity is UI-derived from real hook fields (customer.lifecycle + need.type).
// No backend changes; nothing here invents data.

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

// ----- Severity (UI-derived from need.type) ---------------------------------

export type Severity = 'risk' | 'warn' | 'good' | 'normal';

/** Map a Need type (snake_case from the SDK adapter) to a visual severity. */
export function needSeverity(needType?: string | null): Severity {
  switch (needType) {
    case 'urgent_support':
    case 'escalation':
    case 'renewal_at_risk':
    case 'champion_departed':
    case 'open_commitment_overdue':
      return 'risk';
    case 'going_dark':
    case 'frustrated_signal':
    case 'stalled_milestone':
    case 'onboarding_behind':
    case 'approaching_renewal':
    case 'check_in_due':
      return 'warn';
    case 'positive_signal':
    case 'expansion_signal':
      return 'good';
    default:
      return 'normal';
  }
}

const SEVERITY_RANK: Record<Severity, number> = { risk: 0, warn: 1, normal: 2, good: 3 };

export function compareSeverity(a: Severity, b: Severity): number {
  return SEVERITY_RANK[a] - SEVERITY_RANK[b];
}

// ----- Severity color tokens (charcoal/cream/rust palette) -------------------

export const severityDot: Record<Severity, string> = {
  risk: 'bg-signal-bad',
  warn: 'bg-signal-warn',
  good: 'bg-signal-ok',
  normal: 'bg-fg-400',
};

export const severityText: Record<Severity, string> = {
  risk: 'text-signal-bad',
  warn: 'text-signal-warn',
  good: 'text-signal-ok',
  normal: 'text-fg-300',
};

export const severityBorder: Record<Severity, string> = {
  risk: 'border-l-signal-bad',
  warn: 'border-l-signal-warn',
  good: 'border-l-signal-ok',
  normal: 'border-l-border',
};

// ----- Conversation grouping (UI-derived) -----------------------------------

export type ConversationGroup = 'at_risk' | 'prospects' | 'support' | 'other';

export interface GroupMeta {
  key: ConversationGroup;
  label: string;
  caption: string;
}

export const GROUP_ORDER: GroupMeta[] = [
  { key: 'at_risk', label: 'In the way', caption: 'Risk signals · escalations · churn risk' },
  { key: 'support', label: 'Active · support', caption: 'Live accounts needing a reply' },
  { key: 'prospects', label: 'Prospects', caption: 'Pre-sale & onboarding threads' },
  { key: 'other', label: 'Other', caption: 'Everything else' },
];

/**
 * Derive a conversation's group from real fields only:
 *   - severity (from need.type) takes priority -> "at_risk"
 *   - else customer.lifecycle -> prospects / support
 */
export function conversationGroup(
  lifecycle?: string | null,
  needType?: string | null,
): ConversationGroup {
  if (needSeverity(needType) === 'risk') return 'at_risk';
  const lc = (lifecycle || '').toLowerCase();
  if (lc === 'prospect' || lc === 'onboarding' || lc === 'trial') return 'prospects';
  if (lc === 'active' || lc === 'renewal') return 'support';
  return 'other';
}

// ----- Workflow status (filter chips) ---------------------------------------
//
// The conversation filter chips operate on the *workflow status*:
//   needs_response | awaiting_customer | blocked | snoozed | resolved
//
// Source of truth: the real `Need.status` column (`WorkflowStatus!`, default
// needs_response), selected by GetConversationNeeds / GetResolvedConversationNeeds.
// `workflowStatus()` returns it directly; the resolved_at/snoozed_until/thread
// branches remain only as defensive fallbacks for any row missing a status.
// Resolved needs are fetched via `useResolvedConversationNeeds` (the active query
// filters resolvedAt: isNull, so resolved rows never appear there).

export type WorkflowStatus =
  | 'needs_response'
  | 'awaiting_customer'
  | 'blocked'
  | 'snoozed'
  | 'resolved';

export interface WorkflowFilter {
  key: 'all' | WorkflowStatus;
  label: string;
}

export const WORKFLOW_FILTERS: WorkflowFilter[] = [
  { key: 'all', label: 'All conversations' },
  { key: 'needs_response', label: 'Need response' },
  { key: 'awaiting_customer', label: 'Awaiting customer' },
  { key: 'blocked', label: 'Blocked' },
  { key: 'snoozed', label: 'Snoozed' },
  { key: 'resolved', label: 'Resolved' },
];

const WORKFLOW_VALUES: WorkflowStatus[] = [
  'needs_response',
  'awaiting_customer',
  'blocked',
  'snoozed',
  'resolved',
];

/** A need's workflow status — the real `need.status`, with defensive fallbacks. */
export function workflowStatus(need: {
  status?: string | null;
  snoozed_until?: string | null;
  resolved_at?: string | null;
  threads?: Array<{ status?: string | null }>;
}): WorkflowStatus {
  const s = (need.status || '').toLowerCase() as WorkflowStatus;
  if (WORKFLOW_VALUES.includes(s)) return s;
  // Fallbacks for rows missing a status.
  if (need.resolved_at) return 'resolved';
  if (need.snoozed_until) return 'snoozed';
  const threadStatus = (need.threads?.[0]?.status || '').toLowerCase() as WorkflowStatus;
  if (WORKFLOW_VALUES.includes(threadStatus)) return threadStatus;
  return 'needs_response';
}

// ----- Channel label ---------------------------------------------------------

export function channelTag(channel?: string | null): string {
  const c = (channel || '').toLowerCase();
  if (c.includes('email') || c === 'gmail') return 'EML';
  if (c.includes('slack')) return 'SLK';
  if (c.includes('intercom')) return 'IC';
  if (c.includes('internal') || c === 'sidekick') return 'INT';
  return 'EML';
}

// ----- Need-type display -----------------------------------------------------

export function needTypeLabel(needType?: string | null): string {
  if (!needType) return 'Uncategorized';
  return needType
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

// ----- Avatar initials -------------------------------------------------------

export function initials(name?: string | null, email?: string | null): string {
  let src = name || email || '';
  // Handle "Company — Person" or "Company – Person" format: use person's name for initials
  const separatorMatch = src.match(/ [—–] /);
  if (separatorMatch?.index !== undefined) {
    src = src.slice(separatorMatch.index + separatorMatch[0].length).trim();
  }
  if (!src) return '··';
  const parts = src.trim().split(/[\s@.]+/).filter(Boolean);
  if (parts.length === 0) return '··';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

/** Tiny initials avatar (the nav `UserAvatar` is auth-bound; this is generic). */
export function Avatar({
  name,
  email,
  agent,
  variant,
  size = 'md',
  className,
}: {
  name?: string | null;
  email?: string | null;
  agent?: boolean;
  /** 'internal' = gold (team member), 'customer' = sky-blue (external contact) */
  variant?: 'customer' | 'internal';
  size?: 'sm' | 'md';
  className?: string;
}) {
  const dim = size === 'sm' ? 'h-7 w-7 text-[10px]' : 'h-9 w-9 text-xs';
  const colors = agent || variant === 'internal'
    ? 'border-accent bg-accent-bg text-accent'
    : variant === 'customer'
    ? 'border-sky-500/40 bg-sky-900/20 text-sky-300'
    : 'border-border bg-surface-2 text-fg-300';
  return (
    <span
      className={cn(
        'flex shrink-0 items-center justify-center rounded-full border font-mono font-semibold',
        colors,
        dim,
        className,
      )}
    >
      {agent ? 'SK' : initials(name, email)}
    </span>
  );
}

// ----- Mentions --------------------------------------------------------------

/** Render @mentions (and @sidekick) as highlighted spans inside a huddle body. */
export function renderWithMentions(body: string): ReactNode {
  const parts = body.split(/(@[A-Za-z0-9_]+)/g);
  return parts.map((part, i) => {
    if (/^@[A-Za-z0-9_]+$/.test(part)) {
      const isAgent = part.toLowerCase() === '@sidekick';
      return (
        <span
          key={i}
          className={
            isAgent
              ? 'font-mono text-xs font-semibold text-rust-400'
              : 'font-mono text-xs font-semibold text-fg-100'
          }
        >
          {part}
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

/** Extract @mentions from a composed body (used when posting a huddle message). */
export function extractMentions(body: string): string[] {
  const matches = body.match(/@[A-Za-z0-9_]+/g) || [];
  return Array.from(new Set(matches.map((m) => m.slice(1))));
}

// ----- Time formatting -------------------------------------------------------

export function formatTime(iso?: string | null): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d
      .toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      .toUpperCase();
  } catch {
    return '';
  }
}
