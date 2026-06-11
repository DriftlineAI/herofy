/**
 * SidekickMap - Portfolio health visualization
 *
 * 2D scatter plot showing all customers:
 * - X-axis: Engagement (0-1)
 * - Y-axis: Sentiment (0-1)
 * - Quadrants: Healthy, Quiet, Going Dark, Escalating
 * - Priority list below chart
 *
 * Design reference: Screenshot 2026-05-26 (Sidekick Map mockup)
 */

import React from 'react';
import { cn } from '@/lib/utils';
import { usePortfolioInsights, type PortfolioCustomer, type PortfolioSnapshot } from '@/lib/realtime-hooks';

interface SidekickMapProps {
  className?: string;
  onCustomerClick?: (customerId: string) => void;
}

export function SidekickMap({ className, onCustomerClick }: SidekickMapProps) {
  const { snapshot, isLoading } = usePortfolioInsights();

  if (isLoading) {
    return <SidekickMapSkeleton className={className} />;
  }

  if (!snapshot || snapshot.customers.length === 0) {
    return <SidekickMapEmpty className={className} />;
  }

  return (
    <div className={cn("bg-surface border border-border p-6", className)}>
      {/* Header */}
      <div className="mb-4">
        <span className="text-[11px] font-mono uppercase tracking-[0.25em] text-accent">
          — SIDEKICK MAP
        </span>
        <h3 className="font-display text-2xl mt-1">
          Who needs you, <span className="font-serif italic">and why.</span>
        </h3>
        <p className="text-fg-300 text-sm mt-2">
          Engagement on the x, sentiment on the y. The bottom of the chart is where
          the day is decided — silence is not safety, and a loud unhappy customer
          is the loudest signal you'll get.
        </p>
      </div>

      {/* Chart */}
      <div className="relative aspect-square max-w-full border border-border bg-surface-2/30 mb-4">
        {/* Quadrant labels */}
        <div className="absolute top-2 left-2 text-[9px] font-mono uppercase text-fg-400">
          QUIET
        </div>
        <div className="absolute top-2 right-2 text-[9px] font-mono uppercase text-fg-400">
          HEALTHY
        </div>
        <div className="absolute bottom-2 left-2 text-[9px] font-mono uppercase text-signal-bad">
          GOING DARK
        </div>
        <div className="absolute bottom-2 right-2 text-[9px] font-mono uppercase text-signal-warn">
          ESCALATING
        </div>

        {/* Axis labels */}
        <div className="absolute -left-1 top-1/2 -translate-y-1/2 -rotate-90 text-[9px] font-mono uppercase text-fg-400 whitespace-nowrap">
          SENTIMENT
        </div>
        <div className="absolute bottom-[-16px] left-1/2 -translate-x-1/2 text-[9px] font-mono uppercase text-fg-400">
          ENGAGEMENT →
        </div>

        {/* Grid lines */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border" />
          <div className="absolute top-1/2 left-0 right-0 h-px bg-border" />
        </div>

        {/* Customer dots */}
        {snapshot.customers.map((customer) => (
          <CustomerDot
            key={customer.id}
            customer={customer}
            onClick={() => onCustomerClick?.(customer.id)}
          />
        ))}
      </div>

      {/* Summary Counts */}
      <div className="grid grid-cols-3 gap-2 mb-4 text-[10px] font-mono">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-signal-ok" />
          <span className="text-fg-300">{snapshot.healthy_count} Healthy</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-fg-400" />
          <span className="text-fg-300">{snapshot.quiet_count} Quiet</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-signal-bad" />
          <span className="text-fg-300">{snapshot.going_dark_count + snapshot.escalating_count + snapshot.slipping_count} At Risk</span>
        </div>
      </div>

      {/* Priority List */}
      {snapshot.priority_list.length > 0 && (
        <div className="pt-4 border-t border-border">
          <h5 className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-3">
            Needs Attention
          </h5>
          <div className="space-y-2">
            {snapshot.priority_list.slice(0, 5).map((item) => (
              <button
                key={item.id}
                onClick={() => onCustomerClick?.(item.id)}
                className="flex items-center justify-between w-full text-left px-3 py-2 hover:bg-surface-2 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "w-2 h-2 rounded-full",
                    item.quadrant === 'going_dark' && "bg-signal-bad",
                    item.quadrant === 'escalating' && "bg-signal-warn",
                    item.quadrant === 'slipping' && "bg-signal-bad",
                  )} />
                  <span className="text-fg-200 text-sm">{item.name}</span>
                </div>
                <span className="text-[11px] font-mono uppercase tracking-wider text-signal-bad">
                  {item.reason}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Insight callout */}
      <p className="mt-6 text-fg-300 font-serif italic text-sm">
        Engagement climbing while sentiment falls is{' '}
        <span className="text-accent">the loudest signal you have.</span>{' '}
        Silence at zero is the second.
      </p>
    </div>
  );
}

function CustomerDot({
  customer,
  onClick
}: {
  customer: PortfolioCustomer;
  onClick: () => void;
}) {
  // Position as percentage (x = engagement, y = sentiment)
  // Note: CSS bottom positions from bottom, so y works naturally
  const left = `${customer.x * 100}%`;
  const bottom = `${customer.y * 100}%`;

  const colorClass = {
    healthy: 'bg-signal-ok',
    quiet: 'bg-fg-400',
    going_dark: 'bg-signal-bad',
    escalating: 'bg-signal-warn',
    slipping: 'bg-signal-bad',
  }[customer.quadrant] || 'bg-fg-400';

  return (
    <button
      onClick={onClick}
      className={cn(
        "absolute w-3 h-3 rounded-full -translate-x-1/2 translate-y-1/2 transition-transform hover:scale-150 cursor-pointer",
        colorClass,
        customer.priority === 'high' && "ring-2 ring-accent ring-offset-1 ring-offset-surface"
      )}
      style={{ left, bottom }}
      title={customer.name}
    />
  );
}

function SidekickMapSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("bg-surface border border-border p-6 animate-pulse", className)}>
      <div className="mb-4">
        <div className="h-3 w-24 bg-surface-2 mb-2" />
        <div className="h-7 w-48 bg-surface-2 mb-2" />
        <div className="h-4 w-full bg-surface-2" />
      </div>
      <div className="aspect-square bg-surface-2 mb-4" />
      <div className="space-y-2">
        <div className="h-4 w-32 bg-surface-2" />
        <div className="h-4 w-40 bg-surface-2" />
      </div>
    </div>
  );
}

function SidekickMapEmpty({ className }: { className?: string }) {
  return (
    <div className={cn("bg-surface border border-border p-6", className)}>
      <div className="mb-4">
        <span className="text-[11px] font-mono uppercase tracking-[0.25em] text-accent">
          — SIDEKICK MAP
        </span>
        <h3 className="font-display text-2xl mt-1">
          Who needs you, <span className="font-serif italic">and why.</span>
        </h3>
      </div>
      <div className="py-8 text-center border border-dashed border-border bg-surface-2/30">
        <p className="text-fg-400 italic">
          No customer data yet.
        </p>
        <p className="text-[13px] text-fg-400 mt-2">
          Customer insights will appear here once data is available.
        </p>
      </div>
    </div>
  );
}

export default SidekickMap;
