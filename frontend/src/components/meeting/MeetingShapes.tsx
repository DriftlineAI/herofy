// Three meeting prep shapes: QBR, Kickoff, Check-in
// Each receives the Meeting object (with context + brief) and renders the correct layout.

import React from 'react';
import { cn } from '@/lib/utils';
import { HuddleSidecar } from './HuddleSidecar';
import type {
  Meeting,
  MeetingTalkingPoint,
  MeetingStakeholder,
  MeetingContextMilestone,
  MeetingContextSignal,
  MeetingContextCommitment,
} from '@/lib/api';

// MeetingTalkingPoint is string (backend writes list[str])

// ── shared atoms ──────────────────────────────────────────────────────────────

function SectionHdr({ label, note }: { label: string; note?: string }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <span className="w-7 h-px bg-accent shrink-0" />
      <span className="font-mono text-[10px] font-bold tracking-[0.28em] uppercase text-fg-300">
        {label}
      </span>
      <span className="flex-1 h-px bg-rule" />
      {note && (
        <span className="font-mono text-[9px] tracking-[0.14em] uppercase text-fg-400">{note}</span>
      )}
    </div>
  );
}

function BriefGenHeader({ label, ago }: { label: string; ago?: string }) {
  return (
    <div className="flex items-center gap-3 px-4 py-[11px] border border-border bg-accent-bg border-l-[3px] border-l-accent mb-6">
      <span className="w-6 h-6 rounded-full bg-accent text-page grid place-items-center font-mono font-bold text-[10px] shrink-0">
        SK
      </span>
      <span className="font-mono text-[9.5px] tracking-[0.2em] uppercase text-accent font-bold">
        {label}
        {ago && <span className="text-fg-400 font-normal ml-2">· {ago}</span>}
      </span>
      <button className="ml-auto font-mono text-[9px] tracking-[0.2em] uppercase text-fg-400 hover:text-accent transition-colors">
        ↻ REGENERATE
      </button>
    </div>
  );
}

function TalkingPoint({ point, idx }: { point: MeetingTalkingPoint; idx: number }) {
  return (
    <div className="grid gap-3.5 items-start py-[15px] border-t border-rule first:border-t-0"
      style={{ gridTemplateColumns: '30px 1fr' }}>
      <span className="font-sans italic text-[1.3rem] text-accent/60 leading-none">
        {idx + 1}
      </span>
      <p className="font-sans text-[0.95rem] leading-[1.55] text-fg-200 self-center">{point}</p>
    </div>
  );
}

// ── placeholder talking points ─────────────────────────────────────────────────

const PLACEHOLDER_POINTS: MeetingTalkingPoint[] = [
  'Brief is being assembled — Sidekick is pulling signals, threads, and plan progress. Talking points will appear here once the brief is ready.',
];

// ── stakeholder room ──────────────────────────────────────────────────────────

