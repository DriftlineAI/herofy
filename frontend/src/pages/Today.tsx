import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Timestamp } from '@/components/ui/huds';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useToday, useResolveNeed, useSnoozeNeed, useCustomerIntel, useSidekickItems, useSidekickAskingItems, useCustomerTrends, useTodayWorklist } from '@/lib/dataconnect-hooks';
import { useWorkspaceNotifications, useRefreshOnFocus, useAgentStatusRealtime } from '@/lib/realtime-hooks';
import { useWorkspace } from '@/lib/workspace';
import { useAuth } from '@/lib/auth';
import type { TodayQueueItem, NeedType } from '@/lib/api';
import { Check, AlertTriangle, TrendingUp, Zap, Users, Settings, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { RightRail, type SidekickItem, type CustomerMeta } from '@/components/sidekick';

// Map need types to display labels
const needTypeLabels: Record<NeedType, string> = {
  urgent_support: 'URGENT SUPPORT',
  going_dark: 'GOING DARK',
  stalled_milestone: 'STALLED',
  approaching_renewal: 'RENEWAL',
  open_commitment_overdue: 'OVERDUE',
  frustrated_signal: 'FRUSTRATED',
  champion_departed: 'CHAMPION LEFT',
  onboarding_behind: 'BEHIND SCHEDULE',
  renewal_at_risk: 'RENEWAL RISK',
  new_handoff: 'NEW HANDOFF',
  meeting_prep_ready: 'MEETING PREP',
  positive_signal: 'POSITIVE',
  expansion_signal: 'EXPANSION',
  check_in_due: 'CHECK IN',
  escalation: 'ESCALATION',
  plan_approval_required: 'PLAN REVIEW',
  draft_response_ready: 'DRAFT READY',
  sidekick_question: 'SIDEKICK HELP',
  uncategorized: 'ATTENTION',
};

// Classify need types into severity levels
const riskTypes: NeedType[] = ['urgent_support', 'escalation', 'champion_departed', 'frustrated_signal', 'renewal_at_risk'];
const warnTypes: NeedType[] = ['going_dark', 'stalled_milestone', 'onboarding_behind', 'open_commitment_overdue'];
const positiveTypes: NeedType[] = ['positive_signal', 'expansion_signal'];

function getSeverity(type: NeedType): 'risk' | 'warn' | 'good' | 'neutral' {
  if (riskTypes.includes(type)) return 'risk';
  if (warnTypes.includes(type)) return 'warn';
  if (positiveTypes.includes(type)) return 'good';
  return 'neutral';
}

// Format ARR for display
function formatARR(cents: number | null): string {
  if (!cents) return '';
  const amount = cents / 100;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return `$${amount}`;
}

// Format time ago
function timeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 60) return `T-${minutes}m`;
  if (hours < 24) return `T-${hours}h`;
  return `T-${days}d`;
}

// A need that just landed (e.g. from a live sweep) — pulse it briefly so it's easy to spot in
// the queue. Clears on the next render after the window (the page re-renders often enough).
const FRESH_NEED_MS = 60_000;
function isFreshNeed(createdAt: string | null | undefined): boolean {
  if (!createdAt) return false;
  const t = new Date(createdAt).getTime();
  return Number.isFinite(t) && Date.now() - t < FRESH_NEED_MS;
}

// Format today's greeting
function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

// Format current date
function formatDate(): string {
  return new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric'
  }).toUpperCase();
}

// Loading skeleton component
function LoadingSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="bg-surface border border-border animate-pulse" style={{ minHeight: 80 }}>
          <div className="p-4">
            <div className="h-4 w-48 bg-border rounded mb-2" />
            <div className="h-3 w-full bg-surface-2 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Error display component
function ErrorDisplay({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <div className="bg-surface border border-border p-6">
      <p className="text-fg-200 mb-4">{error.message}</p>
      <button onClick={onRetry} className="btn-hud">
        Retry Connection
      </button>
    </div>
  );
}

// Day Status Banner Component
interface BannerCellProps {
  label: string;
  value: string | number;
  sub?: string;
  alarm?: boolean;
}

function BannerCell({ label, value, sub, alarm }: BannerCellProps) {
  return (
    <div className={cn(
      "px-6 py-5 border-r border-rule last:border-r-0 flex flex-col gap-1",
      alarm && "bg-risk-wash"
    )}>
      <span className="font-mono text-[9.5px] tracking-[0.28em] uppercase text-fg-400 font-bold">
        {label}
      </span>
      <span className={cn(
        "font-display text-[2.4rem] leading-none tracking-tight",
        alarm ? "text-signal-risk" : "text-fg-100"
      )}>
        {value}
      </span>
      {sub && (
        <span className="font-display italic text-[0.92rem] text-fg-300 leading-snug">
          {sub}
        </span>
      )}
    </div>
  );
}

