import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface BriefingRailProps {
  agentName: string;
  customerName: string;
  refcode: string;
  arrCents?: number | null;
  // Why this batch
  batchRationale: string;
  // Progress
  answeredCount: number;
  totalCount: number;
  // Actions
  onSubmit: () => void;
  onDecideRest: () => void;
  onSaveDraft: () => void;
  isSubmitting?: boolean;
  canSubmit?: boolean;
}

function formatArr(cents?: number | null): string {
  if (!cents) return '';
  const d = cents / 100;
  if (d >= 1_000_000) return `$${(d / 1_000_000).toFixed(1)}M ARR`;
  if (d >= 1_000) return `$${Math.round(d / 1_000)}K ARR`;
  return `$${Math.round(d)} ARR`;
}

export function BriefingRail({
  agentName,
  customerName,
  refcode,
  arrCents,
  batchRationale,
  answeredCount,
  totalCount,
  onSubmit,
  onDecideRest,
  onSaveDraft,
  isSubmitting,
  canSubmit,
}: BriefingRailProps) {
  const agentLabel = agentName.replace(/_/g, '-');
  const arrLabel = formatArr(arrCents);

  return (
    <aside className="flex flex-col gap-0 border-r border-border bg-surface/45">
      {/* Who's asking */}
      <div className="px-6 pt-7 pb-5 border-b border-border">
        <div className="font-mono text-[9px] uppercase tracking-[0.24em] text-accent mb-3">Who's asking</div>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 border border-accent/40 flex items-center justify-center text-accent flex-shrink-0">
            <span className="font-display text-[13px]">SK</span>
          </div>
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-fg-100">{agentLabel}</div>
            <div className="font-sans text-[12px] font-medium text-fg-400 mt-0.5">
              Working on {customerName}
            </div>
          </div>
        </div>
      </div>

      {/* The account */}
      <div className="px-6 py-5 border-b border-border">
        <div className="font-mono text-[9px] uppercase tracking-[0.24em] text-accent mb-3">The account</div>
        <h2 className="font-display text-[30px] leading-none text-fg-100 mb-1.5">{customerName}</h2>
        <div className="font-mono text-[10px] tracking-[0.08em] text-fg-400">
          {refcode}
          {arrLabel && <span> · {arrLabel}</span>}
        </div>
      </div>

      {/* Why this batch */}
      <div className="px-6 py-5 border-b border-border flex-1">
        <div className="font-mono text-[9px] uppercase tracking-[0.24em] text-accent mb-3">Why this batch</div>
        <p className="font-sans text-[13.5px] font-medium leading-relaxed text-fg-300">
          I'd rather ask <strong className="text-fg-100 font-semibold">{totalCount} things once</strong> than ping you {totalCount} times.
          Answer what you can — leave the rest, or tell me to decide.
        </p>
        {batchRationale && (
          <p className="font-sans text-[13px] font-medium leading-relaxed text-fg-400 mt-2">
            {batchRationale}
          </p>
        )}
        <p className="font-sans text-[13px] text-fg-400 leading-relaxed mt-3">
          If you only have a minute, answer Q1. That's the hard block; the others I can move forward on with a reasonable default.
        </p>
      </div>

      {/* Progress + actions — pinned to bottom */}
      <div className="px-6 py-5 border-t border-border mt-auto">
        <div className="flex items-baseline gap-2 font-mono text-[10px] tracking-[0.08em] uppercase text-fg-400 mb-3">
          <span className="text-fg-100 text-[17px] font-normal">{answeredCount}</span>
          of {totalCount} answered
        </div>

        {/* Tick bar */}
        <div className="flex gap-1 mb-4">
          {Array.from({ length: totalCount }).map((_, i) => (
            <span
              key={i}
              className={cn('h-1 flex-1', i < answeredCount ? 'bg-accent' : 'bg-border')}
            />
          ))}
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-2">
          <button
            onClick={onSubmit}
            disabled={!canSubmit || isSubmitting}
            className={cn(
              'w-full flex items-center justify-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.18em] px-4 py-2.5 transition-all rounded-sm',
              canSubmit
                ? 'bg-accent text-page hover:bg-accent-hover border border-accent'
                : 'bg-surface-2 text-fg-400 cursor-not-allowed border border-border'
            )}
          >
            {isSubmitting ? (
              <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Sending…</span></>
            ) : (
              'Send · resume agent →'
            )}
          </button>

          <button
            onClick={onDecideRest}
            className="w-full font-mono text-[10.5px] uppercase tracking-[0.18em] px-4 py-2 border border-border text-fg-300 hover:text-fg-100 hover:border-border-strong transition-all rounded-sm"
          >
            Sidekick, decide the rest
          </button>

          <button
            onClick={onSaveDraft}
            className="w-full font-mono text-[10.5px] uppercase tracking-[0.18em] px-4 py-2 border border-border text-fg-400 hover:text-fg-200 hover:border-border-strong transition-all rounded-sm"
          >
            Save draft
          </button>
        </div>
      </div>
    </aside>
  );
}
