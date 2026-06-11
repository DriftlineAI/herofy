import React from 'react';
import { TrendingUp, TrendingDown, Minus, AlertTriangle, Activity, Heart } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SentimentTrend, EngagementTrend } from '@/lib/dataconnect-hooks';

/**
 * DualTrendChart - Combined engagement + sentiment line chart
 */
function DualTrendChart({
  engagementData,
  sentimentData,
  className,
}: {
  engagementData: number[];
  sentimentData: number[];
  className?: string;
}) {
  const viewBoxWidth = 300;
  const viewBoxHeight = 60;
  const padding = { top: 4, right: 12, bottom: 16, left: 12 };
  const chartWidth = viewBoxWidth - padding.left - padding.right;
  const chartHeight = viewBoxHeight - padding.top - padding.bottom;

  // Normalize data to 0-1 range
  const normalizeData = (data: number[]): number[] => {
    if (data.length === 0) return [];
    const max = Math.max(...data, 1);
    const min = Math.min(...data, 0);
    const range = max - min || 1;
    return data.map(v => (v - min) / range);
  };

  const normalizedEngagement = normalizeData(engagementData);
  const normalizedSentiment = normalizeData(sentimentData);

  // Create SVG path
  const createPath = (data: number[]): string => {
    if (data.length === 0) return '';
    const points = data.map((value, index) => {
      const x = padding.left + (index / (data.length - 1 || 1)) * chartWidth;
      const y = padding.top + (1 - value) * chartHeight;
      return `${x},${y}`;
    });
    return `M ${points.join(' L ')}`;
  };

  const engagementPath = createPath(normalizedEngagement);
  const sentimentPath = createPath(normalizedSentiment);

  return (
    <div className={cn("w-full", className)}>
      <svg
        viewBox={`0 0 ${viewBoxWidth} ${viewBoxHeight}`}
        className="w-full h-auto"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Grid line */}
        <line
          x1={padding.left} y1={padding.top + chartHeight / 2}
          x2={viewBoxWidth - padding.right} y2={padding.top + chartHeight / 2}
          stroke="#3a3a3a" strokeWidth="1" strokeDasharray="4,4" opacity="0.5"
        />

        {/* Sentiment line (cream) */}
        {sentimentPath && (
          <path d={sentimentPath} fill="none" stroke="#e8e4d9" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        )}

        {/* Engagement line (amber) */}
        {engagementPath && (
          <path d={engagementPath} fill="none" stroke="#d4a574" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        )}

        {/* X-axis labels */}
        <text x={padding.left} y={viewBoxHeight - 2} fill="#7a7a7a" fontSize="9" fontFamily="monospace">30d</text>
        <text x={viewBoxWidth - padding.right} y={viewBoxHeight - 2} fill="#7a7a7a" fontSize="9" fontFamily="monospace" textAnchor="end">TODAY</text>
      </svg>
    </div>
  );
}

/**
 * Generate sentiment line from trend data
 * TODO: Replace with real daily sentiment data from Firestore
 */
function generateSentimentLine(trend: SentimentTrend, days: number = 30): number[] {
  const values: number[] = [];
  const baseValue = 70;

  for (let i = 0; i < days; i++) {
    let value = baseValue;
    const progress = i / days;

    if (trend.direction === 'declining') {
      value = baseValue - (progress * 40);
    } else if (trend.direction === 'improving') {
      value = (baseValue - 30) + (progress * 40);
    }

    if (trend.negative_count_30d > 10) value -= 20;
    else if (trend.negative_count_30d > 5) value -= 10;

    values.push(Math.max(10, Math.min(100, value)));
  }

  return values;
}

/**
 * Get overall health status from combined trends
 */
function getCombinedStatus(
  sentiment: SentimentTrend | null,
  engagement: EngagementTrend | null
): { label: string; color: 'ok' | 'warn' | 'bad' | 'accent' } {
  const sentimentBad = sentiment && (
    sentiment.negative_count_30d >= 10 ||
    sentiment.direction === 'declining'
  );
  const sentimentWarn = sentiment && (
    sentiment.negative_count_30d >= 5 ||
    (sentiment.negative_count_30d > sentiment.positive_count_30d)
  );

  const engagementBad = engagement && (
    engagement.direction === 'going_dark' ||
    (engagement.days_since_last_interaction !== null && engagement.days_since_last_interaction > 14)
  );
  const engagementWarn = engagement && (
    engagement.direction === 'decreasing' ||
    (engagement.days_since_last_interaction !== null && engagement.days_since_last_interaction > 7)
  );
  const engagementUp = engagement && engagement.direction === 'increasing';

  // Divergence patterns
  if (engagementUp && sentimentBad) return { label: 'ESCALATING', color: 'bad' };
  if (engagementBad && sentimentBad) return { label: 'GOING DARK', color: 'bad' };
  if (engagementBad) return { label: 'GOING QUIET', color: 'warn' };
  if (sentimentBad) return { label: 'TROUBLED', color: 'bad' };
  if (sentimentWarn || engagementWarn) return { label: 'MIXED', color: 'warn' };

  return { label: 'HEALTHY', color: 'ok' };
}


