// Focused inbox rail used inside the reading pane (ConversationDetail deep-link).
// Dense list of conversation NEEDS from useConversationNeeds; the need whose
// primary thread matches `activeThreadId` is highlighted. Mock-free: empty hook
// => clean empty state.

import { Link } from 'react-router-dom';
import { useConversationNeeds, type ConversationNeed } from '@/lib/dataconnect-hooks';
import { cn } from '@/lib/utils';
import {
  needSeverity,
  severityDot,
  severityText,
  severityBorder,
  channelTag,
  needTypeLabel,
  compareSeverity,
  Avatar,
  formatTime,
} from './conversationUtils';

interface ThreadListRailProps {
  activeThreadId?: string;
}

function primaryThread(need: ConversationNeed): ConversationNeed['threads'][number] | null {
  const threads = need.threads || [];
  return threads.find((t) => t.thread_type === 'customer') || threads[0] || null;
}

export function ThreadListRail({ activeThreadId }: ThreadListRailProps) {
  const { data, isLoading } = useConversationNeeds();
  const needs = (data?.needs || [])
    .slice()
    .sort((a, b) => {
      const s = compareSeverity(needSeverity(a.type), needSeverity(b.type));
      if (s !== 0) return s;
      return a.priority_rank - b.priority_rank;
    });

  if (isLoading) {
    return (
      <div className="space-y-2 p-3">
        <div className="h-16 animate-pulse rounded-md bg-surface-2" />
        <div className="h-16 animate-pulse rounded-md bg-surface-2" />
      </div>
    );
  }

  if (needs.length === 0) {
    return (
      <div className="px-4 py-8 text-center">
        <p className="text-xs text-fg-400">No open conversations.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="border-b border-border px-4 py-2.5 font-mono text-[10px] font-semibold uppercase tracking-widest text-fg-400">
        Inbox · {needs.length}
      </div>
      {needs.map((need) => {
        const sev = needSeverity(need.type);
        const thread = primaryThread(need);
        const subject = thread?.subject || need.headline;
        const active = !!thread && thread.id === activeThreadId;
        const to = thread ? `/app/conversations/${thread.id}` : `/app/needs/${need.id}`;
        return (
          <Link
            key={need.id}
            to={to}
            className={cn(
              'flex gap-3 border-b border-l-2 border-border px-4 py-3 transition-colors',
              severityBorder[sev],
              active ? 'bg-surface-2' : 'hover:bg-surface',
            )}
          >
            <Avatar name={need.customer_name} size="sm" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', severityDot[sev])} />
                <span className="truncate text-[13px] font-semibold text-fg-100">
                  {need.customer_name}
                </span>
                <span className="ml-auto shrink-0 font-mono text-[9px] uppercase tracking-wider text-fg-400">
                  {channelTag(thread?.channel)} · {formatTime(thread?.updated_at || need.updated_at)}
                </span>
              </div>
              <p className="mt-0.5 truncate text-xs text-fg-200">{subject}</p>
              <span
                className={cn(
                  'mt-1 inline-block font-mono text-[9px] font-semibold uppercase tracking-wider',
                  severityText[sev],
                )}
              >
                {needTypeLabel(need.type)}
              </span>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
