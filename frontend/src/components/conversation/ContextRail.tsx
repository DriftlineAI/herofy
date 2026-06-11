// Right-hand context rail for a conversation. Customer insights from the real
// customer hook; degrades cleanly when fields are null.
//
// NOTE: the contract names this hook `useCustomerInsights`, but no such hook
// exists in the generated SDK / dataconnect-hooks today. Per the contract rule
// ("if a hook named in §0 is missing, report it rather than invent it"), this is
// flagged as a contract gap. To stay mock-free and still render real customer
// context, we read from the existing `useCustomer` hook (snake_case adapter).

import { useCustomer } from '@/lib/dataconnect-hooks';
import { Pulse, RefCode } from '@/components/ui/huds';
import { cn } from '@/lib/utils';

interface ContextRailProps {
  customerId: string | null;
  className?: string;
}

const HEALTH_TONE: Record<string, string> = {
  good: 'text-signal-ok',
  steady: 'text-signal-ok',
  healthy: 'text-signal-ok',
  warn: 'text-signal-warn',
  at_risk: 'text-signal-bad',
  risk: 'text-signal-bad',
};

export function ContextRail({ customerId, className }: ContextRailProps) {
  const { data, isLoading } = useCustomer(customerId || '');

  if (!customerId) return null;

  if (isLoading) {
    return (
      <aside className={cn('space-y-3 p-4', className)}>
        <div className="h-5 w-32 animate-pulse rounded bg-surface-2" />
        <div className="h-20 w-full animate-pulse rounded bg-surface-2" />
      </aside>
    );
  }

  const customer = data?.customer;
  if (!customer) {
    return (
      <aside className={cn('p-4', className)}>
        <p className="text-xs text-fg-400">No customer context available.</p>
      </aside>
    );
  }

  const cells: { k: string; v: string | null }[] = [
    { k: 'LIFECYCLE', v: titleCase(customer.lifecycle) },
    { k: 'RELATIONSHIP', v: titleCase(customer.relationship_health) },
    { k: 'ARR', v: customer.arr_cents != null ? formatArr(customer.arr_cents) : null },
    {
      k: 'RENEWAL',
      v: customer.days_to_renewal != null ? `${customer.days_to_renewal}d` : null,
    },
    {
      k: 'DAY',
      v:
        customer.onboarding_day_current != null
          ? `Day ${customer.onboarding_day_current}${
              customer.onboarding_day_total ? ` / ${customer.onboarding_day_total}` : ''
            }`
          : null,
    },
  ].filter((c) => c.v);

  const healthTone = HEALTH_TONE[(customer.relationship_health || '').toLowerCase()] || 'text-fg-200';

  return (
    <aside className={cn('space-y-5 p-4', className)}>
      <div>
        <div className="mb-2 flex items-center gap-2">
          <Pulse continuous />
          <span className="font-mono text-[9px] font-semibold tracking-widest text-rust-500">
            FOCUSED · THIS THREAD
          </span>
        </div>
        <h3 className="font-serif text-xl text-fg-100">{customer.name}</h3>
        <div className="mt-1 flex items-center gap-2">
          <RefCode>{customer.id.slice(0, 8).toUpperCase()}</RefCode>
          {customer.relationship_health && (
            <span className={cn('font-mono text-[10px] font-semibold uppercase', healthTone)}>
              {customer.relationship_health}
            </span>
          )}
        </div>
      </div>

      {cells.length > 0 && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          {cells.map((c) => (
            <div key={c.k}>
              <div className="font-mono text-[9px] tracking-wider text-fg-400">{c.k}</div>
              <div className="text-sm text-fg-200">{c.v}</div>
            </div>
          ))}
        </div>
      )}

      {customer.one_liner && (
        <div className="border-t border-border pt-3">
          <div className="mb-1 font-mono text-[9px] tracking-widest text-fg-400">ABOUT</div>
          <p className="font-serif text-sm italic leading-relaxed text-fg-300">
            {customer.one_liner}
          </p>
        </div>
      )}
    </aside>
  );
}

function titleCase(v?: string | null): string | null {
  if (!v) return null;
  return v
    .split(/[_\s]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function formatArr(cents: number): string {
  const dollars = cents / 100;
  if (dollars >= 1000) return `$${Math.round(dollars / 1000)}K`;
  return `$${dollars}`;
}
