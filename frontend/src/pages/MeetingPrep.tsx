import React, { useState } from 'react';
import { useParams, NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { Pulse } from '@/components/ui/huds';
import { useMeeting } from '@/lib/dataconnect-hooks';
import { QBRPrep, KickoffPrep, CheckinPrep } from '@/components/meeting/MeetingShapes';
import { MeetingLiveView } from '@/components/meeting/MeetingLiveView';
import { MeetingFollowupView } from '@/components/meeting/MeetingFollowupView';
import type { Meeting, MeetingType } from '@/lib/api';

// ── shape detection ───────────────────────────────────────────────────────────

function detectShape(type: MeetingType): 'qbr' | 'kickoff' | 'checkin' {
  if (type === 'qbr' || type === 'renewal') return 'qbr';
  if (type === 'kickoff' || type === 'onboarding') return 'kickoff';
  return 'checkin';
}

const SHAPE_TYPE_CFG = {
  qbr:     { label: 'QBR',      cls: 'text-accent border-accent bg-accent/7' },
  kickoff: { label: 'KICKOFF',  cls: 'text-signal-ok border-signal-ok/40' },
  checkin: { label: 'CHECK-IN', cls: 'text-fg-300 border-border' },
};

// ── format helpers ────────────────────────────────────────────────────────────

function fmtScheduled(dateStr: string, status: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = d.getTime() - now.getTime();

  if (status === 'completed') {
    return `COMPLETED · ${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} · ${d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`;
  }
  if (Math.abs(diff) < 5 * 60 * 1000) return 'LIVE NOW';
  if (diff > 0 && diff < 60 * 60 * 1000) {
    const mins = Math.round(diff / 60000);
    return `TODAY · STARTS IN ${mins}M`;
  }
  const isToday = d.toDateString() === now.toDateString();
  const when = isToday ? 'TODAY' : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }).toUpperCase();
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  return `${when} · ${time} · ${/* duration */0}MIN`;
}

function fmtDuration(meeting: Meeting): string {
  const d = new Date(meeting.scheduled_at);
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  return `${time} · ${meeting.duration_minutes}MIN`;
}

// ── workspace header ──────────────────────────────────────────────────────────

interface WSHeaderProps {
  meeting: Meeting;
  shape: 'qbr' | 'kickoff' | 'checkin';
  isLive: boolean;
}

function WSHeader({ meeting, shape, isLive }: WSHeaderProps) {
  const shapeCfg = SHAPE_TYPE_CFG[shape];
  const arr = meeting.context?.arr_cents
    ? `$${(meeting.context.arr_cents / 100).toLocaleString('en-US', { notation: 'compact', maximumFractionDigits: 0 })}`
    : null;

  // Build facts row
  const facts = [
    `ACCOUNT <a class="text-accent">${meeting.customer_name}</a>`,
    arr ? `ARR <span class="text-accent font-bold">${arr}</span>` : null,
    meeting.duration_minutes ? `DURATION <span>${meeting.duration_minutes}M</span>` : null,
  ].filter(Boolean) as string[];

  return (
    <div className="mb-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2.5 mb-4 font-mono text-[10px] tracking-[0.18em] uppercase text-fg-400">
        <NavLink to="/app/meetings" className="hover:text-accent transition-colors">MEETINGS</NavLink>
        <span>›</span>
        <span className="text-fg-200">{meeting.customer_name}</span>
      </div>

      {/* Meta row */}
      <div className="flex items-center gap-3.5 flex-wrap mb-3.5 font-mono text-[10px] tracking-[0.2em] uppercase text-fg-400">
        {isLive && <Pulse active />}
        <span className="text-accent font-bold">
          {meeting.id.slice(0, 8).toUpperCase()}
        </span>
        <span>·</span>
        <span>{fmtDuration(meeting)}</span>
        <span className={cn(
          'font-bold border px-2 py-[3px]',
          shapeCfg.cls,
        )}>
          {shapeCfg.label}
        </span>
      </div>

      {/* Title */}
      <h1 className="font-display text-[3rem] leading-[1.0] tracking-[-0.02em] text-fg-100 mb-3.5">
        {meeting.customer_name}{' '}
        <span className="font-sans italic text-accent font-medium text-[2rem]">
          · {meeting.title}
        </span>
      </h1>

      {/* Facts strip */}
      <div className="flex items-center gap-4 flex-wrap">
        {facts.map((f, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span className="text-fg-400/40">/</span>}
            <span
              className="font-mono text-[10px] tracking-[0.14em] uppercase text-fg-400"
              dangerouslySetInnerHTML={{ __html: f }}
            />
          </React.Fragment>
        ))}
        {meeting.need && (
          <>
            <span className="text-fg-400/40">/</span>
            <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-fg-400">
              RE{' '}
              <NavLink
                to={`/app/customers/${meeting.customer_id}`}
                className="text-fg-200 hover:text-accent transition-colors"
              >
                {meeting.need.headline.slice(0, 40)}…
              </NavLink>
            </span>
          </>
        )}
      </div>
    </div>
  );
}

// ── tab bar ───────────────────────────────────────────────────────────────────

type Tab = 'prep' | 'live' | 'followup';

