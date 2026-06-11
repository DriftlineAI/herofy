import React from 'react';
import { cn } from '@/lib/utils';
import type { SignalState } from '@/lib/api';
import { type RenewalPosture, POSTURE_LABEL } from '@/lib/renewals';

/** Posture chip — expand (green) / hold (brass) / defend (terracotta). */
export function PostureBadge({ posture, className }: { posture: RenewalPosture; className?: string }) {
  return (
    <span className={cn('rn-badge', `rn-badge--${posture}`, className)}>
      {POSTURE_LABEL[posture]}
    </span>
  );
}

/** A progress track with a fill (tone) and optional baseline tick. */
export function ProgressTrack({
  progress,
  baseline,
  tone,
  className,
}: {
  progress: number | null;
  baseline?: number | null;
  tone: SignalState;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(1, progress ?? 0)) * 100;
  return (
    <span className={cn('rn-track block', className)}>
      <span className={`rn-track__fill rn-track__fill--${tone}`} style={{ width: `${pct}%` }} />
      {baseline != null && baseline > 0 && (
        <span className="rn-track__tick" style={{ left: `${Math.min(100, baseline * 100)}%` }} />
      )}
    </span>
  );
}

/** Compact goal-progress row used in the pipeline list. */
export function GoalDot({
  name,
  progress,
  tone,
}: {
  name: string;
  progress: number | null;
  tone: SignalState;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[0.72rem] text-fg-300 flex-1 min-w-0 truncate">{name}</span>
      <ProgressTrack progress={progress} tone={tone} className="w-[54px] h-1 flex-none" />
      <span className="font-mono text-[9px] text-fg-300 w-7 text-right flex-none">
        {progress != null ? `${Math.round(progress * 100)}%` : '—'}
      </span>
    </div>
  );
}

/** Section header: hairline · label · rule · optional note. */
export function SectionHeader({ label, note }: { label: string; note?: string }) {
  return (
    <div className="rn-sechdr">
      <span className="rn-sechdr__hair" />
      <span className="rn-sechdr__lbl">{label}</span>
      <span className="rn-sechdr__line" />
      {note && <span className="rn-sechdr__note">{note}</span>}
    </div>
  );
}
