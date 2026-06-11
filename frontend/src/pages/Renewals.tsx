import React from 'react';
import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useRenewalsPipeline, useCustomers, useSetCustomerRenewalDate } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import { useAuth } from '@/lib/auth';
import type { CustomerWithSignals } from '@/lib/api';
import {
  formatARR,
  computePortfolioStats,
  renewalDateLabel,
  type RenewalPipelineRow,
  type PortfolioStats,
} from '@/lib/renewals';
import { PostureBadge, GoalDot } from '@/components/renewals/atoms';
import { Sidekick } from '@/components/ui/huds';
import { CalendarClock, Plus, Settings, ChevronRight } from 'lucide-react';
import { format } from 'date-fns';
import { SectionHeader } from '@/components/renewals/atoms';
import { DateInput } from '@/components/ui/DateInput';

const GROWTH_LABEL: Record<string, { text: string; cls: string }> = {
  up: { text: '↑ GROWING', cls: 'text-signal-ok' },
  flat: { text: 'FLAT', cls: 'text-fg-400' },
  down: { text: 'AT RISK', cls: 'text-signal-risk' },
};

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-8">
      <div className="h-10 w-80 bg-surface-2" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border">
        {[0, 1, 2, 3].map(i => <div key={i} className="h-20 bg-surface-2" />)}
      </div>
      <div className="space-y-2">
        {[0, 1, 2, 3].map(i => <div key={i} className="h-24 bg-surface-2" />)}
      </div>
    </div>
  );
}

