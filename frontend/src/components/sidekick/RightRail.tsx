import React from 'react';
import { Zap, ArrowRight, TrendingUp, TrendingDown, Minus, Check, MessageSquare, Eye, Lightbulb, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SentimentTrend, EngagementTrend } from '@/lib/dataconnect-hooks';
import {
  useCustomerInsights,
  transformInsightToSentimentTrend,
  transformInsightToEngagementTrend,
} from '@/lib/realtime-hooks';

/**
 * Right Rail - Customer context panel (Goal-Centric Design)
 *
 * HUD-style panel with:
 * - "FOCUSED · [CUSTOMER]" header with pulse indicator
 * - Customer name in serif italic + "Insights" suffix
 * - 2x2 metadata grid (ARR, Lifecycle, Day, Health)
 * - Health score bar
 * - Sparkline trends for Sentiment & Engagement
 * - Clustered Sidekick items with distinct visual variants
 * - Quick actions including "VIEW PLANS TAB"
 */

export interface SidekickItem {
  id: string;
  type: 'tip' | 'asking' | 'resolved' | 'observed' | 'working';
  question?: string;
  resolution?: string;
  text?: string;
  task?: string;
  step?: string;
  stepNum?: number;
  total?: number;
  by?: string;
  timestamp?: string;
  isCurrentItem?: boolean;
}

export interface CustomerMeta {
  id: string;
  name: string;
  refcode: string;
  tier: string;
  arr: string;
  lifecycle: string;
  day?: string;
  dayTotal?: string; // e.g., "105" for "Day 14 of 105"
  health?: string;
  healthColor?: string;
  healthScore?: number;
  sentiment?: string;
  sentimentColor?: string;
  signals?: Array<{ kind: string; state: string; sentence?: string }>;
}

interface RightRailProps {
  customer: CustomerMeta;
  items: SidekickItem[];
  openItemsCount?: number;
  resolvedItemsCount?: number;
  sentimentTrend?: SentimentTrend | null;
  engagementTrend?: EngagementTrend | null;
  trendsLoading?: boolean;
  useLiveInsights?: boolean;
  onOpenCustomer?: () => void;
  onOpenSidekick?: () => void;
  onViewPlans?: () => void;
  className?: string;
}

/**
 * MiniSparkline - Compact sparkline for trend visualization
 */
