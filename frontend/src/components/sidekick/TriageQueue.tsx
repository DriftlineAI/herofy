import React from 'react';
import { cn } from '@/lib/utils';
import type { SidekickQueueItem } from '@/lib/dataconnect-hooks';

export type QueueTag = 'block' | 'follow' | 'low';

export interface QueueRow {
  item: SidekickQueueItem;
  tag: QueueTag;
  waitMs: number;
}

export type FilterId = 'all' | 'block' | 'follow' | 'low';

interface TriageQueueProps {
  rows: QueueRow[];
  selectedId: string | null;
  filter: FilterId;
  onSelectFilter: (f: FilterId) => void;
  onSelectRow: (id: string) => void;
}

const TAG_LABEL: Record<QueueTag, string> = {
  block: 'Blocking',
  follow: 'Follow-up',
  low: 'Low',
};

function formatWait(ms: number): string {
  if (ms <= 0) return 'just now';
  const mins = Math.floor(ms / 60000);
  const hours = Math.floor(ms / 3600000);
  const days = Math.floor(ms / 86400000);
  if (days >= 1) return `${days}d ${hours % 24}h`;
  if (hours >= 1) return `${hours}h ${mins % 60}m`;
  return `${mins}m`;
}

function formatArr(cents: number | null): string {
  if (!cents) return '';
  const dollars = cents / 100;
  if (dollars >= 1_000_000) return `$${(dollars / 1_000_000).toFixed(1)}M`;
  if (dollars >= 1_000) return `$${Math.round(dollars / 1_000)}K`;
  return `$${Math.round(dollars)}`;
}

export function TriageQueue({
  rows,
  selectedId,
  filter,
  onSelectFilter,
  onSelectRow,
}: TriageQueueProps) {
  const counts: Record<FilterId, number> = {
    all: rows.length,
    block: rows.filter(r => r.tag === 'block').length,
    follow: rows.filter(r => r.tag === 'follow').length,
    low: rows.filter(r => r.tag === 'low').length,
  };

  const filters: { id: FilterId; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'block', label: 'Blocking' },
    { id: 'follow', label: 'Follow-up' },
    { id: 'low', label: 'Low' },
  ];

  const shown = filter === 'all' ? rows : rows.filter(r => r.tag === filter);

  return (
    <div className="flex flex-col min-h-0">
      {/* Pane header */}
      <div className="flex-shrink-0 flex items-center gap-2 px-[18px] py-3.5 border-b border-border font-mono text-[10.5px] uppercase tracking-[0.24em] text-accent">
        Needs you
        <span className="text-accent-hover text-[12px]">[{shown.length}]</span>
        <span className="flex-1" />
        <span className="font-mono text-[9.5px] tracking-[0.12em] text-fg-400">Most at stake ↓</span>
      </div>

      {/* Filter chips */}
      <div className="flex-shrink-0 flex gap-1.5 px-3.5 py-3 border-b border-border">
        {filters.map(f => (
          <button
            key={f.id}
            onClick={() => onSelectFilter(f.id)}
            className={cn(
              'inline-flex items-center gap-1.5 font-mono text-[9.5px] uppercase tracking-[0.14em] px-2.5 py-1.5 border rounded-sm transition-all duration-150',
              filter === f.id
                ? 'border-accent/40 text-accent-hover bg-accent/7'
                : 'border-border text-fg-400 bg-transparent hover:text-fg-200 hover:border-border-strong'
            )}
          >
            {f.label}
            <span className={cn(filter === f.id ? 'text-accent-hover' : 'text-fg-300')}>
              {counts[f.id]}
            </span>
          </button>
        ))}
      </div>

      {/* Queue list */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {shown.length === 0 ? (
          <div className="text-center py-12 text-fg-400 font-mono text-[11px] uppercase tracking-[0.2em]">
            No items
          </div>
        ) : (
          shown.map(({ item, tag, waitMs }) => {
            const isSelected = selectedId === item.id;
            const isOld = waitMs > 2 * 3600000; // > 2h
            const arr = formatArr(item.customer_arr_cents);
            const agentLabel = item.agent_type.replace(/_/g, '-');

            return (
              <button
                key={item.id}
                onClick={() => onSelectRow(item.id)}
                className={cn(
                  'relative w-full text-left border-b border-l-[3px] [border-bottom-color:rgba(232,228,220,0.08)] px-[18px] py-[15px] block transition-all duration-150',
                  isSelected
                    ? 'border-l-accent bg-surface-2'
                    : 'border-l-transparent bg-transparent hover:bg-surface'
                )}
              >
                {/* Top row */}
                <div className="flex items-center gap-2 mb-2.5">
                  <span className={cn(
                    'w-[7px] h-[7px] rounded-full flex-shrink-0 relative',
                    tag === 'block' ? 'bg-accent' : tag === 'follow' ? 'bg-signal-warn' : 'bg-border-strong'
                  )}>
                    {tag === 'block' && (
                      <span className="absolute inset-0 rounded-full bg-accent animate-ping opacity-70" />
                    )}
                  </span>
                  <span className={cn(
                    'font-mono text-[10px] tracking-[0.04em]',
                    isSelected ? 'text-accent-hover' : 'text-fg-400'
                  )}>
                    {item.refcode}
                  </span>
                  <span className="ml-auto font-mono text-[8.5px] uppercase tracking-[0.12em] px-1.5 py-0.5 rounded-sm border"
                    style={
                      tag === 'block'
                        ? { color: 'var(--color-accent-hover)', background: 'rgba(200,144,28,0.10)', borderColor: 'rgba(200,144,28,0.28)' }
                        : tag === 'follow'
                        ? { color: 'var(--color-signal-warn)', background: 'rgba(245,158,11,0.08)', borderColor: 'rgba(245,158,11,0.24)' }
                        : { color: 'var(--color-fg-400)', borderColor: 'var(--color-border)' }
                    }
                  >
                    {TAG_LABEL[tag]}
                  </span>
                </div>

                {/* Customer name */}
                <h3 className="font-display text-[23px] leading-none text-fg-100 mb-1.5">
                  {item.customer_name}
                </h3>

                {/* Question summary */}
                <p className="font-sans text-[13.5px] font-medium text-fg-300 leading-snug mb-2.5 max-w-[320px] line-clamp-2">
                  {item.questions[0]?.text || item.context}
                </p>

                {/* Footer */}
                <div className="flex items-center gap-2 font-mono text-[9.5px] tracking-[0.04em] text-fg-400 whitespace-nowrap">
                  {arr && <span className="text-fg-200">{arr}</span>}
                  {arr && <span className="text-border-strong">·</span>}
                  <span className={cn(isOld && 'text-signal-warn')}>
                    {formatWait(waitMs)}
                  </span>
                  <span className="ml-auto text-border-strong">{agentLabel}</span>
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