function StatStrip({ stats: s }: { stats: PortfolioStats }) {
  const cells = [
    { k: 'RENEWING · 90D', v: formatARR(s.renewing_arr_cents), sub: `${s.account_count} accounts`, tone: '' },
    { k: 'EXPANSION PIPE', v: `+${formatARR(s.expansion_pipe_cents)}`, sub: `${s.expand_count} expand-posture`, tone: 'text-signal-ok' },
    { k: 'AT RISK', v: formatARR(s.at_risk_arr_cents), sub: `${s.defend_count} defend-posture`, tone: 'text-signal-risk' },
    { k: 'NET RETENTION', v: s.net_retention_pct != null ? `${s.net_retention_pct}%` : '—', sub: 'projected', tone: 'text-brass' },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border border border-border mb-2">
      {cells.map(c => (
        <div key={c.k} className="bg-surface px-4 py-4">
          <div className="font-mono text-[9px] tracking-[0.18em] uppercase text-fg-400 mb-2">{c.k}</div>
          <div className={cn('font-display text-[1.7rem] leading-none', c.tone || 'text-fg-100')}>{c.v}</div>
          <div className="font-mono text-[9px] tracking-[0.1em] uppercase text-fg-400 mt-1.5">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}

function RenewalRow({ row }: { row: RenewalPipelineRow }) {
  const narrative =
    row.profile?.narrative_lede ||
    row.signals.find(s => s.state === 'risk')?.sentence ||
    row.value_realization_text ||
    row.signals[0]?.sentence ||
    'Quietly satisfied — re-commit to the next goal.';

  // up to 2 goal mini-bars from each goal's first vector
  const dots = row.goals
    .map(g => ({ goal: g, vec: g.vectors[0] }))
    .filter(x => x.vec)
    .slice(0, 2);

  const growth = GROWTH_LABEL[row.growth] || GROWTH_LABEL.flat;

  return (
    <NavLink
      to={`/app/renewals/${row.id}`}
      className={cn(
        'group grid items-center gap-4 md:gap-5 px-4 md:px-5 py-4 bg-surface border border-border',
        'grid-cols-[56px_1fr_auto] md:grid-cols-[84px_1fr_220px_132px_24px]',
        'hover:border-border-strong hover:bg-surface-2 transition-colors',
        `rn-edge-${row.posture}`
      )}
    >
      {/* days */}
      <div className="text-center border-r border-rule pr-3">
        <div className={cn('font-mono text-[1.4rem] leading-none', row.posture === 'defend' ? 'text-signal-risk' : 'text-fg-200')}>
          {row.days_to_renewal}<span className="text-[9px] text-fg-400 tracking-[0.16em]">d</span>
        </div>
        <div className="font-mono text-[8.5px] tracking-[0.14em] uppercase text-fg-400 mt-1">
          {renewalDateLabel(row.days_to_renewal)}
        </div>
      </div>

      {/* main */}
      <div className="min-w-0">
        <div className="flex items-center gap-2.5 mb-1">
          <span className="font-display text-[1.35rem] leading-none text-fg-100 group-hover:text-accent transition-colors truncate">
            {row.name}
          </span>
          <PostureBadge posture={row.posture} />
        </div>
        <p className="text-sm text-fg-300 leading-snug line-clamp-2">{narrative}</p>
        {row.champion_departed && (
          <div className="font-mono text-[9px] tracking-[0.1em] uppercase text-signal-risk mt-1.5">CHAMPION DEPARTED</div>
        )}
      </div>

      {/* goal progress mini */}
      <div className="hidden md:block border-l border-rule pl-4">
        <div className="font-mono text-[8px] font-bold tracking-[0.2em] uppercase text-fg-400 mb-2">GOAL PROGRESS</div>
        {dots.length > 0 ? (
          <div className="space-y-1.5">
            {dots.map(({ goal, vec }) => (
              <GoalDot key={goal.id} name={goal.text} progress={vec.progress} tone={vec.current_state} />
            ))}
          </div>
        ) : (
          <div className="font-mono text-[9px] text-fg-400/60 uppercase tracking-[0.1em]">No goals tracked</div>
        )}
      </div>

      {/* arr + growth */}
      <div className="text-right hidden md:block">
        <div className="font-mono text-[1.05rem] text-fg-100">{formatARR(row.arr_cents)}</div>
        <div className={cn('font-mono text-[9px] tracking-[0.1em] uppercase mt-1.5', growth.cls)}>{growth.text}</div>
      </div>

      <ChevronRight className="hidden md:block w-4 h-4 text-fg-400 group-hover:text-accent transition-colors justify-self-center" />
    </NavLink>
  );
}

function Bucket({ label, rows, urgent }: { label: string; rows: RenewalPipelineRow[]; urgent?: boolean }) {
  if (rows.length === 0) return null;
  const needsWork = rows.filter(r => r.posture === 'defend').length;
  return (
    <div className="mt-7">
      <div className="flex items-center gap-3 mb-3">
        {urgent && <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />}
        <span className={cn('font-mono text-[11px] tracking-[0.25em] uppercase', urgent ? 'text-accent' : 'text-fg-300')}>{label}</span>
        {needsWork > 0 && (
          <span className="font-mono text-[9px] font-bold tracking-[0.16em] uppercase text-signal-risk border border-signal-risk/40 px-1.5 py-0.5">
            NEEDS WORK · {needsWork}
          </span>
        )}
        <span className="font-mono text-[10px] text-fg-400/60">({rows.length})</span>
        <span className="flex-1 h-px bg-rule" />
      </div>
      <div className="space-y-2">
        {rows.map(r => <RenewalRow key={r.id} row={r} />)}
      </div>
    </div>
  );
}

export default function Renewals() {
  const { rows, isLoading, error, refetch } = useRenewalsPipeline();
  const { data: custData, isLoading: custLoading, refetch: refetchCustomers } = useCustomers();
  const { hasCompletedSetup, isStaff } = useAuth();
  const canManageIntegrations = hasCompletedSetup || isStaff;
  useRefreshOnFocus(refetch);

  const refreshAll = React.useCallback(() => { refetch(); refetchCustomers(); }, [refetch, refetchCustomers]);

  const loading = isLoading || custLoading;
  const allCustomers = custData?.customers ?? [];
  const totalCustomers = allCustomers.length;
  const unscheduled = React.useMemo(
    () => allCustomers.filter(c => c.days_to_renewal == null),
    [allCustomers]
  );

  const sorted = React.useMemo(
    () => [...rows].sort((a, b) => (a.days_to_renewal || 0) - (b.days_to_renewal || 0)),
    [rows]
  );

  const inWindow = (r: RenewalPipelineRow, lo: number, hi: number) =>
    r.days_to_renewal != null && r.days_to_renewal > lo && r.days_to_renewal <= hi;
  const next30 = sorted.filter(r => inWindow(r, 0, 30));
  const next60 = sorted.filter(r => inWindow(r, 30, 60));
  const next90 = sorted.filter(r => inWindow(r, 60, 90));
  const later = sorted.filter(r => r.days_to_renewal != null && r.days_to_renewal > 90);

  const stats = React.useMemo(() => computePortfolioStats(sorted), [sorted]);
  const defendNames = sorted.filter(r => r.posture === 'defend').map(r => r.name);

  if (error) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="hud-pane p-8">
          <div className="text-[10px] uppercase tracking-[0.3em] text-signal-bad font-bold mb-4">Connection Error</div>
          <p className="text-fg-200 mb-4">{(error as Error).message}</p>
          <button onClick={() => refetch()} className="btn-hud">Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <header className="mb-6">
        <div className="flex items-center gap-3 font-mono text-[10.5px] tracking-[0.22em] uppercase text-fg-400 mb-3">
          <span className="w-[7px] h-[7px] rounded-full bg-accent animate-pulse" />
          <span>Renewals · Pipeline</span>
          {!isLoading && sorted.length > 0 && (
            <span className="text-accent">· {formatARR(stats.renewing_arr_cents)} renewing</span>
          )}
        </div>
        <h1 className="font-display text-[2.6rem] leading-none tracking-tight text-fg-100 mb-3">Renewals.</h1>
        {!loading && sorted.length > 0 && (
          <p className="text-fg-300 text-base leading-relaxed max-w-3xl">
            {formatARR(stats.renewing_arr_cents)} renews across {sorted.length} account{sorted.length !== 1 ? 's' : ''}.{' '}
            {stats.expand_count > 0 && `${stats.expand_count} tracking to grow`}
            {stats.expand_count > 0 && (stats.hold_count > 0 || stats.defend_count > 0) ? ', ' : ''}
            {stats.hold_count > 0 && `${stats.hold_count} holding`}
            {stats.defend_count > 0 && `, and ${defendNames.slice(0, 2).join(' + ')} need${defendNames.length === 1 ? 's' : ''} defending`}.
          </p>
        )}
        {!loading && sorted.length === 0 && unscheduled.length > 0 && (
          <p className="text-fg-300 text-base leading-relaxed max-w-3xl">
            You have {totalCustomers} customer{totalCustomers !== 1 ? 's' : ''}, but {unscheduled.length === totalCustomers ? 'none have' : `${unscheduled.length} don't have`} a renewal date yet.
            Set one below to start tracking the renewal — Sidekick will assign each account a posture from its signals.
          </p>
        )}
      </header>

      {loading ? (
        <LoadingSkeleton />
      ) : totalCustomers === 0 ? (
        <EmptyState canManageIntegrations={canManageIntegrations} />
      ) : (
        <>
          {sorted.length > 0 && (
            <>
              <StatStrip stats={stats} />
              <Bucket label="NEXT 30 DAYS" rows={next30} urgent />
              <Bucket label="30 – 60 DAYS" rows={next60} />
              <Bucket label="60 – 90 DAYS" rows={next90} />
              <Bucket label="90+ DAYS" rows={later} />
            </>
          )}
          {unscheduled.length > 0 && (
            <UnscheduledSection
              customers={unscheduled}
              leading={sorted.length === 0}
              onSaved={refreshAll}
            />
          )}
        </>
      )}
    </div>
  );
}

function UnscheduledSection({
  customers,
  leading,
  onSaved,
}: {
  customers: CustomerWithSignals[];
  leading: boolean;
  onSaved: () => void;
}) {
  return (
    <div className={leading ? 'mt-2' : 'mt-10'}>
      <SectionHeader label="AWAITING A RENEWAL DATE" note={`${customers.length} TO SCHEDULE`} />
      <div className="space-y-2">
        {customers.map(c => <UnscheduledRow key={c.id} customer={c} onSaved={onSaved} />)}
      </div>
    </div>
  );
}

const DAY_MS = 86_400_000;

/** Next annual anniversary of signup that's still in the future (yyyy-MM-dd). */
function suggestRenewalDate(createdAt: string | null): string {
  const base = createdAt ? new Date(createdAt) : new Date();
  const d = isNaN(base.getTime()) ? new Date() : new Date(base);
  const now = new Date();
  d.setFullYear(d.getFullYear() + 1);
  while (d.getTime() <= now.getTime()) d.setFullYear(d.getFullYear() + 1);
  return format(d, 'yyyy-MM-dd');
}

function daysUntil(dateStr: string): number {
  return Math.ceil((new Date(`${dateStr}T00:00:00`).getTime() - Date.now()) / DAY_MS);
}

function UnscheduledRow({ customer, onSaved }: { customer: CustomerWithSignals; onSaved: () => void }) {
  const { setRenewalDays } = useSetCustomerRenewalDate();
  const suggested = React.useMemo(() => suggestRenewalDate(customer.created_at), [customer.created_at]);
  const [date, setDate] = React.useState(suggested);
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const minDate = format(new Date(Date.now() + DAY_MS), 'yyyy-MM-dd');
  const isSuggested = date === suggested;

  const onSet = async () => {
    const days = daysUntil(date);
    if (days <= 0) { setErr('Pick a future date'); return; }
    setErr(null);
    setSaving(true);
    try {
      await setRenewalDays(customer.id, days);
      setSaving(false);
      onSaved();
    } catch (e: any) {
      setErr(e?.message?.slice(0, 60) || 'Failed to save');
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-4 px-4 md:px-5 py-3.5 bg-surface border border-border rn-edge-hold">
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <span className="font-display text-[1.2rem] leading-none text-fg-100 truncate">{customer.name}</span>
          <span className="font-mono text-[8.5px] tracking-[0.14em] uppercase text-fg-400">{customer.lifecycle}</span>
        </div>
        <div className="font-mono text-[10px] text-fg-400 mt-1.5">
          {formatARR(customer.arr_cents)} ARR
          {isSuggested && <span className="text-fg-400/70"> · suggested {format(new Date(`${suggested}T00:00:00`), 'MMM d, yyyy')} (1yr from signup)</span>}
        </div>
      </div>
      <div className="flex items-center gap-2.5">
        {err && <span className="text-signal-bad text-[11px]">{err}</span>}
        <DateInput value={date} onChange={setDate} minDate={minDate} placeholder="Pick a date" />
        <button
          type="button"
          onClick={onSet}
          disabled={saving}
          className="btn-hud btn-hud--primary disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Set'}
        </button>
      </div>
    </div>
  );
}

function EmptyState({ canManageIntegrations }: { canManageIntegrations: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <div className="w-20 h-20 bg-surface-2 flex items-center justify-center mb-6">
        <CalendarClock className="w-10 h-10 text-fg-400" />
      </div>
      <h2 className="font-display text-2xl text-fg-100 mb-2">No upcoming renewals</h2>
      <p className="text-fg-400 text-center max-w-md mb-8">
        Add customers with renewal dates to track them here, or connect your CRM to import contract data.
      </p>
      <div className="flex flex-col sm:flex-row gap-4 mb-8">
        <NavLink to="/app/customers" className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-page px-6 py-3 font-mono text-xs uppercase tracking-widest font-bold transition-colors">
          <Plus className="w-4 h-4" /> Add Customers
        </NavLink>
        {canManageIntegrations && (
          <NavLink to="/app/settings/account" className="inline-flex items-center gap-2 bg-surface-2 hover:bg-border text-fg-200 px-6 py-3 font-mono text-xs uppercase tracking-widest transition-colors border border-border">
            <Settings className="w-4 h-4" /> Connect CRM
          </NavLink>
        )}
      </div>
      <Sidekick className="max-w-lg">
        <strong>Tip:</strong> Connect HubSpot or Pipedrive to import renewal dates and contract values. I'll set each account's posture — expand, hold, or defend — from its signals.
      </Sidekick>
    </div>
  );
}
