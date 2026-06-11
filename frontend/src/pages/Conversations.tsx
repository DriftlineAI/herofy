// Conversations — the 3-pane triage workspace.
//
// Data model (corrected): the inbox is a list of NEEDS, not threads. The signal
// watcher creates Needs; threads are conversation threads grouped *under* a Need.
// The list binds to `useConversationNeeds().data.needs` (need-first). Each row is
// one Need; its primary thread provides the subject/preview/channel. A threadless
// Need (proactive play) still appears — it shows the need headline/lede.
//
// Layout: filter chips (workflow status) + dense grouped inbox column + reading
// pane (the selected need's thread, or the play layout if threadless) + right
// rail (customer context + internal huddle). All regions render from real hooks.
// Mock-free: no design-file constants leak in.

import { useMemo, useState, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { MessageSquare, Zap } from 'lucide-react';
import { SidekickObserved } from '@/components/sidekick/SidekickAtoms';
import {
  useConversationNeeds,
  useResolvedConversationNeeds,
  useThread,
  useThreadMessages,
  useNeed,
  useThreadDraft,
  useResolveNeed,
  useSnoozeNeed,
  type ConversationNeed,
} from '@/lib/dataconnect-hooks';
import { ThreadHeader } from '@/components/conversation/ThreadHeader';
import { ContextRail } from '@/components/conversation/ContextRail';
import { MessageList } from '@/components/conversation/MessageList';
import { DraftPanel } from '@/components/conversation/DraftPanel';
import { HuddlePanel } from '@/components/conversation/HuddlePanel';
import { ThreadNeeds } from '@/components/conversation/ThreadNeeds';
import { NeedPlayLayout } from '@/components/conversation/NeedPlayLayout';
import type { RawDraft } from '@/components/conversation/DraftPanel';
import { Pulse } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { useWorkspaceNotifications, useRefreshOnFocus } from '@/lib/realtime-hooks';
import { useWorkspace } from '@/lib/workspace';
import {
  GROUP_ORDER,
  WORKFLOW_FILTERS,
  workflowStatus,
  conversationGroup,
  channelTag,
  needSeverity,
  severityDot,
  severityText,
  severityBorder,
  needTypeLabel,
  compareSeverity,
  Avatar,
  formatTime,
  type ConversationGroup,
  type WorkflowFilter,
} from '@/components/conversation/conversationUtils';

// The primary thread for a need = first customer thread, else first thread.
function primaryThread(need: ConversationNeed): ConversationNeed['threads'][number] | null {
  const threads = need.threads || [];
  return threads.find((t) => t.thread_type === 'customer') || threads[0] || null;
}

export default function Conversations() {
  const { data, isLoading, refetch } = useConversationNeeds();
  const { data: resolvedData, isLoading: resolvedLoading } = useResolvedConversationNeeds();
  const [searchParams, setSearchParams] = useSearchParams();
  const [filter, setFilter] = useState<WorkflowFilter['key']>('all');

  const { workspaceId } = useWorkspace();
  const notifications = useWorkspaceNotifications(workspaceId);
  const prevConvCountRef = useRef<number | undefined>(undefined);

  // Refetch on mount and page focus to prevent stale data
  useRefreshOnFocus(refetch);

  // Auto-refetch when new conversations arrive
  useEffect(() => {
    const count = notifications?.conversations_count;
    if (count === undefined) return;
    if (prevConvCountRef.current !== undefined && count !== prevConvCountRef.current) {
      setTimeout(() => refetch(), 300);
    }
    prevConvCountRef.current = count;
  }, [notifications?.conversations_count, refetch]);

  const showResolved = filter === 'resolved';
  const activeNeeds = useMemo(() => data?.needs || [], [data]);
  const resolvedNeeds = useMemo(() => resolvedData?.needs || [], [resolvedData]);
  // Resolved needs come from their own query (the active query filters
  // resolvedAt: isNull); every other chip filters the active needs.
  const needs = showResolved ? resolvedNeeds : activeNeeds;
  const listLoading = showResolved ? resolvedLoading : isLoading;

  // Per-filter counts for the chip row. Live chips count the active needs;
  // the Resolved chip is its own (separately-fetched) list.
  const counts = useMemo(() => {
    const c: Record<string, number> = {
      all: activeNeeds.length,
      resolved: resolvedNeeds.length,
    };
    for (const n of activeNeeds) {
      const s = workflowStatus(n);
      if (s === 'resolved') continue;
      c[s] = (c[s] || 0) + 1;
    }
    return c;
  }, [activeNeeds, resolvedNeeds]);

  // Sidekick-internal needs belong in the Sidekick tab, not the triage inbox.
  // Keep them in activeNeeds so we can count open questions per customer for the
  // right rail CTA, but exclude them from the displayed list.
  const EXCLUDED_NEED_TYPES = new Set(['sidekick_question', 'plan_approval_required']);

  const filtered = useMemo(() => {
    const base = needs.filter((n) => !EXCLUDED_NEED_TYPES.has(n.type));
    return filter === 'all' ? base : base.filter((n) => workflowStatus(n) === filter);
  }, [needs, filter]);

  // Count open sidekick questions per customer so the right rail can surface the CTA.
  const sidekickCountByCustomer = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const n of activeNeeds) {
      if (n.type === 'sidekick_question' && n.customer_id) {
        counts[n.customer_id] = (counts[n.customer_id] || 0) + 1;
      }
    }
    return counts;
  }, [activeNeeds]);

  // Grouped, severity-sorted within each segment.
  const grouped = useMemo(() => {
    const map: Record<ConversationGroup, ConversationNeed[]> = {
      at_risk: [],
      support: [],
      prospects: [],
      other: [],
    };
    for (const n of filtered) {
      map[conversationGroup(n.customer_lifecycle, n.type)].push(n);
    }
    for (const key of Object.keys(map) as ConversationGroup[]) {
      map[key].sort((a, b) => {
        const s = compareSeverity(needSeverity(a.type), needSeverity(b.type));
        if (s !== 0) return s;
        return a.priority_rank - b.priority_rank;
      });
    }
    return map;
  }, [filtered]);

  // Selection — keep in the URL so a row is linkable; default to first need.
  const selectedId = searchParams.get('need') || filtered[0]?.id || null;
  const selectedNeed = useMemo(
    () => needs.find((n) => n.id === selectedId) || null,
    [needs, selectedId],
  );

  // For play needs (threadless), fetch the full need detail so the right rail can
  // render the designed content (Sidekick note, CTAs). DataConnect deduplicates this
  // with the same call inside ReadingPane.
  const isPlayNeed = selectedNeed ? primaryThread(selectedNeed) === null : false;
  const { data: playNeedDetail } = useNeed(isPlayNeed && selectedNeed?.id ? selectedNeed.id : '');

  const selectedSidekickCount = selectedNeed?.customer_id
    ? (sidekickCountByCustomer[selectedNeed.customer_id] || 0)
    : 0;

  function selectNeed(id: string) {
    const next = new URLSearchParams(searchParams);
    next.set('need', id);
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="flex min-h-0 flex-col h-[calc(100dvh-17.5rem)]">
      {/* Filter chips row */}
      <div className="flex flex-wrap items-center gap-2 border-b border-[rgba(232,228,220,0.08)] px-5 py-3">
        <div className="mr-2 flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-fg-400">
          <Pulse continuous />
          <span>Inbox</span>
          {!isLoading && <span className="text-rust-500">· {activeNeeds.length} open</span>}
        </div>
        {WORKFLOW_FILTERS.map((f) => {
          const active = filter === f.key;
          const count = counts[f.key] || 0;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors',
                active
                  ? 'border-rust-700 bg-accent-bg text-rust-400'
                  : 'border-[rgba(232,228,220,0.08)] text-fg-400 hover:bg-surface-2 hover:text-fg-200',
              )}
            >
              {f.label}
              <span className={cn('font-mono', active ? 'text-rust-400' : 'text-fg-400')}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* 3-pane body — grid-rows-1 forces a single row that fills the flex container so
          each column scrolls independently rather than expanding to content height */}
      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-1 overflow-hidden lg:grid-cols-[380px_1fr_20rem]">
        {/* Inbox list column — dense, grouped by segment */}
        <div className="hidden flex-col overflow-y-auto border-r border-[rgba(232,228,220,0.08)] lg:flex">
          {listLoading ? (
            <div className="space-y-2 p-3">
              <div className="h-20 animate-pulse rounded-md bg-surface-2" />
              <div className="h-20 animate-pulse rounded-md bg-surface-2" />
              <div className="h-20 animate-pulse rounded-md bg-surface-2" />
            </div>
          ) : filtered.length === 0 ? (
            <EmptyInbox hasNeeds={needs.length > 0} />
          ) : (
            <div className="pb-6">
              {GROUP_ORDER.map((group) => {
                const items = grouped[group.key];
                if (items.length === 0) return null;
                const alarm = group.key === 'at_risk';
                return (
                  <section key={group.key}>
                    <div className="flex items-center gap-2 border-b border-[rgba(232,228,220,0.08)] bg-bg/60 px-4 py-2">
                      <span
                        className={cn(
                          'font-mono text-xs font-semibold uppercase tracking-widest',
                          alarm ? 'text-signal-bad' : 'text-fg-300',
                        )}
                      >
                        {group.label}
                      </span>
                      <span className="font-mono text-xs text-fg-400">· {items.length}</span>
                      <span className="ml-auto truncate font-mono text-[10px] uppercase tracking-wider text-fg-400">
                        {group.caption}
                      </span>
                    </div>
                    {items.map((need) => (
                      <InboxRow
                        key={need.id}
                        need={need}
                        active={need.id === selectedId}
                        onSelect={() => selectNeed(need.id)}
                      />
                    ))}
                  </section>
                );
              })}
            </div>
          )}
        </div>

        {/* Reading pane — selected need's thread, or play layout if threadless */}
        <div className="overflow-y-auto">
          {listLoading ? (
            <ReadingLoader />
          ) : !selectedNeed ? (
            <ReadingEmpty hasNeeds={needs.length > 0} />
          ) : (
            <ReadingPane key={selectedNeed.id} need={selectedNeed} />
          )}
        </div>

        {/* Right rail — for thread needs: ContextRail + HuddlePanel.
            For play needs: the designed PlayRailContent (ContextRail + Sidekick note + CTAs). */}
        <div className="hidden overflow-y-auto border-l border-[rgba(232,228,220,0.08)] lg:block">
          {selectedNeed && (
            isPlayNeed && playNeedDetail?.need
              ? <PlayRailContent need={playNeedDetail.need} sidekickCount={selectedSidekickCount} />
              : <RightRail need={selectedNeed} sidekickCount={selectedSidekickCount} />
          )}
        </div>
      </div>
    </div>
  );
}

