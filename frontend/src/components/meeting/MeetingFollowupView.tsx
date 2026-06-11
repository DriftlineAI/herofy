// Follow-up wrap-up view.
// Intake banner → AI summary → commitments → proposed goals → needs → sentiment → recap email.

import React from 'react';
import { cn } from '@/lib/utils';
import type { Meeting, MeetingContextCommitment, MeetingContextMilestone } from '@/lib/api';

// ── section header ────────────────────────────────────────────────────────────

function DetGroupHdr({
  label,
  ct,
  accept,
}: {
  label: string;
  ct?: string | number;
  accept?: string;
}) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <span className="w-7 h-px bg-accent shrink-0" />
      <span className="font-mono text-[10px] font-bold tracking-[0.26em] uppercase text-fg-200">
        {label}
      </span>
      {ct && (
        <span className="font-mono text-[9px] tracking-[0.14em] text-accent border border-accent/60 px-1.5 py-[2px]">
          {ct}
        </span>
      )}
      <span className="flex-1 h-px bg-rule" />
      {accept && (
        <button className="font-mono text-[9px] tracking-[0.16em] uppercase text-fg-400 hover:text-accent transition-colors">
          {accept}
        </button>
      )}
    </div>
  );
}

// ── intake banner ─────────────────────────────────────────────────────────────

function IntakeBanner({ meeting }: { meeting: Meeting }) {
  const hasTranscript = false; // would be real data
  const hasLiveNotes  = true;  // we always have live notes capability
  const briefReady    = !!meeting.brief;

  return (
    <div className="border border-border bg-surface px-6 py-5 mb-6 grid gap-5 items-center"
      style={{ gridTemplateColumns: '1fr auto' }}>
      <div>
        <div className="flex items-center gap-2 font-mono text-[9px] font-bold tracking-[0.24em] uppercase text-signal-ok mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-signal-ok" />
          WRAP-UP READY
        </div>
        <h3 className="font-sans font-semibold text-[1.3rem] text-fg-100 mb-1.5">
          {briefReady
            ? 'Sidekick has read your notes and the meeting brief.'
            : 'Drop a transcript to unlock the full wrap-up.'}
        </h3>
        <p className="font-sans text-[0.85rem] text-fg-300">
          {briefReady
            ? 'Review detected commitments, proposed goals, and the recap draft below — approving updates the account plan.'
            : 'Manual wrap-up: document commitments and action items below.'}
        </p>
      </div>
      <div className="flex gap-2">
        <span className={cn(
          'font-mono text-[8.5px] font-bold tracking-[0.16em] uppercase border px-3 py-2 flex items-center gap-2',
          hasLiveNotes ? 'border-signal-ok text-signal-ok' : 'border-border text-fg-400',
        )}>
          {hasLiveNotes && (
            <span className="w-3 h-3 rounded-full bg-signal-ok text-page grid place-items-center text-[7px]">✓</span>
          )}
          LIVE NOTES
        </span>
        <span className={cn(
          'font-mono text-[8.5px] font-bold tracking-[0.16em] uppercase border px-3 py-2 flex items-center gap-2',
          hasTranscript ? 'border-signal-ok text-signal-ok' : 'border-border text-fg-400',
        )}>
          + UPLOAD TRANSCRIPT
        </span>
      </div>
    </div>
  );
}

// ── AI summary ────────────────────────────────────────────────────────────────

function WrapSummary({ narrative }: { narrative: string }) {
  return (
    <div className="border border-accent/60 bg-accent/5 border-l-[3px] border-l-accent px-6 py-5 mb-7">
      <div className="flex items-center gap-2.5 font-mono text-[9px] font-bold tracking-[0.22em] uppercase text-accent mb-3">
        <span className="w-[18px] h-[18px] rounded-full bg-accent text-page grid place-items-center text-[9px]">SK</span>
        WRAP-UP READ
        <span className="text-fg-400 font-normal ml-auto">GENERATED</span>
      </div>
      <p className="font-sans font-semibold text-[1.4rem] leading-[1.35] text-fg-100 text-wrap-pretty">
        {narrative}
      </p>
    </div>
  );
}

// ── commitment card ───────────────────────────────────────────────────────────

interface CommitCardProps {
  commitment: MeetingContextCommitment;
  side: 'ours' | 'theirs';
}

