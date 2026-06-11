import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageSquare } from 'lucide-react';
import {
  useConversationNeeds,
  useResolvedConversationNeeds,
  type ConversationNeed,
} from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import {
  GROUP_ORDER,
  WORKFLOW_FILTERS,
  workflowStatus,
  conversationGroup,
  channelTag,
  needSeverity,
  severityText,
  severityBorder,
  needTypeLabel,
  compareSeverity,
  Avatar,
  formatTime,
  type ConversationGroup,
  type WorkflowFilter,
} from '@/components/conversation/conversationUtils';
import { ScreenHeader, MobileLoading, MobileEmpty, formatARR } from '@/components/mobile/mobileShared';
import { cn } from '@/lib/utils';

// Internal need types live in the Sidekick tab, not the triage inbox.
const EXCLUDED = new Set(['sidekick_question', 'plan_approval_required']);

function primaryThread(need: ConversationNeed): ConversationNeed['threads'][number] | null {
  const threads = need.threads || [];
  return threads.find((t) => t.thread_type === 'customer') || threads[0] || null;
}

export default function MobileConversations() {
  const { data, isLoading, refetch } = useConversationNeeds();
  const { data: resolvedData, isLoading: resolvedLoading } = useResolvedConversationNeeds();
  const [filter, setFilter] = useState<WorkflowFilter['key']>('all');
  const navigate = useNavigate();
  useRefreshOnFocus(refetch);

  const showResolved = filter === 'resolved';
  const activeNeeds = useMemo(() => data?.needs || [], [data]);
  const resolvedNeeds = useMemo(() => resolvedData?.needs || [], [resolvedData]);
  const needs = showResolved ? resolvedNeeds : activeNeeds;
  const listLoading = showResolved ? resolvedLoading : isLoading;

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: activeNeeds.length, resolved: resolvedNeeds.length };
    for (const n of activeNeeds) {
      const s = workflowStatus(n);
      if (s === 'resolved') continue;
      c[s] = (c[s] || 0) + 1;
    }
    return c;
  }, [activeNeeds, resolvedNeeds]);

  const grouped = useMemo(() => {
    const base = needs.filter((n) => !EXCLUDED.has(n.type));
    const filtered = filter === 'all' || filter === 'resolved' ? base : base.filter((n) => workflowStatus(n) === filter);
    const map: Record<ConversationGroup, ConversationNeed[]> = { at_risk: [], support: [], prospects: [], other: [] };
    for (const n of filtered) map[conversationGroup(n.customer_lifecycle, n.type)].push(n);
    for (const key of Object.keys(map) as ConversationGroup[]) {
      map[key].sort((a, b) => {
        const s = compareSeverity(needSeverity(a.type), needSeverity(b.type));
        return s !== 0 ? s : a.priority_rank - b.priority_rank;
      });
    }
    return map;
  }, [needs, filter]);

  const totalShown = (Object.values(grouped) as ConversationNeed[][]).reduce((sum, list) => sum + list.length, 0);

  function openNeed(need: ConversationNeed) {
    const thread = primaryThread(need);
    if (thread) navigate(`/m/conversations/${thread.id}`);
    else if (need.customer_id) navigate(`/m/customers/${need.customer_id}`);
  }

  return (
    <div>
      <ScreenHeader eyebrow="Inbox" title="Conversations" sub={`${activeNeeds.length} open`} />

      {/* Filter chips */}
      <div className="no-scrollbar flex gap-2 overflow-x-auto border-b border-border px-4 pb-3">
        {WORKFLOW_FILTERS.map((f) => {
          const active = filter === f.key;
          return (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                'inline-flex shrink-0 items-center gap-1.5 rounded-sm border px-2.5 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-wider transition-colors',
                active ? 'border-rust-700 bg-accent-bg text-rust-400' : 'border-border text-fg-400',
              )}
            >
              {f.label}
              <span className={active ? 'text-rust-400' : 'text-fg-400'}>{counts[f.key] || 0}</span>
            </button>
          );
        })}
      </div>

      {listLoading ? (
        <MobileLoading />
      ) : totalShown === 0 ? (
        <MobileEmpty
          icon={<MessageSquare className="h-7 w-7" />}
          title={needs.length > 0 ? 'Nothing in this filter' : 'No conversations yet'}
          body={needs.length > 0 ? 'Try another filter.' : 'Surfaced needs appear here grouped by what needs attention.'}
        />
      ) : (
        <div className="pb-6">
          {GROUP_ORDER.map((group) => {
            const items = grouped[group.key];
            if (items.length === 0) return null;
            const alarm = group.key === 'at_risk';
            return (
              <section key={group.key}>
                <div className="flex items-center gap-2 border-b border-border bg-surface/40 px-4 py-2">
                  <span
                    className={cn(
                      'font-mono text-[11px] font-semibold uppercase tracking-widest',
                      alarm ? 'text-signal-bad' : 'text-fg-300',
                    )}
                  >
                    {group.label}
                  </span>
                  <span className="font-mono text-[11px] text-fg-400">· {items.length}</span>
                </div>
                {items.map((need) => (
                  <InboxRow key={need.id} need={need} onSelect={() => openNeed(need)} />
                ))}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function InboxRow({ need, onSelect }: { need: ConversationNeed; onSelect: () => void }) {
  const sev = needSeverity(need.type);
  const thread = primaryThread(need);
  const subject = thread?.subject || need.headline;
  const preview = thread?.latest_interaction?.summary_ai || need.lede || '';
  const when = thread?.latest_interaction?.occurred_at || need.updated_at;
  const channel = channelTag(thread?.channel);
  const unread = workflowStatus(need) === 'needs_response';

  return (
    <button
      onClick={onSelect}
      className={cn(
        'flex w-full gap-3 border-b border-l-[3px] border-b-border px-4 py-3 text-left',
        severityBorder[sev],
      )}
    >
      <Avatar name={need.customer_name} size="md" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-base font-semibold text-fg-100">{need.customer_name}</span>
          {unread && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-rust-500" />}
          <span className="ml-auto shrink-0 font-mono text-[9px] uppercase tracking-wider text-fg-400">
            {channel} · {formatTime(when)}
          </span>
        </div>
        <p className="mt-0.5 truncate text-[15px] font-medium text-fg-200">{subject}</p>
        {preview && <p className="mt-0.5 line-clamp-2 text-[13px] leading-snug text-fg-400">{preview}</p>}
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <span
            className={cn(
              'rounded-sm border border-border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider',
              severityText[sev],
            )}
          >
            {needTypeLabel(need.type)}
          </span>
          {need.customer_arr_cents != null && (
            <span className="font-mono text-[9px] uppercase tracking-wider text-fg-400">
              {formatARR(need.customer_arr_cents)} ARR
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
