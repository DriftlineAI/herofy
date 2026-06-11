import React from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Signal, SignalKind, SignalState } from '@/lib/api';

interface HealthIndicatorProps {
  health: string | null;
  score: number | null;
  reason?: string | null;
  updatedBy?: string | null;
  updatedAt?: string | null;
  onClick?: () => void;
  showError?: boolean;
  className?: string;
  variant?: 'compact' | 'full';
  // Signals for deriving sentiment/engagement
  signals?: Signal[];
}

const HEALTH_CONFIG: Record<string, { color: string; icon: any; label: string }> = {
  strong: { color: '#10b981', icon: TrendingUp, label: 'Strong' },
  healthy: { color: '#10b981', icon: TrendingUp, label: 'Healthy' },
  stable: { color: '#e5dcc8', icon: Minus, label: 'Stable' },
  at_risk: { color: '#d96942', icon: TrendingDown, label: 'At Risk' },
  deteriorating: { color: '#d96942', icon: TrendingDown, label: 'Deteriorating' },
};

// Temperature labels based on score ranges
function getTemperatureLabel(score: number): { label: string; color: string } {
  if (score >= 80) return { label: 'Toasty.', color: '#10b981' };
  if (score >= 60) return { label: 'Warm.', color: '#22c55e' };
  if (score >= 40) return { label: 'Lukewarm.', color: '#e5dcc8' };
  if (score >= 20) return { label: 'Chilly.', color: '#f59e0b' };
  return { label: 'Frosty.', color: '#d96942' };
}

// Get latest signal by kind
function getSignalByKind(signals: Signal[] | undefined, kind: SignalKind): Signal | undefined {
  if (!signals) return undefined;
  return signals.find(s => s.kind === kind);
}

// Map signal state to display
function getStateDisplay(state: SignalState | undefined): { label: string; state: 'ok' | 'warn' | 'risk' } {
  switch (state) {
    case 'ok':
      return { label: 'POSITIVE', state: 'ok' };
    case 'warn':
      return { label: 'GUARDED', state: 'warn' };
    case 'risk':
      return { label: 'NEGATIVE', state: 'risk' };
    default:
      return { label: 'UNKNOWN', state: 'warn' };
  }
}

// Map engagement signal state to momentum display
function getMomentumDisplay(state: SignalState | undefined): { label: string; state: 'ok' | 'warn' | 'risk' } {
  switch (state) {
    case 'ok':
      return { label: 'RISING', state: 'ok' };
    case 'warn':
      return { label: 'STEADY', state: 'warn' };
    case 'risk':
      return { label: 'COOLING', state: 'risk' };
    default:
      return { label: 'UNKNOWN', state: 'warn' };
  }
}

// Format date for display
function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' });
}

const STATE_COLORS = {
  ok: 'text-emerald-500',
  warn: 'text-cream-400',
  risk: 'text-signal-risk',
};

export function HealthIndicator({
  health,
  score,
  reason,
  updatedBy,
  updatedAt,
  onClick,
  showError = false,
  className,
  variant = 'compact',
  signals,
}: HealthIndicatorProps) {
  const healthKey = health || 'stable';
  const displayScore = score ?? 50;
  const config = HEALTH_CONFIG[healthKey] || HEALTH_CONFIG.stable;
  const Icon = config.icon;
  const isUserOverride = updatedBy?.startsWith('user:');
  const temperature = getTemperatureLabel(displayScore);

  // Extract sentiment and engagement from signals
  const sentimentSignal = getSignalByKind(signals, 'sentiment');
  const engagementSignal = getSignalByKind(signals, 'engagement');

  const sentiment = sentimentSignal
    ? getStateDisplay(sentimentSignal.state)
    : { label: 'UNKNOWN', state: 'warn' as const };

  const momentum = engagementSignal
    ? getMomentumDisplay(engagementSignal.state)
    : { label: 'UNKNOWN', state: 'warn' as const };

  // Compact variant - original simple badge style
  if (variant === 'compact') {
    return (
      <div className={cn('flex items-center gap-2', className)}>
        <button
          onClick={onClick}
          disabled={!onClick}
          className={cn(
            'flex items-center gap-2 px-3 py-1 border text-sm font-mono uppercase tracking-widest transition-colors',
            onClick && 'cursor-pointer hover:border-cream-400',
            !onClick && 'cursor-default'
          )}
          style={{ borderColor: config.color, color: config.color }}
          title={reason || undefined}
        >
          <Icon className="w-3 h-3" />
          <span>{config.label}</span>
          <span className="text-xs opacity-70">({displayScore})</span>
        </button>

        {showError && (
          <span className="text-xs text-rust-500 italic">
            I&apos;m having trouble updating this
          </span>
        )}

        {isUserOverride && reason && !showError && (
          <span className="text-xs text-charcoal-400 italic" title={reason}>
            Manual override
          </span>
        )}
      </div>
    );
  }

  // Full variant - rich visualization matching design
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        'text-left transition-all group border border-charcoal-700 bg-charcoal-900/50 p-4 hover:border-charcoal-600',
        onClick && 'cursor-pointer',
        !onClick && 'cursor-default',
        className
      )}
      title={reason || 'Click to update health score'}
    >
      {/* Header Row */}
      <div className="flex items-start justify-between gap-4 mb-2">
        <div className="text-[10px] font-mono uppercase tracking-widest text-charcoal-500">
          SIDEKICK&apos;S READ
        </div>
        {updatedAt && (
          <div className="text-[10px] font-mono uppercase tracking-widest text-charcoal-500">
            {formatDate(updatedAt)}
          </div>
        )}
      </div>

      {/* Temperature & Score */}
      <div className="flex items-end justify-between gap-4 mb-3">
        <div>
          {/* Temperature Label */}
          <div
            className="font-serif text-3xl italic tracking-tight leading-none"
            style={{ color: temperature.color }}
          >
            {temperature.label}
          </div>
        </div>

        {/* Score */}
        <div className="text-right">
          <div className="flex items-baseline gap-1">
            <span
              className="text-2xl font-mono tabular-nums leading-none"
              style={{ color: temperature.color }}
            >
              {displayScore}
            </span>
            <span className="text-sm text-charcoal-500 font-mono">/ 100</span>
          </div>
        </div>
      </div>

      {/* Score Progress Bar */}
      <div className="w-full h-1 bg-charcoal-700 mb-4">
        <div
          className="h-full transition-all duration-500"
          style={{
            width: `${displayScore}%`,
            backgroundColor: temperature.color,
          }}
        />
      </div>

      {/* Status Indicators Row */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono uppercase tracking-widest mb-3">
        <div className="flex items-center gap-1">
          <span className="text-charcoal-500">SENTIMENT</span>
          <span className={STATE_COLORS[sentiment.state]}>
            {sentiment.label}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-charcoal-500">MOMENTUM</span>
          <span className={STATE_COLORS[momentum.state]}>
            {momentum.label}
          </span>
        </div>
      </div>

      {/* Health Status Badge */}
      <div
        className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest"
        style={{ color: config.color }}
      >
        <Icon className="w-3 h-3" />
        <span>{config.label}</span>
      </div>

      {/* Error State */}
      {showError && (
        <div className="mt-2 text-xs text-rust-500 italic">
          Having trouble updating health score
        </div>
      )}

      {/* Manual Override Note */}
      {isUserOverride && reason && !showError && (
        <div className="mt-2 text-[10px] text-charcoal-500 italic" title={reason}>
          Manually set: {reason.slice(0, 40)}{reason.length > 40 ? '...' : ''}
        </div>
      )}
    </button>
  );
}
