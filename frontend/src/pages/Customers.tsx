import React, { useEffect, useRef } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { RefCode, Timestamp, Sidekick } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { useCustomers, useCreateCustomer, useSyncAllCustomers, useIntegrations, useLinkPageToCustomer, type NotionPageResult } from '@/lib/dataconnect-hooks';
import { useWorkspaceNotifications, useRefreshOnFocus } from '@/lib/realtime-hooks';
import { useWorkspace } from '@/lib/workspace';
import type { CustomerWithSignals, CustomerLifecycle, SignalState, CreateCustomerInput } from '@/lib/api';
import { Plus, Users, Upload, RefreshCw } from 'lucide-react';
import { CustomerModal } from '@/components/customer/CustomerModal';
import { SidekickMap } from '@/components/sidekick/SidekickMap';
import { getAuth } from 'firebase/auth';

// Lifecycle display order and labels
const lifecycleOrder: CustomerLifecycle[] = ['at_risk', 'handoff', 'onboarding', 'renewing', 'active', 'prospect', 'churned'];
const lifecycleLabels: Record<CustomerLifecycle, string> = {
  prospect: 'Prospect',
  handoff: 'Handoff',
  onboarding: 'Onboarding',
  active: 'Active',
  renewing: 'Renewing',
  at_risk: 'At Risk',
  churned: 'Churned',
};

// Format ARR for display
function formatARR(cents: number | string | null): string {
  if (!cents) return '-';
  const amount = Number(cents) / 100;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return `$${amount}`;
}

// Get signal indicator color
function getSignalColor(state: SignalState): string {
  switch (state) {
    case 'ok': return 'bg-signal-ok';
    case 'warn': return 'bg-signal-warn';
    case 'risk': return 'bg-signal-bad';
    default: return 'bg-fg-400';
  }
}