/**
 * SparkLine - Mini bar chart for single metric
 */
function SparkLine({
  values,
  color = 'accent',
  className
}: {
  values: number[];
  color?: 'accent' | 'ok' | 'warn' | 'bad';
  className?: string;
}) {
  const max = Math.max(...values, 1);

  const colorClasses = {
    accent: 'bg-accent/40 hover:bg-accent',
    ok: 'bg-signal-ok/40 hover:bg-signal-ok',
    warn: 'bg-signal-warn/40 hover:bg-signal-warn',
    bad: 'bg-signal-bad/40 hover:bg-signal-bad',
  };

  return (
    <div className={cn("flex items-end gap-[1px] h-6", className)}>
      {values.map((v, i) => (
        <div
          key={i}
          className={cn("w-1 transition-colors", colorClasses[color])}
          style={{ height: `${Math.max((v / max) * 100, 4)}%` }}
        />
      ))}
    </div>
  );
}

/**
 * TrendIndicator - Direction arrow with color coding
 */
function TrendIndicator({
  direction,
  size = 'sm'
}: {
  direction: 'improving' | 'increasing' | 'stable' | 'declining' | 'decreasing' | 'going_dark';
  size?: 'sm' | 'md';
}) {
  const sizeClasses = size === 'sm' ? 'w-3 h-3' : 'w-4 h-4';

  switch (direction) {
    case 'improving':
    case 'increasing':
      return <TrendingUp className={cn(sizeClasses, "text-signal-ok")} />;
    case 'declining':
    case 'decreasing':
      return <TrendingDown className={cn(sizeClasses, "text-signal-bad")} />;
    case 'going_dark':
      return <AlertTriangle className={cn(sizeClasses, "text-signal-bad")} />;
    default:
      return <Minus className={cn(sizeClasses, "text-fg-400")} />;
  }
}

/**
 * Get color for trend direction
 */
function getDirectionColor(direction: string): 'ok' | 'warn' | 'bad' | 'accent' {
  switch (direction) {
    case 'improving':
    case 'increasing':
      return 'ok';
    case 'declining':
    case 'decreasing':
      return 'bad';
    case 'going_dark':
      return 'bad';
    default:
      return 'accent';
  }
}

/**
 * Get sentiment severity based on negative count and ratio
 */
function getSentimentSeverity(negative: number, positive: number): 'ok' | 'warn' | 'bad' {
  const total = negative + positive;
  if (total === 0) return 'ok';

  const negativeRatio = negative / total;

  // High volume of negatives or high ratio = bad
  if (negative >= 10 || negativeRatio >= 0.8) return 'bad';
  if (negative >= 5 || negativeRatio >= 0.5) return 'warn';
  return 'ok';
}

/**
 * Get a short status label for sentiment
 */
function getSentimentStatusLabel(severity: 'ok' | 'warn' | 'bad', direction: string): string {
  if (severity === 'bad') return 'TROUBLED';
  if (severity === 'warn') return 'MIXED';
  if (direction === 'improving') return 'IMPROVING';
  return 'HEALTHY';
}

/**
 * SentimentRatioBar - Visual bar showing positive vs negative ratio
 */
function SentimentRatioBar({
  positive,
  negative,
  className
}: {
  positive: number;
  negative: number;
  className?: string;
}) {
  const total = positive + negative;
  if (total === 0) return null;

  const positivePercent = (positive / total) * 100;
  const negativePercent = (negative / total) * 100;

  return (
    <div className={cn("flex h-1.5 w-full overflow-hidden bg-surface-2", className)}>
      {positive > 0 && (
        <div
          className="bg-signal-ok transition-all"
          style={{ width: `${positivePercent}%` }}
        />
      )}
      {negative > 0 && (
        <div
          className="bg-signal-bad transition-all"
          style={{ width: `${negativePercent}%` }}
        />
      )}
    </div>
  );
}

/**
 * SentimentTrendCard - Compact sentiment display
 */
