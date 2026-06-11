import React from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, AlertTriangle, Clock, MessageSquare } from 'lucide-react';
import { Sidekick, IntelBar, RefCode, Timestamp } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import type { ThreadDetail, Signal, Stakeholder, RelatedThread, SignalState } from '@/lib/api';

interface SupportContextRailProps {
  thread: ThreadDetail;
}

function getSignalLabel(kind: Signal['kind']): string {
  const labels: Record<Signal['kind'], string> = {
    engagement: 'Engagement',
    sentiment: 'Sentiment',
    commitments: 'Commitments',
  };
  return labels[kind];
}

function getSignalStateLabel(state: SignalState): string {
  const labels: Record<SignalState, string> = {
    ok: 'On track',
    warn: 'Warning',
    risk: 'At risk',
  };
  return labels[state];
}

function getSignalValue(state: SignalState): number {
  const values: Record<SignalState, number> = {
    ok: 5,
    warn: 3,
    risk: 1,
  };
  return values[state];
}

function formatTimeAgo(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return '1 day ago';
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatResponseTime(minutes: number | null): string {
  if (!minutes) return 'N/A';
  if (minutes < 60) return `${Math.round(minutes)}m`;
  if (minutes < 1440) return `${(minutes / 60).toFixed(1)}h`;
  return `${(minutes / 1440).toFixed(1)}d`;
}

function formatARR(cents: number | null): string {
  if (!cents) return '';
  const dollars = cents / 100;
  if (dollars >= 1000) {
    return `$${(dollars / 1000).toFixed(0)}K`;
  }
  return `$${dollars.toFixed(0)}`;
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

function SignalRow({ signal }: { signal: Signal }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "w-2 h-2 rounded-full",
            signal.state === 'ok' && "bg-emerald-500",
            signal.state === 'warn' && "bg-amber-500",
            signal.state === 'risk' && "bg-rust-500"
          )}
        />
        <span className="text-sm text-cream-300">{getSignalLabel(signal.kind)}</span>
      </div>
      <div className="flex items-center gap-2">
        <IntelBar value={getSignalValue(signal.state)} max={5} />
        <span
          className={cn(
            "text-xs font-mono",
            signal.state === 'ok' && "text-emerald-400",
            signal.state === 'warn' && "text-amber-400",
            signal.state === 'risk' && "text-rust-400"
          )}
        >
          {getSignalStateLabel(signal.state)}
        </span>
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

function RelatedThreadCard({ relatedThread }: { relatedThread: RelatedThread }) {
  return (
    <Link
      to={`/app/conversations/${relatedThread.id}`}
      className="block py-2 hover:bg-charcoal-800/50 -mx-2 px-2 rounded transition-colors"
    >
      <div className="flex items-start gap-2">
        <MessageSquare className="w-3.5 h-3.5 text-charcoal-500 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <RefCode>{relatedThread.id.slice(0, 8).toUpperCase()}</RefCode>
            <span
              className={cn(
                "text-[10px] font-mono uppercase tracking-wider px-1 py-0.5 rounded",
                relatedThread.status === 'open' && "bg-rust-900/30 text-rust-400",
                relatedThread.status === 'resolved' && "bg-emerald-900/30 text-emerald-400",
                relatedThread.status === 'archived' && "bg-charcoal-800 text-charcoal-400"
              )}
            >
              {relatedThread.status}
            </span>
          </div>
          <p className="text-sm text-cream-300 mt-0.5 truncate">
            {relatedThread.subject || 'No subject'}
          </p>
          <Timestamp time={formatTimeAgo(relatedThread.latest_message_at)} className="mt-1" />
        </div>
      </div>
    </Link>
  );
}

export function SupportContextRail({ thread }: SupportContextRailProps) {
  const { customer, signals, stakeholders, stats, related_threads, sidekick } = thread;

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
                  customer.lifecycle === 'active' && "border-emerald-500/50 text-emerald-400",
                  customer.lifecycle === 'at_risk' && "border-rust-500/50 text-rust-400",
                  customer.lifecycle === 'onboarding' && "border-amber-500/50 text-amber-400",
                  !['active', 'at_risk', 'onboarding'].includes(customer.lifecycle) && "border-charcoal-600 text-cream-400"
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
        {/* Sidekick Intelligence */}
        {sidekick && (
          <Sidekick className="mt-0 mb-4">
            {sidekick.summary}
          </Sidekick>
        )}

        {/* Signal Health */}
        {signals.length > 0 && (
          <RailSection title="Signal Health">
            <div className="space-y-1">
              {signals.map((signal) => (
                <SignalRow key={signal.id} signal={signal} />
              ))}
            </div>
          </RailSection>
        )}

        {/* Thread Stats */}
        <RailSection title="This Thread">
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-charcoal-400 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                First contact
              </span>
              <span className="text-cream-300">
                {formatTimeAgo(stats.first_contact_at)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-charcoal-400">Messages</span>
              <span className="text-cream-300">
                {stats.message_count} ({stats.our_message_count} us, {stats.their_message_count} them)
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-charcoal-400">Avg response time</span>
              <span className="text-cream-300">
                {formatResponseTime(stats.avg_response_time_minutes)}
              </span>
            </div>
          </div>
        </RailSection>

        {/* Related Threads */}
        {related_threads.length > 0 && (
          <RailSection title="Related Threads">
            <div className="space-y-1">
              {related_threads.slice(0, 5).map((rt) => (
                <RelatedThreadCard key={rt.id} relatedThread={rt} />
              ))}
              {related_threads.length > 5 && (
                <p className="text-xs text-charcoal-500 pt-2">
                  +{related_threads.length - 5} more threads
                </p>
              )}
            </div>
          </RailSection>
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

        {/* Derailment Risks */}
        {thread.derailment_risks.length > 0 && (
          <RailSection title="Risks Detected">
            <div className="space-y-2">
              {thread.derailment_risks.map((risk, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500 mt-0.5 flex-shrink-0" />
                  <span className="text-amber-300">{risk}</span>
                </div>
              ))}
            </div>
          </RailSection>
        )}
      </div>
    </div>
  );
}
