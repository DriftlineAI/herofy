import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, ChevronRight } from 'lucide-react';
import {
  useSidekickQuestions,
  useRunningAgents,
  useRecentlyResolvedRuns,
  type SidekickQueueItem,
} from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import { ScreenHeader, MobileLoading, MobileError, MobileEmpty, formatARR, timeAgo } from '@/components/mobile/mobileShared';
import { cn } from '@/lib/utils';

type Tag = 'block' | 'follow' | 'low';
type FilterId = 'all' | Tag;

function deriveTag(item: SidekickQueueItem): Tag {
  const waitMs = Date.now() - new Date(item.created_at).getTime();
  if (item.is_blocking !== false) return 'block';
  if (waitMs < 30 * 60 * 1000) return 'low';
  return 'follow';
}

const TAG_LABEL: Record<Tag, string> = { block: 'Blocking', follow: 'Follow-up', low: 'Low' };

export default function MobileSidekick() {
  const { data, isLoading, error, refetch } = useSidekickQuestions();
  const { data: runningAgents } = useRunningAgents();
  const { data: resolvedRuns } = useRecentlyResolvedRuns();
  const navigate = useNavigate();
  useRefreshOnFocus(refetch);

  const [filter, setFilter] = useState<FilterId>('all');

  const rows = useMemo(
    () => (data?.items || []).map((item) => ({ item, tag: deriveTag(item) })),
    [data?.items],
  );

  const counts: Record<FilterId, number> = {
    all: rows.length,
    block: rows.filter((r) => r.tag === 'block').length,
    follow: rows.filter((r) => r.tag === 'follow').length,
    low: rows.filter((r) => r.tag === 'low').length,
  };

  const shown = filter === 'all' ? rows : rows.filter((r) => r.tag === filter);
  const arrBlocked = useMemo(
    () => (data?.items || []).reduce((sum, i) => sum + (i.customer_arr_cents || 0), 0),
    [data?.items],
  );

  const filters: { id: FilterId; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'block', label: 'Blocking' },
    { id: 'follow', label: 'Follow-up' },
    { id: 'low', label: 'Low' },
  ];

  return (
    <div>
      <ScreenHeader
        eyebrow="Sidekick // Mission Control"
        title="The bridge"
        sub="What the agents need from you."
      />

      {/* Compact telemetry */}
      <div className="grid grid-cols-3 gap-px border-y border-border bg-border">
        <Stat label="Open" value={rows.length} />
        <Stat label="Blocking" value={counts.block} tone={counts.block > 0 ? 'alarm' : undefined} />
        <Stat label="ARR blocked" value={formatARR(arrBlocked)} />
        <Stat label="Running" value={runningAgents.length} tone="accent" />
        <Stat label="Resolved" value={resolvedRuns.length} />
        <Stat
          label="Oldest"
          value={rows.length ? timeAgo([...rows].sort((a, b) => +new Date(a.item.created_at) - +new Date(b.item.created_at))[0].item.created_at) : '–'}
        />
      </div>

      {/* Filter chips */}
      <div className="no-scrollbar flex gap-2 overflow-x-auto px-4 py-3">
        {filters.map((f) => {
          const active = filter === f.id;
          return (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={cn(
                'inline-flex shrink-0 items-center gap-1.5 rounded-sm border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wider transition-colors',
                active ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border text-fg-400',
              )}
            >
              {f.label}
              <span>{counts[f.id]}</span>
            </button>
          );
        })}
      </div>

      {error ? (
        <MobileError message="Failed to load Sidekick questions" onRetry={() => refetch()} />
      ) : isLoading ? (
        <MobileLoading />
      ) : shown.length === 0 ? (
        <MobileEmpty
          icon={<Zap className="h-7 w-7 text-accent" />}
          title="Queue clear"
          body="Nothing needs you right now. Sidekick is running autonomously."
        />
      ) : (
        <div className="space-y-3 px-4 pb-6">
          {shown.map(({ item, tag }) => {
            const waitMs = Date.now() - new Date(item.created_at).getTime();
            const arr = formatARR(item.customer_arr_cents);
            return (
              <button
                key={item.id}
                onClick={() => item.run_id && navigate(`/m/sidekick/${item.run_id}`)}
                className={cn(
                  'block w-full rounded-md border border-border bg-surface p-4 text-left',
                  tag === 'block' && 'edge-brass',
                )}
              >
                <div className="mb-2 flex items-center gap-2">
                  <span
                    className={cn(
                      'h-1.5 w-1.5 rounded-full',
                      tag === 'block' ? 'bg-accent' : tag === 'follow' ? 'bg-signal-warn' : 'bg-fg-400',
                    )}
                  />
                  <span className="font-mono text-[9px] tracking-wider text-fg-400">{item.refcode}</span>
                  <span
                    className={cn(
                      'ml-auto rounded-sm border px-1.5 py-0.5 font-mono text-[8.5px] uppercase tracking-wider',
                      tag === 'block'
                        ? 'border-accent/30 text-accent'
                        : tag === 'follow'
                          ? 'border-signal-warn/30 text-signal-warn'
                          : 'border-border text-fg-400',
                    )}
                  >
                    {TAG_LABEL[tag]}
                  </span>
                </div>
                <h3 className="font-display text-xl leading-none text-fg-100">{item.customer_name}</h3>
                <p className="mt-1.5 line-clamp-2 text-[14px] leading-snug text-fg-300">
                  {item.questions[0]?.text || item.context}
                </p>
                <div className="mt-2.5 flex items-center gap-2 font-mono text-[9px] tracking-wider text-fg-400">
                  {arr !== '-' && <span className="text-fg-200">{arr}</span>}
                  {arr !== '-' && <span>·</span>}
                  <span className={cn(waitMs > 2 * 3600000 && 'text-signal-warn')}>{timeAgo(item.created_at)}</span>
                  <span className="ml-auto">{item.agent_type.replace(/_/g, '-')}</span>
                  <ChevronRight className="h-4 w-4" />
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: 'alarm' | 'accent';
}) {
  return (
    <div className="bg-page px-3 py-2.5">
      <div className="font-mono text-[8.5px] uppercase tracking-[0.2em] text-fg-400">{label}</div>
      <div
        className={cn(
          'mt-0.5 font-display text-lg leading-none',
          tone === 'alarm' ? 'text-signal-bad' : tone === 'accent' ? 'text-accent' : 'text-fg-100',
        )}
      >
        {value}
      </div>
    </div>
  );
}