// Loading skeleton
function LoadingSkeleton() {
  return (
    <div className="space-y-16">
      {[1, 2, 3].map((i) => (
        <div key={i} className="animate-pulse">
          <div className="h-4 w-32 bg-border rounded mb-6" />
          <div className="space-y-4">
            {[1, 2].map((j) => (
              <div key={j} className="hud-pane p-6">
                <div className="grid grid-cols-12 gap-4">
                  <div className="col-span-3">
                    <div className="h-3 w-16 bg-border rounded mb-2" />
                    <div className="h-6 w-32 bg-border rounded" />
                  </div>
                  <div className="col-span-6">
                    <div className="h-4 w-full bg-surface-2 rounded" />
                  </div>
                  <div className="col-span-3">
                    <div className="h-4 w-24 bg-surface-2 rounded ml-auto" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// Empty state when no customers exist
function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <div className="w-20 h-20 bg-surface-2 flex items-center justify-center mb-6">
        <Users className="w-10 h-10 text-fg-400" />
      </div>

      <h2 className="text-2xl text-fg-100 mb-2">No customers yet</h2>
      <p className="text-fg-400 text-center max-w-md mb-8">
        Build your portfolio by importing existing customers or adding them one at a time.
      </p>

      <div className="flex flex-col sm:flex-row gap-4">
        <button
          onClick={onCreateClick}
          className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-page px-6 py-3 font-mono text-xs uppercase tracking-widest font-bold transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add First Customer
        </button>

        <a
          href="/setup"
          className="inline-flex items-center gap-2 bg-surface-2 hover:bg-border text-fg-200 px-6 py-3 font-mono text-xs uppercase tracking-widest transition-colors border border-border"
        >
          <Upload className="w-4 h-4" />
          Import Customers
        </a>
      </div>

      <Sidekick className="mt-12 max-w-lg">
        <strong>Tip:</strong> Connect HubSpot, Pipedrive, or upload a CSV to bring in your existing customer data along with contacts and deal history.
      </Sidekick>
    </div>
  );
}

// Customer card component
function CustomerCard({ customer }: { customer: CustomerWithSignals }) {
  const isAtRisk = customer.lifecycle === 'at_risk';
  const nextEvent = customer.days_to_renewal
    ? `Renewal in ${customer.days_to_renewal} days`
    : customer.onboarding_day_current !== null && customer.onboarding_day_total
    ? `Day ${customer.onboarding_day_current} of ${customer.onboarding_day_total}`
    : null;

  return (
    <NavLink
      to={`/app/customers/${customer.id}`}
      className="hud-pane hud-pane--compact group"
    >
      {/* Header Strip */}
      <div className="hud-pane__header">
        {isAtRisk && <span className="hud-pane__pulse" />}
        <span className="hud-pane__label">
          {customer.slug.toUpperCase()} · {customer.lifecycle.replace('_', ' ').toUpperCase()}
        </span>
        <span className="grow" />
        <span className="hud-pane__ref">Updated {new Date(customer.updated_at).toLocaleDateString()}</span>
      </div>

      {/* Body */}
      <div className="hud-pane__body hud-pane__body--compact">
        <div className="grid grid-cols-12 items-start gap-4">
          <div className="col-span-12 md:col-span-4">
            <div className="hud-pane__title-row mb-1">
              <h3 className="hud-pane__customer">{customer.name}</h3>
            </div>
            <span className="text-xs font-mono text-fg-400">
              {formatARR(customer.arr_cents)} ARR
            </span>
          </div>

          <div className="col-span-12 md:col-span-5">
            {customer.one_liner && (
              <p className="text-fg-300 leading-relaxed mb-2">
                {customer.one_liner}
              </p>
            )}

            {/* Signal indicators */}
            {customer.signals.length > 0 && (
              <div className="flex items-center gap-3 mt-2">
                {customer.signals.map((signal) => (
                  <div key={signal.id} className="flex items-center gap-1.5">
                    <div className={cn("w-2 h-2 rounded-full", getSignalColor(signal.state))} />
                    <span className="text-xs text-fg-400 capitalize">{signal.kind}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="col-span-12 md:col-span-3 flex flex-row md:flex-col justify-between md:items-end">
            {nextEvent && (
              <span className="text-[11px] font-mono text-fg-300 bg-surface-2 px-2 py-1 border border-border">
                {nextEvent}
              </span>
            )}
          </div>
        </div>
      </div>
    </NavLink>
  );
}

export default function Customers() {
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = useCustomers();
  const createCustomer = useCreateCustomer();
  const { syncAll, isPending: isSyncing } = useSyncAllCustomers();
  const { data: integrations } = useIntegrations();
  const { linkPage } = useLinkPageToCustomer();
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [syncMessage, setSyncMessage] = React.useState<string | null>(null);

  const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

  // Real-time notifications subscription - refetch when data changes
  const { workspaceId } = useWorkspace();
  const notifications = useWorkspaceNotifications(workspaceId);
  const prevUpdateRef = useRef<number | null>(null);

  // Refetch on mount and page focus to prevent stale data
  useRefreshOnFocus(refetch);

  // Refetch when any notification updates (indicates agent activity)
  useEffect(() => {
    // Debug: log all notification updates
    if (notifications) {
      console.log('[Customers] Notifications received:', {
        today_count: notifications.today_count,
        updated_at: notifications.updated_at,
      });
    }

    if (notifications?.updated_at) {
      // Convert Firestore timestamp to ms for proper comparison
      const updateTime = notifications.updated_at instanceof Date
        ? notifications.updated_at.getTime()
        : (notifications.updated_at as any)?.toMillis?.() ?? Date.now();

      if (prevUpdateRef.current !== null && updateTime !== prevUpdateRef.current) {
        console.log('[Customers] Notifications updated, refetching');
        refetch();
      }
      prevUpdateRef.current = updateTime;
    }
  }, [notifications?.updated_at, refetch]);

  const handleSyncAll = async () => {
    try {
      const result = await syncAll();
      if (result.synced_count > 0) {
        setSyncMessage(`Synced ${result.synced_count} customer${result.synced_count > 1 ? 's' : ''}`);
        refetch(); // Refresh the list
      } else if (result.skipped_count > 0) {
        setSyncMessage(`No customers with external sources to sync (${result.skipped_count} skipped)`);
      } else {
        setSyncMessage('No customers to sync');
      }
      setTimeout(() => setSyncMessage(null), 5000);
    } catch (err) {
      setSyncMessage('Sync failed - check integration settings');
      setTimeout(() => setSyncMessage(null), 3000);
    }
  };

  // Group customers by lifecycle
  const groupedCustomers = React.useMemo(() => {
    if (!data?.customers) return {};

    return lifecycleOrder.reduce((acc, lifecycle) => {
      const customers = data.customers.filter((c) => c.lifecycle === lifecycle);
      if (customers.length > 0) {
        acc[lifecycle] = customers;
      }
      return acc;
    }, {} as Record<CustomerLifecycle, CustomerWithSignals[]>);
  }, [data?.customers]);

  const handleCreateCustomer = (data: CreateCustomerInput, notionPages: NotionPageResult[]) => {
    createCustomer.mutate(data, {
      onSuccess: async (response) => {
        setIsModalOpen(false);
        // Navigate to the new customer's detail page
        navigate(`/app/customers/${response.customer.id}`);

        // Link selected Notion pages (each triggers content fetch + enrichment in backend)
        for (const page of notionPages) {
          linkPage(response.customer.id, {
            source: 'notion',
            page_id: page.id,
            page_type: 'handoff',
            url: page.url,
            title: page.title,
          }).catch(() => {});
        }

        // Trigger handoff agent when there's context to work from
        const isOnboarding = data.lifecycle === 'handoff' || data.lifecycle === 'onboarding';
        const hasNotes = !!data.raw_notes?.trim();
        const hasIntegrations = (integrations || []).some((i) => i.connected);
        const hasPages = notionPages.length > 0;

        if (isOnboarding && (hasNotes || hasIntegrations || hasPages)) {
          try {
            const token = await getAuth().currentUser?.getIdToken();
            fetch(`${PYTHON_URL}/agents/handoff-auto/run`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${token}`,
              },
              body: JSON.stringify({
                workspace_id: workspaceId,
                customer_id: response.customer.id,
                trigger_type: 'manual_customer_add',
              }),
            }).catch(() => {});
          } catch { /* token failure — agent won't run */ }
        }
      },
    });
  };

  if (error) {
    return (
      <div className="max-w-7xl mx-auto">
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

  // Navigate to customer detail when clicking on map
  const handleCustomerClick = (customerId: string) => {
    navigate(`/app/customers/${customerId}`);
  };

  return (
    <div className="max-w-[1600px] mx-auto">
      {/* Sync message toast */}
      {syncMessage && (
        <div className="mb-4 px-3 py-2 bg-surface-2 border border-border text-xs text-fg-300">
          {syncMessage}
        </div>
      )}

      <header className="flex justify-between items-end border-b border-border pb-6 mb-8">
        <div>
          <h1 className="text-sm tracking-[0.3em] font-mono text-fg-400 uppercase mb-2">Portfolio</h1>
          <p className="text-fg-300 text-sm">
            {data?.total || 0} customers · {formatARR(
              data?.customers.reduce((sum, c) => sum + Number(c.arr_cents || 0), 0) || 0
            )} total ARR
          </p>
        </div>
        <div className="flex gap-4 items-center">
          {/* Sync All button */}
          <button
            onClick={handleSyncAll}
            disabled={isSyncing}
            className={cn(
              'text-[11px] font-mono uppercase tracking-[0.2em] px-3 py-2 transition-colors flex items-center gap-1.5 border border-border',
              isSyncing
                ? 'text-fg-400 cursor-not-allowed'
                : 'text-fg-400 hover:text-fg-100 hover:border-border-strong'
            )}
            title="Refresh all customers from external sources"
          >
            <RefreshCw className={cn('w-3 h-3', isSyncing && 'animate-spin')} />
            {isSyncing ? 'Syncing...' : 'Sync'}
          </button>
          <button
            onClick={() => setIsModalOpen(true)}
            className="text-[11px] font-mono uppercase tracking-[0.2em] bg-accent text-page px-4 py-2 hover:bg-accent-hover transition-colors flex items-center gap-2 font-bold"
          >
            <Plus className="w-3 h-3" />
            New Customer
          </button>
          <NavLink
            to="/app/onboarding"
            className="text-[11px] font-mono uppercase tracking-[0.2em] text-fg-400 hover:text-fg-100 transition-colors hidden sm:block"
          >
            Mission Timelines →
          </NavLink>
          <NavLink
            to="/app/at-risk"
            className="text-[11px] font-mono uppercase tracking-[0.2em] text-signal-bad hover:text-signal-bad/80 transition-colors"
          >
            Go to War Room →
          </NavLink>
        </div>
      </header>

      {/* Main content with right rail */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_400px] gap-8">
        {/* Customer List */}
        <div className="space-y-12 min-w-0">
          {isLoading ? (
            <LoadingSkeleton />
          ) : Object.keys(groupedCustomers).length === 0 ? (
            <EmptyState onCreateClick={() => setIsModalOpen(true)} />
          ) : (
            <div className="space-y-12">
              {(Object.entries(groupedCustomers) as [CustomerLifecycle, CustomerWithSignals[]][]).map(([lifecycle, customers]) => (
                <section key={lifecycle}>
                  <h2 className="text-[11px] tracking-[0.25em] text-fg-400 font-mono uppercase mb-6 flex items-center gap-4">
                    <span className={cn(
                      lifecycle === 'at_risk' && 'text-signal-bad',
                      lifecycle === 'handoff' && 'text-signal-warn'
                    )}>
                      {lifecycleLabels[lifecycle]}
                    </span>
                    <span className="text-fg-400/50">({customers.length})</span>
                    <div className="h-[1px] flex-1 bg-border"></div>
                  </h2>
                  <div className="grid grid-cols-1 gap-4">
                    {customers.map((customer) => (
                      <CustomerCard key={customer.id} customer={customer} />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>

        {/* Right Rail - Portfolio Insights */}
        <aside className="hidden xl:block space-y-6">
          <SidekickMap onCustomerClick={handleCustomerClick} />
        </aside>
      </div>

      {/* Customer Creation Modal */}
      <CustomerModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleCreateCustomer}
        isSubmitting={createCustomer.isPending}
      />
    </div>
  );
}
