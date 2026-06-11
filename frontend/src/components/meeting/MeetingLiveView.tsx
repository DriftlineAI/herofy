// Live meeting view — talking-point checklist + note capture pad + quick capture.

import React, { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import type { Meeting, MeetingTalkingPoint } from '@/lib/api';

// ── live timer (display only) ─────────────────────────────────────────────────

function LiveTimer() {
  const [elapsed, setElapsed] = useState(0);
  const start = useRef(Date.now());

  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - start.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const s = String(elapsed % 60).padStart(2, '0');

  return (
    <div className="flex items-center gap-3 px-4 py-[14px] border border-border bg-surface-2 border-l-[3px] border-l-accent mb-4">
      <span className="w-[9px] h-[9px] rounded-full bg-signal-bad animate-pulse shrink-0" />
      <span className="font-mono text-[1.4rem] text-fg-100 tracking-[0.02em]">{m}:{s}</span>
      <span className="font-mono text-[9px] tracking-[0.2em] uppercase text-fg-400 ml-auto">RECORDING</span>
    </div>
  );
}

// ── talking-point checklist ───────────────────────────────────────────────────

const PLACEHOLDER_LIVE_POINTS: MeetingTalkingPoint[] = [
  'Brief loading — talking points will appear once the brief is ready.',
];

function LivePoint({
  point,
  done,
  onToggle,
}: {
  point: MeetingTalkingPoint;
  done: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className="grid gap-3 items-start py-[13px] border-t border-rule first:border-t-0 cursor-pointer group"
      style={{ gridTemplateColumns: '22px 1fr' }}
      onClick={onToggle}
    >
      <span className={cn(
        'w-4 h-4 border mt-0.5 relative shrink-0 transition-colors',
        done ? 'bg-signal-ok border-signal-ok' : 'border-border',
      )}>
        {done && (
          <span className="absolute inset-0 grid place-items-center text-page text-[11px] font-bold">✓</span>
        )}
      </span>
      <p className={cn(
        'font-sans text-[0.92rem] leading-[1.45] transition-colors self-center',
        done ? 'text-fg-400 line-through decoration-fg-400' : 'text-fg-100 group-hover:text-accent',
      )}>
        {point}
      </p>
    </div>
  );
}

// ── quick capture buttons ─────────────────────────────────────────────────────

function QuickCaptureBtn({
  color,
  label,
  onClick,
}: {
  color: 'brass' | 'warn' | 'risk';
  label: string;
  onClick: () => void;
}) {
  const sqCls = {
    brass: 'bg-accent',
    warn:  'bg-signal-warn',
    risk:  'bg-signal-bad',
  }[color];

  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2.5 px-[13px] py-[10px] border border-border bg-surface font-mono text-[9px] font-bold tracking-[0.16em] uppercase text-fg-300 hover:border-accent hover:text-accent transition-colors"
    >
      <span className={cn('w-2 h-2 shrink-0', sqCls)} />
      {label}
    </button>
  );
}

// ── note line renderer ────────────────────────────────────────────────────────

interface NoteLine {
  text: string;
  flag?: 'COMMITMENT' | 'NEED';
}

function NoteLineRow({ line }: { line: NoteLine }) {
  return (
    <div className="font-sans text-[1.25rem] leading-[1.4] text-fg-100 tracking-[-0.005em] pl-[22px] relative">
      <span className="absolute left-0 text-accent/60">—</span>
      {line.text}
      {line.flag && (
        <span className={cn(
          'inline-block ml-2.5 align-middle font-mono text-[8.5px] font-bold tracking-[0.18em] uppercase border px-[7px] py-[2px]',
          line.flag === 'COMMITMENT'
            ? 'text-accent border-accent'
            : 'text-signal-warn border-signal-warn/40',
        )}>
          {line.flag}
        </span>
      )}
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

interface MeetingLiveViewProps {
  meeting: Meeting;
  liveNotes: string;
  onNotesChange: (v: string) => void;
}

export function MeetingLiveView({ meeting, liveNotes, onNotesChange }: MeetingLiveViewProps) {
  const points = meeting.brief?.talking_points ?? PLACEHOLDER_LIVE_POINTS;
  const [done, setDone] = useState<Set<number>>(new Set());
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function toggleDone(idx: number) {
    setDone(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  }

  function appendFlag(flag: 'COMMITMENT' | 'NEED' | 'RISK') {
    const prefix = flag === 'COMMITMENT' ? '[COMMIT] ' : flag === 'NEED' ? '[NEED] ' : '[RISK] ';
    onNotesChange(liveNotes + (liveNotes ? '\n' : '') + prefix);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }

  const doneCount = done.size;

  return (
    <div className="grid gap-6 items-start" style={{ gridTemplateColumns: '320px 1fr' }}>
      {/* Left rail */}
      <div className="sticky top-5">
        <LiveTimer />

        <div className="font-mono text-[9.5px] font-bold tracking-[0.26em] uppercase text-fg-400 mb-3 flex items-center gap-2.5">
          RUN OF SHOW
          <span className="flex-1 h-px bg-rule" />
          <span className="text-[9px] text-fg-400">{doneCount} / {points.length}</span>
        </div>

        {points.map((pt, i) => (
          <LivePoint key={i} point={pt} done={done.has(i)} onToggle={() => toggleDone(i)} />
        ))}

        {/* Quick capture */}
        <div className="mt-4 pt-4 border-t border-border flex flex-col gap-2">
          <QuickCaptureBtn color="brass" label="FLAG A COMMITMENT" onClick={() => appendFlag('COMMITMENT')} />
          <QuickCaptureBtn color="warn"  label="FLAG A NEED"       onClick={() => appendFlag('NEED')} />
          <QuickCaptureBtn color="risk"  label="FLAG A RISK"       onClick={() => appendFlag('RISK')} />
        </div>
      </div>

      {/* Note capture */}
      <div className="min-w-0">
        <div className="font-mono text-[9.5px] font-bold tracking-[0.26em] uppercase text-fg-400 mb-3 flex items-center gap-2.5">
          LIVE NOTES
          <span className="flex-1 h-px bg-rule" />
          <span className="text-[9px] text-fg-400">AUTOSAVING</span>
        </div>
        <div className="border border-border bg-surface px-7 py-6 min-h-[540px]">
          {liveNotes ? (
            <div className="flex flex-col gap-4 mb-4">
              {liveNotes.split('\n').filter(Boolean).map((line, i) => {
                const flag = line.startsWith('[COMMIT]')
                  ? 'COMMITMENT' as const
                  : line.startsWith('[NEED]')
                  ? 'NEED' as const
                  : undefined;
                const text = line.replace(/^\[(COMMIT|NEED|RISK)\] ?/, '');
                return <NoteLineRow key={i} line={{ text, flag }} />;
              })}
            </div>
          ) : (
            <p className="font-sans italic text-[1.4rem] text-fg-400/50 mb-6">
              Type to capture raw notes…
            </p>
          )}
          <textarea
            ref={textareaRef}
            value={liveNotes}
            onChange={e => onNotesChange(e.target.value)}
            placeholder={liveNotes ? '' : 'Start typing…'}
            className="w-full bg-transparent border-0 font-sans text-[1.25rem] text-fg-100 placeholder:text-fg-400/40 focus:ring-0 resize-none outline-none leading-[1.4] tracking-[-0.005em]"
            style={{ minHeight: 240 }}
          />
        </div>
      </div>
    </div>
  );
}
