import React from 'react';
import { NavLink } from 'react-router-dom';
import { Pulse } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { useMeetings } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import { useAuth } from '@/lib/auth';
import type { Meeting, MeetingType } from '@/lib/api';
import { Calendar, Settings, Plus } from 'lucide-react';
import { Sidekick } from '@/components/ui/huds';

// ── type config ───────────────────────────────────────────────────────────────

const MEETING_TYPE_CFG: Record<MeetingType, { label: string; cls: string }> = {
  qbr:       { label: 'QBR',      cls: 'text-accent border-accent bg-accent/7' },
  renewal:   { label: 'RENEWAL',  cls: 'text-signal-warn border-signal-warn/40' },
  check_in:  { label: 'CHECK-IN', cls: 'text-fg-300 border-border' },
  onboarding:{ label: 'KICKOFF',  cls: 'text-signal-ok border-signal-ok/40' },
  kickoff:   { label: 'KICKOFF',  cls: 'text-signal-ok border-signal-ok/40' },
  support:   { label: 'SUPPORT',  cls: 'text-signal-warn border-signal-warn/40' },
  other:     { label: 'MEETING',  cls: 'text-fg-400 border-border' },
};

// ── helpers ───────────────────────────────────────────────────────────────────

function parseDateKey(dateStr: string) {
  const date = new Date(dateStr);
  const now  = new Date();
  const tmrw = new Date(now); tmrw.setDate(tmrw.getDate() + 1);
  const isToday    = date.toDateString() === now.toDateString();
  const isTomorrow = date.toDateString() === tmrw.toDateString();
  return { date, isToday, isTomorrow };
}

function dayLabel(dateStr: string) {
  const { date, isToday, isTomorrow } = parseDateKey(dateStr);
  if (isToday)    return 'TODAY';
  if (isTomorrow) return 'TOMORROW';
  return date.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' }).toUpperCase();
}

function groupByDate(meetings: Meeting[]) {
  const groups = new Map<string, Meeting[]>();
  for (const m of meetings) {
    const key = new Date(m.scheduled_at).toDateString();
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(m);
  }
  return groups;
}

function fmtTime(dateStr: string) {
  const d = new Date(dateStr);
  const h = d.getHours() % 12 || 12;
  const min = String(d.getMinutes()).padStart(2, '0');
  const ampm = d.getHours() < 12 ? 'AM' : 'PM';
  return { h: `${h}:${min}`, ampm };
}

