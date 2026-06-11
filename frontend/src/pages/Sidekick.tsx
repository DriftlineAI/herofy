import React, { useEffect, useRef, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  useSidekickQuestions,
  useRunningAgents,
  useRecentlyResolvedRuns,
  type SidekickQueueItem,
} from '@/lib/dataconnect-hooks';
import { useWorkspaceNotifications, useRefreshOnFocus } from '@/lib/realtime-hooks';
import { useWorkspace } from '@/lib/workspace';
import { TelemetryStrip } from '@/components/sidekick/TelemetryStrip';
import { TriageQueue, type QueueRow, type FilterId, type QueueTag } from '@/components/sidekick/TriageQueue';
import { FocusPane } from '@/components/sidekick/FocusPane';
import { LiveOpsRail } from '@/components/sidekick/LiveOpsRail';

// ai-step animation for live-ops step bars
const AI_STEP_STYLE = `
@keyframes ai-step {
  0%, 100% { opacity: 0.35; }
  50% { opacity: 1; }
}
`;

function deriveTag(item: SidekickQueueItem): QueueTag {
  const waitMs = Date.now() - new Date(item.created_at).getTime();
  if (item.is_blocking !== false) return 'block';
  if (waitMs < 30 * 60 * 1000) return 'low'; // <30min non-blocking = Low
  return 'follow';
}

