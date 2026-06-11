import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { useUpdateRiskPlayStep, type useRiskBriefsForCustomer } from '@/lib/dataconnect-hooks';

// Midnight-Brass alarm treatment (terracotta = urgent, brass = emphasis/sequence) lives in
// `src/styles/risk-card.css` as reusable `risk-card*` classes. Colors stay in CSS so the card
// can be dropped in anywhere; only layout/typography are Tailwind utilities here.

type RiskBrief = NonNullable<ReturnType<typeof useRiskBriefsForCustomer>['data']>['briefs'][number];

interface RiskStakeholder {
  status?: string | null;
  last_interaction_at?: string | null;
}

interface RiskSignal {
  kind?: string | null;
  state?: string | null;
  sentence?: string | null;
  evidence_text?: string | null;
}

interface RiskSavePlayCardProps {
  briefs: RiskBrief[];
  /** Real customer fields used to populate the urgency strip (rendered only when present). */
  daysToRenewal?: number | null;
  healthLabel?: string | null;
  healthScore?: number | null;
  arrCents?: number | null;
  lifecycle?: string | null;
  stakeholders?: RiskStakeholder[];
  /** Customer signals — the risk-state one carries the event metrics (silent/WAU/renewal). */
  signals?: RiskSignal[];
  onStartPlay?: () => void;
  onEscalation?: () => void;
  onMarkStable?: () => void;
  /** Called after a step is marked done / notes saved, so the parent can refetch. */
  onStepChanged?: () => void;
  className?: string;
}

function formatARR(cents: number | null | undefined): string | null {
  if (!cents) return null;
  const amount = cents / 100;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return `$${amount}`;
}

function healthTemperature(score: number): string {
  if (score >= 80) return 'Toasty';
  if (score >= 60) return 'Warm';
  if (score >= 40) return 'Lukewarm';
  if (score >= 20) return 'Chilly';
  return 'Frosty';
}

interface UrgencyTile {
  k: string;
  v: string;
  unit?: string;
  crit?: boolean;
}

interface EventMetrics {
  renewalDays?: number;
  silentDays?: number;
  wauDropPct?: number;
  championDeparted?: boolean;
}

/**
 * Pull the headline risk numbers out of the brief's own prose (whatChanged + evidence + play).
 * The orchestrator's risk event carries these as facts — e.g. "Last inbound 21 days ago.
 * Champion (VP Eng) departed. WAU down 60% MoM. Renewal in 60 days." — but not as discrete
 * columns, so we read them from the event return rather than hardcoding anything.
 */
function parseEventMetrics(text: string): EventMetrics {
  const m: EventMetrics = {};
  const renewal = text.match(/renewal\s+(?:is\s+)?(?:in|due in|due)\s+(\d+)\s*days?/i);
  if (renewal) m.renewalDays = parseInt(renewal[1], 10);
  const silent =
    text.match(/last\s+inbound\s+(\d+)\s*days?/i) ||
    text.match(/(\d+)\s*days?\s*(?:ago|of silence|silent|since|dark)/i) ||
    text.match(/silent\s+for\s+(\d+)\s*days?/i);
  if (silent) m.silentDays = parseInt(silent[1], 10);
  const wau = text.match(/\bw[ae]u\b[^.%]*?(\d+)\s*%/i) || text.match(/(?:usage|active users)[^.%]*?(\d+)\s*%/i);
  if (wau) m.wauDropPct = parseInt(wau[1], 10);
  if (/champion[^.]*depart|depart[^.]*champion/i.test(text)) m.championDeparted = true;
  return m;
}

type PlayStep = RiskBrief['steps'][number];

/**
 * One save-play step. The number circle is a Mark-complete toggle (not HITL — just "I did this"),
 * and "+ Notes" expands an optional textarea for CSM findings (captured for the record; a future
 * AI run can fold them back in). Persists via UpdateRiskPlayStep, then asks the parent to refetch.
 */