function StanceIndicator({ status }: { status: string }) {
  const lower = (status || '').toLowerCase();
  if (lower.includes('champion') || lower.includes('sponsor') || lower.includes('active')) {
    return (
      <div className="flex items-center gap-1.5 font-mono text-[8.5px] tracking-[0.18em] uppercase text-signal-ok mt-2">
        <span className="w-1.5 h-1.5 rounded-full bg-signal-ok" />
        CHAMPION
      </div>
    );
  }
  if (lower.includes('risk') || lower.includes('skeptic') || lower.includes('detractor')) {
    return (
      <div className="flex items-center gap-1.5 font-mono text-[8.5px] tracking-[0.18em] uppercase text-signal-bad mt-2">
        <span className="w-1.5 h-1.5 rounded-full bg-signal-bad" />
        SKEPTIC
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1.5 font-mono text-[8.5px] tracking-[0.18em] uppercase text-fg-400 mt-2">
      <span className="w-1.5 h-1.5 rounded-full bg-fg-400" />
      NEUTRAL
    </div>
  );
}

function PersonCard({ s, isKey }: { s: MeetingStakeholder; isKey: boolean }) {
  const initials = s.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
  return (
    <div className={cn(
      'p-4 border border-border bg-surface',
      isKey && 'border-l-[3px] border-l-accent',
    )}>
      <div className="flex items-center gap-2.5 mb-2">
        <span className={cn(
          'w-8 h-8 rounded-full grid place-items-center font-mono font-bold text-[10px] shrink-0',
          isKey ? 'bg-accent text-page' : 'bg-surface-deep text-fg-200',
        )}>
          {initials}
        </span>
        <div>
          <span className="font-sans font-semibold text-[1.05rem] text-fg-100 block leading-tight">
            {s.name}
          </span>
          {s.role && (
            <span className="font-mono text-[8.5px] tracking-[0.18em] uppercase text-accent block mt-0.5">
              {s.role}
            </span>
          )}
        </div>
      </div>
      {s.sentiment_note && (
        <p className="font-sans text-[0.82rem] leading-[1.5] text-fg-300">{s.sentiment_note}</p>
      )}
      <StanceIndicator status={s.status} />
    </div>
  );
}

function TheRoom({ stakeholders, attendeesTheirs }: {
  stakeholders: MeetingStakeholder[];
  attendeesTheirs: Meeting['attendees_theirs'];
}) {
  // Prefer rich stakeholders from context, fall back to attendee list
  if (stakeholders.length > 0) {
    return (
      <div className="grid grid-cols-2 gap-3">
        {stakeholders.map((s, i) => (
          <PersonCard key={s.id} s={s} isKey={i === 0} />
        ))}
      </div>
    );
  }

  if (attendeesTheirs.length > 0) {
    return (
      <div className="grid grid-cols-2 gap-3">
        {attendeesTheirs.map((a, i) => (
          <div key={i} className={cn('p-4 border border-border bg-surface', i === 0 && 'border-l-[3px] border-l-accent')}>
            <span className="font-sans font-semibold text-[1.05rem] text-fg-100 block">{a.name}</span>
            {a.role && <span className="font-mono text-[8.5px] tracking-[0.18em] uppercase text-accent block mt-1">{a.role}</span>}
            {a.email && <span className="font-mono text-[9px] text-fg-400 block mt-1">{a.email}</span>}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="border border-dashed border-border px-4 py-6 text-center">
      <p className="font-mono text-[9.5px] tracking-[0.2em] uppercase text-fg-400">
        No attendees added yet
      </p>
    </div>
  );
}

// ── 30/60/90 plan ─────────────────────────────────────────────────────────────

function Plan9090({ milestones }: { milestones: MeetingContextMilestone[] }) {
  // Take first 3, otherwise show placeholders
  const slots = [
    { when: 30, label: '30 DAYS' },
    { when: 60, label: '60 DAYS' },
    { when: 90, label: '90 DAYS' },
  ];

  return (
    <div className="grid grid-cols-3 gap-px bg-border border border-border">
      {slots.map((slot, i) => {
        const ms = milestones[i];
        return (
          <div key={slot.when} className="bg-surface px-[18px] py-[18px]">
            <div className="font-mono text-[1.4rem] text-accent tracking-[-0.01em] mb-1">
              {slot.when}
              <span className="text-[9px] tracking-[0.2em] text-fg-400 block mt-0.5">{slot.label}</span>
            </div>
            {ms ? (
              <>
                <div className="font-sans font-semibold text-[1rem] text-fg-100 mt-3 mb-1.5 leading-tight">
                  {ms.title}
                </div>
                {ms.goal_rationale && (
                  <p className="font-sans text-[0.8rem] text-fg-300 leading-[1.45]">{ms.goal_rationale}</p>
                )}
              </>
            ) : (
              <p className="font-sans text-[0.8rem] text-fg-400 leading-[1.45] mt-3 italic">
                Milestone TBD
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── check-in digest ───────────────────────────────────────────────────────────

function CheckinDigest({ signals, commitments }: {
  signals: MeetingContextSignal[];
  commitments: MeetingContextCommitment[];
}) {
  const rows: { k: string; v: string; cls?: string }[] = [];

  // Signals
  const posSignal = signals.find(s => s.state === 'positive' || s.state === 'green');
  const warnSignal = signals.find(s => s.state === 'negative' || s.state === 'red' || s.state === 'yellow');

  if (posSignal) rows.push({ k: 'ENGAGEMENT', v: posSignal.sentence, cls: 'text-signal-ok' });
  if (warnSignal) rows.push({ k: 'WATCH', v: warnSignal.sentence, cls: 'text-signal-warn' });

  // Open commitment
  const ourCommit = commitments.find(c => c.side === 'us' || c.side === 'ours');
  if (ourCommit) rows.push({ k: 'OPEN LOOP', v: ourCommit.text, cls: 'text-signal-warn' });

  // Fallback
  if (rows.length === 0) {
    rows.push(
      { k: 'SIGNALS', v: 'No active signals detected. Good cadence.' },
      { k: 'COMMITMENTS', v: 'No open commitments.' },
    );
  }

  return (
    <div className="flex flex-col gap-px bg-border border border-border">
      {rows.map((r, i) => (
        <div key={i} className="bg-surface px-[18px] py-3.5 grid gap-4 items-baseline"
          style={{ gridTemplateColumns: '130px 1fr' }}>
          <span className="font-mono text-[9.5px] font-bold tracking-[0.18em] uppercase text-fg-400">
            {r.k}
          </span>
          <span className={cn('font-sans text-[0.92rem] leading-[1.5] text-fg-200', r.cls)}>
            {r.v}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── QBR goal scorecard ─────────────────────────────────────────────────────────

function GoalScorecard({ milestones }: { milestones: MeetingContextMilestone[] }) {
  if (milestones.length === 0) {
    return (
      <div className="border border-dashed border-border px-4 py-5 text-center">
        <p className="font-mono text-[9.5px] tracking-[0.2em] uppercase text-fg-400">
          No milestones tracked yet
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2.5">
      {milestones.map(ms => {
        const isDone = ms.status === 'completed' || ms.status === 'done';
        const isAt  = ms.status === 'at_risk' || ms.status === 'blocked';
        return (
          <div
            key={ms.id}
            className={cn(
              'grid gap-4 items-center px-[18px] py-4 border border-border bg-surface',
              isDone && 'border-l-[3px] border-l-signal-ok',
              isAt   && 'border-l-[3px] border-l-signal-bad',
            )}
            style={{ gridTemplateColumns: '1fr 140px 56px' }}
          >
            <div>
              <p className="font-sans text-[1.05rem] text-fg-100 mb-1">{ms.title}</p>
              {ms.goal?.text && (
                <p className="font-sans text-[0.8rem] text-fg-400 leading-[1.45]">
                  Goal: {ms.goal.text}
                </p>
              )}
            </div>
            <div>
              <div className="h-1.5 bg-surface-deep mb-1.5">
                <div
                  className={cn('h-full', isDone ? 'bg-signal-ok' : isAt ? 'bg-signal-bad' : 'bg-accent')}
                  style={{ width: isDone ? '100%' : isAt ? '30%' : '65%' }}
                />
              </div>
              <span className="font-mono text-[9px] tracking-[0.12em] uppercase text-fg-400">
                {ms.status?.replace(/_/g, ' ')}
              </span>
            </div>
            <span className={cn(
              'font-mono text-[1.2rem] text-right',
              isDone ? 'text-signal-ok' : isAt ? 'text-signal-bad' : 'text-accent',
            )}>
              {isDone ? '100%' : isAt ? '30%' : '65%'}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── prep footer ───────────────────────────────────────────────────────────────

function PrepFooter({ readyLabel }: { readyLabel: string }) {
  return (
    <div className="col-span-full flex items-center gap-3.5 pt-6 mt-1 border-t border-border">
      <div className="flex items-center gap-2 font-mono text-[9.5px] tracking-[0.18em] uppercase text-fg-400">
        <span className="w-[7px] h-[7px] rounded-full bg-signal-ok" />
        {readyLabel}
      </div>
      <span className="flex-1" />
      <button className="font-mono text-[10px] tracking-[0.2em] uppercase text-fg-300 border border-border px-4 py-2 hover:border-accent hover:text-accent transition-colors">
        EXPORT
      </button>
      <button className="font-mono text-[10px] tracking-[0.2em] uppercase bg-accent text-page px-4 py-2 hover:bg-accent-hover transition-colors font-bold">
        START LIVE MODE →
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// QBR PREP
// ─────────────────────────────────────────────────────────────────────────────

export function QBRPrep({ meeting }: { meeting: Meeting }) {
  const brief   = meeting.brief;
  const ctx     = meeting.context;
  const points  = brief?.talking_points ?? PLACEHOLDER_POINTS;
  const milestones = ctx?.milestones ?? [];
  const stakeholders = ctx?.stakeholders ?? [];

  return (
    <div className="grid gap-6 items-start" style={{ gridTemplateColumns: '1fr 340px' }}>
      {/* Brief */}
      <div className="min-w-0">
        <BriefGenHeader
          label={`QBR BRIEF · DRAFTED FROM ${milestones.length} MILESTONES, SIGNALS + THREADS`}
          ago={brief?.generated_at ? 'READY' : undefined}
        />

        {brief?.progress_narrative ? (
          <>
            <p className="font-sans font-semibold text-[1.5rem] leading-[1.3] text-fg-100 mb-3 text-wrap-pretty">
              {brief.progress_narrative}
            </p>
            {brief.friction && (
              <p className="font-sans text-[0.95rem] leading-[1.6] text-fg-300 mb-6">{brief.friction}</p>
            )}
          </>
        ) : (
          <p className="font-sans font-semibold text-[1.5rem] leading-[1.3] text-fg-100 mb-6">
            Sidekick is preparing your QBR brief — goal scorecard, run of show, and the room.
          </p>
        )}

        <div className="mb-7">
          <SectionHdr label="GOAL SCORECARD" note="CURRENT STATUS" />
          <GoalScorecard milestones={milestones} />
        </div>

        <div className="mb-7">
          <SectionHdr label="RUN OF SHOW" note="SIDEKICK-SEQUENCED" />
          <div>
            {points.map((pt, i) => (
              <TalkingPoint key={i} point={pt} idx={i} />
            ))}
          </div>
        </div>

        <div className="mb-7">
          <SectionHdr label="THE ROOM" note={`${meeting.attendees_theirs.length || stakeholders.length} EXTERNAL`} />
          <TheRoom stakeholders={stakeholders} attendeesTheirs={meeting.attendees_theirs} />
        </div>

        <PrepFooter readyLabel={brief ? 'BRIEF READY' : 'BRIEF DRAFTING'} />
      </div>

      {/* Sidecar */}
      <HuddleSidecar
        meeting={meeting}
        skSuggestion={
          brief?.expansion_signals
            ? brief.expansion_signals
            : undefined
        }
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// KICKOFF PREP
// ─────────────────────────────────────────────────────────────────────────────

export function KickoffPrep({ meeting }: { meeting: Meeting }) {
  const brief      = meeting.brief;
  const ctx        = meeting.context;
  const points     = brief?.talking_points ?? PLACEHOLDER_POINTS;
  const milestones = ctx?.milestones ?? [];
  const stakeholders = ctx?.stakeholders ?? [];

  // North Star — use primary goal or value_delivered
  const northStar = brief?.value_delivered
    ?? ctx?.milestones.find(ms => ms.goal?.is_primary)?.goal?.text
    ?? null;

  return (
    <div className="grid gap-6 items-start" style={{ gridTemplateColumns: '1fr 340px' }}>
      {/* Brief */}
      <div className="min-w-0">
        <BriefGenHeader
          label="KICKOFF BRIEF · DRAFTED FROM SALES HANDOFF + DISCOVERY NOTES"
          ago={brief?.generated_at ? 'READY' : undefined}
        />

        {/* North Star banner */}
        <div className="border border-accent/60 bg-accent/6 px-6 py-5 mb-7 relative">
          <div className="font-mono text-[9.5px] font-bold tracking-[0.28em] uppercase text-accent mb-3">
            ★ THE NORTH STAR · SET TODAY, REFERENCED EVERY MEETING AFTER
          </div>
          <p className="font-sans font-semibold text-[1.65rem] leading-[1.25] text-fg-100 text-wrap-pretty">
            {northStar ?? 'Success definition will be set in this meeting.'}
          </p>
          {ctx?.milestones[0]?.target_date && (
            <div className="flex gap-6 mt-4">
              <div className="font-mono text-[9px] tracking-[0.16em] uppercase text-fg-400">
                TARGET
                <span className="font-sans text-[1rem] text-accent block mt-1">
                  {new Date(ctx.milestones[0].target_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="mb-7">
          <SectionHdr label="STAKEHOLDER MAP" note="WHO CARES ABOUT WHAT" />
          <TheRoom stakeholders={stakeholders} attendeesTheirs={meeting.attendees_theirs} />
        </div>

        {milestones.length > 0 && (
          <div className="mb-7">
            <SectionHdr label="THE 30 / 60 / 90" note="WHAT WE COMMIT TO TODAY" />
            <Plan9090 milestones={milestones} />
          </div>
        )}

        <div className="mb-7">
          <SectionHdr label="OPEN THE MEETING WITH" />
          <div>
            {points.map((pt, i) => (
              <TalkingPoint key={i} point={pt} idx={i} />
            ))}
          </div>
        </div>

        <PrepFooter readyLabel={brief ? 'NORTH STAR SET · 90-DAY PLAN DRAFTED' : 'BRIEF DRAFTING'} />
      </div>

      {/* Sidecar */}
      <HuddleSidecar
        meeting={meeting}
        skSuggestion={brief?.risk_to_renewal ?? undefined}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CHECK-IN PREP (lean fallback)
// ─────────────────────────────────────────────────────────────────────────────

export function CheckinPrep({ meeting }: { meeting: Meeting }) {
  const brief       = meeting.brief;
  const ctx         = meeting.context;
  const points      = brief?.talking_points ?? PLACEHOLDER_POINTS;
  const signals     = ctx?.signals ?? [];
  const commitments = ctx?.commitments ?? [];

  return (
    <div className="grid gap-6 items-start" style={{ gridTemplateColumns: '1fr 340px' }}>
      {/* Brief */}
      <div className="min-w-0">
        <BriefGenHeader
          label="CHECK-IN BRIEF · LEAN SHAPE"
          ago={brief?.generated_at ? 'READY' : undefined}
        />

        {brief?.progress_narrative ? (
          <p className="font-sans font-semibold text-[1.5rem] leading-[1.3] text-fg-100 mb-6 text-wrap-pretty">
            {brief.progress_narrative}
          </p>
        ) : (
          <p className="font-sans font-semibold text-[1.5rem] leading-[1.3] text-fg-100 mb-6">
            A lean check-in. Close open loops, read the room, plant one seed.
          </p>
        )}

        <div className="mb-7">
          <SectionHdr label="SINCE WE LAST TALKED" />
          <CheckinDigest signals={signals} commitments={commitments} />
        </div>

        <div className="mb-7">
          <SectionHdr label="THE ONE THING TO ADVANCE" />
          <div>
            {points.map((pt, i) => (
              <TalkingPoint key={i} point={pt} idx={i} />
            ))}
          </div>
        </div>

        {signals.length > 0 && (
          <div className="mb-7">
            <SectionHdr label="SENTIMENT PULSE" />
            <CheckinDigest
              signals={signals}
              commitments={[]}
            />
          </div>
        )}

        <PrepFooter readyLabel={brief ? 'LEAN BRIEF READY' : 'BRIEF DRAFTING'} />
      </div>

      {/* Sidecar */}
      <HuddleSidecar
        meeting={meeting}
        skSuggestion={brief?.expansion_signals ?? undefined}
      />
    </div>
  );
}
