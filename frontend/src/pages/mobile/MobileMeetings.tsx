import { useMemo, useState } from 'react';
import { Calendar, Users, ChevronRight, LinkIcon } from 'lucide-react';
import { useMeetings } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import type { MeetingType } from '@/lib/api';

// The hook returns the generated SDK row (its `source` enum differs from lib/api's
// Meeting), so derive the row type from the hook rather than importing Meeting.
type MeetingRow = NonNullable<ReturnType<typeof useMeetings>['data']>['meetings'][number];
import { ScreenHeader, MobileLoading, MobileError, MobileEmpty } from '@/components/mobile/mobileShared';
import { cn } from '@/lib/utils';

const meetingTypeConfig: Record<MeetingType, { label: string; color: string }> = {
  qbr: { label: 'QBR', color: 'text-accent border-accent' },
  renewal: { label: 'Renewal', color: 'text-signal-warn border-signal-warn' },
  check_in: { label: 'Check-in', color: 'text-fg-300 border-border' },
  onboarding: { label: 'Onboarding', color: 'text-signal-ok border-signal-ok' },
  kickoff: { label: 'Kickoff', color: 'text-signal-ok border-signal-ok' },
  support: { label: 'Support', color: 'text-signal-warn border-signal-warn' },
  other: { label: 'Meeting', color: 'text-fg-400 border-border' },
};

function dateLabel(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (date.toDateString() === now.toDateString()) return 'Today';
  if (date.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
  return date.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
}

function isToday(dateStr: string): boolean {
  return new Date(dateStr).toDateString() === new Date().toDateString();
}

function groupByDate(meetings: MeetingRow[]): [string, MeetingRow[]][] {
  const groups = new Map<string, MeetingRow[]>();
  for (const m of meetings) {
    const key = new Date(m.scheduled_at).toDateString();
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(m);
  }
  return Array.from(groups.entries());
}

export default function MobileMeetings() {
  const { data, isLoading, error, refetch } = useMeetings();
  const [showPast, setShowPast] = useState(false);
  useRefreshOnFocus(refetch);

  const now = new Date();
  const upcoming = useMemo(
    () =>
      (data?.meetings || [])
        .filter((m) => new Date(m.scheduled_at) >= now && m.status === 'scheduled')
        .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()),
    [data?.meetings],
  );
  const past = useMemo(
    () =>
      (data?.meetings || [])
        .filter((m) => new Date(m.scheduled_at) < now || m.status === 'completed')
        .sort((a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime()),
    [data?.meetings],
  );

  return (
    <div>
      <ScreenHeader eyebrow="Calendar" title="Meetings" sub={`${upcoming.length} upcoming`} />

      {error ? (
        <MobileError message={(error as Error).message} onRetry={() => refetch()} />
      ) : isLoading ? (
        <MobileLoading />
      ) : upcoming.length === 0 ? (
        <MobileEmpty
          icon={<Calendar className="h-7 w-7" />}
          title="No meetings scheduled"
          body="Connect your calendar on desktop to sync upcoming calls."
        />
      ) : (
        <div className="space-y-6 px-4 pb-6">
          {groupByDate(upcoming).map(([key, meetings]) => (
            <section key={key}>
              <h2 className="mb-3 flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.24em]">
                <span className={cn(isToday(key) ? 'text-accent' : 'text-fg-400')}>{dateLabel(key)}</span>
                <span className="text-fg-400/60">({meetings.length})</span>
                <span className="h-px flex-1 bg-border" />
              </h2>
              <div className="space-y-3">
                {meetings.map((m) => (
                  <MeetingCard key={m.id} meeting={m} />
                ))}
              </div>
            </section>
          ))}

          {past.length > 0 && (
            <div>
              <button
                onClick={() => setShowPast((v) => !v)}
                className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-400"
              >
                <ChevronRight className={cn('h-3 w-3 transition-transform', showPast && 'rotate-90')} />
                Past meetings ({past.length})
              </button>
              {showPast && (
                <div className="space-y-3 opacity-60">
                  {past.slice(0, 10).map((m) => (
                    <MeetingCard key={m.id} meeting={m} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MeetingCard({ meeting }: { meeting: MeetingRow }) {
  const type = meetingTypeConfig[meeting.type] || meetingTypeConfig.other;
  const today = isToday(meeting.scheduled_at);
  const time = new Date(meeting.scheduled_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  const attendees = meeting.attendees_theirs.length + meeting.attendees_ours.length;

  return (
    <div className={cn('rounded-md border border-border bg-surface p-4', today && 'edge-brass')}>
      <div className="mb-2 flex items-center gap-2">
        <span className={cn('border px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest', type.color)}>
          {type.label}
        </span>
        {meeting.need_id && (
          <span className="flex items-center gap-1 font-mono text-[9px] uppercase tracking-widest text-fg-400">
            <LinkIcon className="h-3 w-3" />
            Linked
          </span>
        )}
        <span className="ml-auto font-mono text-[10px] text-fg-400">{meeting.duration_minutes}min</span>
      </div>

      <div className="flex items-baseline gap-3">
        <span className={cn('font-mono text-lg', today ? 'text-accent' : 'text-fg-200')}>{time}</span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-display text-lg leading-tight text-fg-100">{meeting.title}</h3>
          <p className="truncate text-[13px] text-fg-300">
            <span className="font-medium text-fg-200">{meeting.customer_name}</span>
            {meeting.need && <span className="italic text-fg-400"> · re: {meeting.need.headline}</span>}
          </p>
        </div>
      </div>

      {attendees > 0 && (
        <div className="mt-2 flex items-center gap-1.5 text-[11px] text-fg-400">
          <Users className="h-3 w-3" />
          {meeting.attendees_theirs.length} external
          {meeting.attendees_ours.length > 0 && `, ${meeting.attendees_ours.length} internal`}
        </div>
      )}
    </div>
  );
}