interface TabBarProps {
  active: Tab;
  onChange: (t: Tab) => void;
  prepDone: boolean;
  followupReady: boolean;
}

function TabBar({ active, onChange, prepDone, followupReady }: TabBarProps) {
  const tabs: { id: Tab; label: string; done?: boolean }[] = [
    { id: 'prep',     label: 'Prep', done: prepDone },
    { id: 'live',     label: 'Live' },
    { id: 'followup', label: 'Follow-up', done: followupReady },
  ];

  return (
    <div className="flex gap-[30px] border-b border-border mb-7">
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            'pb-3.5 font-mono text-[11px] tracking-[0.22em] uppercase relative flex items-center gap-2 transition-colors',
            active === tab.id ? 'text-fg-100' : 'text-fg-400 hover:text-fg-200',
          )}
        >
          {tab.label}
          {tab.done && (
            <span className="text-signal-ok text-[10px]">✓</span>
          )}
          {active === tab.id && (
            <span className="absolute left-0 right-0 bottom-[-1px] h-[2px] bg-accent" />
          )}
        </button>
      ))}
    </div>
  );
}

// ── loading skeleton ──────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-8">
      <div className="flex items-center gap-4">
        <div className="h-3 w-24 bg-border" />
        <div className="h-3 w-32 bg-border" />
      </div>
      <div className="h-12 w-64 bg-border" />
      <div className="h-8 w-full bg-surface-2" />
      <div className="grid gap-6" style={{ gridTemplateColumns: '1fr 340px' }}>
        <div className="h-64 bg-surface-2" />
        <div className="h-64 bg-surface-2" />
      </div>
    </div>
  );
}

// ── workspace ─────────────────────────────────────────────────────────────────

function MeetingWorkspace({ meeting }: { meeting: Meeting }) {
  const [activeTab, setActiveTab] = useState<Tab>('prep');
  const [liveNotes, setLiveNotes] = useState('');

  const shape  = detectShape(meeting.type);
  const isLive = meeting.status !== 'completed' && (() => {
    const diff = Math.abs(new Date(meeting.scheduled_at).getTime() - Date.now());
    return diff < 5 * 60 * 1000;
  })();

  const hasBrief     = !!meeting.brief;
  const isCompleted  = meeting.status === 'completed';

  return (
    <div>
      <WSHeader meeting={meeting} shape={shape} isLive={isLive} />

      <TabBar
        active={activeTab}
        onChange={setActiveTab}
        prepDone={hasBrief}
        followupReady={isCompleted}
      />

      {activeTab === 'prep' && (
        <>
          {shape === 'qbr'     && <QBRPrep     meeting={meeting} />}
          {shape === 'kickoff' && <KickoffPrep  meeting={meeting} />}
          {shape === 'checkin' && <CheckinPrep  meeting={meeting} />}
        </>
      )}

      {activeTab === 'live' && (
        <MeetingLiveView
          meeting={meeting}
          liveNotes={liveNotes}
          onNotesChange={setLiveNotes}
        />
      )}

      {activeTab === 'followup' && (
        <MeetingFollowupView meeting={meeting} />
      )}
    </div>
  );
}

// ── page entry ────────────────────────────────────────────────────────────────

export default function MeetingPrep() {
  const { meetingId } = useParams<{ meetingId?: string }>();
  const { data, isLoading, error, refetch } = useMeeting(meetingId || '');

  if (!meetingId) {
    return (
      <div className="py-24 text-center">
        <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-fg-400">
          No meeting selected.
        </p>
        <NavLink
          to="/app/meetings"
          className="inline-block mt-4 font-mono text-xs uppercase tracking-widest text-accent hover:text-accent-hover"
        >
          ← Back to Meetings
        </NavLink>
      </div>
    );
  }

  if (error) {
    return (
      <div className="hud-pane p-8 border-l-[3px] border-l-signal-bad">
        <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-signal-bad font-bold mb-4">
          Meeting Not Found
        </div>
        <p className="text-fg-200 mb-4">{(error as Error).message}</p>
        <div className="flex gap-4">
          <button
            onClick={() => refetch()}
            className="font-mono text-xs uppercase tracking-widest border border-signal-bad text-signal-bad px-4 py-2 hover:bg-signal-bad hover:text-page transition-colors"
          >
            Retry
          </button>
          <NavLink
            to="/app/meetings"
            className="font-mono text-xs uppercase tracking-widest border border-border text-fg-400 px-4 py-2 hover:border-fg-100 hover:text-fg-100 transition-colors"
          >
            Back to Meetings
          </NavLink>
        </div>
      </div>
    );
  }

  if (isLoading) return <LoadingSkeleton />;

  if (!data?.meeting) {
    return (
      <div className="py-12 text-center">
        <p className="text-fg-400 font-mono text-xs uppercase tracking-widest mb-4">
          Meeting not found.
        </p>
        <NavLink
          to="/app/meetings"
          className="font-mono text-xs uppercase tracking-widest text-accent hover:text-accent-hover"
        >
          ← Back to Meetings
        </NavLink>
      </div>
    );
  }

  return <MeetingWorkspace meeting={data.meeting as Meeting} />;
}
