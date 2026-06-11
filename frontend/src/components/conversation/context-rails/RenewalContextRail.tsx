import React from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, AlertTriangle, Calendar, ArrowRight, Clock, Video } from 'lucide-react';
import { Sidekick, Timestamp } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import type { ThreadDetail, UpcomingMeeting, Stakeholder } from '@/lib/api';

interface RenewalContextRailProps {
  thread: ThreadDetail;
}

function formatARR(cents: number | null): string {
  if (!cents) return '';
  const dollars = cents / 100;
  if (dollars >= 1000) {
    return `$${(dollars / 1000).toFixed(0)}K`;
  }
  return `$${dollars.toFixed(0)}`;
}

function formatMeetingTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

  if (diffHours < 0) {
    return 'Past';
  } else if (diffHours < 24) {
    return diffHours < 1 ? 'In < 1 hour' : `In ${diffHours} hours`;
  } else if (diffDays === 0) {
    return 'Today';
  } else if (diffDays === 1) {
    return 'Tomorrow';
  } else if (diffDays < 7) {
    return date.toLocaleDateString('en-US', { weekday: 'long' });
  } else {
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }
}

function formatMeetingDateTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

function getDaysToRenewal(daysToRenewal: number | null): string {
  if (daysToRenewal === null) return '';
  if (daysToRenewal < 0) return `${Math.abs(daysToRenewal)} days past`;
  if (daysToRenewal === 0) return 'Today';
  if (daysToRenewal === 1) return 'Tomorrow';
  return `${daysToRenewal} days`;
}

function RailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-charcoal-700 py-4 last:border-b-0">
      <h3 className="font-mono text-[10px] uppercase tracking-widest text-charcoal-400 mb-3">
        {title}
      </h3>
      {children}
    </div>
  );
}

