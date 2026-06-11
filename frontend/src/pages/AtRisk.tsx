import React from 'react';
import { NavLink } from 'react-router-dom';
import { RefCode, Sidekick, Pulse, Timestamp } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { useCustomers } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import type { CustomerWithSignals, Signal, SignalState } from '@/lib/api';
import { AlertTriangle, ChevronRight } from 'lucide-react';

// Format ARR for display
function formatARR(cents: number | null): string {
  if (!cents) return '-';
  const amount = cents / 100;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return `$${amount}`;
}

// Loading skeleton
function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-8">
      <div className="hud-pane p-8 md:p-12">
        <div className="h-12 w-64 bg-border rounded mb-4" />
        <div className="h-6 w-96 bg-surface-2 rounded mb-8" />
        <div className="grid grid-cols-2 gap-8">
          <div className="h-48 bg-surface-2 rounded" />
          <div className="h-48 bg-surface-2 rounded" />
        </div>
      </div>
    </div>
  );
}

// At-risk customer card (featured)
function AtRiskCard({ customer, featured = false }: { customer: CustomerWithSignals; featured?: boolean }) {
  // Get risk signals
  const riskSignals = customer.signals.filter(s => s.state === 'risk');
  const warnSignals = customer.signals.filter(s => s.state === 'warn');

  // Generate evidence from signals
  const evidence = [
    ...riskSignals.map(s => s.sentence || s.evidence_text).filter(Boolean),
    ...warnSignals.map(s => s.sentence || s.evidence_text).filter(Boolean),
  ].slice(0, 4);

  // Get recommendation from the most severe risk signal
  const primaryRisk = riskSignals[0] || warnSignals[0];
  const recommendation = primaryRisk?.next_action;

  if (featured) {
    return (
      <div className="hud-pane p-8 md:p-12 shadow-2xl relative overflow-hidden border-l-signal-bad">
        <div className="absolute top-0 right-0 p-4">
          <RefCode className="text-signal-bad/50">{customer.slug.toUpperCase()}</RefCode>
        </div>

        <div className="mb-12 border-b border-signal-bad/30 pb-8">
          <NavLink
            to={`/app/customers/${customer.id}`}
            className="font-serif text-5xl text-fg-100 hover:text-signal-bad transition-colors"
          >
            {customer.name}
          </NavLink>
          <p className="text-2xl text-signal-bad mt-4">{customer.one_liner || 'Requires immediate attention'}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-16">
          <div>
            <h3 className="text-xs uppercase tracking-widest font-mono text-fg-400 mb-6">Evidence</h3>
            {evidence.length > 0 ? (
              <ul className="space-y-4 font-serif text-lg text-fg-200">
                {evidence.map((item, i) => (
                  <li key={i} className="flex gap-4">
                    <span className="text-signal-bad">—</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-fg-400 italic">No detailed evidence available.</p>
            )}

            <div className="mt-12">
              <h3 className="text-xs uppercase tracking-widest font-mono text-fg-400 mb-4">Account Details</h3>
              <div className="border border-border bg-surface-2/30 p-4 font-mono text-sm text-fg-400 space-y-2">
                <div className="flex justify-between">
                  <span>ARR</span>
                  <span className="text-fg-200">{formatARR(customer.arr_cents)}</span>
                </div>
                {customer.days_to_renewal !== null && (
                  <div className="flex justify-between">
                    <span>Days to Renewal</span>
                    <span className={cn(
                      customer.days_to_renewal <= 30 ? "text-signal-bad" : "text-fg-200"
                    )}>
                      {customer.days_to_renewal}
                    </span>
                  </div>
                )}
                {customer.tier && (
                  <div className="flex justify-between">
                    <span>Tier</span>
                    <span className="text-fg-200">{customer.tier}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="flex flex-col">
            {recommendation && (
              <Sidekick className="mt-0 text-base">
                <strong className="block text-signal-bad mb-2 font-mono uppercase text-xs">Recommended Action</strong>
                {recommendation}
              </Sidekick>
            )}

            <div className="mt-auto pt-12">
              <NavLink
                to={`/app/customers/${customer.id}`}
                className="block w-full bg-signal-bad hover:bg-signal-bad/80 text-page font-bold text-lg uppercase tracking-widest py-6 transition-colors cursor-pointer text-center"
              >
                View Full Details →
              </NavLink>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Compact card for additional at-risk customers
  return (
    <NavLink
      to={`/app/customers/${customer.id}`}
      className="hud-pane hud-pane--compact group"
    >
      {/* Header Strip */}
      <div className="hud-pane__header">
        <span className="hud-pane__pulse" />
        <span className="hud-pane__label">
          {customer.slug.toUpperCase()} · AT RISK
        </span>
        <span className="grow" />
        <span className="hud-pane__ref">{formatARR(customer.arr_cents)} ARR</span>
      </div>

      {/* Body */}
      <div className="hud-pane__body hud-pane__body--compact">
        <h3 className="hud-pane__customer group-hover:text-signal-bad transition-colors mb-2">
          {customer.name}
        </h3>

        {customer.one_liner && (
          <p className="text-fg-300 mb-3">{customer.one_liner}</p>
        )}

        <div className="flex items-center gap-4">
          {riskSignals.length > 0 && (
            <span className="text-xs font-mono uppercase tracking-widest text-signal-bad flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              {riskSignals.length} risk signals
            </span>
          )}
          {customer.days_to_renewal !== null && customer.days_to_renewal <= 60 && (
            <span className="text-xs font-mono uppercase tracking-widest text-signal-warn">
              Renewal in {customer.days_to_renewal}d
            </span>
          )}
        </div>
      </div>
    </NavLink>
  );
}

export default function AtRisk() {
  const { data, isLoading, error, refetch } = useCustomers();

  // Refetch on mount and page focus to prevent stale data
  useRefreshOnFocus(refetch);

  // Filter to only at-risk customers
  const atRiskCustomers = data?.customers.filter(c => c.lifecycle === 'at_risk') || [];

  // Sort by ARR (highest first) to prioritize
  const sortedCustomers = [...atRiskCustomers].sort((a, b) =>
    (b.arr_cents || 0) - (a.arr_cents || 0)
  );

  const [featured, ...others] = sortedCustomers;

  if (error) {
    return (
      <div className="max-w-5xl mx-auto">
        <header className="mb-12 border-b border-border pb-6">
          <h1 className="text-sm tracking-[0.3em] font-mono text-signal-bad uppercase mb-2 flex items-center gap-3">
            <Pulse active /> War Room
          </h1>
        </header>
        <div className="hud-pane p-8">
          <div className="text-[10px] uppercase tracking-[0.3em] text-signal-bad font-bold mb-4">
            Connection Error
          </div>
          <p className="text-fg-200 mb-4">{(error as Error).message}</p>
          <button
            onClick={() => refetch()}
            className="text-xs font-mono uppercase tracking-widest border border-signal-bad text-signal-bad px-4 py-2 hover:bg-signal-bad hover:text-page transition-colors"
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto">
      <header className="mb-12 border-b border-border pb-6 flex justify-between items-end">
        <div>
          <h1 className="text-sm tracking-[0.3em] font-mono text-signal-bad uppercase mb-2 flex items-center gap-3">
            <Pulse active /> War Room
          </h1>
          <p className="text-fg-300 text-sm">
            {atRiskCustomers.length} account{atRiskCustomers.length !== 1 ? 's' : ''} requiring attention.
          </p>
        </div>
        <NavLink
          to="/app/customers"
          className="text-[11px] font-mono uppercase tracking-[0.2em] text-fg-400 hover:text-fg-100 transition-colors border border-border px-3 py-1"
        >
          ← Back to Portfolio
        </NavLink>
      </header>

      {isLoading ? (
        <LoadingSkeleton />
      ) : atRiskCustomers.length === 0 ? (
        <div className="hud-pane p-12 text-center">
          <div className="text-6xl mb-4">✓</div>
          <h2 className="text-2xl text-fg-100 mb-2">All Clear</h2>
          <p className="text-fg-400">No customers are currently flagged as at-risk.</p>
        </div>
      ) : (
        <div className="space-y-8">
          {/* Featured (highest ARR) at-risk customer */}
          {featured && <AtRiskCard customer={featured} featured />}

          {/* Other at-risk customers */}
          {others.length > 0 && (
            <div>
              <h2 className="text-[11px] tracking-[0.25em] text-fg-400 font-mono uppercase mb-6 flex items-center gap-4">
                Additional Escalations
                <span className="text-fg-400/50">({others.length})</span>
                <div className="h-[1px] flex-1 bg-border" />
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {others.map((customer) => (
                  <AtRiskCard key={customer.id} customer={customer} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
