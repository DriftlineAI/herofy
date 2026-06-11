// Shared primitives for the mobile (/m) route tree.
//
// These keep the desktop design system (tokens, fonts, HUD chrome) but reflow for
// a single thumb-driven column. The right-rail context that desktop shows beside
// each workspace gets *folded into* these cards and detail views instead.

import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { cn } from '@/lib/utils';

// ----- Formatting ------------------------------------------------------------

export function formatARR(cents: number | string | null | undefined): string {
  if (!cents) return '-';
  const amount = Number(cents) / 100;
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
  if (amount >= 1_000) return `$${(amount / 1_000).toFixed(0)}K`;
  return `$${amount}`;
}

export function timeAgo(dateString?: string | null): string {
  if (!dateString) return '';
  const diff = Date.now() - new Date(dateString).getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (minutes < 1) return 'now';
  if (minutes < 60) return `${minutes}m`;
  if (hours < 24) return `${hours}h`;
  return `${days}d`;
}

// ----- List-screen header ----------------------------------------------------

export function ScreenHeader({
  eyebrow,
  title,
  sub,
  action,
}: {
  eyebrow: string;
  title: ReactNode;
  sub?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="px-4 pt-5 pb-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-2 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.22em] text-fg-400">
            <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
            {eyebrow}
          </div>
          <h1 className="font-display text-[2rem] leading-none tracking-tight text-fg-100">{title}</h1>
          {sub && <p className="mt-1.5 font-sans text-[13px] italic text-fg-300">{sub}</p>}
        </div>
        {action}
      </div>
    </div>
  );
}

// ----- Detail-screen back bar ------------------------------------------------

export function BackBar({
  title,
  subtitle,
  fallback,
  right,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  fallback?: string;
  right?: ReactNode;
}) {
  const navigate = useNavigate();
  return (
    <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-page/95 px-3 py-2.5 backdrop-blur">
      <button
        type="button"
        onClick={() => (fallback ? navigate(fallback) : navigate(-1))}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-border text-fg-300 transition-colors hover:text-fg-100"
        aria-label="Back"
      >
        <ChevronLeft className="h-5 w-5" />
      </button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate font-display text-xl leading-tight text-fg-100">{title}</h1>
        {subtitle && (
          <p className="truncate font-mono text-[10px] uppercase tracking-[0.18em] text-fg-400">{subtitle}</p>
        )}
      </div>
      {right}
    </div>
  );
}

// ----- Section divider (between folded lanes) --------------------------------

export function SectionLabel({
  label,
  count,
  tone = 'default',
}: {
  label: string;
  count?: number;
  tone?: 'default' | 'alarm' | 'quiet';
}) {
  return (
    <div className="flex items-center gap-3 px-4 pb-3 pt-6">
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full',
          tone === 'alarm' ? 'bg-signal-bad animate-pulse' : tone === 'quiet' ? 'bg-fg-400' : 'bg-accent',
        )}
      />
      <span
        className={cn(
          'font-mono text-[10.5px] font-bold uppercase tracking-[0.24em]',
          tone === 'alarm' ? 'text-signal-bad' : tone === 'quiet' ? 'text-fg-400' : 'text-accent',
        )}
      >
        {label}
      </span>
      {count !== undefined && <span className="font-mono text-[10.5px] text-fg-400">· {count}</span>}
      <span className="ml-auto h-px flex-1 bg-border" />
    </div>
  );
}

// ----- Loading / empty -------------------------------------------------------

export function MobileLoading({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3 px-4 py-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-md border border-border bg-surface-2" />
      ))}
    </div>
  );
}

export function MobileEmpty({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-8 py-20 text-center">
      {icon && (
        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-md border border-border bg-surface-2 text-fg-400">
          {icon}
        </div>
      )}
      <h2 className="font-display text-2xl text-fg-100">{title}</h2>
      {body && <p className="mx-auto mt-2 max-w-xs text-sm text-fg-400">{body}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function MobileError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="mx-4 my-6 rounded-md border border-signal-bad/40 bg-signal-bad/5 p-5">
      <div className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.28em] text-signal-bad">
        Connection error
      </div>
      <p className="mb-4 text-sm text-fg-200">{message}</p>
      <button
        onClick={onRetry}
        className="border border-signal-bad px-4 py-2 font-mono text-[11px] uppercase tracking-widest text-signal-bad transition-colors hover:bg-signal-bad hover:text-page"
      >
        Retry
      </button>
    </div>
  );
}