function StepRow({
  step,
  index,
  total,
  onChanged,
}: {
  step: PlayStep;
  index: number;
  total: number;
  onChanged?: () => void;
}) {
  const updateStep = useUpdateRiskPlayStep();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(step.notes ?? '');
  const [busy, setBusy] = useState(false);

  async function run(done: boolean, notes: string | null) {
    setBusy(true);
    try {
      await updateStep.mutateAsync({ id: step.id, done, notes });
      onChanged?.();
    } catch (e) {
      console.warn('Step update failed:', e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="relative flex gap-4 pb-5 last:pb-0">
      {index < total - 1 && (
        <span className="absolute left-[15px] top-8 bottom-0 border-l border-border" aria-hidden />
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() => run(!step.done, step.notes ?? null)}
        title={step.done ? 'Mark not done' : 'Mark complete'}
        className={cn(
          'relative z-10 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full font-mono text-sm transition hover:brightness-110 disabled:opacity-50',
          step.done
            ? 'risk-card__step-num risk-card__step-num--done'
            : index === 0
            ? 'risk-card__step-num risk-card__step-num--active'
            : 'risk-card__step-num'
        )}
      >
        {step.done ? '✓' : index + 1}
      </button>
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <h5
            className={cn(
              'font-sans text-base font-semibold normal-case tracking-normal',
              step.done ? 'text-fg-400 line-through' : 'text-fg-100'
            )}
          >
            {step.label}
          </h5>
          {index === 0 && !step.done && (
            <span className="risk-card__donow font-mono text-[9px] font-bold uppercase tracking-[0.2em] px-1.5 py-0.5">
              Do now
            </span>
          )}
        </div>
        {step.rationale && (
          <p className="text-fg-300 text-sm mt-1 leading-relaxed">{step.rationale}</p>
        )}

        {editing ? (
          <div className="mt-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={3}
              placeholder="What did you find / do? (optional)"
              className="w-full resize-y rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg-100 focus:border-accent focus:outline-none"
            />
            <div className="mt-1.5 flex gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => run(step.done, draft.trim() || null).then(() => setEditing(false))}
                className="bg-accent px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-page hover:bg-accent-hover disabled:opacity-50"
              >
                Save note
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraft(step.notes ?? '');
                  setEditing(false);
                }}
                className="border border-border px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-fg-300 hover:bg-surface-2"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : step.notes ? (
          <div className="mt-2 rounded-md border-l-2 border-l-accent bg-surface-2 px-3 py-2">
            <p className="whitespace-pre-wrap text-sm text-fg-200">{step.notes}</p>
            <button
              type="button"
              onClick={() => {
                setDraft(step.notes ?? '');
                setEditing(true);
              }}
              className="mt-1 font-mono text-[10px] uppercase tracking-widest text-fg-400 hover:text-accent"
            >
              Edit note
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => {
              setDraft('');
              setEditing(true);
            }}
            className="mt-1.5 font-mono text-[10px] uppercase tracking-widest text-fg-400 hover:text-accent"
          >
            + Notes
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * Renders the orchestrator's Risk/Save play output (RiskBrief + ordered RiskPlaySteps) as the
 * urgent "Save Play" centerpiece of the Customer Detail overview. Shows the most recent brief;
 * older briefs are history (v2: a "previous plays" disclosure). The caller gates on
 * `briefs.length > 0`, so this never renders an empty state.
 */
export function RiskSavePlayCard({
  briefs,
  daysToRenewal,
  healthLabel,
  healthScore,
  arrCents,
  lifecycle,
  stakeholders,
  signals,
  onStartPlay,
  onEscalation,
  onMarkStable,
  onStepChanged,
  className,
}: RiskSavePlayCardProps) {
  const brief = briefs[0];
  if (!brief) return null;

  const generatedAt = brief.generatedAt || brief.createdAt;
  const generatedLabel = generatedAt
    ? new Date(generatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()
    : null;

  const title = brief.play || brief.whatChanged || 'Renewal at risk — save play ready';
  const steps = brief.steps;

  // Urgency strip — the headline risk numbers, read from the brief's own event prose first
  // (the risk event carries them), with customer/stakeholder fields as fallbacks. Ordered
  // most-risk-relevant first, then capped at 4 tiles to match the mock's row.
  // The risk-state signal is the authoritative event return (deterministic metrics); the
  // brief's prose is the fallback. Parse the signal text first so it wins.
  const signalText = (signals || [])
    .filter((s) => s.state === 'risk')
    .map((s) => `${s.evidence_text || ''} ${s.sentence || ''}`)
    .join(' ');
  const ev = parseEventMetrics(
    `${signalText} ${brief.whatChanged || ''} ${brief.evidenceText || ''} ${brief.play || ''}`
  );
  const tiles: UrgencyTile[] = [];

  // Renewal countdown — from the event, else the customer record.
  const renewalDays = ev.renewalDays ?? (daysToRenewal != null ? daysToRenewal : undefined);
  if (renewalDays != null) {
    tiles.push({ k: 'RENEWAL IN', v: `${renewalDays}`, unit: 'days', crit: renewalDays <= 90 });
  }

  // Account silent — from the event, else days since the most recent stakeholder interaction.
  let silentDays = ev.silentDays;
  if (silentDays == null) {
    const lastTouch = (stakeholders || [])
      .map((s) => (s.last_interaction_at ? new Date(s.last_interaction_at).getTime() : null))
      .filter((t): t is number => t != null && !Number.isNaN(t))
      .sort((a, b) => b - a)[0];
    if (lastTouch) silentDays = Math.max(0, Math.floor((Date.now() - lastTouch) / 86400000));
  }
  if (silentDays != null) {
    tiles.push({ k: 'ACCOUNT SILENT', v: `${silentDays}`, unit: 'days', crit: silentDays >= 14 });
  }

  // Weekly active users — only from the event (no customer column for it).
  if (ev.wauDropPct != null) {
    tiles.push({ k: 'WEEKLY ACTIVE USERS', v: `−${ev.wauDropPct}%`, crit: true });
  }

  // Champion departed — from the event or a stakeholder marked departed.
  const departed = ev.championDeparted || (stakeholders || []).some((s) => s.status === 'departed');
  if (departed) {
    tiles.push({ k: 'CHAMPION', v: 'Departed', crit: true });
  }

  // Fallbacks so the strip is never empty for non-renewal briefs.
  if (healthScore != null) {
    tiles.push({ k: 'RELATIONSHIP', v: healthTemperature(healthScore), crit: healthScore < 40 });
  } else if (healthLabel) {
    tiles.push({ k: 'RELATIONSHIP', v: healthLabel.replace(/_/g, ' ') });
  }
  const arr = formatARR(arrCents);
  if (arr) tiles.push({ k: 'ARR', v: arr });
  if (lifecycle) {
    tiles.push({ k: 'LIFECYCLE', v: lifecycle.replace(/_/g, ' '), crit: lifecycle === 'at_risk' });
  }
  const shownTiles = tiles.slice(0, 4);

  return (
    <div className={cn('risk-card mb-8', className)}>
      {/* alarm header (terracotta wash + bottom rule via .risk-card__alarm) */}
      <div className="risk-card__alarm flex flex-wrap items-center justify-between gap-2 px-6 py-3">
        <span className="risk-card__alarm-label flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[0.2em]">
          <span className="text-[10px] leading-none" aria-hidden>▲</span>
          Renewal at risk · Save play active
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-400">
          SK-Generated{generatedLabel ? ` · ${generatedLabel}` : ''} · Review before acting
        </span>
      </div>

      <div className="relative px-6 py-6">
        {/* headline = the one-line save-play summary */}
        <h2 className="font-serif text-3xl sm:text-4xl text-fg-100 mb-5 leading-none">{title}</h2>

        {/* urgency strip — terracotta-tinted frame + dividers; crit numbers in full terracotta */}
        {shownTiles.length > 0 && (
          <div className="risk-card__strip grid grid-cols-2 mb-6">
            {shownTiles.map((t) => (
              <div key={t.k} className="risk-card__cell px-4 py-3">
                <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-400 mb-1">
                  {t.k}
                </div>
                <div className={cn('font-serif text-2xl leading-none', t.crit ? 'risk-card__num--crit' : 'text-fg-100')}>
                  {t.v}
                  {t.unit && <span className="font-sans text-sm lowercase italic text-fg-300 ml-1">{t.unit}</span>}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* what changed */}
        {brief.whatChanged && (
          <div className="mb-4">
            <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-400 mb-1">
              What changed
            </h4>
            <p className="text-fg-200">{brief.whatChanged}</p>
          </div>
        )}

        {/* evidence */}
        {brief.evidenceText && (
          <div className="mb-6 border-l border-border pl-4">
            <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-400 mb-1">
              Evidence
            </h4>
            <p className="text-fg-300 text-sm leading-relaxed">{brief.evidenceText}</p>
          </div>
        )}

        {/* the save play */}
        <div className="risk-card__seq font-mono text-[10px] uppercase tracking-[0.2em] mb-4 flex items-center gap-1.5">
          <span className="text-sm leading-none">✦</span>
          The save play{steps.length > 0 ? ` · ${steps.length} ${steps.length === 1 ? 'move' : 'moves'}` : ''}
        </div>

        {steps.length === 0 ? (
          <p className="text-fg-400 text-sm italic">No steps recorded.</p>
        ) : (
          <ol className="space-y-0">
            {steps.map((step, i) => (
              <StepRow
                key={step.id}
                step={step}
                index={i}
                total={steps.length}
                onChanged={onStepChanged}
              />
            ))}
          </ol>
        )}

        {/* cta row */}
        <div className="flex flex-wrap items-center gap-3 mt-7">
          <button
            onClick={onStartPlay}
            className="risk-card__cta px-4 py-2 text-sm font-medium inline-flex items-center gap-2"
          >
            Start the save play <span aria-hidden>→</span>
          </button>
          <button
            onClick={onEscalation}
            className="text-sm text-fg-400 hover:text-fg-200 transition-colors"
          >
            Escalation brief
          </button>
          <button
            onClick={onMarkStable}
            className="text-sm text-fg-400 hover:text-fg-200 transition-colors"
          >
            Mark stable
          </button>
        </div>
      </div>
    </div>
  );
}