function CommitCard({ commitment, side }: CommitCardProps) {
  const isOurs = side === 'ours' || commitment.side === 'us' || commitment.side === 'ours';
  const initials = commitment.stake_holder?.name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() ?? 'US';

  return (
    <div
      className={cn(
        'grid gap-4 items-center px-4 py-4 border border-border bg-surface mb-2',
        isOurs ? 'border-l-[3px] border-l-accent' : 'border-l-[3px] border-l-signal-ok',
      )}
      style={{ gridTemplateColumns: '56px 1fr auto' }}
    >
      <div className={cn(
        'font-mono text-[8.5px] font-bold tracking-[0.14em] uppercase text-center',
        isOurs ? 'text-accent' : 'text-signal-ok',
      )}>
        <span className={cn(
          'w-8 h-8 rounded-full grid place-items-center font-bold text-[10px] mx-auto mb-1.5',
          isOurs ? 'bg-accent text-page' : 'bg-signal-ok text-page',
        )}>
          {initials}
        </span>
        {isOurs ? 'OURS' : 'THEIRS'}
      </div>
      <div>
        <p className="font-sans text-[0.95rem] leading-[1.45] text-fg-100 mb-1">{commitment.text}</p>
        {commitment.stake && (
          <p className="font-sans italic text-[0.82rem] text-fg-400">"{commitment.stake}"</p>
        )}
        <div className="flex gap-3.5 mt-2 font-mono text-[8.5px] tracking-[0.14em] uppercase text-fg-400">
          {commitment.stake_holder?.name && (
            <span className="text-fg-300">OWNER · {commitment.stake_holder.name}</span>
          )}
          {commitment.due_label && (
            <span className="text-signal-warn">DUE · {commitment.due_label}</span>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <button className="font-mono text-[8px] font-bold tracking-[0.16em] uppercase px-2.5 py-1.5 bg-accent border-accent text-page text-center whitespace-nowrap">
          {isOurs ? 'ADD TO TODAY' : 'TRACK'}
        </button>
        <button className="font-mono text-[8px] font-bold tracking-[0.16em] uppercase px-2.5 py-1.5 border border-border text-fg-300 text-center whitespace-nowrap">
          EDIT
        </button>
      </div>
    </div>
  );
}

// ── placeholder commitment ────────────────────────────────────────────────────

function PlaceholderCommit() {
  return (
    <div className="border border-dashed border-border px-4 py-6 text-center mb-2">
      <p className="font-mono text-[9.5px] tracking-[0.2em] uppercase text-fg-400">
        Drop a transcript to auto-detect commitments
      </p>
    </div>
  );
}

// ── proposed goal card ────────────────────────────────────────────────────────

function GoalPropCard({ milestone }: { milestone: MeetingContextMilestone }) {
  return (
    <div className="px-5 py-4 border border-border bg-surface mb-2">
      <div className="flex items-center gap-3 mb-2.5">
        <span className="font-mono text-[8px] font-bold tracking-[0.18em] uppercase text-accent border border-accent/60 px-1.5 py-[3px]">
          GOAL
        </span>
        <span className="font-mono text-[8.5px] tracking-[0.16em] uppercase text-fg-400">
          VECTOR · ONBOARDING
        </span>
      </div>
      <h4 className="font-sans font-semibold text-[1.2rem] text-fg-100 mb-1.5 leading-tight">
        {milestone.title}
      </h4>
      {milestone.goal_rationale && (
        <p className="font-sans text-[0.86rem] leading-[1.5] text-fg-300 mb-3">
          {milestone.goal_rationale}
        </p>
      )}
      <div className="flex items-center gap-2.5">
        <span className="font-mono text-[8.5px] tracking-[0.14em] uppercase text-fg-400 mr-auto">
          SOURCE · ACCOUNT PLAN
        </span>
        <button className="font-mono text-[8.5px] font-bold tracking-[0.16em] uppercase px-3 py-1.5 border border-border text-fg-300 hover:border-accent hover:text-accent transition-colors">
          EDIT
        </button>
        <button className="font-mono text-[8.5px] font-bold tracking-[0.16em] uppercase px-3 py-1.5 bg-accent text-page">
          ADD TO ACCOUNT PLAN
        </button>
      </div>
    </div>
  );
}

// ── sentiment delta ───────────────────────────────────────────────────────────

function SentimentDelta() {
  return (
    <div className="border border-border bg-surface px-5 py-5 mb-2">
      <div className="grid gap-5 items-center" style={{ gridTemplateColumns: '110px 1fr 110px' }}>
        <div className="text-center">
          <div className="font-mono text-[8.5px] tracking-[0.18em] uppercase text-fg-400 mb-1.5">BEFORE</div>
          <div className="font-sans italic text-[1.5rem] text-signal-warn">Guarded</div>
        </div>
        <div className="text-center">
          <div className="h-1.5 bg-surface-deep relative mb-2">
            <div className="absolute inset-y-0 left-0 bg-signal-warn/40" style={{ width: '46%' }} />
            <div className="absolute inset-y-0 left-0 bg-signal-ok" style={{ width: '72%' }} />
          </div>
          <div className="font-mono text-[9px] tracking-[0.16em] uppercase text-signal-ok">
            ↑ IMPROVING
          </div>
        </div>
        <div className="text-center">
          <div className="font-mono text-[8.5px] tracking-[0.18em] uppercase text-fg-400 mb-1.5">AFTER</div>
          <div className="font-sans italic text-[1.5rem] text-signal-ok">Warm</div>
        </div>
      </div>
      <p className="font-sans text-[0.84rem] leading-[1.55] text-fg-300 mt-4 pt-3.5 border-t border-rule">
        Sentiment assessment based on tone and language patterns in the meeting notes.
        Upload a transcript for a more detailed sentiment shift analysis.
      </p>
    </div>
  );
}

// ── recap email draft ─────────────────────────────────────────────────────────

function RecapEmailDraft({ meeting }: { meeting: Meeting }) {
  const email = meeting.brief?.followup_email;

  return (
    <div className="border border-border bg-surface mb-2">
      <div className="px-4 py-3 border-b border-rule flex items-center gap-3 font-mono text-[9px] font-bold tracking-[0.2em] uppercase text-accent">
        <span>DRAFT</span>
        {email?.to && (
          <span className="text-fg-400 font-normal">TO · {email.to.join(', ')}</span>
        )}
        <button className="ml-auto text-fg-400 font-normal hover:text-accent transition-colors">
          EDIT ✎
        </button>
      </div>
      <div className="px-6 py-5">
        {email ? (
          <>
            <p className="font-sans font-semibold text-[1rem] text-fg-100 mb-3.5 pb-3.5 border-b border-rule">
              {email.subject}
            </p>
            <div
              className="font-sans text-[0.9rem] leading-[1.65] text-fg-200"
              dangerouslySetInnerHTML={{ __html: email.body }}
            />
          </>
        ) : (
          <div>
            <p className="font-sans font-semibold text-[1rem] text-fg-100 mb-3.5 pb-3.5 border-b border-rule">
              {meeting.title} — recap and next steps
            </p>
            <p className="font-sans text-[0.9rem] leading-[1.65] text-fg-200 mb-3">
              Hi — thanks for the time today. Here's a quick recap of what we covered and the
              agreed next steps.
            </p>
            <p className="font-sans text-[0.9rem] leading-[1.65] text-fg-400 italic">
              Upload a transcript to generate a detailed recap with commitments and action items.
            </p>
          </div>
        )}
      </div>
      <div className="flex items-center gap-3 px-6 py-3.5 border-t border-rule">
        <span className="font-mono text-[9px] tracking-[0.18em] uppercase text-fg-400">
          SIDEKICK DRAFT · YOUR VOICE PROFILE
        </span>
        <span className="flex-1" />
        <button className="font-mono text-[10px] tracking-[0.2em] uppercase border border-border text-fg-300 px-4 py-2 hover:border-accent hover:text-accent transition-colors">
          EDIT FULL DRAFT
        </button>
        <button className="font-mono text-[10px] tracking-[0.2em] uppercase bg-accent text-page px-4 py-2 hover:bg-accent-hover transition-colors font-bold">
          SEND RECAP →
        </button>
      </div>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

interface MeetingFollowupViewProps {
  meeting: Meeting;
}

export function MeetingFollowupView({ meeting }: MeetingFollowupViewProps) {
  const brief       = meeting.brief;
  const ctx         = meeting.context;
  const commitments = ctx?.commitments ?? [];
  const milestones  = ctx?.milestones ?? [];

  const ourCommits    = commitments.filter(c => c.side === 'us' || c.side === 'ours');
  const theirCommits  = commitments.filter(c => c.side === 'them' || c.side === 'theirs' || c.side === 'customer');
  const allCommits    = commitments.length > 0 ? commitments : [];

  return (
    <div className="max-w-[980px]">
      <IntakeBanner meeting={meeting} />

      {brief?.progress_narrative && (
        <WrapSummary narrative={brief.progress_narrative} />
      )}

      {/* Commitments */}
      <div className="mb-8">
        <DetGroupHdr
          label="COMMITMENTS"
          ct={allCommits.length || undefined}
          accept={allCommits.length > 1 ? 'ACCEPT ALL →' : undefined}
        />
        {allCommits.length > 0 ? (
          allCommits.map(c => (
            <CommitCard
              key={c.id}
              commitment={c}
              side={
                c.side === 'us' || c.side === 'ours'
                  ? 'ours'
                  : 'theirs'
              }
            />
          ))
        ) : (
          <PlaceholderCommit />
        )}
      </div>

      {/* Proposed goals */}
      {milestones.length > 0 && (
        <div className="mb-8">
          <DetGroupHdr
            label="ACCOUNT PLAN MILESTONES"
            ct={milestones.length}
            accept="REVIEW IN PLAN →"
          />
          {milestones.slice(0, 3).map(ms => (
            <GoalPropCard key={ms.id} milestone={ms} />
          ))}
        </div>
      )}

      {/* Sentiment */}
      <div className="mb-8">
        <DetGroupHdr label="SENTIMENT ENRICHMENT" />
        <SentimentDelta />
      </div>

      {/* Recap email */}
      <div className="mb-8">
        <DetGroupHdr label="RECAP EMAIL · DRAFTED" />
        <RecapEmailDraft meeting={meeting} />
      </div>
    </div>
  );
}
