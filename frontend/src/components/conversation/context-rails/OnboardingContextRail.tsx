import React from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, AlertTriangle, CheckCircle2, Circle, ArrowRight, Clock } from 'lucide-react';
import { Sidekick, RefCode } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import type { ThreadDetail, Milestone, MilestoneStatus } from '@/lib/api';

interface OnboardingContextRailProps {
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

function getOwnerLabel(side: Milestone['owner_side']): string {
  const labels: Record<Milestone['owner_side'], string> = {
    us: 'Us',
    customer: 'Customer',
    joint: 'Joint',
  };
  return labels[side];
}

function getMilestoneStatusIcon(status: MilestoneStatus) {
  switch (status) {
    case 'done':
      return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
    case 'in_progress':
      return <ArrowRight className="w-4 h-4 text-rust-500" />;
    case 'blocked':
      return <AlertTriangle className="w-4 h-4 text-amber-500" />;
    case 'skipped':
      return <Circle className="w-4 h-4 text-charcoal-600" />;
    default:
      return <Circle className="w-4 h-4 text-charcoal-500" />;
  }
}

function getDaysRemaining(targetDate: string | null): { days: number; isOverdue: boolean } | null {
  if (!targetDate) return null;
  const target = new Date(targetDate);
  const now = new Date();
  const diffMs = target.getTime() - now.getTime();
  const days = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  return { days: Math.abs(days), isOverdue: days < 0 };
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

function MilestoneCard({ milestone, isActive }: { milestone: Milestone; isActive: boolean }) {
  const daysInfo = getDaysRemaining(milestone.target_date);

  return (
    <div
      className={cn(
        "py-2 px-2 -mx-2 rounded",
        isActive && "bg-charcoal-800/50 border-l-2 border-l-rust-500"
      )}
    >
      <div className="flex items-start gap-2">
        {getMilestoneStatusIcon(milestone.status)}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "text-sm font-medium",
                milestone.status === 'done' && "text-charcoal-400 line-through",
                milestone.status === 'in_progress' && "text-cream-100",
                milestone.status === 'blocked' && "text-amber-300",
                milestone.status === 'skipped' && "text-charcoal-500",
                milestone.status === 'not_started' && "text-cream-300"
              )}
            >
              {milestone.title}
            </span>
            {isActive && (
              <span className="text-[10px] font-mono uppercase tracking-wider px-1 py-0.5 bg-rust-900/30 text-rust-400 rounded">
                Now
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 mt-1 text-xs">
            <span className="text-charcoal-400">
              Owner: <span className="text-cream-400">{getOwnerLabel(milestone.owner_side)}</span>
            </span>
            {daysInfo && milestone.status !== 'done' && milestone.status !== 'skipped' && (
              <span
                className={cn(
                  daysInfo.isOverdue ? "text-rust-400" : "text-cream-400"
                )}
              >
                {daysInfo.isOverdue
                  ? `${daysInfo.days} days overdue`
                  : `${daysInfo.days} days left`
                }
              </span>
            )}
          </div>

          {milestone.description && isActive && (
            <p className="text-xs text-charcoal-400 mt-1 leading-relaxed">
              {milestone.description}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function ProgressBar({ milestones }: { milestones: Milestone[] }) {
  const completed = milestones.filter((m) => m.status === 'done').length;
  const total = milestones.length;
  const percent = total > 0 ? (completed / total) * 100 : 0;

  // Calculate current day estimate
  const currentMilestone = milestones.find((m) => m.status === 'in_progress');
  const currentDay = currentMilestone?.sort_order ?? completed + 1;
  const totalDays = milestones.length > 0 ? Math.max(...milestones.map((m) => m.sort_order + 1)) : 0;

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2 text-xs font-mono">
        <span className="text-charcoal-400">Progress</span>
        <span className="text-cream-300">
          Day {currentDay} of {totalDays}
        </span>
      </div>
      <div className="h-2 bg-charcoal-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-rust-600 to-rust-500 transition-all duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="flex items-center justify-between mt-1 text-xs">
        <span className="text-charcoal-500">{completed} of {total} milestones</span>
        <span className="text-cream-400">{Math.round(percent)}%</span>
      </div>
    </div>
  );
}

export function OnboardingContextRail({ thread }: OnboardingContextRailProps) {
  const { customer, milestones, sidekick, derailment_risks } = thread;

  // Sort milestones by sort_order
  const sortedMilestones = [...milestones].sort((a, b) => a.sort_order - b.sort_order);

  // Find the current active milestone
  const activeMilestoneId = sortedMilestones.find((m) => m.status === 'in_progress')?.id;

  // Identify blockers from milestones
  const blockedMilestones = sortedMilestones.filter((m) => m.status === 'blocked');

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
              <span className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border border-amber-500/50 text-amber-400">
                Onboarding
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
        {/* Milestone Progress */}
        {sortedMilestones.length > 0 && (
          <RailSection title="Milestone Progress">
            <ProgressBar milestones={sortedMilestones} />
            <div className="space-y-1">
              {sortedMilestones.map((milestone) => (
                <MilestoneCard
                  key={milestone.id}
                  milestone={milestone}
                  isActive={milestone.id === activeMilestoneId}
                />
              ))}
            </div>
          </RailSection>
        )}

        {/* Blockers */}
        {blockedMilestones.length > 0 && (
          <RailSection title="Blockers">
            <div className="space-y-2">
              {blockedMilestones.map((milestone) => (
                <div key={milestone.id} className="flex items-start gap-2 text-sm">
                  <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                  <div>
                    <span className="text-amber-300 font-medium">{milestone.title}</span>
                    {milestone.description && (
                      <p className="text-xs text-charcoal-400 mt-0.5">{milestone.description}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </RailSection>
        )}

        {/* Additional Risks */}
        {derailment_risks.length > 0 && (
          <RailSection title="Risks Detected">
            <div className="space-y-2">
              {derailment_risks.map((risk, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500 mt-0.5 flex-shrink-0" />
                  <span className="text-amber-300">{risk}</span>
                </div>
              ))}
            </div>
          </RailSection>
        )}

        {/* Sidekick Intelligence */}
        {sidekick && (
          <Sidekick className="mt-4">
            {sidekick.summary}
          </Sidekick>
        )}

        {/* Thread Context Link */}
        {thread.need && (
          <div className="mt-4 p-3 bg-charcoal-800/50 rounded border border-charcoal-700">
            <div className="flex items-center gap-2 text-xs text-charcoal-400 mb-1">
              <Clock className="w-3.5 h-3.5" />
              <span className="font-mono uppercase tracking-wider">Thread Context</span>
            </div>
            <p className="text-sm text-cream-300">
              {thread.need.headline}
            </p>
            {thread.need.lede && (
              <p className="text-xs text-charcoal-400 mt-1">{thread.need.lede}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