// ── skeleton ──────────────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      {[0, 1].map(i => (
        <div key={i}>
          <div className="h-3 w-32 bg-border rounded mb-4" />
          <div className="space-y-2">
            {[0, 1].map(j => (
              <div key={j} className="bg-surface border border-border h-24" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── meeting row ───────────────────────────────────────────────────────────────

function MeetingRow({ meeting, isLive }: { meeting: Meeting; isLive: boolean }) {
  const cfg = MEETING_TYPE_CFG[meeting.type] ?? MEETING_TYPE_CFG.other;
  const { h, ampm } = fmtTime(meeting.scheduled_at);
  const hasBrief = !!meeting.brief;

  return (
    <NavLink
      to={`/app/meetings/${meeting.id}`}
      className={cn(
        'grid gap-5 items-stretch px-5 py-[18px]',
        'border border-border bg-surface cursor-pointer',
        'hover:border-accent/60 hover:bg-surface-2 transition-all duration-150',
        'group',
        isLive && 'border-l-[3px] border-l-accent',
      )}
      style={{ gridTemplateColumns: '72px 1fr 260px 36px' }}
    >
      {/* Time */}
      <div className="text-center border-r border-rule pr-4 flex flex-col justify-center">
        <span className={cn(
          'font-mono text-xl leading-none block',
          isLive ? 'text-accent' : 'text-fg-200',
        )}>
          {h}
        </span>
        <span className="font-mono text-[9px] tracking-[0.2em] uppercase text-fg-400">{ampm} EST</span>
        <span className="font-mono text-[9px] tracking-[0.1em] text-fg-400 block mt-1 opacity-70">
          {meeting.duration_minutes}M
        </span>
      </div>

      {/* Main */}
      <div className="min-w-0">
        {/* Type badge */}
        <span className={cn(
          'inline-flex items-center gap-1.5 font-mono text-[9px] font-bold tracking-[0.22em] uppercase',
          'border px-2 py-[3px] mb-2',
          cfg.cls,
        )}>
          {isLive && (
            <span className="w-[5px] h-[5px] rounded-full bg-current animate-pulse" />
          )}
          {cfg.label}
        </span>
        {/* Customer / title */}
        <h3 className={cn(
          'font-display text-[1.35rem] leading-[1.1] text-fg-100 mb-1',
          'group-hover:text-accent transition-colors',
        )}>
          {meeting.customer_name}
        </h3>
        <p className="font-sans text-[0.88rem] text-fg-300 mb-2">{meeting.title}</p>
        {/* Attendees meta */}
        <div className="flex items-center gap-4 font-mono text-[9.5px] tracking-[0.12em] uppercase text-fg-400">
          {meeting.attendees_theirs.length > 0 && (
            <span className="text-fg-300">{meeting.attendees_theirs.length} EXTERNAL</span>
          )}
          {meeting.source === 'calendar_sync' && (
            <span className="flex items-center gap-1">
              <Calendar className="w-2.5 h-2.5" />
              CALENDAR
            </span>
          )}
          {meeting.need && (
            <span className="italic text-fg-400 truncate normal-case font-sans tracking-normal text-[0.78rem]">
              re: {meeting.need.headline}
            </span>
          )}
        </div>
      </div>

      {/* Brief status */}
      <div className="border-l border-rule pl-5 flex flex-col justify-center">
        <span className={cn(
          'font-mono text-[8.5px] font-bold tracking-[0.24em] uppercase mb-1.5 flex items-center gap-1.5',
          hasBrief ? 'text-accent' : 'text-fg-400',
        )}>
          <span className={cn(
            'w-[14px] h-[14px] rounded-full grid place-items-center font-bold text-[8px]',
            hasBrief ? 'bg-accent text-page' : 'bg-surface-deep text-fg-300',
          )}>
            {hasBrief ? 'SK' : '··'}
          </span>
          {hasBrief ? 'BRIEF READY' : 'DRAFTING BRIEF'}
        </span>
        {hasBrief && meeting.brief?.progress_narrative && (
          <p className="font-sans text-[0.8rem] leading-[1.45] text-fg-300 line-clamp-2">
            {meeting.brief.progress_narrative}
          </p>
        )}
        {!hasBrief && (
          <p className="font-sans text-[0.8rem] leading-[1.45] text-fg-400">
            Sidekick is assembling the brief now.
          </p>
        )}
        {meeting.need && (
          <div className="mt-2 font-mono text-[8.5px] tracking-[0.12em] uppercase text-fg-400 flex items-center gap-1.5">
            <span>GOAL</span>
            <span className="text-accent font-bold">LINKED</span>
          </div>
        )}
      </div>

      {/* Arrow */}
      <div className="flex items-center justify-center text-fg-400 group-hover:text-accent transition-colors font-mono text-base">
        →
      </div>
    </NavLink>
  );
}

// ── day group ─────────────────────────────────────────────────────────────────

function DayGroup({ dateKey, meetings }: { dateKey: string; meetings: Meeting[] }) {
  const { date, isToday } = parseDateKey(dateKey);
  const label = dayLabel(dateKey);
  const suffix = isToday
    ? date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()
    : '';

  return (
    <div className="mt-7 first:mt-0">
      <div className="flex items-center gap-3 mb-2.5">
        {isToday && <Pulse active />}
        <span className={cn(
          'font-mono text-[11px] tracking-[0.25em] uppercase',
          isToday ? 'text-accent' : 'text-fg-400',
        )}>
          {label}{suffix ? ` · ${suffix}` : ''}
        </span>
        <span className="font-mono text-[10px] text-fg-400/60">({meetings.length})</span>
        <div className="h-px flex-1 bg-rule" />
      </div>
      <div className="flex flex-col gap-2">
        {meetings.map(m => (
          <MeetingRow key={m.id} meeting={m} isLive={false} />
        ))}
      </div>
    </div>
  );
}

// ── detection banner ──────────────────────────────────────────────────────────

function DetectionBanner() {
  return (
    <div className="flex items-center gap-3.5 px-[18px] py-3 mt-4 mb-1 border border-border bg-accent-bg border-l-[3px] border-l-accent">
      <span className="w-[26px] h-[26px] rounded-full bg-accent text-page grid place-items-center font-mono font-bold text-[11px] shrink-0">
        SK
      </span>
      <p className="font-sans text-[0.86rem] leading-[1.5] text-fg-200">
        I flag a calendar invite as a customer meeting when a participant's email domain matches one
        of your accounts — the brief starts drafting immediately.
      </p>
      <NavLink
        to="/app/settings/account"
        className="ml-auto shrink-0 font-mono text-[9.5px] tracking-[0.2em] uppercase text-fg-400 border border-border px-2.5 py-1.5 hover:border-accent hover:text-accent transition-colors"
      >
        ⚙ SETTINGS
      </NavLink>
    </div>
  );
}

// ── page ──────────────────────────────────────────────────────────────────────

export default function Meetings() {
  const { data, isLoading, error, refetch } = useMeetings();
  const [showPast, setShowPast] = React.useState(false);
  const { hasCompletedSetup, isStaff } = useAuth();
  const canManageIntegrations = hasCompletedSetup || isStaff;

  useRefreshOnFocus(refetch);

  const now = new Date();

  const upcomingMeetings = React.useMemo(() => {
    if (!data?.meetings) return [];
    return data.meetings
      .filter(m => new Date(m.scheduled_at) >= now && m.status === 'scheduled')
      .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime());
  }, [data?.meetings]);

  const pastMeetings = React.useMemo(() => {
    if (!data?.meetings) return [];
    return data.meetings
      .filter(m => new Date(m.scheduled_at) < now || m.status === 'completed')
      .sort((a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime());
  }, [data?.meetings]);

  const grouped = groupByDate(upcomingMeetings as any);

  if (error) {
    return (
      <div className="max-w-5xl mx-auto">
        <div className="hud-pane p-8">
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-signal-bad font-bold mb-4">
            Connection Error
          </div>
          <p className="text-fg-200 mb-4">{(error as Error).message}</p>
          <button
            onClick={() => refetch()}
            className="font-mono text-xs uppercase tracking-widest border border-signal-bad text-signal-bad px-4 py-2 hover:bg-signal-bad hover:text-page transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Page head */}
      <header className="mb-8 pb-6 border-b border-border flex justify-between items-end">
        <div>
          <div className="flex items-center gap-3 mb-4">
            <Pulse active />
            <span className="font-mono text-[10.5px] tracking-[0.22em] uppercase text-fg-400">
              MEETINGS · THIS WEEK
            </span>
            {!isLoading && (
              <span className="font-mono text-[10.5px] tracking-[0.2em] uppercase text-accent">
                · {upcomingMeetings.length} UPCOMING
              </span>
            )}
          </div>
          <h1 className="font-display text-[2.6rem] leading-none text-fg-100 mb-3">
            Meetings.
          </h1>
          <p className="font-sans text-fg-300 text-[1rem] leading-[1.55] max-w-[720px]">
            Every external meeting Sidekick found on your calendar — each one matched to a customer
            and shaped into a{' '}
            <span className="font-sans italic text-accent">goal-aware brief.</span>
          </p>
        </div>

        <button
          className="font-mono text-[11px] uppercase tracking-[0.2em] bg-accent text-page px-4 py-2 hover:bg-accent-hover transition-colors flex items-center gap-2 font-bold"
          onClick={() => console.log('Create meeting')}
        >
          <Plus className="w-3 h-3" />
          SCHEDULE
        </button>
      </header>

      {isLoading ? (
        <LoadingSkeleton />
      ) : upcomingMeetings.length === 0 ? (
        /* ── empty state ── */
        <div className="flex flex-col items-center justify-center py-16">
          <div className="w-20 h-20 bg-surface-2 border border-border flex items-center justify-center mb-6">
            <Calendar className="w-10 h-10 text-fg-400" />
          </div>
          <h2 className="font-display text-3xl text-fg-100 mb-2">No meetings scheduled.</h2>
          <p className="text-fg-400 text-center max-w-md mb-8 font-sans">
            Connect your calendar to automatically sync meetings, or schedule one manually.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 mb-8">
            <button
              className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-page px-6 py-3 font-mono text-xs uppercase tracking-widest font-bold transition-colors"
              onClick={() => console.log('Create meeting')}
            >
              <Plus className="w-4 h-4" />
              Schedule Meeting
            </button>
            {canManageIntegrations && (
              <NavLink
                to="/app/settings/account"
                className="inline-flex items-center gap-2 bg-surface-2 hover:bg-border text-fg-200 px-6 py-3 font-mono text-xs uppercase tracking-widest transition-colors border border-border"
              >
                <Settings className="w-4 h-4" />
                Connect Calendar
              </NavLink>
            )}
          </div>
          <Sidekick className="max-w-lg">
            <strong>Tip:</strong> Connect Google Calendar to automatically import meetings with your
            customers. I'll prepare briefings before each call.
          </Sidekick>
        </div>
      ) : (
        <>
          <DetectionBanner />
          {Array.from(grouped.entries()).map(([dateKey, meetings]) => (
            <DayGroup key={dateKey} dateKey={dateKey} meetings={meetings} />
          ))}
        </>
      )}

      {/* Past meetings */}
      {pastMeetings.length > 0 && (
        <div className="mt-16">
          <button
            onClick={() => setShowPast(!showPast)}
            className="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-400 hover:text-fg-100 transition-colors flex items-center gap-2 mb-4"
          >
            <span className={cn('transition-transform', showPast && 'rotate-90')}>›</span>
            PAST MEETINGS ({pastMeetings.length})
          </button>
          {showPast && (
            <div className="flex flex-col gap-2 opacity-60">
              {pastMeetings.slice(0, 10).map(m => (
                <MeetingRow key={m.id} meeting={m as any} isLive={false} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
