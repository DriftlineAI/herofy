// Static-placeholder huddle sidecar.
// Internal team prep-notes panel — warm-paper register.
// No live data model yet; renders placeholder notes + compose box.

import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import type { Meeting } from '@/lib/api';

interface HuddleNote {
  initials: string;
  who: string;
  role: string;
  when: string;
  body: string;
  isSidekick?: boolean;
  action?: string;
}

const PLACEHOLDER_NOTES: HuddleNote[] = [
  {
    initials: 'SK',
    who: 'Sidekick',
    role: 'AI',
    when: 'JUST NOW',
    isSidekick: true,
    body: 'Brief assembled from recent signals and conversation history. Review the talking points and sharpen anything before you go live.',
    action: 'REVIEW BRIEF',
  },
  {
    initials: 'ME',
    who: 'You',
    role: 'OWNER',
    when: 'T-1H',
    body: 'Use this space to prep with your team — loop anyone in, add context Sidekick missed, or ask Sidekick to dig deeper.',
  },
];

// ── lock icon (pure CSS) ──────────────────────────────────────────────────────

function LockIcon() {
  return (
    <span className="inline-block relative w-[10px] h-[8px] border border-current rounded-t-[2px] shrink-0"
      style={{ borderBottom: 'none', top: '-1px' }}>
      <span className="absolute bg-current"
        style={{ top: 7, left: -3, right: -3, height: 7, display: 'block' }} />
    </span>
  );
}

// ── single note ───────────────────────────────────────────────────────────────

function HuddleNoteRow({ note }: { note: HuddleNote }) {
  return (
    <div className="grid gap-[11px] py-3 border-b border-dashed last:border-b-0 last:pb-1"
      style={{ gridTemplateColumns: '26px 1fr' }}>
      <span className={cn(
        'w-[25px] h-[25px] rounded-full grid place-items-center font-mono font-bold text-[9px] shrink-0',
        note.isSidekick ? 'bg-[#997839] text-[#faf6ec]' : 'bg-[#d4cdb9] text-[#1d2230]',
      )}>
        {note.initials}
      </span>
      <div>
        <div className="flex items-baseline gap-2">
          <span className="font-sans italic text-[0.95rem] text-[#1d2230]">{note.who}</span>
          <span className="font-mono text-[8px] tracking-[0.18em] uppercase text-[#997839] font-bold">
            {note.role}
          </span>
          <span className="font-mono text-[8.5px] tracking-[0.14em] uppercase text-[#8a8676] ml-auto">
            {note.when}
          </span>
        </div>
        <p className="font-sans text-[0.85rem] leading-[1.5] text-[#2a2f3a] mt-1">
          {note.body}
        </p>
        {note.action && (
          <button className="mt-2 px-[11px] py-[5px] bg-[#997839] text-[#faf6ec] font-mono text-[8.5px] font-bold tracking-[0.2em] uppercase">
            {note.action}
          </button>
        )}
      </div>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

interface HuddleSidecarProps {
  meeting: Meeting;
  skSuggestion?: string;
}

export function HuddleSidecar({ meeting, skSuggestion }: HuddleSidecarProps) {
  const [activeTab, setActiveTab] = useState<'note' | 'sidekick'>('note');

  return (
    <div className="sticky top-5 flex flex-col gap-4">
      {/* Main huddle card — warm paper */}
      <div
        className="relative border"
        style={{
          background: '#faf6ec',
          borderColor: '#c9c5b5',
          color: '#1d2230',
        }}
      >
        {/* Brass left rail */}
        <div className="absolute top-0 left-0 bottom-0 w-[3px] bg-accent" />

        {/* Header */}
        <div
          className="flex items-center gap-2 px-4 py-3 font-mono text-[9px] font-bold tracking-[0.24em] uppercase border-b"
          style={{ borderColor: '#d8d3c4', color: '#6e6b5d' }}
        >
          <LockIcon />
          <span>PREP HUDDLE</span>
          <span style={{ color: '#1d2230' }}>· {PLACEHOLDER_NOTES.length} NOTES</span>
          <span className="ml-auto" style={{ color: '#8a8676' }}>INTERNAL · NOT SENT</span>
        </div>

        {/* Notes */}
        <div className="px-4 pt-1 pb-3">
          {PLACEHOLDER_NOTES.map((n, i) => (
            <HuddleNoteRow key={i} note={n} />
          ))}
        </div>

        {/* Compose */}
        <div className="px-4 pb-4">
          <div className="flex border-b mb-3" style={{ borderColor: '#d8d3c4' }}>
            {(['note', 'sidekick'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  'px-[11px] py-2 font-mono text-[8.5px] font-bold tracking-[0.16em] uppercase border-b-2 -mb-px',
                  activeTab === tab
                    ? tab === 'sidekick'
                      ? 'border-[#997839] text-[#997839]'
                      : 'border-[#997839] text-[#1d2230]'
                    : 'border-transparent text-[#8a8676]',
                )}
              >
                {tab === 'note' ? 'ADD NOTE' : '@ ASK SIDEKICK'}
              </button>
            ))}
          </div>
          <div className="font-sans text-[0.85rem] pb-3" style={{ color: '#8a8676' }}>
            {activeTab === 'note'
              ? 'Sharpen a talking point, loop a teammate…'
              : 'Ask Sidekick to dig into something specific…'}
          </div>
          <div className="flex items-center gap-2">
            <button
              className="font-mono text-[8.5px] font-bold tracking-[0.18em] uppercase px-[11px] py-[7px] border"
              style={{ borderColor: '#c9c5b5', color: '#6e6b5d', background: 'transparent' }}
            >
              @ LOOP
            </button>
            <button
              className="ml-auto font-mono text-[8.5px] font-bold tracking-[0.18em] uppercase px-[11px] py-[7px]"
              style={{ background: '#997839', color: '#faf6ec', border: 'none' }}
            >
              POST TO HUDDLE
            </button>
          </div>
        </div>
      </div>

      {/* Sidekick suggestion card (dark register) */}
      {skSuggestion && (
        <div className="border border-border border-l-[3px] border-l-accent bg-accent-bg p-4">
          <div className="font-mono text-[9px] font-bold tracking-[0.24em] uppercase text-accent mb-2 flex items-center gap-2">
            <span className="w-4 h-4 rounded-full bg-accent text-page grid place-items-center font-bold text-[8px]">SK</span>
            SUGGESTED ADD
          </div>
          <p className="font-sans text-[0.85rem] leading-[1.55] text-fg-200">{skSuggestion}</p>
          <div className="flex gap-2 mt-3">
            <button className="font-mono text-[8.5px] font-bold tracking-[0.18em] uppercase px-[10px] py-[6px] bg-accent border-accent text-page">
              ADD TO BRIEF
            </button>
            <button className="font-mono text-[8.5px] font-bold tracking-[0.18em] uppercase px-[10px] py-[6px] border border-border text-fg-300">
              DISMISS
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