function MeetingCard({ meeting, isNext }: { meeting: UpcomingMeeting; isNext: boolean }) {
  return (
    <div
      className={cn(
        "py-2 px-2 -mx-2 rounded",
        isNext && "bg-charcoal-800/50 border-l-2 border-l-rust-500"
      )}
    >
      <div className="flex items-start gap-2">
        <Video className={cn("w-4 h-4 mt-0.5 flex-shrink-0", isNext ? "text-rust-400" : "text-charcoal-500")} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn("text-sm font-medium", isNext ? "text-cream-100" : "text-cream-300")}>
              {meeting.title}
            </span>
            {isNext && (
              <span className="text-[10px] font-mono uppercase tracking-wider px-1 py-0.5 bg-rust-900/30 text-rust-400 rounded">
                Next
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 mt-1 text-xs text-charcoal-400">
            <span className={cn(isNext && "text-rust-300")}>
              {formatMeetingTime(meeting.scheduled_at)}
            </span>
            <span>•</span>
            <span>{formatMeetingDateTime(meeting.scheduled_at)}</span>
            <span>•</span>
            <span>{formatDuration(meeting.duration_minutes)}</span>
          </div>

          {isNext && (
            <Link
              to="/app/meeting-prep"
              className="inline-flex items-center gap-1 mt-2 text-xs text-rust-400 hover:text-rust-300 transition-colors"
            >
              Open Meeting Prep
              <ArrowRight className="w-3 h-3" />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

function StakeholderCard({ stakeholder }: { stakeholder: Stakeholder }) {
  return (
    <div className="py-2">
      <div className="flex items-start gap-2">
        <span
          className={cn(
            "w-2 h-2 mt-1.5 rounded-full flex-shrink-0",
            stakeholder.status === 'active' ? "bg-emerald-500" : "bg-charcoal-600"
          )}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm text-cream-200 font-medium truncate">
              {stakeholder.name}
            </span>
            {stakeholder.role && (
              <span className="text-xs text-charcoal-400 font-mono">
                ({stakeholder.role})
              </span>
            )}
          </div>
          {stakeholder.sentiment_note && (
            <p className="text-xs text-charcoal-400 mt-0.5 leading-relaxed">
              {stakeholder.sentiment_note}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export function RenewalContextRail({ thread }: RenewalContextRailProps) {
  const { customer, upcoming_meetings, stakeholders, sidekick, derailment_risks, need } = thread;

  // Sort meetings by date
  const sortedMeetings = [...upcoming_meetings].sort(
    (a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()
  );

  // Next meeting is the first one in the future
  const now = new Date();
  const nextMeetingId = sortedMeetings.find(
    (m) => new Date(m.scheduled_at).getTime() > now.getTime()
  )?.id;

  // Calculate days to renewal (mock - would come from customer data)
  // Using lifecycle to determine renewal context
  const isRenewalContext = customer.lifecycle === 'renewing' || customer.lifecycle === 'at_risk';

  return (
    <div className="h-full overflow-y-auto">
      {/* Customer Header */}
      <div className="p-4 border-b border-charcoal-700 bg-charcoal-800/50">
        <Link
          to={`/app/customers/${customer.id}`}
          className="group flex items-start justify-between"
        >
          <div>
            <h2 className="font-serif text-lg text-cream-100 group-hover:text-cream-50 transition-colors">
              {customer.name}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span
                className={cn(
                  "text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border",
                  customer.lifecycle === 'at_risk' && "border-rust-500/50 text-rust-400",
                  customer.lifecycle === 'renewing' && "border-emerald-500/50 text-emerald-400",
                  !['at_risk', 'renewing'].includes(customer.lifecycle) && "border-charcoal-600 text-cream-400"
                )}
              >
                {customer.lifecycle.replace('_', ' ')}
              </span>
              {customer.arr_cents && (
                <span className="text-xs font-mono text-cream-300">
                  {formatARR(customer.arr_cents)} ARR
                </span>
              )}
            </div>
          </div>
          <ExternalLink className="w-4 h-4 text-charcoal-500 group-hover:text-cream-300 transition-colors flex-shrink-0" />
        </Link>
      </div>

      <div className="p-4">
        {/* Upcoming Meetings */}
        {sortedMeetings.length > 0 && (
          <RailSection title="Upcoming Meetings">
            <div className="space-y-1">
              {sortedMeetings.slice(0, 4).map((meeting) => (
                <MeetingCard
                  key={meeting.id}
                  meeting={meeting}
                  isNext={meeting.id === nextMeetingId}
                />
              ))}
            </div>
          </RailSection>
        )}

        {/* Derailment Risks */}
        {derailment_risks.length > 0 && (
          <RailSection title="Derailment Risks">
            <div className="space-y-2">
              {derailment_risks.map((risk, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <AlertTriangle className="w-3.5 h-3.5 text-rust-500 mt-0.5 flex-shrink-0" />
                  <span className="text-rust-300">{risk}</span>
                </div>
              ))}
            </div>
          </RailSection>
        )}

        {/* Thread Context */}
        {need && (
          <RailSection title="Thread Context">
            <div className="p-3 bg-charcoal-800/50 rounded border border-charcoal-700">
              <p className="text-sm text-cream-300">{need.headline}</p>
              {need.lede && (
                <p className="text-xs text-charcoal-400 mt-1">{need.lede}</p>
              )}
            </div>
          </RailSection>
        )}

        {/* Sidekick Intelligence */}
        {sidekick && (
          <Sidekick className="mt-0">
            {sidekick.summary}
          </Sidekick>
        )}

        {/* Key Stakeholders */}
        {stakeholders.length > 0 && (
          <RailSection title="Key Stakeholders">
            <div className="space-y-1">
              {stakeholders.slice(0, 4).map((stakeholder) => (
                <StakeholderCard key={stakeholder.id} stakeholder={stakeholder} />
              ))}
              {stakeholders.length > 4 && (
                <Link
                  to={`/app/customers/${customer.id}`}
                  className="text-xs text-rust-400 hover:text-rust-300 transition-colors"
                >
                  View all {stakeholders.length} stakeholders
                </Link>
              )}
            </div>
          </RailSection>
        )}

        {/* Renewal Timeline */}
        {isRenewalContext && (
          <div className="mt-4 p-3 bg-charcoal-800/50 rounded border border-charcoal-700">
            <div className="flex items-center gap-2 text-xs text-charcoal-400 mb-2">
              <Calendar className="w-3.5 h-3.5" />
              <span className="font-mono uppercase tracking-wider">Renewal Timeline</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-cream-300">Days to renewal</span>
              <span
                className={cn(
                  "text-sm font-mono",
                  customer.lifecycle === 'at_risk' ? "text-rust-400" : "text-emerald-400"
                )}
              >
                {customer.lifecycle === 'at_risk' ? '< 30' : '45'} days
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
