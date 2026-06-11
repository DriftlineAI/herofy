import React from 'react';
import type { RunningAgentItem, ResolvedRunItem } from '@/lib/dataconnect-hooks';
import type { SidekickQueueItem } from '@/lib/dataconnect-hooks';

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
}

function formatArr(cents: number | null): string {
  if (!cents) return '';
  const d = cents / 100;
  if (d >= 1_000_000) return `$${(d / 1_000_000).toFixed(1)}M`;
  if (d >= 1_000) return `$${Math.round(d / 1_000)}K`;
  return `$${Math.round(d)}`;
}

interface LiveOpsRailProps {
  running: RunningAgentItem[];
  resolved: ResolvedRunItem[];
  queueItems: SidekickQueueItem[];
}

function StepBar({ totalSteps = 8, completedStr }: { totalSteps?: number; completedStr?: string | null }) {
  // Parse "3/8" or "step 3 of 8" etc.
  let done = 0;
  let total = totalSteps;
  if (completedStr) {
    const m = completedStr.match(/(\d+)\s*[/of]+\s*(\d+)/);
    if (m) { done = parseInt(m[1], 10); total = parseInt(m[2], 10); }
  }
  return (
    <div className="flex gap-0.5 mt-2">
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className="h-0.5 flex-1"
          style={{
            background: i < done - 1
              ? 'var(--color-accent)'
              : i === done - 1
              ? 'var(--color-accent)'
              : 'var(--color-border)',
            animation: i === done - 1 ? 'ai-step 1.4s ease-in-out infinite' : undefined,
            opacity: i === done - 1 ? undefined : undefined,
          }}
        />
      ))}
    </div>
  );
}

// Aggregate ARR blocked by customer from queue items
interface ArrBlockedRow {
  customer_name: string;
  arr_cents: number;
}

function getArrBlockedRows(items: SidekickQueueItem[]): ArrBlockedRow[] {
  const map = new Map<string, number>();
  for (const item of items) {
    if (!item.customer_arr_cents) continue;
    const prev = map.get(item.customer_name) || 0;
    map.set(item.customer_name, Math.max(prev, item.customer_arr_cents));
  }
  return Array.from(map.entries())
    .map(([customer_name, arr_cents]) => ({ customer_name, arr_cents }))
    .sort((a, b) => b.arr_cents - a.arr_cents)
    .slice(0, 5);
}

export function LiveOpsRail({ running, resolved, queueItems }: LiveOpsRailProps) {
  const arrRows = getArrBlockedRows(queueItems);
  const maxArr = arrRows[0]?.arr_cents || 1;

  return (
    <div className="flex-1 min-h-0 overflow-y-auto">
      {/* Agents running */}
      <div className="px-4 pt-4 pb-3 border-b border-border">
        <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.22em] text-fg-400 mb-3">
          Agents running
          <span className="ml-auto text-accent">{running.length || '—'}</span>
        </div>

        {running.length === 0 ? (
          <div className="font-mono text-[10px] text-fg-400 uppercase tracking-[0.16em]">None active</div>
        ) : (
          <div className="space-y-4">
            {running.map(r => (
              <div key={r.id} className="border-l-2 border-accent pl-3">
                <div className="font-display text-[19px] leading-none text-fg-100 mb-1">
                  {r.customer_name}
                </div>
                <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-accent mb-2">
                  {r.agent_name.replace(/_/g, '-')}
                </div>
                {r.current_step && (
                  <div className="font-mono text-[10px] text-fg-300 flex gap-1.5 flex-wrap">
                    <span className="text-accent-hover">running</span>
                    <span className="text-border-strong">//</span>
                    <span className="line-clamp-1">{r.current_step.replace(/_/g, ' ')}</span>
                  </div>
                )}
                <StepBar completedStr={r.current_step} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Resolved today */}
      <div className="px-4 pt-4 pb-3 border-b border-border">
        <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.22em] text-fg-400 mb-3">
          Resolved · today
          <span className="ml-auto text-accent">{resolved.length || '0'}</span>
        </div>

        {resolved.length === 0 ? (
          <div className="font-mono text-[10px] text-fg-400 uppercase tracking-[0.16em]">None yet</div>
        ) : (
          <div className="divide-y divide-border/40">
            {resolved.slice(0, 8).map(r => (
              <div key={r.id} className="flex gap-2.5 items-start py-2">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-signal-ok mt-0.5 shrink-0 opacity-85 flex-shrink-0">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
                <div>
                  <div className="font-sans text-[13px] font-medium text-fg-300 leading-snug">
                    <strong className="text-fg-100 font-semibold">{r.customer_name}</strong>{' '}
                    {r.agent_name.replace(/_/g, '-')} completed.
                  </div>
                  <div className="font-mono text-[8.5px] uppercase tracking-[0.1em] text-fg-400 mt-0.5">
                    {formatTime(r.completed_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ARR blocked by account */}
      {arrRows.length > 0 && (
        <div className="px-4 pt-4 pb-3">
          <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-fg-400 mb-3">
            ARR blocked · by account
          </div>
          <div className="space-y-3">
            {arrRows.map(row => (
              <div key={row.customer_name}>
                <div className="flex justify-between font-mono text-[10px] text-fg-300 mb-1">
                  <span>{row.customer_name}</span>
                  <span className="text-fg-400">{formatArr(row.arr_cents)}</span>
                </div>
                <div className="h-0.5 bg-border relative">
                  <span
                    className="absolute left-0 top-0 bottom-0 bg-accent"
                    style={{ width: `${(row.arr_cents / maxArr) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
