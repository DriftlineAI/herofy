import React from 'react';
import { cn } from '@/lib/utils';

/* Shared "Plan 04" timeline treatment: a vertical rail with a
   status-colored dot per item, wrapping each surface's existing card.
   See styles/plan-timeline.css. */

/** Map any milestone/step status to a dot modifier class.
 *  done → green · in_progress/current → brass · blocked/at-risk → terracotta. */
export function planDotClass(status?: string | null): string {
  switch (status) {
    case 'done':
      return 'plan-tl__dot--done';
    case 'in_progress':
    case 'current':
      return 'plan-tl__dot--active';
    case 'blocked':
    case 'at_risk':
    case 'risk':
      return 'plan-tl__dot--risk';
    case 'skipped':
      return 'plan-tl__dot--skip';
    default:
      return '';
  }
}

export function PlanTimeline({
  children,
  className,
  gap,
}: {
  children: React.ReactNode;
  className?: string;
  /** Override the vertical gap between items (e.g. 0 for collapsed-border cards). */
  gap?: number | string;
}) {
  const style = gap !== undefined
    ? ({ '--plan-tl-gap': typeof gap === 'number' ? `${gap}px` : gap } as React.CSSProperties)
    : undefined;
  return (
    <div className={cn('plan-tl', className)} style={style}>
      <span className="plan-tl__rail" aria-hidden />
      {children}
    </div>
  );
}

export function PlanTimelineItem({
  status,
  children,
  className,
  dotTop,
}: {
  status?: string | null;
  children: React.ReactNode;
  className?: string;
  /** Override the dot's top offset (px) to align with the card's title line. */
  dotTop?: number;
}) {
  const style = dotTop !== undefined
    ? ({ '--plan-dot-top': `${dotTop}px` } as React.CSSProperties)
    : undefined;
  return (
    <div className={cn('plan-tl__item', className)} style={style}>
      <span className={cn('plan-tl__dot', planDotClass(status))} aria-hidden />
      {children}
    </div>
  );
}