// Lane Header Component
interface LaneHeaderProps {
  badge: string;
  badgeCount: number;
  variant?: 'alarm' | 'quiet' | 'default';
  copy: React.ReactNode;
  meta?: string;
}

function LaneHeader({ badge, badgeCount, variant = 'default', copy, meta }: LaneHeaderProps) {
  const badgeClasses = cn(
    "flex items-center gap-2.5 px-3.5 py-2 border font-mono text-[10.5px] font-bold tracking-[0.28em] uppercase",
    {
      'border-signal-risk bg-risk-wash text-signal-risk': variant === 'alarm',
      'border-border text-fg-400': variant === 'quiet',
      'border-border text-accent': variant === 'default',
    }
  );

  const pulseClasses = cn(
    "w-[7px] h-[7px] rounded-full animate-pulse",
    {
      'bg-signal-risk': variant === 'alarm',
      'bg-fg-400': variant === 'quiet',
      'bg-accent': variant === 'default',
    }
  );

  return (
    <div className="grid grid-cols-[auto_1fr_auto] gap-4 items-center mb-4">
      <div className={badgeClasses}>
        <span className={pulseClasses} />
        {badge} · {badgeCount}
      </div>
      <div className="font-display italic text-[1.1rem] text-fg-300 leading-snug">
        {copy}
      </div>
      {meta && (
        <div className="font-mono text-[9.5px] tracking-[0.22em] uppercase text-fg-400">
          {meta}
        </div>
      )}
    </div>
  );
}

// Situation Row Component (Lane 1)
interface SituationRowProps {
  customer: string;
  type: string;
  what: string;
  why?: string;
  age: string;
  nextAction: string;
  severity: 'risk' | 'warn' | 'good' | 'neutral';
  onClick: () => void;
  onHover: () => void;
  isHovered?: boolean;
}

function SituationRow({ customer, type, what, why, age, nextAction, severity, onClick, onHover, isHovered }: SituationRowProps) {
  const borderColor = {
    risk: 'edge-risk',
    warn: 'edge-warn',
    good: 'edge-ok',
    neutral: ''
  }[severity];

  const typeColor = {
    risk: 'text-signal-risk',
    warn: 'text-signal-warn',
    good: 'text-signal-ok',
    neutral: 'text-fg-400'
  }[severity];

  const tagBg = {
    risk: 'bg-signal-risk',
    warn: 'bg-signal-warn',
    good: 'bg-signal-ok',
    neutral: 'bg-fg-400'
  }[severity];

  const tagClip = severity === 'good'
    ? 'polygon(50% 100%, 0 0, 100% 0)'
    : 'polygon(50% 0, 100% 100%, 0 100%)';

  return (
    <div
      className={cn(
        "grid grid-cols-[26px_180px_1fr_180px] gap-4 py-4 px-5 bg-surface border border-border border-t-0 first:border-t items-center cursor-pointer transition-colors hover:bg-surface-2",
        borderColor,
        isHovered && "bg-surface-2"
      )}
      onClick={onClick}
      onMouseEnter={onHover}
    >
      {/* Tag icon */}
      <span
        className={cn("w-[14px] h-[14px] mt-1", tagBg)}
        style={{ clipPath: tagClip }}
      />

      {/* Customer + type */}
      <div className="font-mono text-[9.5px] tracking-[0.2em] uppercase text-fg-400">
        <span className="block font-display italic text-[1.08rem] text-fg-100 tracking-normal normal-case mb-0.5">
          {customer}
        </span>
        <span className={cn("font-bold", typeColor)}>{type}</span>
      </div>

      {/* What + why */}
      <div className="text-[0.92rem] text-fg-100 leading-snug">
        {what}
        {why && (
          <span className="block text-[0.82rem] text-fg-300 mt-1 leading-relaxed">
            {why}
          </span>
        )}
      </div>

      {/* Action */}
      <div className="flex flex-col gap-1 items-end">
        <span className="font-mono text-[9px] tracking-[0.22em] uppercase text-fg-400">
          {age}
        </span>
        <span className={cn(
          "font-mono text-[10.5px] font-bold tracking-[0.22em] uppercase",
          severity === 'risk' ? "text-signal-risk" : "text-accent"
        )}>
          {nextAction} →
        </span>
      </div>
    </div>
  );
}

// Worklist Row Component (Lane 2)
interface WorklistRowProps {
  customer: string;
  customerRef: string;
  planType: string;
  what: string;
  why?: string;
  vector?: string;
  delta?: string;
  toward?: string;
  isKeystone?: boolean;
  onClick: () => void;
  onHover: () => void;
  isHovered?: boolean;
}

