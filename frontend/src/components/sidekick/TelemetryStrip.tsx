import React from 'react';
import { cn } from '@/lib/utils';

interface TeleCellProps {
  label: React.ReactNode;
  value: React.ReactNode;
  delta?: React.ReactNode;
  alert?: boolean;
  pulse?: boolean;
}

function TeleCell({ label, value, delta, alert, pulse }: TeleCellProps) {
  return (
    <div className={cn(
      'px-5 py-3.5 border-r border-border last:border-r-0',
      alert && 'bg-accent/5'
    )}>
      <div className="flex items-center gap-2 mb-2.5 font-mono text-[9.5px] uppercase tracking-[0.2em] text-fg-400">
        {pulse && (
          <span className="relative inline-block w-2 h-2 rounded-full bg-accent shrink-0">
            <span className="absolute inset-0 rounded-full bg-accent animate-ping opacity-70" />
          </span>
        )}
        {label}
      </div>
      <div className={cn(
        'font-mono text-[28px] leading-none text-fg-100',
        alert && 'text-accent-hover'
      )}>
        {value}
      </div>
      {delta && (
        <div className="mt-2 font-mono text-[10px] tracking-[0.08em] uppercase text-fg-400">
          {delta}
        </div>
      )}
    </div>
  );
}

interface TelemetryStripProps {
  agentsRunning: number;
  customersWithRunning: number;
  questionsOpen: number;
  questionsBlocking: number;
  questionsFollowUp: number;
  arrBlockedCents: number;
  accountsBlocked: number;
  oldestWaitMs: number;
  oldestWaitCustomer: string;
  oldestWaitAgent: string;
  resolvedToday: number;
  resolvedDelta: number;
}

function formatWait(ms: number): string {
  if (ms <= 0) return '—';
  const hours = Math.floor(ms / 3600000);
  const mins = Math.floor((ms % 3600000) / 60000);
  if (hours === 0) return `${mins}m`;
  if (hours < 24) return `${hours}h ${mins}m`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}

function formatArr(cents: number): string {
  if (cents <= 0) return '$0';
  const dollars = cents / 100;
  if (dollars >= 1_000_000) return `$${(dollars / 1_000_000).toFixed(1)}M`;
  if (dollars >= 1_000) return `$${Math.round(dollars / 1_000)}K`;
  return `$${Math.round(dollars)}`;
}

export function TelemetryStrip({
  agentsRunning,
  customersWithRunning,
  questionsOpen,
  questionsBlocking,
  questionsFollowUp,
  arrBlockedCents,
  accountsBlocked,
  oldestWaitMs,
  oldestWaitCustomer,
  oldestWaitAgent,
  resolvedToday,
  resolvedDelta,
}: TelemetryStripProps) {
  return (
    <div className="grid grid-cols-5 border border-border border-l-[3px] border-l-accent bg-surface/60 shadow-lift mt-5">
      <TeleCell
        pulse
        label="Agents running"
        value={agentsRunning || '—'}
        delta={agentsRunning > 0 ? (
          <span className="text-fg-300">across {customersWithRunning} customer{customersWithRunning !== 1 ? 's' : ''}</span>
        ) : <span>none active</span>}
      />
      <TeleCell
        label="Questions open"
        value={questionsOpen || '—'}
        delta={questionsOpen > 0 ? (
          <>
            <span className="text-signal-risk">{questionsBlocking} blocking</span>
            {' · '}
            {questionsFollowUp} follow-up
          </>
        ) : <span>queue clear</span>}
      />
      <TeleCell
        alert={arrBlockedCents > 0}
        label="ARR blocked"
        value={arrBlockedCents > 0 ? formatArr(arrBlockedCents) : '—'}
        delta={arrBlockedCents > 0 ? (
          <><span className="text-signal-warn">{accountsBlocked} account{accountsBlocked !== 1 ? 's' : ''}</span> waiting</>
        ) : undefined}
      />
      <TeleCell
        label="Oldest wait"
        value={oldestWaitMs > 0 ? formatWait(oldestWaitMs) : '—'}
        delta={oldestWaitMs > 0 ? (
          <>
            <span className="text-signal-warn">{oldestWaitCustomer}</span>
            {' · '}
            {oldestWaitAgent.replace(/_/g, '-')}
          </>
        ) : undefined}
      />
      <TeleCell
        label="Resolved · 24h"
        value={resolvedToday}
        delta={resolvedDelta > 0 ? (
          <><span className="text-signal-ok">↑ {resolvedDelta}</span> vs yesterday</>
        ) : resolvedDelta < 0 ? (
          <><span className="text-signal-warn">↓ {Math.abs(resolvedDelta)}</span> vs yesterday</>
        ) : <span>same as yesterday</span>}
      />
    </div>
  );
}
