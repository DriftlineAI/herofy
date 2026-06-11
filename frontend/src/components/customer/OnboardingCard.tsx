import React from 'react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { ChevronRight, CheckCircle, Clock, AlertTriangle } from 'lucide-react';

interface OnboardingCardProps {
  customerId: string;
  customerName: string;
  playbookSlug?: string;
  playbookTitle?: string;
  daysCurrent: number;
  daysTotal: number;
  completedSteps: number;
  totalSteps: number;
  nextMandate?: string;
  nextMandateDate?: string;
  status: 'on_track' | 'at_risk' | 'behind';
  className?: string;
}

/**
 * OnboardingCard - Shows onboarding progress summary at the top of customer records
 * Links directly to the customer's plan
 */
export function OnboardingCard({
  customerId,
  customerName,
  playbookSlug = 'PB-ENT-ONB',
  playbookTitle = 'Enterprise onboarding',
  daysCurrent,
  daysTotal,
  completedSteps,
  totalSteps,
  nextMandate,
  nextMandateDate,
  status,
  className
}: OnboardingCardProps) {
  const progressPercent = Math.round((completedSteps / totalSteps) * 100);

  const statusConfig = {
    on_track: {
      icon: CheckCircle,
      color: 'text-signal-ok',
      borderColor: 'border-l-signal-ok',
      label: 'On track'
    },
    at_risk: {
      icon: AlertTriangle,
      color: 'text-signal-warn',
      borderColor: 'border-l-signal-warn',
      label: 'At risk'
    },
    behind: {
      icon: Clock,
      color: 'text-rust-500',
      borderColor: 'border-l-rust-500',
      label: 'Behind schedule'
    }
  };

  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <Link
      to={`/app/onboarding/${customerId}`}
      className={cn(
        'block border border-charcoal-700 border-l-2',
        config.borderColor,
        'bg-charcoal-900/50 p-5 hover:border-charcoal-600 transition-colors',
        className
      )}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono uppercase tracking-widest text-charcoal-400">
            Onboarding
          </span>
          <span className="text-xs font-mono text-charcoal-400">·</span>
          <span className="text-xs font-mono uppercase tracking-wider text-rust-500 font-bold">
            {playbookSlug}
          </span>
        </div>
        <div className={cn('flex items-center gap-2', config.color)}>
          <Icon className="w-4 h-4" />
          <span className="text-xs font-mono uppercase tracking-wider">
            {config.label}
          </span>
        </div>
      </div>

      {/* Title & progress */}
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="font-serif text-xl text-app-fg-100">
          {playbookTitle}
        </h3>
        <div className="flex items-baseline gap-1">
          <span className="font-serif italic text-2xl text-rust-500">
            {completedSteps}
          </span>
          <span className="font-mono text-xs text-app-fg-400 uppercase">
            /{totalSteps} done
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-3 h-1.5 bg-charcoal-800 rounded-full overflow-hidden">
        <div
          className={cn(
            'h-full transition-all duration-300',
            status === 'on_track' && 'bg-signal-ok',
            status === 'at_risk' && 'bg-signal-warn',
            status === 'behind' && 'bg-rust-500'
          )}
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-app-fg-400">
          Day <span className="text-app-fg-200 font-medium">{daysCurrent}</span> of {daysTotal}
        </span>
        {nextMandate && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono uppercase tracking-wider text-app-fg-400">
              Next mandate
            </span>
            <span className="text-app-fg-200">{nextMandate}</span>
            {nextMandateDate && (
              <span className="text-rust-500">{nextMandateDate}</span>
            )}
          </div>
        )}
        <ChevronRight className="w-5 h-5 text-app-fg-400 ml-2" />
      </div>
    </Link>
  );
}
