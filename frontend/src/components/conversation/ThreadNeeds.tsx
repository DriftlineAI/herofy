// All un-resolved Needs on a thread (1:N fan-out). A draft-reply need and a
// risk need can coexist — each renders as its own card with severity treatment
// consistent with the Risk/Save surface on Customer Detail.

import { Link } from 'react-router-dom';
import { useNeedsForThread } from '@/lib/dataconnect-hooks';
import { cn } from '@/lib/utils';
import {
  needSeverity,
  severityDot,
  severityText,
  severityBorder,
  needTypeLabel,
  compareSeverity,
} from './conversationUtils';

interface ThreadNeed {
  id: string;
  type: string;
  headline: string | null;
  lede: string | null;
  priority_rank: number | null;
  created_at: string;
}

export function ThreadNeeds({ threadId, className }: { threadId: string; className?: string }) {
  const { data, isLoading } = useNeedsForThread(threadId);
  const needs: ThreadNeed[] = ((data?.needs as ThreadNeed[] | undefined) || [])
    .slice()
    .sort((a, b) => {
      const s = compareSeverity(needSeverity(a.type), needSeverity(b.type));
      if (s !== 0) return s;
      return (a.priority_rank ?? 999) - (b.priority_rank ?? 999);
    });

  if (isLoading) {
    return (
      <div className={cn('space-y-2', className)}>
        <div className="h-16 w-full animate-pulse rounded-md bg-surface-2" />
      </div>
    );
  }

  if (needs.length === 0) {
    return (
      <div className={cn('rounded-md border border-dashed border-border bg-surface px-3 py-2.5', className)}>
        <p className="text-xs text-fg-400">No open needs on this thread.</p>
      </div>
    );
  }

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] font-semibold tracking-widest text-fg-400">
          NEEDS ON THIS THREAD
        </span>
        <span className="font-mono text-[10px] text-rust-500">· {needs.length}</span>
      </div>
      {needs.map((need) => {
        const sev = needSeverity(need.type);
        return (
          <Link
            key={need.id}
            to={`/app/needs/${need.id}`}
            className={cn(
              'block rounded-md border border-border border-l-2 bg-surface px-3 py-2.5 transition-colors hover:bg-surface-2',
              severityBorder[sev],
            )}
          >
            <div className="flex items-center gap-2">
              <span className={cn('h-1.5 w-1.5 rounded-full', severityDot[sev])} />
              <span className={cn('font-mono text-[10px] font-semibold uppercase tracking-wider', severityText[sev])}>
                {needTypeLabel(need.type)}
              </span>
            </div>
            {need.headline && (
              <p className="mt-1 text-sm font-medium leading-snug text-fg-100">
                {need.headline}
              </p>
            )}
            {need.lede && <p className="mt-0.5 text-xs leading-relaxed text-fg-300">{need.lede}</p>}
          </Link>
        );
      })}
    </div>
  );
}
