import React from 'react';
import { NavLink, useParams } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useRenewalWorkspace } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import {
  formatARR,
  renewalDateLabel,
  PLAY_KIND_LABEL,
  POSTURE_LABEL,
  type RenewalWorkspaceData,
  type RenewalGoal,
  type RenewalPlay,
  type RenewalRiskItem,
  type RenewalStakeholder,
} from '@/lib/renewals';
import type { RiskLevel } from '@/lib/renewals';
import type { SignalState } from '@/lib/api';
import { PostureBadge, ProgressTrack, SectionHeader } from '@/components/renewals/atoms';
import { ChevronRight } from 'lucide-react';

const TONE_TEXT: Record<SignalState, string> = { ok: 'text-signal-ok', warn: 'text-signal-warn', risk: 'text-signal-risk' };
const TONE_DOT: Record<SignalState, string> = { ok: 'bg-signal-ok', warn: 'bg-signal-warn', risk: 'bg-signal-risk' };
const SEV: Record<RiskLevel, { tone: SignalState; label: string }> = {
  high: { tone: 'risk', label: 'HIGH' },
  medium: { tone: 'warn', label: 'MED' },
  low: { tone: 'ok', label: 'LOW' },
};

// ---- hero ----------------------------------------------------
function Hero({ ws }: { ws: RenewalWorkspaceData }) {
  const p = ws.posture;
  const allVecs = ws.goals.flatMap(g => g.vectors);
  const greenVecs = allVecs.filter(v => v.current_state === 'ok').length;
  const totalVecs = allVecs.length;
  const champion = ws.stakeholders.find(s => s.is_champion);
  const championFact = champion
    ? (champion.status === 'departed' ? 'Departed' : champion.name.split(' ')[0])
    : 'None';

  const facts: Array<{ k: string; v: string; tone?: string }> = [
    { k: p === 'expand' ? 'CURRENT ARR' : 'ARR', v: formatARR(ws.arr_cents) },
    { k: 'RENEWS IN', v: ws.days_to_renewal != null ? `${ws.days_to_renewal} days` : '—', tone: p === 'defend' && (ws.days_to_renewal ?? 99) <= 30 ? 'text-signal-risk' : '' },
    p === 'expand' && ws.profile?.expansion_pipe_cents
      ? { k: 'EXPANSION PIPE', v: `+${formatARR(ws.profile.expansion_pipe_cents)}`, tone: 'text-brass' }
      : { k: 'CHAMPION', v: championFact, tone: champion?.status === 'departed' ? 'text-signal-risk' : '' },
    { k: 'GOAL COVERAGE', v: totalVecs ? `${greenVecs} of ${totalVecs} green` : '—', tone: 'text-brass' },
  ];

  return (
    <div className={cn('relative mb-6 border border-border', `rn-hero--${p}`)}>
      <div className="flex items-center gap-3.5 px-6 py-3 border-b border-rule">
        <span className={cn('font-mono text-[10px] font-bold tracking-[0.24em] uppercase flex items-center gap-2.5', TONE_TEXT[p === 'hold' ? 'warn' : p === 'expand' ? 'ok' : 'risk'])}>
          <span className={cn('w-2 h-2 rounded-full', p === 'defend' ? 'bg-signal-risk' : p === 'expand' ? 'bg-signal-ok' : 'bg-brass')} />
          POSTURE · {POSTURE_LABEL[p]}
        </span>
        <span className="ml-auto flex items-center gap-2 font-mono text-[9px] tracking-[0.16em] uppercase text-fg-400">
          <span className="w-4 h-4 rounded-full bg-accent text-page grid place-items-center text-[8px] font-bold">SK</span>
          {ws.profile?.posture_reason || 'Posture set from account signals'}
        </span>
      </div>
      <div className="px-6 pt-5 pb-6">
        <div className="flex items-center gap-3.5 mb-3.5 font-mono text-[10px] tracking-[0.2em] uppercase text-fg-400 flex-wrap">
          <span className="text-accent">RNW-{ws.slug.toUpperCase()}</span>
          {ws.tier && <><span>·</span><span>{ws.tier}</span></>}
          {ws.one_liner && <><span>·</span><span className="normal-case tracking-normal text-fg-300">{ws.one_liner}</span></>}
        </div>
        <h1 className="font-display text-[2.6rem] leading-none tracking-tight text-fg-100 mb-3.5">{ws.name}</h1>
        {ws.profile?.narrative_lede && (
          <p className="text-lg text-fg-200 leading-snug max-w-3xl mb-4">{ws.profile.narrative_lede}</p>
        )}
        <div className="flex items-stretch border border-border">
          {facts.map((f, i) => (
            <div key={i} className={cn('flex-1 px-4 py-3', i < facts.length - 1 && 'border-r border-rule')}>
              <div className="font-mono text-[8.5px] tracking-[0.16em] uppercase text-fg-400 mb-1.5">{f.k}</div>
              <div className={cn('font-mono text-[1.1rem]', f.tone || 'text-fg-100')}>{f.v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- goal-progress spine -------------------------------------
function ProofRow({ goal }: { goal: RenewalGoal }) {
  return (
    <>
      {goal.vectors.map(v => (
        <div key={v.id} className={cn('bg-surface border border-border px-5 py-4', `rn-edge-${v.current_state === 'risk' ? 'defend' : v.current_state === 'ok' ? 'expand' : 'hold'}`)}>
          <div className="grid grid-cols-[1fr_180px_52px] gap-4 items-center">
            <div>
              <p className="text-[1.05rem] text-fg-100 leading-tight mb-1">{goal.text}</p>
              <span className="font-mono text-[8.5px] tracking-[0.16em] uppercase text-fg-400">VECTOR · {v.category.replace('_', ' ')}</span>
            </div>
            <div>
              <ProgressTrack progress={v.progress} baseline={v.baseline_progress} tone={v.current_state} className="h-1.5 mb-1.5" />
              {v.target_label && <div className="font-mono text-[8.5px] tracking-[0.1em] uppercase text-fg-400">{v.target_label}</div>}
            </div>
            <div className={cn('font-mono text-[1.4rem] text-right', TONE_TEXT[v.current_state])}>
              {v.progress != null ? `${Math.round(v.progress * 100)}%` : '—'}
            </div>
          </div>
          {v.unlocks && (
            <div className="mt-3.5 pt-3 border-t border-rule grid grid-cols-[64px_1fr] gap-3 items-start">
              <span className="font-mono text-[8px] font-bold tracking-[0.16em] uppercase text-accent pt-0.5">SAY IT AS</span>
              <p className="text-sm text-fg-200 leading-relaxed italic">{v.unlocks}</p>
            </div>
          )}
        </div>
      ))}
    </>
  );
}

// ---- play card -----------------------------------------------
function PlayCard({ play }: { play: RenewalPlay }) {
  const badgeTone = play.posture === 'expand' ? 'bg-signal-ok' : play.posture === 'defend' ? 'bg-signal-risk' : 'bg-brass';
  return (
    <div className={cn('bg-surface border border-border px-5 py-4', play.is_primary && 'rn-play--primary')}>
      <div className="flex items-center gap-3 mb-2.5">
        <span className={cn('font-mono text-[8px] font-bold tracking-[0.18em] uppercase px-2 py-0.5 text-page', badgeTone)}>
          {PLAY_KIND_LABEL[play.kind]}
        </span>
        {play.value_label && <span className="ml-auto font-mono text-[9px] tracking-[0.14em] uppercase text-brass font-bold">{play.value_label}</span>}
      </div>
      <h4 className="font-display text-[1.2rem] leading-tight text-fg-100 mb-2">{play.title}</h4>
      <p className="text-sm text-fg-300 leading-relaxed mb-3">{play.description}</p>
      {play.basis && (
        <div className="flex items-center gap-2 font-mono text-[8.5px] tracking-[0.14em] uppercase text-fg-400">
          <span className="w-1.5 h-1.5 bg-brass" /> BASIS · {play.basis}
        </div>
      )}
    </div>
  );
}

// ---- risk register -------------------------------------------
function RiskRow({ risk }: { risk: RenewalRiskItem }) {
  const sev = SEV[risk.severity];
  return (
    <div className="bg-surface px-5 py-3.5 grid grid-cols-[18px_1fr_auto] gap-3.5 items-center">
      <span className={cn('w-2 h-2 rounded-full', TONE_DOT[sev.tone])} />
      <div>
        <h5 className="text-[0.92rem] font-semibold text-fg-100 mb-0.5">{risk.title}</h5>
        <p className="text-[0.8rem] text-fg-400 leading-snug">
          {risk.description}
          {risk.mitigation && <span className="text-brass italic"> Mitigation: {risk.mitigation}</span>}
        </p>
      </div>
      <span className={cn('font-mono text-[8px] font-bold tracking-[0.16em] uppercase px-2 py-1 border', TONE_TEXT[sev.tone])} style={{ borderColor: 'currentColor' }}>
        {sev.label}
      </span>
    </div>
  );
}

// ---- right rail ----------------------------------------------
function StakeholderRow({ s }: { s: RenewalStakeholder }) {
  return (
    <div className="grid grid-cols-[28px_1fr_auto] gap-3 items-center py-2.5 border-t border-rule first:border-t-0 first:pt-0.5">
      <span className={cn('w-7 h-7 rounded-full grid place-items-center font-mono font-bold text-[9px]', s.is_champion ? 'bg-accent text-page' : 'bg-surface-deep text-fg-200')}>
        {s.initials}
      </span>
      <div className="min-w-0">
        <span className="text-[0.95rem] text-fg-100 block leading-tight truncate">{s.name}</span>
        <span className="font-mono text-[8px] tracking-[0.14em] uppercase text-fg-400 block mt-0.5 truncate">{s.role || '—'}</span>
      </div>
      <span className={cn('w-2 h-2 rounded-full', TONE_DOT[s.tone])} />
    </div>
  );
}

function Rail({ ws }: { ws: RenewalWorkspaceData }) {
  const p = ws.profile;
  const crit = (ws.days_to_renewal ?? 99) <= 30 && ws.posture === 'defend';
  const contract: Array<[string, string, string?]> = [
    ['CURRENT ARR', formatARR(ws.arr_cents)],
    p?.target_arr_cents ? ['TARGET ARR', formatARR(p.target_arr_cents), 'text-brass'] : ['TERM', p?.term_note || 'Annual'],
    ['RENEWAL TYPE', p?.renewal_type || '—', ws.posture === 'defend' ? 'text-signal-risk' : ws.posture === 'expand' ? 'text-signal-ok' : ''],
    ['AUTO-RENEW', p?.auto_renew == null ? '—' : p.auto_renew ? 'Yes' : 'No · opt-in'],
    ['LAST PRICE CHANGE', p?.last_price_change_note || '—'],
    ['READINESS', (ws.renewal_readiness || '—').replace('_', ' ')],
  ];
  // recommended motion = the play titles in order (first 3)
  const motion = ws.plays.slice(0, 3);

  return (
    <div className="sticky top-6 space-y-4">
      {/* countdown */}
      <div className="border border-border bg-surface">
        <div className="px-4 py-5 text-center border-b border-rule">
          <div className={cn('font-display text-[3rem] leading-none', crit ? 'text-signal-risk' : 'text-brass')}>{ws.days_to_renewal ?? '—'}</div>
          <div className="font-mono text-[9px] tracking-[0.2em] uppercase text-fg-400 mt-2">DAYS TO RENEWAL · {renewalDateLabel(ws.days_to_renewal)}</div>
        </div>
        <div className="px-4 py-3 font-mono text-[9.5px] font-bold tracking-[0.24em] uppercase text-accent">CONTRACT</div>
        <div className="px-4 pb-4 grid grid-cols-2 gap-x-3 gap-y-3.5">
          {contract.map(([k, v, tone]) => (
            <div key={k}>
              <div className="font-mono text-[8.5px] tracking-[0.16em] uppercase text-fg-400 mb-1">{k}</div>
              <div className={cn('text-[0.95rem] font-medium capitalize', tone || 'text-fg-100')}>{v}</div>
            </div>
          ))}
        </div>
      </div>

      {/* stakeholders */}
      {ws.stakeholders.length > 0 && (
        <div className="border border-border bg-surface">
          <div className="px-4 py-3 border-b border-rule flex items-center font-mono text-[9.5px] font-bold tracking-[0.24em] uppercase text-accent">
            <span>STAKEHOLDERS</span>
            <span className="ml-auto text-fg-400 font-normal">{ws.stakeholders.length}</span>
          </div>
          <div className="px-4 py-3">
            {ws.stakeholders.map(s => <StakeholderRow key={s.id} s={s} />)}
          </div>
        </div>
      )}

      {/* recommended motion */}
      {motion.length > 0 && (
        <div className="border border-brass/50 bg-surface p-4" style={{ boxShadow: 'inset 3px 0 0 0 var(--brass-500)' }}>
          <div className="flex items-center gap-2 font-mono text-[9px] font-bold tracking-[0.22em] uppercase text-accent mb-2.5">
            <span className="w-4 h-4 rounded-full bg-accent text-page grid place-items-center text-[8px]">SK</span>
            RECOMMENDED MOTION
          </div>
          {ws.profile?.narrative_lede && <p className="text-[0.86rem] text-fg-200 leading-relaxed">{ws.profile.narrative_lede}</p>}
          <ol className="rn-steps">
            {motion.map((m, i) => <li key={m.id} data-n={String(i + 1)}>{m.title}</li>)}
          </ol>
        </div>
      )}
    </div>
  );
}

// ---- page ----------------------------------------------------
function WorkspaceSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="h-40 bg-surface-2 border border-border" />
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6">
        <div className="space-y-3">{[0, 1, 2].map(i => <div key={i} className="h-28 bg-surface-2" />)}</div>
        <div className="h-72 bg-surface-2" />
      </div>
    </div>
  );
}

export default function RenewalWorkspace() {
  const { customerId } = useParams();
  const { workspace: ws, isLoading, error, refetch } = useRenewalWorkspace(customerId ?? null);
  useRefreshOnFocus(refetch);

  const goalsWithVectors = React.useMemo(
    () => (ws?.goals || []).filter(g => g.vectors.length > 0),
    [ws]
  );

  const playsLabel = ws?.posture === 'expand' ? 'EXPANSION PLAYS' : ws?.posture === 'defend' ? 'DEFENSE PLAYS' : 'RENEWAL PLAYS';

  return (
    <div>
      <div className="flex items-center gap-2.5 mb-5 font-mono text-[10px] tracking-[0.18em] uppercase text-fg-400">
        <NavLink to="/app/renewals" className="hover:text-accent transition-colors">RENEWALS</NavLink>
        <span>›</span>
        <span className="text-fg-200">{ws?.name || '…'}</span>
      </div>

      {error ? (
        <div className="hud-pane p-8">
          <div className="text-[10px] uppercase tracking-[0.3em] text-signal-bad font-bold mb-4">Connection Error</div>
          <p className="text-fg-200 mb-4">{(error as Error).message}</p>
          <button onClick={() => refetch()} className="btn-hud">Retry</button>
        </div>
      ) : isLoading ? (
        <WorkspaceSkeleton />
      ) : !ws ? (
        <div className="hud-pane p-12 text-center">
          <h2 className="font-display text-2xl text-fg-100 mb-2">Renewal not found</h2>
          <p className="text-fg-400 mb-6">This account has no renewal data yet.</p>
          <NavLink to="/app/renewals" className="btn-hud">← Back to Renewals</NavLink>
        </div>
      ) : (
        <>
          <Hero ws={ws} />
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 items-start">
            <div className="min-w-0">
              {goalsWithVectors.length > 0 && (
                <section className="mb-8">
                  <SectionHeader label="GOAL-PROGRESS SPINE" note="THE PROOF · WHAT THEY BOUGHT US FOR" />
                  <div className="space-y-2.5">
                    {goalsWithVectors.map(g => <ProofRow key={g.id} goal={g} />)}
                  </div>
                </section>
              )}

              {ws.plays.length > 0 && (
                <section className="mb-8">
                  <SectionHeader label={playsLabel} note="SIDEKICK-SEQUENCED" />
                  <div className="space-y-2">
                    {ws.plays.map(pl => <PlayCard key={pl.id} play={pl} />)}
                  </div>
                </section>
              )}

              {ws.risk_items.length > 0 && (
                <section className="mb-8">
                  <SectionHeader label="RISK REGISTER" note="WHAT COULD LOSE IT" />
                  <div className="flex flex-col gap-px bg-border border border-border">
                    {ws.risk_items.map(r => <RiskRow key={r.id} risk={r} />)}
                  </div>
                </section>
              )}

              <div className="flex items-center gap-4 pt-5 border-t border-border">
                <span className="font-mono text-[9.5px] tracking-[0.16em] uppercase text-fg-400 flex items-center gap-2.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                  {POSTURE_LABEL[ws.posture]} PLAN · {ws.plays.length} PLAY{ws.plays.length !== 1 ? 'S' : ''} · RENEWAL T-{ws.days_to_renewal}d
                </span>
                <span className="flex-1" />
                <NavLink to={`/app/customers/${ws.id}`} className="btn-hud">OPEN CUSTOMER</NavLink>
                <NavLink to={`/app/customers/${ws.id}`} className="btn-hud btn-hud--primary">
                  BUILD RENEWAL DECK <ChevronRight className="w-3.5 h-3.5" />
                </NavLink>
              </div>
            </div>

            <Rail ws={ws} />
          </div>
        </>
      )}
    </div>
  );
}