export function SentimentTrendCard({
  trend,
  compact = false,
  className,
}: {
  trend: SentimentTrend | null;
  compact?: boolean;
  className?: string;
}) {
  if (!trend) {
    return (
      <div className={cn("text-fg-400 text-sm italic", className)}>
        No sentiment data
      </div>
    );
  }

  const severity = getSentimentSeverity(trend.negative_count_30d, trend.positive_count_30d);
  const statusLabel = getSentimentStatusLabel(severity, trend.direction);
  const total = trend.positive_count_30d + trend.negative_count_30d;

  if (compact) {
    return (
      <div className={cn("flex items-center justify-between", className)}>
        <span className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400">
          Sentiment
        </span>
        <span className={cn(
          "font-serif italic text-sm",
          severity === 'bad' && "text-signal-bad",
          severity === 'warn' && "text-signal-warn",
          severity === 'ok' && "text-signal-ok",
        )}>
          {statusLabel}
        </span>
      </div>
    );
  }

  return (
    <div className={cn("", className)}>
      {/* Header row: label left, status right */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400">
          Sentiment
        </span>
        <span className={cn(
          "font-serif italic",
          severity === 'bad' && "text-signal-bad",
          severity === 'warn' && "text-signal-warn",
          severity === 'ok' && "text-signal-ok",
        )}>
          {statusLabel}
        </span>
      </div>

      {/* Ratio bar */}
      {total > 0 && (
        <SentimentRatioBar
          positive={trend.positive_count_30d}
          negative={trend.negative_count_30d}
          className="mb-2"
        />
      )}

      {/* Summary line: counts + week-over-week in one line */}
      <div className={cn(
        "text-[12px]",
        severity === 'bad' ? "text-signal-bad" : severity === 'warn' ? "text-signal-warn" : "text-fg-300"
      )}>
        {total > 0 ? (
          <>
            <span className="font-mono">{trend.negative_count_30d}</span> negative
            {trend.positive_count_30d > 0 && (
              <>, <span className="font-mono">{trend.positive_count_30d}</span> positive</>
            )}
            {trend.week_over_week?.interpretation && (
              <span className="text-fg-400"> · </span>
            )}
          </>
        ) : (
          <span className="text-fg-400 italic">No signals in 30 days</span>
        )}
        {trend.week_over_week?.interpretation && (
          <span className={severity !== 'ok' ? '' : 'text-fg-400'}>
            {trend.week_over_week.interpretation}
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * Get engagement status label
 */
function getEngagementStatusLabel(direction: string, daysSince: number | null): string {
  if (direction === 'going_dark') return 'GOING DARK';
  if (daysSince !== null && daysSince > 14) return 'COOLING';
  if (direction === 'decreasing') return 'COOLING';
  if (direction === 'increasing') return 'WARMING';
  return 'ACTIVE';
}

/**
 * EngagementTrendCard - Compact engagement display with sparkline
 */
export function EngagementTrendCard({
  trend,
  compact = false,
  showSparkline = true,
  className,
}: {
  trend: EngagementTrend | null;
  compact?: boolean;
  showSparkline?: boolean;
  className?: string;
}) {
  if (!trend) {
    return (
      <div className={cn("text-fg-400 text-sm italic", className)}>
        No engagement data
      </div>
    );
  }

  const color = getDirectionColor(trend.direction);
  const statusLabel = getEngagementStatusLabel(trend.direction, trend.days_since_last_interaction);
  const isWarning = trend.direction === 'going_dark' || trend.direction === 'decreasing' ||
    (trend.days_since_last_interaction !== null && trend.days_since_last_interaction > 7);

  if (compact) {
    return (
      <div className={cn("flex items-center justify-between", className)}>
        <span className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400">
          Engagement
        </span>
        <span className={cn(
          "font-serif italic text-sm",
          color === 'ok' && "text-signal-ok",
          color === 'bad' && "text-signal-bad",
          color === 'accent' && "text-fg-300",
        )}>
          {statusLabel}
        </span>
      </div>
    );
  }

  return (
    <div className={cn("", className)}>
      {/* Header row: label left, status right */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400">
          Engagement
        </span>
        <span className={cn(
          "font-serif italic",
          color === 'ok' && "text-signal-ok",
          color === 'bad' && "text-signal-bad",
          color === 'accent' && "text-fg-300",
        )}>
          {statusLabel}
        </span>
      </div>

      {/* Sparkline */}
      {showSparkline && trend.daily_totals && trend.daily_totals.length > 0 && (
        <div className="mb-2">
          <SparkLine values={trend.daily_totals} color={color} />
        </div>
      )}

      {/* Summary line */}
      <div className={cn(
        "text-[12px]",
        isWarning ? "text-signal-warn" : "text-fg-300"
      )}>
        <span className="font-mono">{trend.total_interactions_30d}</span> interactions
        {trend.days_since_last_interaction !== null && trend.days_since_last_interaction > 0 && (
          <>
            <span className="text-fg-400"> · </span>
            Last <span className="font-mono">{trend.days_since_last_interaction}</span>d ago
          </>
        )}
        {trend.week_over_week?.percent_change !== null && trend.week_over_week.percent_change !== 0 && (
          <>
            <span className="text-fg-400"> · </span>
            <span className={trend.week_over_week.percent_change > 0 ? "text-signal-ok" : "text-signal-bad"}>
              {trend.week_over_week.percent_change > 0 ? '+' : ''}{trend.week_over_week.percent_change}% WoW
            </span>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * TrendCard - Combined dual-line chart for sentiment + engagement
 *
 * Shows both metrics on one chart to visualize divergence patterns:
 * - Engagement up + Sentiment down = "Getting angrier" (ESCALATING)
 * - Both dropping = "Going quiet" (GOING DARK)
 * - Both stable/high = "Holding steady" (HEALTHY)
 */
export function TrendCard({
  sentiment,
  engagement,
  compact = false,
  showSparkline = true,
  className,
}: {
  sentiment?: SentimentTrend | null;
  engagement?: EngagementTrend | null;
  compact?: boolean;
  showSparkline?: boolean;
  className?: string;
}) {
  // If no data at all, show placeholder
  if (!sentiment && !engagement) {
    return (
      <div className={cn("text-fg-400 text-sm italic py-2", className)}>
        No trend data available
      </div>
    );
  }

  const status = getCombinedStatus(sentiment, engagement);

  // Chart data
  const engagementData = engagement?.daily_totals || [];
  const sentimentData = sentiment ? generateSentimentLine(sentiment, engagementData.length || 30) : [];

  // Build summary text
  const summaryParts: string[] = [];
  if (sentiment) {
    if (sentiment.negative_count_30d > 0) {
      summaryParts.push(`${sentiment.negative_count_30d} negative signals`);
    }
    if (sentiment.week_over_week?.interpretation) {
      summaryParts.push(sentiment.week_over_week.interpretation.toLowerCase());
    }
  }
  if (engagement) {
    if (engagement.days_since_last_interaction !== null && engagement.days_since_last_interaction > 7) {
      summaryParts.push(`last contact ${engagement.days_since_last_interaction}d ago`);
    }
    if (engagement.week_over_week?.percent_change !== null && Math.abs(engagement.week_over_week.percent_change) > 20) {
      const direction = engagement.week_over_week.percent_change > 0 ? 'up' : 'down';
      summaryParts.push(`activity ${direction} ${Math.abs(engagement.week_over_week.percent_change)}%`);
    }
  }

  if (compact) {
    return (
      <div className={cn("", className)}>
        {/* Compact: just status + one line summary */}
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] font-mono uppercase tracking-widest text-fg-400">
            30-DAY TREND
          </span>
          <span className={cn(
            "text-[10px] font-mono uppercase tracking-widest px-1.5 py-0.5",
            status.color === 'ok' && "text-signal-ok bg-signal-ok/10",
            status.color === 'warn' && "text-signal-warn bg-signal-warn/10",
            status.color === 'bad' && "text-signal-risk bg-signal-risk-soft",
            status.color === 'accent' && "text-fg-300 bg-surface-2",
          )}>
            {status.label}
          </span>
        </div>
        {summaryParts.length > 0 && (
          <p className={cn(
            "text-[11px]",
            status.color === 'bad' ? "text-signal-risk" :
            status.color === 'warn' ? "text-signal-warn" : "text-fg-400"
          )}>
            {summaryParts.slice(0, 2).join(' · ')}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className={cn("", className)}>
      {/* Status badge */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-widest text-fg-400">
          30-DAY WINDOW
        </span>
        <span className={cn(
          "text-[10px] font-mono uppercase tracking-widest px-1.5 py-0.5",
          status.color === 'ok' && "text-signal-ok bg-signal-ok/10",
          status.color === 'warn' && "text-signal-warn bg-signal-warn/10",
          status.color === 'bad' && "text-signal-risk bg-signal-risk-soft",
          status.color === 'accent' && "text-fg-300 bg-surface-2",
        )}>
          {status.label}
        </span>
      </div>

      {/* Dual-line chart */}
      {(engagementData.length > 0 || sentimentData.length > 0) && (
        <DualTrendChart
          engagementData={engagementData}
          sentimentData={sentimentData}
          className="mb-2"
        />
      )}

      {/* Legend */}
      <div className="flex items-center gap-4 mb-2 text-[9px] font-mono uppercase tracking-widest">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5" style={{ backgroundColor: '#d4a574' }} />
          <span style={{ color: '#7a7a7a' }}>Engagement</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5" style={{ backgroundColor: '#e8e4d9' }} />
          <span style={{ color: '#7a7a7a' }}>Sentiment</span>
        </div>
      </div>

      {/* Summary line */}
      {summaryParts.length > 0 && (
        <p className={cn(
          "text-[11px]",
          status.color === 'bad' ? "text-signal-risk" :
          status.color === 'warn' ? "text-signal-warn" : "text-fg-300"
        )}>
          {summaryParts.join(' · ')}
        </p>
      )}
    </div>
  );
}

export default TrendCard;