function WorklistRow({ customer, customerRef, planType, what, why, vector, delta, toward, isKeystone, onClick, onHover, isHovered }: WorklistRowProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-[26px_130px_1fr_180px] gap-4 py-4 px-5 bg-surface border border-border border-t-0 first:border-t items-center cursor-pointer transition-colors hover:bg-surface-2",
        isHovered && "bg-surface-2"
      )}
      onClick={onClick}
      onMouseEnter={onHover}
    >
      {/* Checkbox */}
      <span className="w-4 h-4 border-[1.5px] border-fg-400/50 bg-charcoal" />

      {/* Customer + plan type */}
      <div className="font-mono text-[10px] tracking-[0.2em] uppercase">
        <span className="block font-display italic text-[1.1rem] text-fg-100 tracking-normal normal-case mb-0.5">
          {customer}
        </span>
        <span className="text-accent">{customerRef}</span> · <span className="text-fg-400">{planType} PLAN</span>
      </div>

      {/* What + why */}
      <div className="text-[0.92rem] text-fg-100 leading-snug">
        {what}
        {why && (
          <span className="block text-[0.82rem] text-fg-300 mt-1 leading-relaxed">
            {why}
          </span>
        )}
      </div>

      {/* Impact */}
      <div className="flex flex-col gap-1 items-end text-right">
        {vector && (
          <span className="font-mono text-[9px] tracking-[0.22em] uppercase text-fg-400 font-bold">
            VECTOR · {vector}
          </span>
        )}
        {delta && (
          <span className="font-display italic text-[1.2rem] text-accent leading-none">
            {delta}
          </span>
        )}
        {toward && (
          <span className="text-[0.74rem] text-fg-300 italic max-w-[16ch]">
            toward <span className="text-accent">{toward}</span>
          </span>
        )}
        {isKeystone && (
          <span className="font-mono text-[9px] tracking-[0.25em] uppercase text-brass font-bold border border-brass px-1.5 py-0.5 mt-1">
            KEYSTONE
          </span>
        )}
      </div>
    </div>
  );
}

// Sidekick Ask Row Component (Lane 3)
interface AskRowProps {
  customer: string;
  question: string;
  timeEstimate?: string;
  onClick: () => void;
}

function AskRow({ customer, question, timeEstimate, onClick }: AskRowProps) {
  return (
    <div
      className="grid grid-cols-[26px_110px_1fr_auto] gap-4 py-3.5 px-5 bg-surface border border-border border-t-0 first:border-t items-center cursor-pointer transition-colors hover:bg-surface-2"
      onClick={onClick}
    >
      {/* SK badge */}
      <span className="w-[22px] h-[22px] rounded-full bg-accent text-charcoal grid place-items-center font-mono font-bold text-[10px]">
        SK
      </span>

      {/* Customer */}
      <span className="font-mono text-[9.5px] tracking-[0.18em] uppercase text-accent font-bold">
        {customer}
      </span>

      {/* Question */}
      <span className="font-display italic text-[1.05rem] text-fg-200 leading-snug">
        {question}
      </span>

      {/* Time estimate */}
      {timeEstimate && (
        <span className="font-mono text-[9.5px] tracking-[0.22em] uppercase text-fg-400">
          {timeEstimate}
        </span>
      )}
    </div>
  );
}

// A customer's situations, grouped into one collapsible card. The point: a customer with 9
// open needs reads as "one account on fire", not nine separate to-dos.
interface SituationGroup {
  customerId: string;
  customer: string;
  arrCents: number | null;
  severity: 'risk' | 'warn';
  oldest: string;
  needs: TodayQueueItem[];
}

