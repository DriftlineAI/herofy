import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, ChevronRight, Zap } from 'lucide-react';
import { useToday, useSidekickAskingItems, useTodayWorklist } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import { useAuth } from '@/lib/auth';
import type { TodayQueueItem } from '@/lib/api';
import { needSeverity, severityText, needTypeLabel } from '@/components/conversation/conversationUtils';
import {
  ScreenHeader,
  SectionLabel,
  MobileLoading,
  MobileError,
  MobileEmpty,
  formatARR,
  timeAgo,
} from '@/components/mobile/mobileShared';
import { cn } from '@/lib/utils';

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

// One account = one card; its open situations are folded inline (no right rail).
interface SituationGroup {
  customerId: string;
  customer: string;
  arrCents: number | null;
  severity: 'risk' | 'warn';
  oldest: string;
  needs: TodayQueueItem[];
}

export default function MobileToday() {
  const { data, isLoading, error, refetch } = useToday();
  const { items: asks, isLoading: asksLoading } = useSidekickAskingItems();
  const { data: worklistData, isLoading: worklistLoading } = useTodayWorklist();
  const { user } = useAuth();
  const navigate = useNavigate();

  useRefreshOnFocus(refetch);

  const { situationGroups, positives } = useMemo(() => {
    const items = (data?.items || []).filter((i) => i.type !== 'sidekick_question');
    const situations: TodayQueueItem[] = [];
    const pos: TodayQueueItem[] = [];
    for (const item of items) {
      const sev = needSeverity(item.type);
      if (sev === 'risk' || sev === 'warn') situations.push(item);
      else if (sev === 'good') pos.push(item);
    }

    const map = new Map<string, SituationGroup>();
    for (const item of situations) {
      let g = map.get(item.customer_id);
      if (!g) {
        g = {
          customerId: item.customer_id,
          customer: item.customer_name,
          arrCents: item.customer_arr_cents ?? null,
          severity: 'warn',
          oldest: item.created_at,
          needs: [],
        };
        map.set(item.customer_id, g);
      }
      g.needs.push(item);
      if (needSeverity(item.type) === 'risk') g.severity = 'risk';
      if (item.created_at < g.oldest) g.oldest = item.created_at;
    }
    const groups = Array.from(map.values());
    groups.forEach((g) =>
      g.needs.sort((a, b) => {
        const r = (needSeverity(a.type) === 'risk' ? 0 : 1) - (needSeverity(b.type) === 'risk' ? 0 : 1);
        if (r !== 0) return r;
        return a.created_at < b.created_at ? 1 : -1;
      }),
    );
    groups.sort((a, b) => {
      if (a.severity !== b.severity) return a.severity === 'risk' ? -1 : 1;
      if (b.needs.length !== a.needs.length) return b.needs.length - a.needs.length;
      return a.oldest < b.oldest ? -1 : 1;
    });
    pos.sort((a, b) => a.priority_rank - b.priority_rank);
    return { situationGroups: groups, positives: pos };
  }, [data?.items]);

  const worklist = useMemo(() => {
    return (worklistData?.milestones || [])
      .filter((m) => !!(m.goal?.customer?.id && m.goal?.customer?.name))
      .map((m) => ({
        id: m.id,
        customerId: m.goal!.customer!.id,
        customer: m.goal!.customer!.name,
        title: m.title,
        description: m.description,
      }));
  }, [worklistData?.milestones]);

  const firstName = user?.displayName?.split(' ')[0];
  const loading = isLoading || asksLoading || worklistLoading;
  const empty =
    situationGroups.length === 0 && positives.length === 0 && worklist.length === 0 && asks.length === 0;

  return (
    <div>
      <ScreenHeader
        eyebrow={new Date()
          .toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })
          .toUpperCase()}
        title={
          <>
            {getGreeting()}{firstName ? <>, <em className="font-normal italic text-accent">{firstName}</em></> : ''}.
          </>
        }
        sub={
          situationGroups.length > 0
            ? `${situationGroups.length} account${situationGroups.length === 1 ? '' : 's'} in the way`
            : 'All clear up top'
        }
      />

      {error ? (
        <MobileError message={(error as Error).message} onRetry={() => refetch()} />
      ) : loading ? (
        <MobileLoading />
      ) : empty ? (
        <MobileEmpty
          icon={<Check className="h-7 w-7 text-signal-ok" />}
          title="All clear"
          body="Nothing needs you right now. Sidekick is watching your portfolio."
        />
      ) : (
        <div className="pb-6">
          {situationGroups.length > 0 && (
            <>
              <SectionLabel label="In the way" count={situationGroups.length} tone="alarm" />
              <div className="space-y-3 px-4">
                {situationGroups.map((g) => (
                  <SituationCard key={g.customerId} group={g} onOpen={() => navigate(`/m/customers/${g.customerId}`)} />
                ))}
              </div>
            </>
          )}

          {positives.length > 0 && (
            <>
              <SectionLabel label="Positive signals" count={positives.length} />
              <div className="space-y-3 px-4">
                {positives.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => navigate(`/m/customers/${item.customer_id}`)}
                    className="block w-full rounded-md border border-border bg-surface p-4 text-left edge-ok"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-display text-lg text-fg-100">{item.customer_name}</span>
                      <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-fg-400">
                        {timeAgo(item.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-[15px] leading-snug text-fg-200">{item.headline}</p>
                  </button>
                ))}
              </div>
            </>
          )}

          {worklist.length > 0 && (
            <>
              <SectionLabel label="Today's worklist" count={worklist.length} />
              <div className="space-y-3 px-4">
                {worklist.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => navigate(`/m/customers/${m.customerId}`)}
                    className="block w-full rounded-md border border-border bg-surface p-4 text-left"
                  >
                    <div className="mb-1 flex items-center gap-2">
                      <span className="h-3.5 w-3.5 shrink-0 border-[1.5px] border-fg-400/50" />
                      <span className="font-display text-base text-fg-100">{m.customer}</span>
                    </div>
                    <p className="text-[15px] leading-snug text-fg-200">{m.title}</p>
                    {m.description && (
                      <p className="mt-0.5 line-clamp-2 text-[13px] leading-snug text-fg-400">{m.description}</p>
                    )}
                  </button>
                ))}
              </div>
            </>
          )}

          {asks.length > 0 && (
            <>
              <SectionLabel label="Sidekick asks" count={asks.length} tone="quiet" />
              <div className="space-y-3 px-4">
                {asks.map((a) => (
                  <button
                    key={a.id}
                    onClick={() => navigate('/m/sidekick')}
                    className="flex w-full items-center gap-3 rounded-md border border-border bg-surface p-3.5 text-left"
                  >
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent font-mono text-[10px] font-bold text-page">
                      SK
                    </span>
                    <div className="min-w-0 flex-1">
                      <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-accent">
                        {a.customer_name}
                      </span>
                      <p className="truncate font-sans text-[15px] italic text-fg-200">{a.question}</p>
                    </div>
                    <Zap className="h-4 w-4 shrink-0 text-accent" />
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SituationCard({ group, onOpen }: { group: SituationGroup; onOpen: () => void }) {
  const risk = group.severity === 'risk';
  const arr = formatARR(group.arrCents);
  return (
    <button
      onClick={onOpen}
      className={cn('block w-full rounded-md border border-border bg-surface p-4 text-left', risk ? 'edge-risk' : 'edge-warn')}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-display text-xl leading-none text-fg-100">{group.customer}</span>
          </div>
          <div className="mt-1 flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.18em] text-fg-400">
            <span className={cn('font-bold', risk ? 'text-signal-bad' : 'text-signal-warn')}>
              {group.needs.length} {group.needs.length === 1 ? 'need' : 'needs'}
            </span>
            {arr !== '-' && <span>· {arr} ARR</span>}
            <span>· {timeAgo(group.oldest)}</span>
          </div>
        </div>
        <ChevronRight className="mt-1 h-5 w-5 shrink-0 text-fg-400" />
      </div>

      <div className="mt-3 space-y-1.5 border-t border-border pt-3">
        {group.needs.slice(0, 3).map((n) => (
          <div key={n.id} className="flex items-baseline gap-2">
            <span
              className={cn(
                'shrink-0 font-mono text-[9px] font-bold uppercase tracking-[0.16em]',
                severityText[needSeverity(n.type)],
              )}
            >
              {needTypeLabel(n.type)}
            </span>
            <span className="truncate text-[14px] leading-snug text-fg-300">{n.headline}</span>
          </div>
        ))}
        {group.needs.length > 3 && (
          <p className="text-[12px] italic text-fg-400">+{group.needs.length - 3} more</p>
        )}
      </div>
    </button>
  );
}