function MiniSparkline({
  values,
  color = 'accent',
  className,
}: {
  values: number[];
  color?: 'accent' | 'ok' | 'warn' | 'bad';
  className?: string;
}) {
  if (values.length === 0) return null;

  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;

  // Normalize and create path
  const width = 60;
  const height = 20;
  const padding = 2;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;

  const points = values.map((v, i) => {
    const x = padding + (i / (values.length - 1 || 1)) * chartWidth;
    const y = padding + (1 - (v - min) / range) * chartHeight;
    return `${x},${y}`;
  });

  const pathD = `M ${points.join(' L ')}`;

  const colorMap = {
    accent: 'var(--color-accent)',
    ok: 'var(--color-signal-ok)',
    warn: 'var(--color-signal-warn)',
    bad: 'var(--color-signal-bad)',
  };

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={cn('h-5 w-16', className)}
      preserveAspectRatio="none"
    >
      <path
        d={pathD}
        fill="none"
        stroke={colorMap[color]}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * TrendRow - Single trend metric with sparkline and delta
 */
function TrendRow({
  label,
  direction,
  delta,
  sparklineData,
  className,
}: {
  label: string;
  direction: 'up' | 'down' | 'stable';
  delta?: string;
  sparklineData?: number[];
  className?: string;
}) {
  const DirectionIcon = direction === 'up' ? TrendingUp : direction === 'down' ? TrendingDown : Minus;
  const color = direction === 'up' ? 'ok' : direction === 'down' ? 'bad' : 'accent';
  const colorClass = direction === 'up' ? 'text-signal-ok' : direction === 'down' ? 'text-signal-bad' : 'text-fg-400';

  return (
    <div className={cn('flex items-center justify-between gap-3', className)}>
      <span className="text-[11px] font-mono uppercase tracking-[0.2em] text-fg-400">{label}</span>
      <div className="flex items-center gap-2">
        {sparklineData && sparklineData.length > 0 && (
          <MiniSparkline values={sparklineData} color={color} />
        )}
        <div className={cn('flex items-center gap-1', colorClass)}>
          <DirectionIcon className="w-3 h-3" />
          {delta && <span className="text-[11px] font-mono">{delta}</span>}
        </div>
      </div>
    </div>
  );
}

/**
 * SidekickItemCard - Styled card for different sidekick item types
 */
function SidekickItemCard({
  item,
  onAnswer,
}: {
  item: SidekickItem;
  onAnswer?: () => void;
}) {
  const typeConfig = {
    asking: {
      icon: Zap,
      label: 'SIDEKICK ASKING',
      borderClass: 'border-l-accent',
      bgClass: 'bg-accent-bg',
      iconBg: 'bg-accent text-charcoal',
    },
    working: {
      icon: Loader2,
      label: 'SIDEKICK WORKING',
      borderClass: 'border-l-fg-400',
      bgClass: 'bg-surface-2/50',
      iconBg: 'bg-fg-400 text-charcoal',
    },
    observed: {
      icon: Eye,
      label: 'SIDEKICK OBSERVED',
      borderClass: 'border-l-signal-warn',
      bgClass: 'bg-signal-warn/5',
      iconBg: 'bg-signal-warn text-charcoal',
    },
    tip: {
      icon: Lightbulb,
      label: 'SIDEKICK TIP',
      borderClass: 'border-l-signal-ok',
      bgClass: 'bg-signal-ok/5',
      iconBg: 'bg-signal-ok text-charcoal',
    },
    resolved: {
      icon: Check,
      label: 'RESOLVED',
      borderClass: 'border-l-fg-400/50',
      bgClass: 'bg-surface-2/30',
      iconBg: 'bg-fg-400/50 text-charcoal',
    },
  };

  const config = typeConfig[item.type];
  const Icon = config.icon;

  return (
    <div
      className={cn(
        'border border-border rounded-sm overflow-hidden',
        'border-l-[3px]',
        config.borderClass,
        config.bgClass
      )}
    >
      {/* Header strip */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/50">
        <div className={cn('w-5 h-5 rounded-full flex items-center justify-center', config.iconBg)}>
          <Icon className={cn('w-3 h-3', item.type === 'working' && 'animate-spin')} />
        </div>
        <span className="text-[10px] font-mono uppercase tracking-[0.25em] text-fg-400">
          {config.label}
        </span>
        <span className="grow" />
        {item.isCurrentItem && (
          <span className="text-[9px] font-mono uppercase tracking-widest text-accent">YOU ARE HERE</span>
        )}
      </div>

      {/* Body */}
      <div className="px-3 py-2.5">
        {item.type === 'asking' && item.question && (
          <p className="text-fg-200 text-[13px] leading-relaxed">{item.question}</p>
        )}
        {item.type === 'working' && (
          <>
            {item.task && <p className="text-fg-200 text-[13px] mb-1">{item.task}</p>}
            {item.step && (
              <p className="text-fg-400 text-[11px] font-mono">
                Step {item.stepNum}/{item.total}: {item.step}
              </p>
            )}
          </>
        )}
        {item.type === 'observed' && item.text && (
          <p className="text-fg-200 text-[13px] leading-relaxed">{item.text}</p>
        )}
        {item.type === 'tip' && item.text && (
          <p className="text-fg-200 text-[13px] leading-relaxed">{item.text}</p>
        )}
        {item.type === 'resolved' && (
          <>
            {item.question && (
              <p className="text-fg-400 text-[12px] mb-1 line-through">{item.question}</p>
            )}
            {item.resolution && (
              <p className="text-fg-300 text-[13px]">{item.resolution}</p>
            )}
            {(item.by || item.timestamp) && (
              <p className="text-fg-400 text-[10px] font-mono uppercase tracking-wider mt-1">
                {item.by && <span>By {item.by}</span>}
                {item.by && item.timestamp && <span> · </span>}
                {item.timestamp && <span>{item.timestamp}</span>}
              </p>
            )}
          </>
        )}
      </div>

      {/* CTA for asking items */}
      {item.type === 'asking' && onAnswer && (
        <button
          onClick={onAnswer}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 border-t border-border/50 text-[11px] font-mono uppercase tracking-[0.2em] text-accent hover:bg-accent/10 transition-colors"
        >
          <span>Answer</span>
          <ArrowRight className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}

export const RightRail: React.FC<RightRailProps> = ({
  customer,
  items,
  openItemsCount,
  resolvedItemsCount,
  sentimentTrend: propSentimentTrend,
  engagementTrend: propEngagementTrend,
  trendsLoading: propTrendsLoading,
  useLiveInsights = true,
  onOpenCustomer,
  onOpenSidekick,
  onViewPlans,
  className,
}) => {
  // Use live insights from Firestore (with API fallback)
  const { insight, isLoading: insightLoading } = useCustomerInsights(
    useLiveInsights ? customer.id : null
  );

  // Derive trend data from insight if using live insights
  const sentimentTrend = useLiveInsights && insight
    ? transformInsightToSentimentTrend(insight)
    : propSentimentTrend;
  const engagementTrend = useLiveInsights && insight
    ? transformInsightToEngagementTrend(insight)
    : propEngagementTrend;
  const trendsLoading = useLiveInsights ? insightLoading : propTrendsLoading;

  const openItems = items.filter((i) => i.type !== 'resolved');
  const resolvedItems = items.filter((i) => i.type === 'resolved');

  // Derive sentiment direction for sparkline
  const sentimentDirection: 'up' | 'down' | 'stable' = sentimentTrend
    ? sentimentTrend.direction === 'improving'
      ? 'up'
      : sentimentTrend.direction === 'declining'
        ? 'down'
        : 'stable'
    : 'stable';

  // Derive engagement direction for sparkline
  const engagementDirection: 'up' | 'down' | 'stable' = engagementTrend
    ? engagementTrend.direction === 'increasing'
      ? 'up'
      : engagementTrend.direction === 'decreasing' || engagementTrend.direction === 'going_dark'
        ? 'down'
        : 'stable'
    : 'stable';

  // Format delta strings
  const sentimentDelta = sentimentTrend?.week_over_week?.percent_change
    ? `${sentimentTrend.week_over_week.percent_change > 0 ? '+' : ''}${sentimentTrend.week_over_week.percent_change}%`
    : undefined;
  const engagementDelta = engagementTrend?.week_over_week?.percent_change
    ? `${engagementTrend.week_over_week.percent_change > 0 ? '+' : ''}${engagementTrend.week_over_week.percent_change}%`
    : undefined;

  return (
    <aside className={cn('bg-surface border border-border shadow-lift flex flex-col', className)}>
      {/* HUD Header: FOCUSED · [CUSTOMER] */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-surface-2/50">
        <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
        <span className="text-[10px] font-mono uppercase tracking-[0.3em] text-accent font-bold">
          FOCUSED
        </span>
        <span className="text-[10px] font-mono uppercase tracking-[0.3em] text-fg-400">·</span>
        <span className="text-[10px] font-mono uppercase tracking-[0.25em] text-fg-400 truncate">
          {customer.name.toUpperCase()}
        </span>
      </div>

      {/* Customer Name + Insights */}
      <div className="px-4 pt-4 pb-3">
        <h3 className="font-display text-xl italic text-fg-100 mb-0.5">{customer.name}</h3>
        <p className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400">
          {customer.refcode} · Insights
        </p>
      </div>

      {/* 2x2 Metadata Grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 pb-4 border-b border-border">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-0.5">ARR</div>
          <div className="text-fg-200 font-medium text-sm">{customer.arr}</div>
        </div>
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-0.5">Lifecycle</div>
          <div className="text-fg-200 font-display italic text-sm capitalize">
            {customer.lifecycle.replace('_', ' ')}
          </div>
        </div>
        {customer.day && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-0.5">Day</div>
            <div className="text-fg-200 font-medium text-sm">
              {customer.day}
              {customer.dayTotal && <span className="text-fg-400"> of {customer.dayTotal}</span>}
            </div>
          </div>
        )}
        {customer.health && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-0.5">Health</div>
            <div
              className="font-display italic text-sm"
              style={{ color: customer.healthColor || 'var(--color-fg-200)' }}
            >
              {customer.health}
            </div>
          </div>
        )}
      </div>

      {/* Health Score Bar */}
      {customer.healthScore !== undefined && (
        <div className="px-4 py-3 border-b border-border">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-mono uppercase tracking-[0.25em] text-fg-400">
              Health Score
            </span>
            <span
              className="text-[13px] font-mono font-medium"
              style={{ color: customer.healthColor || 'var(--color-fg-200)' }}
            >
              {customer.healthScore}/100
            </span>
          </div>
          <div className="h-1.5 bg-surface-2 rounded-full overflow-hidden">
            <div
              className="h-full transition-all duration-500 rounded-full"
              style={{
                width: `${customer.healthScore}%`,
                backgroundColor: customer.healthColor || 'var(--color-accent)',
              }}
            />
          </div>
        </div>
      )}

      {/* Sentiment Chip */}
      {(customer.sentiment || sentimentTrend) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono uppercase tracking-[0.25em] text-fg-400">
              Sentiment
            </span>
            {customer.sentiment && (
              <span
                className="text-[10px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-sm"
                style={{
                  color: customer.sentimentColor || 'var(--color-signal-ok)',
                  backgroundColor: `${customer.sentimentColor || 'var(--color-signal-ok)'}15`,
                }}
              >
                {customer.sentiment}
              </span>
            )}
          </div>
          {sentimentTrend && (sentimentTrend.positive_count_30d > 0 || sentimentTrend.negative_count_30d > 0) && (
            <div className="flex items-center gap-2 text-[10px] font-mono uppercase">
              {sentimentTrend.positive_count_30d > 0 && (
                <span className="text-signal-ok">{sentimentTrend.positive_count_30d} POS</span>
              )}
              {sentimentTrend.negative_count_30d > 0 && (
                <span className="text-signal-bad">{sentimentTrend.negative_count_30d} NEG</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Trends Section */}
      {(sentimentTrend || engagementTrend || trendsLoading) && (
        <div className="px-4 py-3 border-b border-border space-y-2.5">
          <h5 className="text-[10px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-2">
            Trends · 30 Days
          </h5>
          {trendsLoading ? (
            <div className="text-fg-400 text-[12px] italic">Loading trends...</div>
          ) : (
            <>
              {sentimentTrend && (
                <TrendRow
                  label="Sentiment"
                  direction={sentimentDirection}
                  delta={sentimentDelta}
                  // Real gap-filled daily sentiment scores (0.0-1.0), scaled to 0-100.
                  // Empty until signals exist, in which case the sparkline is hidden.
                  sparklineData={
                    sentimentTrend?.daily_scores && sentimentTrend.daily_scores.length > 0
                      ? sentimentTrend.daily_scores.map((s) => s * 100)
                      : undefined
                  }
                />
              )}
              {engagementTrend && (
                <TrendRow
                  label="Engagement"
                  direction={engagementDirection}
                  delta={engagementDelta}
                  sparklineData={engagementTrend.daily_totals || undefined}
                />
              )}
              {/* Derived engagement-health (durable, from MetricSnapshot via heartbeat).
                  Only rendered when live insights carry a real series. */}
              {insight?.engagement_health &&
                insight.engagement_health.sparkline.length > 0 && (
                  <TrendRow
                    label="Engagement Health"
                    direction={
                      insight.engagement_health.direction === 'improving'
                        ? 'up'
                        : insight.engagement_health.direction === 'declining'
                          ? 'down'
                          : 'stable'
                    }
                    delta={insight.engagement_health.state.toUpperCase()}
                    // 0-1 daily series scaled to 0-100 for the sparkline.
                    sparklineData={insight.engagement_health.sparkline.map((s) => s * 100)}
                  />
                )}
            </>
          )}
        </div>
      )}

      {/* Sidekick Items */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <div className="flex items-center justify-between mb-3">
          <h5 className="text-[10px] font-mono uppercase tracking-[0.25em] text-fg-400">
            Sidekick Activity
          </h5>
          {(openItemsCount !== undefined || resolvedItemsCount !== undefined) && (
            <span className="text-[10px] font-mono text-fg-400">
              {openItemsCount !== undefined && `${openItemsCount} open`}
              {openItemsCount !== undefined && resolvedItemsCount !== undefined && ' · '}
              {resolvedItemsCount !== undefined && `${resolvedItemsCount} resolved`}
            </span>
          )}
        </div>

        {openItems.length === 0 && resolvedItems.length === 0 ? (
          <div className="py-6 px-4 text-center border border-dashed border-border bg-surface-2/30 rounded-sm">
            <MessageSquare className="w-5 h-5 mx-auto mb-2 text-fg-400" />
            <p className="text-fg-400 text-[12px] italic">
              No Sidekick activity for this customer yet.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Open items by type priority: asking > working > observed > tip */}
            {openItems
              .sort((a, b) => {
                const priority = { asking: 0, working: 1, observed: 2, tip: 3, resolved: 4 };
                return priority[a.type] - priority[b.type];
              })
              .map((item) => (
                <SidekickItemCard key={item.id} item={item} />
              ))}

            {/* Resolved items (collapsed section) */}
            {resolvedItems.length > 0 && (
              <div className="pt-3 mt-3 border-t border-border/50">
                <h6 className="text-[9px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-2">
                  Recently Resolved
                </h6>
                <div className="space-y-2">
                  {resolvedItems.slice(0, 2).map((item) => (
                    <SidekickItemCard key={item.id} item={item} />
                  ))}
                  {resolvedItems.length > 2 && (
                    <p className="text-[10px] font-mono text-fg-400 text-center">
                      +{resolvedItems.length - 2} more resolved
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="px-4 py-3 border-t border-border space-y-2">
        {onViewPlans && (
          <button
            className="w-full flex items-center justify-between px-3 py-2.5 text-[11px] font-mono uppercase tracking-[0.2em] bg-accent/10 hover:bg-accent/20 text-accent border border-accent/30 hover:border-accent/50 transition-colors rounded-sm"
            onClick={onViewPlans}
          >
            <span>View Plans Tab</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        )}
        {onOpenCustomer && (
          <button
            className="w-full flex items-center justify-between px-3 py-2.5 text-[11px] font-mono uppercase tracking-[0.2em] bg-surface-2 hover:bg-border text-fg-200 border border-border transition-colors rounded-sm"
            onClick={onOpenCustomer}
          >
            <span>Open Customer</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        )}
        {onOpenSidekick && (
          <button
            className="w-full flex items-center justify-between px-3 py-2.5 text-[11px] font-mono uppercase tracking-[0.2em] bg-surface-2 hover:bg-border text-fg-200 border border-border transition-colors rounded-sm"
            onClick={onOpenSidekick}
          >
            <span>Open in Sidekick</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </aside>
  );
};

export default RightRail;
