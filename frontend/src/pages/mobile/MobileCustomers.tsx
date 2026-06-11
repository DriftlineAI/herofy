import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, ChevronRight } from 'lucide-react';
import { useCustomers } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import type { CustomerWithSignals, CustomerLifecycle, SignalState } from '@/lib/api';
import { ScreenHeader, MobileLoading, MobileError, MobileEmpty, formatARR } from '@/components/mobile/mobileShared';
import { cn } from '@/lib/utils';

const lifecycleOrder: CustomerLifecycle[] = [
  'at_risk',
  'handoff',
  'onboarding',
  'renewing',
  'active',
  'prospect',
  'churned',
];
const lifecycleLabels: Record<CustomerLifecycle, string> = {
  prospect: 'Prospect',
  handoff: 'Handoff',
  onboarding: 'Onboarding',
  active: 'Active',
  renewing: 'Renewing',
  at_risk: 'At Risk',
  churned: 'Churned',
};

function signalColor(state: SignalState): string {
  switch (state) {
    case 'ok':
      return 'bg-signal-ok';
    case 'warn':
      return 'bg-signal-warn';
    case 'risk':
      return 'bg-signal-bad';
    default:
      return 'bg-fg-400';
  }
}

export default function MobileCustomers() {
  const { data, isLoading, error, refetch } = useCustomers();
  const navigate = useNavigate();
  useRefreshOnFocus(refetch);

  const grouped = useMemo(() => {
    const map = {} as Record<CustomerLifecycle, CustomerWithSignals[]>;
    for (const lc of lifecycleOrder) {
      const list = (data?.customers || []).filter((c) => c.lifecycle === lc);
      if (list.length) map[lc] = list;
    }
    return map;
  }, [data?.customers]);

  const totalArr = useMemo(
    () => (data?.customers || []).reduce((sum, c) => sum + Number(c.arr_cents || 0), 0),
    [data?.customers],
  );

  return (
    <div>
      <ScreenHeader
        eyebrow="Portfolio"
        title="Customers"
        sub={`${data?.total || 0} accounts · ${formatARR(totalArr)} ARR`}
      />

      {error ? (
        <MobileError message={(error as Error).message} onRetry={() => refetch()} />
      ) : isLoading ? (
        <MobileLoading />
      ) : Object.keys(grouped).length === 0 ? (
        <MobileEmpty icon={<Users className="h-7 w-7" />} title="No customers yet" body="Add accounts on desktop to start monitoring them here." />
      ) : (
        <div className="space-y-6 px-4 pb-6">
          {(Object.entries(grouped) as [CustomerLifecycle, CustomerWithSignals[]][]).map(([lc, customers]) => (
            <section key={lc}>
              <h2 className="mb-3 flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.24em]">
                <span
                  className={cn(
                    'font-bold',
                    lc === 'at_risk' ? 'text-signal-bad' : lc === 'handoff' ? 'text-signal-warn' : 'text-fg-400',
                  )}
                >
                  {lifecycleLabels[lc]}
                </span>
                <span className="text-fg-400/60">({customers.length})</span>
                <span className="h-px flex-1 bg-border" />
              </h2>
              <div className="space-y-3">
                {customers.map((c) => (
                  <CustomerCard key={c.id} customer={c} onOpen={() => navigate(`/m/customers/${c.id}`)} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function CustomerCard({ customer, onOpen }: { customer: CustomerWithSignals; onOpen: () => void }) {
  const atRisk = customer.lifecycle === 'at_risk';
  const nextEvent = customer.days_to_renewal
    ? `Renewal in ${customer.days_to_renewal}d`
    : customer.onboarding_day_current !== null && customer.onboarding_day_total
      ? `Day ${customer.onboarding_day_current}/${customer.onboarding_day_total}`
      : null;

  return (
    <button
      onClick={onOpen}
      className={cn('block w-full rounded-md border border-border bg-surface p-4 text-left', atRisk && 'edge-risk')}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-display text-xl leading-none text-fg-100">{customer.name}</h3>
          <span className="mt-1 block font-mono text-[10px] uppercase tracking-[0.16em] text-fg-400">
            {formatARR(customer.arr_cents)} ARR
          </span>
        </div>
        <ChevronRight className="mt-0.5 h-5 w-5 shrink-0 text-fg-400" />
      </div>

      {customer.one_liner && (
        <p className="mt-2 line-clamp-2 text-[14px] leading-snug text-fg-300">{customer.one_liner}</p>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {customer.signals.slice(0, 4).map((s) => (
          <span key={s.id} className="flex items-center gap-1.5">
            <span className={cn('h-2 w-2 rounded-full', signalColor(s.state))} />
            <span className="text-[11px] capitalize text-fg-400">{s.kind}</span>
          </span>
        ))}
        {nextEvent && (
          <span className="ml-auto border border-border bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-fg-300">
            {nextEvent}
          </span>
        )}
      </div>
    </button>
  );
}
