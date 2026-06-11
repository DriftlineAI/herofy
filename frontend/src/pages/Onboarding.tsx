import React from 'react';
import { NavLink, useParams } from 'react-router-dom';
import { RefCode, Timestamp, Pulse } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { PlanTimeline, PlanTimelineItem } from '@/components/ui/PlanTimeline';
import { useCustomers, useCustomer, usePlan, useApprovePlan, useRejectPlan, useRegeneratePlan } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import type { CustomerWithSignals, Customer, Milestone } from '@/lib/api';
import { ChevronRight, Check, X, RefreshCw, Edit3 } from 'lucide-react';

// Loading skeleton for the list view
function LoadingSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      {[1, 2, 3].map((i) => (
        <div key={i} className="hud-pane p-8">
          <div className="flex justify-between items-start mb-8">
            <div>
              <div className="h-4 w-20 bg-border rounded mb-2" />
              <div className="h-8 w-48 bg-border rounded" />
            </div>
            <div className="h-4 w-32 bg-surface-2 rounded" />
          </div>
          <div className="h-3 w-full bg-surface-2 rounded" />
        </div>
      ))}
    </div>
  );
}

// Onboarding customer card
function OnboardingCard({ customer }: { customer: CustomerWithSignals }) {
  const progress = customer.onboarding_day_total && customer.onboarding_day_current !== null
    ? (customer.onboarding_day_current / customer.onboarding_day_total) * 100
    : 0;

  const isBlocked = customer.signals.some(s => s.state === 'risk');
  const currentMilestone = customer.one_liner || 'In progress';

  return (
    <NavLink
      to={`/app/customers/${customer.id}`}
      className="hud-pane group"
    >
      {/* Header Strip */}
      <div className="hud-pane__header">
        {isBlocked && <span className="hud-pane__pulse" />}
        <span className="hud-pane__label">
          {customer.slug.toUpperCase()} · ONBOARDING
        </span>
        <span className="grow" />
        {customer.onboarding_day_current !== null && customer.onboarding_day_total && (
          <span className="hud-pane__ref">
            Day {customer.onboarding_day_current} of {customer.onboarding_day_total}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="hud-pane__body">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-6 gap-4">
          <div>
            <h3 className="hud-pane__customer group-hover:text-accent transition-colors">
              {customer.name}
            </h3>
          </div>
          <div className="text-left md:text-right">
            <div className={cn(
              "text-sm font-mono",
              isBlocked ? "text-signal-bad" : "text-fg-300"
            )}>
              {currentMilestone}
            </div>
          </div>
        </div>

        {/* Timeline Bar */}
        <div className="h-3 w-full bg-surface-2 rounded-sm overflow-hidden flex relative">
          <div
            className={cn(
              "h-full transition-all",
              isBlocked ? "bg-signal-bad/70 border-r-2 border-signal-bad" : "bg-accent/50"
            )}
            style={{ width: `${progress}%` }}
          />
          {/* Waypoints */}
          <div className="absolute inset-0 flex justify-between px-1">
            {[20, 40, 60, 80].map((w) => (
              <div key={w} className="w-px h-full bg-border" />
            ))}
          </div>
        </div>

        {isBlocked && (
          <div className="mt-4 border border-signal-bad/30 bg-signal-bad/10 p-3 text-sm text-signal-bad flex items-center gap-2">
            <Pulse active className="static" />
            <span>Blocked - attention required</span>
          </div>
        )}
      </div>
    </NavLink>
  );
}

// Plan approval view when a specific customer is selected
function PlanApprovalView({ customerId }: { customerId: string }) {
  const { data: customerData, isLoading: customerLoading } = useCustomer(customerId);
  const approvePlan = useApprovePlan();
  const rejectPlan = useRejectPlan();
  const regeneratePlan = useRegeneratePlan();

  // Find the plan that needs approval - this would come from the customer's open needs
  // For now, we'll show a placeholder until we wire up the full plan fetching
  const pendingPlanNeed = customerData?.open_needs.find(n => n.type === 'plan_approval_required');

  if (customerLoading) {
    return (
      <div className="animate-pulse space-y-8">
        <div className="h-12 w-64 bg-border rounded" />
        <div className="grid grid-cols-2 gap-8">
          <div className="h-96 bg-surface-2 rounded" />
          <div className="h-96 bg-surface-2 rounded" />
        </div>
      </div>
    );
  }

  if (!customerData) {
    return (
      <div className="hud-pane p-8 text-center">
        <p className="text-fg-400">Customer not found.</p>
      </div>
    );
  }

  const { customer, milestones } = customerData;

  if (!pendingPlanNeed) {
    // Show customer onboarding progress instead
    return (
      <div className="space-y-8">
        <header className="border-b border-border pb-6">
          <div className="flex items-center gap-2 text-xs font-mono text-fg-400 mb-4">
            <NavLink to="/app/onboarding" className="hover:text-fg-200 transition-colors">
              Onboarding
            </NavLink>
            <ChevronRight className="w-3 h-3" />
            <span className="text-fg-200">{customer.name}</span>
          </div>
          <h1 className="text-3xl text-fg-100 mb-2">{customer.name}</h1>
          <p className="text-fg-400 text-sm">Onboarding Timeline</p>
        </header>

        {/* Progress bar */}
        {customer.onboarding_day_current !== null && customer.onboarding_day_total && (
          <div className="hud-pane p-6">
            <div className="flex justify-between items-center mb-4">
              <span className="text-xs font-mono uppercase tracking-widest text-fg-400">
                Progress
              </span>
              <span className="text-fg-200 font-mono">
                Day {customer.onboarding_day_current} of {customer.onboarding_day_total}
              </span>
            </div>
            <div className="h-4 bg-surface-2 rounded-sm overflow-hidden">
              <div
                className="h-full bg-accent transition-all"
                style={{ width: `${(customer.onboarding_day_current / customer.onboarding_day_total) * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* Milestones */}
        {milestones.length > 0 && (
          <div>
            <h2 className="text-[11px] tracking-[0.25em] text-fg-400 font-mono uppercase mb-4 flex items-center gap-4">
              Milestones
              <div className="h-[1px] flex-1 bg-border" />
            </h2>
            <PlanTimeline gap={8}>
              {milestones.map((milestone) => (
                <MilestoneRow key={milestone.id} milestone={milestone} />
              ))}
            </PlanTimeline>
          </div>
        )}

        {milestones.length === 0 && (
          <div className="hud-pane p-8 text-center border-dashed">
            <p className="text-fg-400 font-mono text-sm uppercase tracking-widest">
              No milestones defined yet
            </p>
            <p className="text-fg-300 mt-2">
              A plan will be generated when the handoff is processed.
            </p>
          </div>
        )}
      </div>
    );
  }

  // TODO: Wire up full dual-pane approval UI in Phase D
  // For now, show a simplified view
  return (
    <div className="space-y-8">
      <header className="border-b border-border pb-6">
        <div className="flex items-center gap-2 text-xs font-mono text-fg-400 mb-4">
          <NavLink to="/app/onboarding" className="hover:text-fg-200 transition-colors">
            Onboarding
          </NavLink>
          <ChevronRight className="w-3 h-3" />
          <span className="text-fg-200">{customer.name}</span>
        </div>
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-3xl text-fg-100 mb-2">{customer.name}</h1>
            <p className="text-signal-warn font-mono text-sm uppercase tracking-widest">
              Plan Approval Required
            </p>
          </div>
          <div className="text-xs font-mono uppercase tracking-widest px-3 py-1 border border-signal-warn text-signal-warn">
            Pending Review
          </div>
        </div>
      </header>

      <div className="hud-pane p-8">
        <h2 className="text-2xl text-fg-100 mb-4">{pendingPlanNeed.headline}</h2>
        {pendingPlanNeed.lede && (
          <p className="text-fg-300 mb-6">{pendingPlanNeed.lede}</p>
        )}

        <div className="flex gap-4">
          <NavLink
            to={`/app/customers/${customer.id}`}
            className="text-xs font-mono uppercase tracking-widest bg-accent text-page px-6 py-3 hover:bg-accent-hover transition-colors font-bold"
          >
            Review Full Details →
          </NavLink>
        </div>
      </div>
    </div>
  );
}

// Milestone row for the timeline view. Status is carried by the
// shared PlanTimeline rail dot (done→green, in_progress→brass, blocked→terracotta).
function MilestoneRow({ milestone }: { milestone: Milestone }) {
  return (
    <PlanTimelineItem status={milestone.status}>
      <div className="flex items-center gap-4 p-4 hud-pane hud-pane--compact">
        <div className="flex-1">
          <span className="text-fg-200 font-medium">{milestone.title}</span>
          {milestone.description && (
            <p className="text-sm text-fg-400">{milestone.description}</p>
          )}
        </div>
        <div className="text-right">
          <span className={cn(
            "text-xs font-mono uppercase",
            milestone.owner_side === 'us' ? "text-accent" : "text-fg-400"
          )}>
            {milestone.owner_side}
          </span>
          {milestone.target_date && (
            <span className="block text-xs text-fg-400">
              {new Date(milestone.target_date).toLocaleDateString()}
            </span>
          )}
        </div>
      </div>
    </PlanTimelineItem>
  );
}

export default function Onboarding() {
  const { customerId } = useParams<{ customerId?: string }>();
  const { data, isLoading, error, refetch } = useCustomers();

  // Refetch on mount and page focus to prevent stale data
  useRefreshOnFocus(refetch);

  // If a specific customer is selected, show their plan approval view
  if (customerId) {
    return (
      <div className="max-w-5xl mx-auto">
        <PlanApprovalView customerId={customerId} />
      </div>
    );
  }

  // Filter to only onboarding customers
  const onboardingCustomers = data?.customers.filter(c => c.lifecycle === 'onboarding') || [];

  if (error) {
    return (
      <div className="max-w-6xl mx-auto">
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
    <div className="max-w-6xl mx-auto">
      <header className="mb-12 border-b border-border pb-6 flex justify-between items-end">
        <div>
          <h1 className="text-sm tracking-[0.3em] font-mono text-fg-400 uppercase mb-2">Onboarding Progress</h1>
          <p className="text-fg-300 text-sm">
            Mission timelines. {onboardingCustomers.length} active onboardings.
          </p>
        </div>
        <NavLink
          to="/app/customers"
          className="text-[11px] font-mono uppercase tracking-[0.2em] text-fg-400 hover:text-fg-100 transition-colors"
        >
          ← Back to Portfolio
        </NavLink>
      </header>

      {isLoading ? (
        <LoadingSkeleton />
      ) : onboardingCustomers.length === 0 ? (
        <div className="hud-pane p-12 text-center">
          <div className="text-fg-400 font-mono text-sm uppercase tracking-widest mb-4">
            No Active Onboardings
          </div>
          <p className="text-fg-300">
            New customers will appear here as they move through the handoff process.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {onboardingCustomers.map((customer) => (
            <OnboardingCard key={customer.id} customer={customer} />
          ))}
        </div>
      )}
    </div>
  );
}
