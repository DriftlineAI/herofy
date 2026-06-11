import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { RefCode, Timestamp, Pulse } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { useHandoffs } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import { useAuth } from '@/lib/auth';
import type { HandoffBrief, HandoffStatus } from '@/lib/api';
import { ChevronRight, FileText, AlertTriangle, Check, Clock, ArrowRightLeft, Settings } from 'lucide-react';
import { Sidekick } from '@/components/ui/huds';

// Status display configuration
const statusConfig: Record<HandoffStatus, { label: string; color: string; icon: React.ElementType }> = {
  draft: { label: 'Draft', color: 'text-fg-400 border-border', icon: FileText },
  confirmed: { label: 'Confirmed', color: 'text-signal-ok border-signal-ok', icon: Check },
  needs_correction: { label: 'Needs Correction', color: 'text-signal-warn border-signal-warn', icon: AlertTriangle },
};

// Loading skeleton
function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      {[1, 2, 3].map((i) => (
        <div key={i} className="hud-pane p-6">
          <div className="flex justify-between items-start">
            <div>
              <div className="h-4 w-24 bg-border rounded mb-2" />
              <div className="h-6 w-48 bg-border rounded" />
            </div>
            <div className="h-6 w-20 bg-surface-2 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Handoff card component
function HandoffCard({ brief }: { brief: HandoffBrief }) {
  const config = statusConfig[brief.status];
  const StatusIcon = config.icon;
  const isPending = brief.status === 'draft';

  return (
    <NavLink
      to={`/app/handoffs/${brief.id}`}
      className="hud-pane hud-pane--compact group"
    >
      {/* Header Strip */}
      <div className="hud-pane__header">
        {isPending && <span className="hud-pane__pulse" />}
        <span className="hud-pane__label">
          {brief.id.slice(0, 8).toUpperCase()} · HANDOFF
        </span>
        <span className={cn(
          "text-xs font-mono uppercase tracking-widest px-2 py-0.5 border flex items-center gap-1 ml-2",
          config.color
        )}>
          <StatusIcon className="w-3 h-3" />
          {config.label}
        </span>
        <span className="grow" />
        <span className="hud-pane__ref">{new Date(brief.captured_at).toLocaleDateString()}</span>
      </div>

      {/* Body */}
      <div className="hud-pane__body hud-pane__body--compact">
        <div className="flex flex-col md:flex-row justify-between items-start gap-4">
          <div className="flex-1">
            <h3 className="hud-pane__customer group-hover:text-accent transition-colors mb-2">
              Handoff Brief
            </h3>

            <div className="flex flex-wrap gap-4 text-sm text-fg-400">
              {brief.sales_commitments && brief.sales_commitments.length > 0 && (
                <span>{brief.sales_commitments.length} commitment{brief.sales_commitments.length !== 1 ? 's' : ''}</span>
              )}
              {brief.technical_context && brief.technical_context.length > 0 && (
                <span>{brief.technical_context.length} technical item{brief.technical_context.length !== 1 ? 's' : ''}</span>
              )}
            </div>

            {/* Quick preview of commitments */}
            {brief.sales_commitments && brief.sales_commitments.length > 0 && (
              <div className="mt-3 text-sm text-fg-300">
                <span className="text-fg-400">Key commitment: </span>
                {brief.sales_commitments[0].item}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 text-fg-400 group-hover:text-fg-100 transition-colors">
            <span className="text-xs font-mono uppercase tracking-widest">Review</span>
            <ChevronRight className="w-4 h-4" />
          </div>
        </div>
      </div>
    </NavLink>
  );
}

// Filter tabs
function FilterTabs({
  selected,
  onChange,
  counts
}: {
  selected: string | undefined;
  onChange: (status: string | undefined) => void;
  counts: { all: number; draft: number; confirmed: number; needs_correction: number };
}) {
  const tabs = [
    { value: undefined, label: 'All', count: counts.all },
    { value: 'draft', label: 'Pending', count: counts.draft },
    { value: 'needs_correction', label: 'Needs Correction', count: counts.needs_correction },
    { value: 'confirmed', label: 'Confirmed', count: counts.confirmed },
  ];

  return (
    <div className="flex gap-2 flex-wrap">
      {tabs.map((tab) => (
        <button
          key={tab.value || 'all'}
          onClick={() => onChange(tab.value)}
          className={cn(
            "text-xs font-mono uppercase tracking-widest px-4 py-2 border transition-colors",
            selected === tab.value
              ? "border-accent text-accent"
              : "border-border text-fg-400 hover:border-border-strong hover:text-fg-100"
          )}
        >
          {tab.label} ({tab.count})
        </button>
      ))}
    </div>
  );
}

export default function Handoffs() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const { data, isLoading, error, refetch } = useHandoffs(statusFilter);
  const { hasCompletedSetup, isStaff } = useAuth();

  // Only workspace owners (who completed setup) or staff can manage integrations
  const canManageIntegrations = hasCompletedSetup || isStaff;

  // Refetch on mount and page focus to prevent stale data
  useRefreshOnFocus(refetch);

  // Also fetch all to get counts
  const { data: allData } = useHandoffs();

  // Calculate counts
  const counts = {
    all: allData?.count || 0,
    draft: allData?.briefs.filter(b => b.status === 'draft').length || 0,
    confirmed: allData?.briefs.filter(b => b.status === 'confirmed').length || 0,
    needs_correction: allData?.briefs.filter(b => b.status === 'needs_correction').length || 0,
  };

  if (error) {
    return (
      <div className="max-w-5xl mx-auto">
        <div className="hud-pane p-8">
          <div className="text-[10px] uppercase tracking-[0.3em] text-signal-bad font-bold mb-4">
            Connection Error
          </div>
          <p className="text-fg-200 mb-4">{(error as Error).message}</p>
          <button
            onClick={() => refetch()}
            className="text-xs font-mono uppercase tracking-widest border border-signal-bad text-signal-bad px-4 py-2 hover:bg-signal-bad hover:text-page transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto">
      <header className="mb-12 border-b border-border pb-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
          <div>
            <h1 className="text-sm tracking-[0.3em] font-mono text-fg-400 uppercase mb-2">
              Handoff Briefs
            </h1>
            <p className="text-fg-300 text-sm">
              Sales-to-CS intelligence transfer. {data?.count || 0} briefs.
            </p>
          </div>
          <NavLink
            to="/app/customers"
            className="text-[11px] font-mono uppercase tracking-[0.2em] text-fg-400 hover:text-fg-100 transition-colors"
          >
            ← Back to Portfolio
          </NavLink>
        </div>
      </header>

      {/* Filters */}
      <div className="mb-8">
        <FilterTabs
          selected={statusFilter}
          onChange={setStatusFilter}
          counts={counts}
        />
      </div>

      {/* Content */}
      {isLoading ? (
        <LoadingSkeleton />
      ) : !data?.briefs || data.briefs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16">
          <div className="w-20 h-20 bg-surface-2 flex items-center justify-center mb-6">
            <ArrowRightLeft className="w-10 h-10 text-fg-400" />
          </div>

          <h2 className="text-2xl text-fg-100 mb-2">No handoffs yet</h2>
          <p className="text-fg-400 text-center max-w-md mb-8">
            Connect your CRM to automatically receive handoff briefs when deals close, or create them manually.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 mb-8">
            {canManageIntegrations && (
              <NavLink
                to="/app/settings/account"
                className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-page px-6 py-3 font-mono text-xs uppercase tracking-widest font-bold transition-colors"
              >
                <Settings className="w-4 h-4" />
                Connect CRM
              </NavLink>
            )}

            <NavLink
              to="/app/customers"
              className="inline-flex items-center gap-2 bg-surface-2 hover:bg-border text-fg-200 px-6 py-3 font-mono text-xs uppercase tracking-widest transition-colors border border-border"
            >
              <FileText className="w-4 h-4" />
              View Customers
            </NavLink>
          </div>

          <Sidekick className="max-w-lg">
            <strong>Tip:</strong> Connect HubSpot or Pipedrive to automatically capture deal context when customers convert. I'll help you build onboarding plans from sales intel.
          </Sidekick>
        </div>
      ) : (
        <div className="space-y-4">
          {data.briefs.map((brief) => (
            <HandoffCard key={brief.id} brief={brief} />
          ))}
        </div>
      )}
    </div>
  );
}
