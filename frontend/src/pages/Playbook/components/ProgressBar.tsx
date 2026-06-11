import React from 'react';
import { cn } from '@/lib/utils';

interface ProgressBarProps {
  done: number;
  total: number;
  nextMandate?: string;
  nextMandateDate?: string;
  className?: string;
}

/**
 * ProgressBar - Segmented progress indicator with next mandate
 * Used in PlaybookRunning (Artboard 6)
 */
export function ProgressBar({
  done,
  total,
  nextMandate,
  nextMandateDate,
  className
}: ProgressBarProps) {
  const segments = Array.from({ length: total }, (_, i) => {
    if (i < done) return 'done';
    if (i === done) return 'current';
    return 'pending';
  });

  return (
    <div className={cn('pb-progress', className)}>
      <div className="pb-progress__head">
        <div className="pb-progress__count">
          <span className="pb-progress__count-num">{done}</span>
          <span className="pb-progress__count-denom">/{total} done</span>
        </div>
        {nextMandate && (
          <div className="pb-progress__next">
            NEXT MANDATE · {nextMandate}
            {nextMandateDate && (
              <> by <span className="text-rust-500">{nextMandateDate}</span></>
            )}
          </div>
        )}
      </div>
      <div className="pb-progress__bar">
        {segments.map((state, i) => (
          <div
            key={i}
            className={cn(
              'pb-progress__segment',
              state === 'done' && 'pb-progress__segment--done',
              state === 'current' && 'pb-progress__segment--current'
            )}
          />
        ))}
      </div>
    </div>
  );
}