function CustomerSituationGroup({
  group,
  defaultExpanded,
  hoveredNeedId,
  onNavigate,
  onHoverNeed,
  onHoverCustomer,
}: {
  group: SituationGroup;
  defaultExpanded: boolean;
  hoveredNeedId?: string;
  onNavigate: (item: TodayQueueItem) => void;
  onHoverNeed: (item: TodayQueueItem) => void;
  onHoverCustomer: (customerId: string) => void;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const risk = group.severity === 'risk';
  const accent = risk ? 'text-signal-risk' : 'text-signal-warn';
  const arr = formatARR(group.arrCents);
  // Collapsed peek: the top 1–2 needs (already most-urgent-then-most-recent ordered).
  const peek = group.needs.slice(0, 2);

  return (
    <div className={cn('bg-surface border border-border mb-3', risk ? 'edge-risk' : 'edge-warn')}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        onMouseEnter={() => onHoverCustomer(group.customerId)}
        className="group w-full flex items-center gap-4 p-4 text-left transition-colors hover:bg-surface-2"
      >
        <ChevronRight className={cn('w-4 h-4 shrink-0 transition-transform', accent, expanded && 'rotate-90')} />
        <span className={cn('w-[14px] h-[14px] shrink-0', risk ? 'bg-signal-risk' : 'bg-signal-warn')} style={{ clipPath: 'polygon(50% 0, 100% 100%, 0 100%)' }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-display italic text-[1.15rem] text-fg-100 leading-none">{group.customer}</span>
            <span className={cn('font-mono text-[10px] font-bold tracking-[0.2em] uppercase', accent)}>
              · {group.needs.length} {group.needs.length === 1 ? 'need' : 'needs'}
            </span>
          </div>
          {!expanded && (
            <div className="mt-1.5 space-y-1">
              {peek.map((n) => {
                const sev = getSeverity(n.type);
                const sevColor = sev === 'risk' ? 'text-signal-risk' : sev === 'warn' ? 'text-signal-warn' : 'text-fg-400';
                return (
                  <p key={n.id} className="text-[0.84rem] text-fg-300 truncate">
                    <span className={cn('font-mono text-[9px] tracking-[0.18em] uppercase mr-1.5', sevColor)}>
                      {needTypeLabels[n.type] || n.type}
                    </span>
                    {n.headline}
                  </p>
                );
              })}
              {group.needs.length > peek.length && (
                <p className="text-[0.78rem] text-fg-400 italic">+{group.needs.length - peek.length} more</p>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-0.5 shrink-0 text-right">
          {arr && <span className="font-mono text-[9px] tracking-[0.22em] uppercase text-fg-400">{arr} ARR</span>}
          <span className="font-mono text-[9px] tracking-[0.22em] uppercase text-fg-400">{timeAgo(group.oldest)}</span>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border">
          {group.needs.map((item) => {
            const sev = getSeverity(item.type);
            const sevColor = sev === 'risk' ? 'text-signal-risk' : sev === 'warn' ? 'text-signal-warn' : 'text-fg-400';
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onNavigate(item)}
                onMouseEnter={() => onHoverNeed(item)}
                className={cn(
                  'group w-full flex items-start gap-3 pl-12 pr-4 py-3 text-left border-t border-border first:border-t-0 transition-colors hover:bg-surface-2',
                  hoveredNeedId === item.id && 'bg-surface-2'
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={cn('font-mono text-[9.5px] font-bold tracking-[0.2em] uppercase', sevColor)}>
                      {needTypeLabels[item.type] || item.type}
                    </span>
                    <span className="font-mono text-[9.5px] tracking-[0.2em] uppercase text-fg-400">· {timeAgo(item.created_at)}</span>
                    {isFreshNeed(item.created_at) && (
                      <span className="font-mono text-[8.5px] font-bold tracking-[0.18em] uppercase px-1.5 py-0.5 rounded-sm bg-accent text-page animate-pulse">
                        New
                      </span>
                    )}
                  </div>
                  <p className="text-[0.9rem] text-fg-100 leading-snug mt-0.5">{item.headline}</p>
                  {item.lede && <p className="text-[0.8rem] text-fg-300 leading-relaxed mt-0.5">{item.lede}</p>}
                </div>
                <span className={cn('shrink-0 mt-0.5 font-mono text-[10px] font-bold tracking-[0.2em] uppercase', sev === 'risk' ? 'text-signal-risk' : 'text-accent')}>
                  View →
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function Today() {
  const { data, isLoading, error, refetch } = useToday();
  const { items: sidekickItems, isLoading: sidekickAskingLoading, refetch: refetchSidekick } = useSidekickAskingItems();
  const { data: worklistData, isLoading: worklistLoading } = useTodayWorklist();
  const resolveNeed = useResolveNeed();
  const snoozeNeed = useSnoozeNeed();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, hasCompletedSetup, isStaff } = useAuth();

  // Only workspace owners (who completed setup) or staff can manage integrations
  const canManageIntegrations = hasCompletedSetup || isStaff;

  // Real-time notifications subscription
  const { workspaceId } = useWorkspace();
  const notifications = useWorkspaceNotifications(workspaceId);
  const prevNotifSigRef = useRef<string | null>(null);
  // Refresh after an agent (backend) write. useToday/useSidekickAskingItems wrap their refetch
  // with a SERVER_ONLY fetch (see useServerRefetch), so these bypass the Data Connect client cache
  // that backend writes never update — no full reload needed.
  const refreshToday = useCallback(() => {
    void refetch();
    void refetchSidekick();
  }, [refetch, refetchSidekick]);

  // A signature of the live notification doc. `updated_at` (SERVER_TIMESTAMP) bumps on
  // every agent write, so this changes even when the integer today_count happens to stay
  // flat — e.g. a going-dark sweep whose new need the backend count query and the UI's
  // (broader) Today query disagree on. Keying the refetch on this catches all of them.
  const notifSig = notifications
    ? [
        notifications.today_count,
        notifications.sidekick_questions,
        (notifications.updated_at as { toMillis?: () => number; seconds?: number } | undefined)
          ?.toMillis?.() ??
          (notifications.updated_at as { seconds?: number } | undefined)?.seconds ??
          '',
      ].join('|')
    : null;

  // Live orchestrator progress — subscribes to active_run_id written by the queue consumer
  const activeRunId = (notifications?.active_run_id) ?? null;
  const agentStatus = useAgentStatusRealtime(activeRunId);

  // Refetch on mount and page focus to prevent stale data
  useRefreshOnFocus(refetch);

  // Refetch when the notification doc changes (new items added by agents)
  useEffect(() => {
    if (notifSig === null) return;
    const prev = prevNotifSigRef.current;
    if (prev !== null && prev !== notifSig) {
      refreshToday();
    }
    prevNotifSigRef.current = notifSig;
  }, [notifSig, refreshToday]);

  // A run just finished. The consumer clears active_run_id when the worker is done —
  // the most reliable "new needs may exist" signal, since need-creation notifies can
  // lag or no-op (e.g. the risk play's SurfaceRiskNeed doesn't always bump the doc).
  // Refetch on that falling edge, plus when the live status reports completion.
  const prevActiveRunRef = useRef<string | null>(null);
  useEffect(() => {
    const prev = prevActiveRunRef.current;
    if (prev && !activeRunId) {
      refreshToday();
    }
    prevActiveRunRef.current = activeRunId;
  }, [activeRunId, refreshToday]);

  useEffect(() => {
    if (agentStatus?.status === 'completed') {
      refreshToday();
    }
  }, [agentStatus?.status, refreshToday]);

  // Safety net: the notification doc carries the authoritative today_count. If it disagrees
  // with what's actually rendered, the list is stale — force a refresh. Bounded to once per
  // distinct count so a legitimate query-shape difference can't cause a refetch loop.
  const lastReconciledCountRef = useRef<number | null>(null);
  useEffect(() => {
    const notifCount = notifications?.today_count;
    const renderedCount = data?.count;
    if (notifCount == null || renderedCount == null) return;
    if (notifCount !== renderedCount && lastReconciledCountRef.current !== notifCount) {
      lastReconciledCountRef.current = notifCount;
      refreshToday();
    }
  }, [notifications?.today_count, data?.count, refreshToday]);

  // Refetch data when navigating back from Sidekick question submission
  useEffect(() => {
    const state = location.state as { refetch?: boolean } | null;
    if (state?.refetch) {
      navigate(location.pathname, { replace: true, state: {} });
      refetch();
      refetchSidekick();
    }
  }, [location.state, location.pathname, navigate, refetch, refetchSidekick]);

  // Separate needs into situations (urgent/warn) and positive signals
  const { situationItems, positiveItems, otherItems } = useMemo(() => {
    const rawItems = data?.items || [];
    const situations: TodayQueueItem[] = [];
    const positives: TodayQueueItem[] = [];
    const others: TodayQueueItem[] = [];

    const nowMs = Date.now();
    rawItems.forEach(item => {
      // Skip sidekick questions - they go in lane 3
      if (item.type === 'sidekick_question') return;
      // Snoozed off the queue (e.g. an outreach was sent to a still-dark account) — hidden from
      // "what to do now" until the re-surface floor passes, then it returns to the queue.
      if (item.snoozed_until && new Date(item.snoozed_until).getTime() > nowMs) return;

      const severity = getSeverity(item.type);
      if (severity === 'risk' || severity === 'warn') {
        situations.push(item);
      } else if (severity === 'good') {
        positives.push(item);
      } else {
        others.push(item);
      }
    });

    // Sort by priority
    situations.sort((a, b) => a.priority_rank - b.priority_rank);
    positives.sort((a, b) => a.priority_rank - b.priority_rank);
    others.sort((a, b) => a.priority_rank - b.priority_rank);

    return { situationItems: situations, positiveItems: positives, otherItems: others };
  }, [data?.items]);

  // Group situations by customer — one card per account, sorted by urgency then load.
  const situationGroups = useMemo<SituationGroup[]>(() => {
    const map = new Map<string, SituationGroup>();
    situationItems.forEach((item) => {
      let g = map.get(item.customer_id);
      if (!g) {
        g = {
          customerId: item.customer_id,
          customer: item.customer_name,
          arrCents: item.customer_arr_cents ?? null,
          severity: 'warn',
          oldest: item.created_at,
          needs: [],
        };
        map.set(item.customer_id, g);
      }
      g.needs.push(item);
      if (getSeverity(item.type) === 'risk') g.severity = 'risk';
      if (item.created_at < g.oldest) g.oldest = item.created_at;
    });
    // Within a customer: most urgent first (risk → warn → other), then most recent.
    const sevRank = (t: NeedType) => {
      const s = getSeverity(t);
      return s === 'risk' ? 0 : s === 'warn' ? 1 : 2;
    };
    const groups = Array.from(map.values());
    groups.forEach((g) => g.needs.sort((a, b) => {
      const r = sevRank(a.type) - sevRank(b.type);
      if (r !== 0) return r;
      return a.created_at < b.created_at ? 1 : -1;
    }));
    groups.sort((a, b) => {
      if (a.severity !== b.severity) return a.severity === 'risk' ? -1 : 1;
      if (b.needs.length !== a.needs.length) return b.needs.length - a.needs.length;
      return a.oldest < b.oldest ? -1 : 1;
    });
    return groups;
  }, [situationItems]);

  // Transform worklist data (milestones with goal linkage)
  const worklistItems = useMemo(() => {
    if (!worklistData?.milestones) return [];

    return worklistData.milestones
      .filter((m): m is typeof m & { goal: NonNullable<typeof m.goal> } =>
        !!(m.goal?.customer?.id && m.goal?.customer?.name)
      )
      .map(milestone => {
        // Extract first word from goalRationale as vector category hint (e.g., "TRUST: building..." -> "TRUST")
        const vectorMatch = milestone.goalRationale?.match(/^([A-Za-z]+)/);
        const vectorHint = vectorMatch?.[1]?.toUpperCase();

        return {
          id: milestone.id,
          customerId: milestone.goal.customer.id,
          customer: milestone.goal.customer.name,
          customerRef: milestone.goal.customer.slug?.toUpperCase().slice(0, 8) || '',
          planType: milestone.goal.isPrimary ? 'ONBOARDING' : 'SOLUTION',
          what: milestone.title,
          why: milestone.description,
          vector: vectorHint,
          delta: undefined, // TODO: Compute from ProgressVector data
          toward: milestone.goal.text?.slice(0, 30),
          targetDate: milestone.targetDate,
          status: milestone.status,
          isKeystone: milestone.sortOrder === 1,
        };
      });
  }, [worklistData?.milestones]);

  // Track hovered customer for right rail
  const [hoveredCustomerId, setHoveredCustomerId] = useState<string | null>(null);
  const [hoveredNeed, setHoveredNeed] = useState<TodayQueueItem | null>(null);

  // Fetch sidekick items for hovered customer
  const { data: sidekickData, isLoading: sidekickLoadingDetail } = useSidekickItems(hoveredCustomerId);

  // Fetch customer trends (sentiment + engagement) for right rail
  const { data: trendsData, isLoading: trendsLoading } = useCustomerTrends(hoveredCustomerId);

  // Transform sidekick data to match RightRail's expected format
  const railData = sidekickData ? {
    customer: {
      id: sidekickData.customer.id,
      name: sidekickData.customer.name,
      refcode: sidekickData.customer.refcode || '',
      tier: sidekickData.customer.tier || 'STANDARD',
      arr: sidekickData.customer.arr || '$0',
      lifecycle: sidekickData.customer.lifecycle || 'active',
      day: sidekickData.customer.day,
      health: sidekickData.customer.health,
      healthColor: sidekickData.customer.health_color,
      healthScore: sidekickData.customer.health_score,
      sentiment: sidekickData.customer.sentiment,
      sentimentColor: sidekickData.customer.sentiment_color,
      signals: sidekickData.customer.signals,
    },
    items: sidekickData.items.map(item => ({
      id: item.id,
      type: item.type as 'tip' | 'asking' | 'resolved' | 'observed' | 'working',
      question: item.question,
      resolution: item.resolution,
      text: item.text,
      task: item.task,
      step: item.step,
      stepNum: item.step_num,
      total: item.total_steps,
      by: item.resolved_by,
      timestamp: item.timestamp_label,
      isCurrentItem: item.is_current_item,
    })),
    openItemsCount: sidekickData.open_count,
    resolvedItemsCount: sidekickData.resolved_count,
  } : null;

  // Initialize hovered customer from first situation
  useEffect(() => {
    const firstItem = situationItems[0] || positiveItems[0] || worklistItems[0];
    if (firstItem && !hoveredCustomerId) {
      setHoveredCustomerId('customer_id' in firstItem ? firstItem.customer_id : firstItem.customerId);
      if ('customer_id' in firstItem) {
        setHoveredNeed(firstItem);
      }
    }
  }, [situationItems, positiveItems, worklistItems, hoveredCustomerId]);

  const handleHoverSituation = (item: TodayQueueItem) => {
    setHoveredCustomerId(item.customer_id);
    setHoveredNeed(item);
  };

  const handleHoverWorklist = (customerId: string) => {
    setHoveredCustomerId(customerId);
    setHoveredNeed(null);
  };

  // Calculate banner stats
  const inTheWayCount = situationItems.length;
  const worklistCount = worklistItems.length;
  const asksCount = sidekickItems.length;
  const positiveCount = positiveItems.length;

  const firstName = user?.displayName?.split(' ')[0];

  return (
    <div>
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center gap-3 font-mono text-[10.5px] tracking-[0.22em] uppercase text-fg-400 mb-3">
          <span className="w-[7px] h-[7px] rounded-full bg-accent animate-pulse" />
          <span>{formatDate()} · {new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
        <h1 className="font-display text-[2.8rem] leading-none tracking-tight text-fg-100">
          {getGreeting()}{firstName ? <>, <em className="italic text-accent font-normal">{firstName}</em></> : ''}.
        </h1>
      </header>

      {/* Live orchestrator progress — visible while a worker run is active */}
      {agentStatus && agentStatus.status !== 'completed' && agentStatus.status !== 'failed' && (
        <div className="mb-6 bg-surface border border-border border-l-4 border-l-accent px-4 py-3 flex items-center gap-4">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span className="text-xs font-mono tracking-wider uppercase text-accent">
                {agentStatus.customer_name
                  ? `Herofy · ${agentStatus.customer_name}`
                  : 'Herofy is working…'}
              </span>
              <span className="text-xs font-mono text-fg-400 shrink-0">{agentStatus.progress_pct}%</span>
            </div>
            <div className="w-full h-0.5 bg-surface-2">
              <div
                className="h-full bg-accent transition-all duration-500"
                style={{ width: `${agentStatus.progress_pct}%` }}
              />
            </div>
            {agentStatus.message && (
              <p className="text-[11px] text-fg-400 mt-1 font-mono truncate">{agentStatus.message}</p>
            )}
          </div>
        </div>
      )}

      {/* Day Status Banner */}
      <div className="grid grid-cols-4 bg-surface border border-border mb-9">
        <BannerCell
          label="In the Way"
          value={situationGroups.length}
          sub={situationGroups.length > 0
            ? `${inTheWayCount} open need${inTheWayCount === 1 ? '' : 's'} · clear first`
            : 'All clear'}
          alarm={situationGroups.length > 0}
        />
        <BannerCell
          label="Today's Worklist"
          value={worklistCount}
          sub={worklistCount > 0 ? 'Goal-anchored tasks' : 'No tasks due'}
        />
        <BannerCell
          label="Sidekick Asks"
          value={asksCount}
          sub={asksCount > 0 ? 'Under a minute each' : 'No questions'}
        />
        <BannerCell
          label="Positive Signals"
          value={positiveCount}
          sub={positiveCount > 0 ? positiveItems[0]?.customer_name : 'None today'}
        />
      </div>

      {/* Main content with right rail */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-7 items-start">
        {/* Main lanes — min-w-0 prevents the 1fr grid cell from expanding beyond
            its allocated width (CSS Grid min-width:auto gotcha) */}
        <div className="space-y-9 min-w-0 overflow-hidden">
          {isLoading || sidekickAskingLoading || worklistLoading ? (
            <LoadingSkeleton />
          ) : error ? (
            <ErrorDisplay error={error as Error} onRetry={() => refetch()} />
          ) : (
            <>
              {/* Lane 1: In the Way — situations grouped by customer */}
              {situationGroups.length > 0 && (
                <div>
                  <LaneHeader
                    badge="IN THE WAY"
                    badgeCount={situationGroups.length}
                    variant="alarm"
                    copy={<>These customers need you <em className="text-signal-risk">before anything else</em>.</>}
                    meta="GROUPED BY ACCOUNT"
                  />

                  {situationGroups.map((g) => (
                    <CustomerSituationGroup
                      key={g.customerId}
                      group={g}
                      defaultExpanded={g.needs.length === 1}
                      hoveredNeedId={hoveredNeed?.id}
                      onNavigate={(item) => {
                        if (item.type === 'plan_approval_required' && item.plan_id) {
                          navigate(`/app/plans/${item.plan_id}`);
                        } else {
                          navigate(`/app/customers/${item.customer_id}`);
                        }
                      }}
                      onHoverNeed={(item) => handleHoverSituation(item)}
                      onHoverCustomer={(customerId) => handleHoverWorklist(customerId)}
                    />
                  ))}
                </div>
              )}

              {/* Positive signals — celebratory, kept as individual rows */}
              {positiveCount > 0 && (
                <div>
                  <LaneHeader
                    badge="POSITIVE SIGNALS"
                    badgeCount={positiveCount}
                    variant="default"
                    copy={<>Good news worth a <em className="text-accent">follow-up</em>.</>}
                    meta="CELEBRATE · EXPAND"
                  />
                  {positiveItems.map((item) => (
                    <SituationRow
                      key={item.id}
                      customer={item.customer_name}
                      type={needTypeLabels[item.type] || item.type}
                      what={item.headline}
                      why={item.lede || undefined}
                      age={timeAgo(item.created_at)}
                      nextAction="FOLLOW UP"
                      severity="good"
                      onClick={() => navigate(`/app/customers/${item.customer_id}`)}
                      onHover={() => handleHoverSituation(item)}
                      isHovered={hoveredNeed?.id === item.id}
                    />
                  ))}
                </div>
              )}

              {/* Lane 2: Today's Worklist */}
              {worklistItems.length > 0 && (
                <div>
                  <LaneHeader
                    badge="TODAY'S WORKLIST"
                    badgeCount={worklistItems.length}
                    copy={<>Goal-anchored tasks across your <em className="text-accent">active plans</em>.</>}
                    meta="CROSS-CUSTOMER · CROSS-PLAN"
                  />

                  {worklistItems.map((item) => (
                    <WorklistRow
                      key={item.id}
                      customer={item.customer}
                      customerRef={item.customerRef}
                      planType={item.planType}
                      what={item.what}
                      why={item.why}
                      vector={item.vector}
                      delta={item.delta}
                      toward={item.toward}
                      isKeystone={item.isKeystone}
                      onClick={() => navigate(`/app/customers/${item.customerId}`)}
                      onHover={() => handleHoverWorklist(item.customerId)}
                      isHovered={hoveredCustomerId === item.customerId && !hoveredNeed}
                    />
                  ))}
                </div>
              )}

              {/* Lane 3: Sidekick Asks */}
              {sidekickItems.length > 0 && (
                <div>
                  <LaneHeader
                    badge="SIDEKICK ASKS"
                    badgeCount={sidekickItems.length}
                    variant="quiet"
                    copy={<>Micro-decisions before Sidekick can <em className="text-accent">draft on your behalf</em>.</>}
                    meta="UNDER A MINUTE EACH"
                  />

                  {sidekickItems.map((item) => (
                    <AskRow
                      key={item.id}
                      customer={item.customer_name?.toUpperCase() || 'CUSTOMER'}
                      question={item.question}
                      timeEstimate="30 SEC"
                      onClick={() => navigate(`/app/needs/${item.need_id || item.id}`)}
                    />
                  ))}
                </div>
              )}

              {/* Other items that don't fit the lanes */}
              {otherItems.length > 0 && (
                <div>
                  <LaneHeader
                    badge="OTHER ITEMS"
                    badgeCount={otherItems.length}
                    variant="quiet"
                    copy={<>Additional items requiring attention.</>}
                    meta="VARIOUS"
                  />

                  {otherItems.map((item) => (
                    <SituationRow
                      key={item.id}
                      customer={item.customer_name}
                      type={needTypeLabels[item.type] || item.type}
                      what={item.headline}
                      why={item.lede || undefined}
                      age={timeAgo(item.created_at)}
                      nextAction="VIEW"
                      severity="neutral"
                      onClick={() => navigate(`/app/customers/${item.customer_id}`)}
                      onHover={() => handleHoverSituation(item)}
                      isHovered={hoveredNeed?.id === item.id}
                    />
                  ))}
                </div>
              )}

              {/* Empty state */}
              {inTheWayCount === 0 && worklistItems.length === 0 && sidekickItems.length === 0 && otherItems.length === 0 && positiveCount === 0 && (
                <div className="flex flex-col items-center justify-center py-16">
                  <div className="w-20 h-20 bg-signal-ok/20 flex items-center justify-center mb-6">
                    <Check className="w-10 h-10 text-signal-ok" />
                  </div>

                  <h2 className="text-2xl mb-2">All Clear</h2>
                  <p className="text-fg-300 text-center max-w-md mb-8">
                    No situations requiring your attention right now. Check back later or add customers to start monitoring.
                  </p>

                  <div className="flex flex-col sm:flex-row gap-4 mb-8">
                    <Link to="/app/customers" className="btn-hud">
                      <Users className="w-4 h-4" />
                      View Portfolio
                    </Link>

                    {canManageIntegrations && (
                      <Link to="/app/settings/account" className="btn-hud">
                        <Settings className="w-4 h-4" />
                        Connect Integrations
                      </Link>
                    )}
                  </div>

                  <div className="bg-surface border border-border max-w-lg p-6">
                    <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.28em] uppercase text-accent font-bold mb-3">
                      <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse" />
                      SIDEKICK TIP
                    </div>
                    <p className="font-display italic text-fg-200">
                      Connect Gmail, Slack, and Calendar to let me monitor customer signals automatically. I'll surface what needs attention here.
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Right Rail */}
        <div className="sticky top-6 hidden lg:block">
          {hoveredCustomerId && railData && (
            <RightRail
              key={railData.customer.id}
              customer={railData.customer}
              items={railData.items}
              openItemsCount={railData.openItemsCount}
              resolvedItemsCount={railData.resolvedItemsCount}
              sentimentTrend={trendsData?.sentiment}
              engagementTrend={trendsData?.engagement}
              trendsLoading={trendsLoading}
              onOpenCustomer={() => navigate(`/app/customers/${railData.customer.id}`)}
              onOpenSidekick={() => navigate('/app/sidekick')}
              onViewPlans={() => navigate(`/app/customers/${railData.customer.id}?tab=plans`)}
            />
          )}
          {hoveredCustomerId && !railData && !sidekickLoadingDetail && (
            <div className="bg-surface border border-border p-6">
              <div className="font-mono text-[10px] tracking-[0.28em] uppercase text-fg-400 mb-3">
                NO CUSTOMER DATA
              </div>
              <p className="text-fg-300 text-sm">
                Select a customer to view their context.
              </p>
            </div>
          )}
          {hoveredCustomerId && sidekickLoadingDetail && (
            <div className="bg-surface border border-border animate-pulse">
              <div className="p-6">
                <div className="h-4 w-32 bg-border rounded mb-4" />
                <div className="h-6 w-48 bg-border rounded mb-4" />
                <div className="h-3 w-full bg-surface-2 rounded" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