export default function Sidekick() {
  const navigate = useNavigate();
  const { workspaceId } = useWorkspace();

  const { data, isLoading, error, refetch } = useSidekickQuestions();
  const { data: runningAgents, refetch: refetchRunning } = useRunningAgents();
  const { data: resolvedRuns, refetch: refetchResolved } = useRecentlyResolvedRuns();

  useRefreshOnFocus(refetch);

  // Real-time count-based refetch
  const notifications = useWorkspaceNotifications(workspaceId);
  const prevCountRef = useRef<number | null>(null);
  useEffect(() => {
    if (notifications?.sidekick_questions === undefined) return;
    const prev = prevCountRef.current;
    const next = notifications.sidekick_questions;
    let timer: ReturnType<typeof setTimeout> | null = null;
    if (prev !== null && prev !== next) {
      timer = setTimeout(() => { refetch(); refetchRunning(); refetchResolved(); }, 300);
    }
    prevCountRef.current = next;
    return () => { if (timer) clearTimeout(timer); };
  }, [notifications?.sidekick_questions, refetch, refetchRunning, refetchResolved]);

  const queueItems = data?.items || [];

  // Build queue rows with tags
  const queueRows = useMemo((): QueueRow[] =>
    queueItems.map(item => ({
      item,
      tag: deriveTag(item),
      waitMs: Date.now() - new Date(item.created_at).getTime(),
    })),
    [queueItems]
  );

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterId>('all');

  // Auto-select first item on load
  useEffect(() => {
    if (queueRows.length > 0 && !selectedId) {
      setSelectedId(queueRows[0].item.id);
    }
  }, [queueRows.length]);

  const selectedItem = queueItems.find(i => i.id === selectedId) || null;

  const handleSelectRow = (id: string) => {
    setSelectedId(id);
  };

  // Telemetry aggregates
  const telemetry = useMemo(() => {
    const blocking = queueRows.filter(r => r.tag === 'block').length;
    const followUp = queueRows.filter(r => r.tag === 'follow').length;
    const arrBlockedCents = queueItems.reduce((sum, i) => sum + (i.customer_arr_cents || 0), 0);
    const uniqueBlockedAccounts = new Set(queueItems.filter(i => i.customer_arr_cents).map(i => i.customer_id)).size;
    const oldest = queueRows.sort((a, b) => b.waitMs - a.waitMs)[0];
    return {
      questionsOpen: queueRows.length,
      questionsBlocking: blocking,
      questionsFollowUp: followUp,
      arrBlockedCents,
      accountsBlocked: uniqueBlockedAccounts,
      oldestWaitMs: oldest?.waitMs || 0,
      oldestWaitCustomer: oldest?.item.customer_name || '',
      oldestWaitAgent: oldest?.item.agent_type || '',
    };
  }, [queueRows, queueItems]);

  if (error) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-center py-16">
        <p className="text-signal-bad mb-4 font-sans">Failed to load Sidekick questions</p>
        <button
          onClick={() => refetch()}
          className="inline-flex items-center gap-2 px-4 py-2 bg-surface-2 hover:bg-border text-fg-200 font-mono text-xs uppercase tracking-widest transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <style>{AI_STEP_STYLE}</style>

      {/* Full-height flex column — same height approach as Conversations */}
      <div className="@container flex flex-col h-[calc(100dvh-17.5rem)] min-h-0">

        {/* Page header */}
        <div className="flex-shrink-0 px-8 pt-5 pb-0">
          <div className="flex items-end justify-between gap-8">
            <div>
              <div className="flex items-center gap-2.5 mb-2.5 font-mono text-[10px] uppercase tracking-[0.28em]">
                <span className="flex items-center gap-1.5 text-accent">
                  <span className="relative w-1.5 h-1.5 rounded-full bg-accent">
                    <span className="absolute inset-0 rounded-full bg-accent animate-ping opacity-70" />
                  </span>
                  Sidekick
                </span>
                <span className="text-border-strong">//</span>
                <span className="text-fg-400">Mission_Control</span>
              </div>
              <h1 className="font-display text-[48px] leading-none text-fg-100 mb-0">
                The bridge<em className="font-sans italic not-uppercase text-accent text-[0.7em]">.</em>
              </h1>
              <p className="font-sans italic font-medium text-[17px] text-fg-300 mt-2 max-w-[520px]">
                What the agents need from you — and what they're getting done without you.
              </p>
            </div>

            {/* Scope control */}
            <div className="flex border border-border rounded-sm overflow-hidden flex-shrink-0 mb-1">
              {['My desk', 'Team', 'Portfolio'].map((label, i) => (
                <button
                  key={label}
                  disabled={i > 0}
                  className={cn(
                    'font-mono text-[10px] uppercase tracking-[0.16em] px-4 py-2 border-r border-border last:border-r-0 transition-all',
                    i === 0
                      ? 'bg-accent text-page'
                      : 'bg-transparent text-fg-400 opacity-40 cursor-not-allowed'
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Telemetry strip */}
          <TelemetryStrip
            agentsRunning={runningAgents.length}
            customersWithRunning={new Set(runningAgents.map(r => r.customer_name)).size}
            questionsOpen={telemetry.questionsOpen}
            questionsBlocking={telemetry.questionsBlocking}
            questionsFollowUp={telemetry.questionsFollowUp}
            arrBlockedCents={telemetry.arrBlockedCents}
            accountsBlocked={telemetry.accountsBlocked}
            oldestWaitMs={telemetry.oldestWaitMs}
            oldestWaitCustomer={telemetry.oldestWaitCustomer}
            oldestWaitAgent={telemetry.oldestWaitAgent}
            resolvedToday={resolvedRuns.length}
            resolvedDelta={0}
          />
        </div>

        {/* Three-pane cockpit. Stacks below a ~1152px CONTAINER width (not viewport) so it
            collapses cleanly when the Sidekick drawer narrows the content instead of overlapping. */}
        <div className="flex-1 min-h-0 grid grid-cols-1 @6xl:grid-cols-[384px_minmax(0,1fr)_326px] overflow-y-auto @6xl:overflow-visible mx-8 mb-7 mt-5 border border-border bg-page/50 shadow-lift">

          {/* Pane 1 — Triage Queue */}
          <div className="border-b @6xl:border-b-0 @6xl:border-r border-border min-h-0 flex flex-col">
            {isLoading ? (
              <div className="p-4 space-y-3 animate-pulse">
                {[1, 2, 3].map(i => <div key={i} className="h-24 bg-surface-2 rounded" />)}
              </div>
            ) : (
              <TriageQueue
                rows={queueRows}
                selectedId={selectedId}
                filter={filter}
                onSelectFilter={setFilter}
                onSelectRow={handleSelectRow}
              />
            )}
          </div>

          {/* Pane 2 — Focus */}
          <div className="min-h-0 flex flex-col">
            <div className="flex-shrink-0 flex items-center gap-2 px-[18px] py-3.5 border-b border-border font-mono text-[10.5px] uppercase tracking-[0.24em] text-accent">
              Focus
              <span className="flex-1" />
              {selectedItem && (
                <span className="font-mono text-[9.5px] tracking-[0.12em] text-fg-400">{selectedItem.refcode}</span>
              )}
            </div>
            <FocusPane
              item={selectedItem}
              onAnswered={() => {
                refetch();
                // Move to next item
                const idx = queueRows.findIndex(r => r.item.id === selectedId);
                const next = queueRows[idx + 1]?.item.id || queueRows[0]?.item.id || null;
                if (next !== selectedId) setSelectedId(next);
              }}
            />
          </div>

          {/* Pane 3 — Live Ops */}
          <div className="border-t @6xl:border-t-0 @6xl:border-l border-border min-h-0 flex flex-col bg-surface/30">
            <div className="flex-shrink-0 flex items-center gap-2 px-[18px] py-3.5 border-b border-border font-mono text-[10.5px] uppercase tracking-[0.24em] text-accent">
              <span className="relative w-1.5 h-1.5 rounded-full bg-accent flex-shrink-0">
                <span className="absolute inset-0 rounded-full bg-accent animate-ping opacity-70" />
              </span>
              Live ops
            </div>
            <LiveOpsRail
              running={runningAgents}
              resolved={resolvedRuns}
              queueItems={queueItems}
            />
          </div>
        </div>
      </div>
    </>
  );
}