// ----- Inbox row (one per Need) ----------------------------------------------

function InboxRow({
  need,
  active,
  onSelect,
}: {
  need: ConversationNeed;
  active: boolean;
  onSelect: () => void;
}) {
  const sev = needSeverity(need.type);
  const thread = primaryThread(need);
  const subject = thread?.subject || need.headline;
  const preview = thread?.latest_interaction?.summary_ai || need.lede || '';
  const when = thread?.latest_interaction?.occurred_at || need.updated_at;
  const channel = channelTag(thread?.channel);
  const threadCount = need.threads?.length || 0;
  const unread = workflowStatus(need) === 'needs_response';

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'flex w-full gap-3 border-b border-l-[3px] [border-bottom-color:rgba(232,228,220,0.08)] px-4 py-3 text-left transition-colors',
        active ? 'border-l-accent bg-surface-2' : cn(severityBorder[sev], 'hover:bg-surface'),
      )}
    >
      <Avatar name={need.customer_name} size="md" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-lg font-semibold text-fg-100">{need.customer_name}</span>
          {unread && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-rust-500" />}
          <span className="ml-auto shrink-0 font-mono text-[10px] uppercase tracking-wider text-fg-400">
            {channel} · {formatTime(when)}
          </span>
        </div>
        <p className="mt-0.5 truncate text-[17px] font-medium text-fg-200">{subject}</p>
        {preview && (
          <p className="mt-0.5 line-clamp-2 text-[15px] leading-snug text-fg-400">{preview}</p>
        )}
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <span
            className={cn(
              'rounded-sm border border-[rgba(232,228,220,0.08)] px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider',
              severityText[sev],
            )}
          >
            {needTypeLabel(need.type)}
          </span>
          {threadCount > 1 && (
            <span className="rounded-sm border border-[rgba(232,228,220,0.08)] px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-fg-400">
              {threadCount} threads
            </span>
          )}
          {need.customer_arr_cents != null && (
            <span className="font-mono text-[10px] uppercase tracking-wider text-fg-400">
              {formatArr(need.customer_arr_cents)} ARR
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

function formatArr(cents: number): string {
  const dollars = cents / 100;
  if (dollars >= 1000) return `$${Math.round(dollars / 1000)}K`;
  return `$${Math.round(dollars)}`;
}

// ----- Reading pane ----------------------------------------------------------

function ReadingPane({ need }: { need: ConversationNeed }) {
  const resolveNeed = useResolveNeed();
  const snoozeNeed = useSnoozeNeed();
  const thread = primaryThread(need);

  // Threadless need (proactive play) → render the play layout. Pull the full
  // need detail (NeedPlayLayout consumes the GetNeed shape, not ConversationNeed).
  const { data: needDetail } = useNeed(!thread ? need.id : '');

  if (!thread) {
    const detail = needDetail?.need;
    if (!detail) return <ReadingLoader />;
    return (
      <div className="px-6 py-6">
        <NeedPlayLayout
          need={detail}
          onResolve={() => resolveNeed.mutate(need.id)}
          onSnooze={() => snoozeNeed.mutate({ needId: need.id, snoozedUntil: snoozeDefault() })}
          embedded
        />
      </div>
    );
  }

  return <ThreadReader threadId={thread.id} needType={need.type} needId={need.id} />;
}

function ThreadReader({
  threadId,
  needType,
  needId,
}: {
  threadId: string;
  needType: string;
  needId: string;
}) {
  const { data: threadData } = useThread(threadId);
  const { data: messagesData, refetch: refetchMessages } = useThreadMessages(threadId);
  const { data: draftData, refetch: refetchDraft } = useThreadDraft(threadId);

  // After a send, the draft clears AND a new sent message lands — refresh both.
  const refreshConversation = () => {
    void refetchDraft();
    void refetchMessages();
  };

  const [tab, setTab] = useState<'reply' | 'huddle'>('reply');
  const [pinnedInteractionId, setPinnedInteractionId] = useState<string | null>(null);

  const thread = threadData?.thread;
  const messages = messagesData?.messages || [];
  const customerId = thread?.customer?.id || null;
  const recipient = thread?.customer?.name || null;
  const resolved = thread?.status === 'resolved';
  const composeDraft = (draftData?.draft || null) as RawDraft | null;

  function handlePinHuddle(interactionId: string) {
    setPinnedInteractionId(interactionId);
    setTab('huddle');
  }

  return (
    <div className="flex min-h-full flex-col px-6 py-5">
      <ThreadHeader
        subject={thread?.subject ?? null}
        customerName={thread?.customer?.name}
        channel={thread?.channel}
        primaryNeedType={needType}
      />

      <ThreadNeeds threadId={threadId} className="mt-4" />

      {resolved && (
        <div className="mt-4 flex items-center gap-2 rounded-md border border-border bg-surface px-4 py-2.5">
          <span className="h-1.5 w-1.5 rounded-full bg-signal-ok" />
          <span className="font-mono text-[10px] font-semibold tracking-wider text-signal-ok">
            RESOLVED
          </span>
          <span className="text-xs text-fg-400">This conversation is closed.</span>
        </div>
      )}

      <div className="mt-5 flex-1">
        <MessageList messages={messages} onPinHuddle={handlePinHuddle} />
      </div>

      {!resolved && (
        <div className="mt-6 border-t border-border pt-4">
          <div className="mb-3 flex gap-1">
            <TabButton active={tab === 'reply'} onClick={() => setTab('reply')}>
              Reply
            </TabButton>
            <TabButton active={tab === 'huddle'} onClick={() => setTab('huddle')}>
              Internal huddle
            </TabButton>
          </div>

          {tab === 'reply' ? (
            <DraftPanel
              draft={composeDraft}
              threadId={threadId}
              recipient={recipient}
              needId={needId}
              onChanged={refreshConversation}
            />
          ) : (
            <HuddlePanel
              threadId={threadId}
              customerId={customerId}
              anchorInteractionId={pinnedInteractionId}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ----- Right rail ------------------------------------------------------------

type PlayNeedDetail = NonNullable<ReturnType<typeof useNeed>['data']>['need'];

/** Designed right rail for threadless play needs — the styled content that was previously
 *  the internal right column of NeedPlayLayout when shown standalone. */
function PlayRailContent({ need, sidekickCount = 0 }: { need: PlayNeedDetail; sidekickCount?: number }) {
  const navigate = useNavigate();
  const customerId = need.customer?.id || null;
  return (
    <div className="space-y-4 p-4">
      <div className="rounded-md border border-border bg-surface">
        <ContextRail customerId={customerId} />
      </div>

      {(need.agent_reasoning || need.lede) && (
        <SidekickObserved>
          {need.agent_reasoning || need.lede}
        </SidekickObserved>
      )}

      <div className="space-y-2">
        {customerId && (
          <button
            onClick={() => navigate(`/app/customers/${customerId}`)}
            className="flex w-full items-center justify-center gap-2 border border-charcoal-600 px-4 py-2.5 font-mono text-[11px] uppercase tracking-widest text-charcoal-400 transition-colors hover:text-cream-200"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Open customer
          </button>
        )}
        {sidekickCount > 0 && (
          <button
            onClick={() => navigate('/app/sidekick')}
            className="flex w-full items-center justify-center gap-2 border border-accent/30 bg-accent-bg px-4 py-2.5 font-mono text-[11px] uppercase tracking-widest text-accent shadow-[0_0_10px_var(--color-accent-glow)] transition-all hover:border-accent/60 hover:shadow-[0_0_18px_var(--color-accent-glow)]"
          >
            <Zap className="h-3.5 w-3.5" />
            Open Sidekick ({sidekickCount})
          </button>
        )}
      </div>
    </div>
  );
}

function RightRail({ need, sidekickCount = 0 }: { need: ConversationNeed; sidekickCount?: number }) {
  const navigate = useNavigate();
  const thread = primaryThread(need);
  return (
    <div className="space-y-4 p-4">
      <ContextRail customerId={need.customer_id} />
      {thread && (
        <div className="border-t border-[rgba(232,228,220,0.08)] pt-4">
          <div className="mb-3 flex items-center gap-2 px-0 font-mono text-[10px] font-semibold uppercase tracking-widest text-fg-400">
            <Pulse continuous />
            <span>Internal huddle</span>
          </div>
          <HuddlePanel threadId={thread.id} customerId={need.customer_id} />
        </div>
      )}
      <div className="space-y-2">
        {need.customer_id && (
          <button
            onClick={() => navigate(`/app/customers/${need.customer_id}`)}
            className="flex w-full items-center justify-center gap-2 border border-charcoal-600 px-4 py-2.5 font-mono text-[11px] uppercase tracking-widest text-charcoal-400 transition-colors hover:text-cream-200"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Open customer
          </button>
        )}
        {sidekickCount > 0 && (
          <button
            onClick={() => navigate('/app/sidekick')}
            className="flex w-full items-center justify-center gap-2 border border-accent/30 bg-accent-bg px-4 py-2.5 font-mono text-[11px] uppercase tracking-widest text-accent shadow-[0_0_10px_var(--color-accent-glow)] transition-all hover:border-accent/60 hover:shadow-[0_0_18px_var(--color-accent-glow)]"
          >
            <Zap className="h-3.5 w-3.5" />
            Open Sidekick ({sidekickCount})
          </button>
        )}
      </div>
    </div>
  );
}

// ----- States ----------------------------------------------------------------

function EmptyInbox({ hasNeeds }: { hasNeeds: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
      <h2 className="font-serif text-xl text-fg-100">
        {hasNeeds ? 'Nothing in this filter' : 'No conversations yet'}
      </h2>
      <p className="mx-auto mt-2 max-w-xs text-sm text-fg-400">
        {hasNeeds
          ? 'Try another filter to see open needs.'
          : 'When the signal watcher surfaces a need, it appears here grouped by what needs attention.'}
      </p>
    </div>
  );
}

function ReadingEmpty({ hasNeeds }: { hasNeeds: boolean }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-fg-400">
        <Pulse continuous />
        <span>Reading pane</span>
      </div>
      <h2 className="font-serif text-2xl text-fg-100">
        {hasNeeds ? 'Select a conversation' : 'Nothing to read yet'}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-fg-400">
        {hasNeeds
          ? 'Pick a need from the inbox to read its thread and compose a reply.'
          : 'Needs surfaced by the signal watcher will open here.'}
      </p>
    </div>
  );
}

function ReadingLoader() {
  return (
    <div className="flex h-full items-center justify-center py-16">
      <div className="flex items-center gap-2 text-fg-400">
        <Pulse continuous />
        <span className="font-mono text-xs uppercase tracking-widest">Loading conversation…</span>
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-sm px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors',
        active ? 'bg-surface-2 text-rust-400' : 'text-fg-400 hover:bg-surface-2 hover:text-fg-200',
      )}
    >
      {children}
    </button>
  );
}

function snoozeDefault(): Date {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d;
}
