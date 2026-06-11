import React from 'react';
import { Zap } from 'lucide-react';
import {
  SidekickTip,
  SidekickResolved,
  SidekickObserved,
  SidekickWorking,
} from './SidekickAtoms';
import { TrendCard } from '@/components/ui/TrendCard';
import { cn } from '@/lib/utils';
import type { SentimentTrend, EngagementTrend } from '@/lib/dataconnect-hooks';
import {
  useCustomerInsights,
  transformInsightToSentimentTrend,
  transformInsightToEngagementTrend,
  type CustomerInsight
} from '@/lib/realtime-hooks';

/**
 * Right Rail - Customer context with clustered AI items
 *
 * Slides in when a need is selected in Today Queue.
 * Shows:
 * - Customer profile summary (ARR, lifecycle, health)
 * - ALL Sidekick items for that customer (clustered)
 * - Quick actions
 *
 * Per RightRailSurface design from Claude Design export.
 *
 * Backend Requirements:
 * - GET /api/workspaces/:id/customers/:customer_id/sidekick-items
 *   Returns: { customer, items: Array<SidekickItem>, metadata }
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
  isCurrentItem?: boolean; // "You are here"
}

export interface CustomerMeta {
  id: string;
  name: string;
  refcode: string;
  tier: string;
  arr: string;
  lifecycle: string;
  day?: string;
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
  /** Sentiment trend data (deprecated - use useCustomerInsights internally) */
  sentimentTrend?: SentimentTrend | null;
  /** Engagement trend data (deprecated - use useCustomerInsights internally) */
  engagementTrend?: EngagementTrend | null;
  /** Whether trends are loading (deprecated) */
  trendsLoading?: boolean;
  /** If true, fetch trends via useCustomerInsights hook (default: true) */
  useLiveInsights?: boolean;
  onOpenCustomer?: () => void;
  onOpenSidekick?: () => void;
  className?: string;
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
  className
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

  const openItems = items.filter(i => i.type !== 'resolved');
  const resolvedItems = items.filter(i => i.type === 'resolved');
  const hasTrends = sentimentTrend || engagementTrend;

  return (
    <aside className={cn('bg-surface border border-border shadow-lift p-6', className)}>
      {/* Customer Info */}
      <h4 className="font-display text-2xl uppercase text-fg-100 mb-2">{customer.name}</h4>
      <div className="text-[13px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-6">
        {customer.refcode} · {customer.tier}
      </div>

      {/* Customer Metadata Grid */}
      <div className="grid grid-cols-2 gap-4 mb-6 pb-6 border-b border-border">
        <div>
          <div className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-1">ARR</div>
          <div className="text-fg-200 font-medium">{customer.arr}</div>
        </div>
        <div>
          <div className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-1">Lifecycle</div>
          <div className="text-fg-200 font-medium capitalize">{customer.lifecycle.replace('_', ' ')}</div>
        </div>
        {customer.day && (
          <div>
            <div className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-1">Day</div>
            <div className="text-fg-200 font-medium">{customer.day}</div>
          </div>
        )}
        {customer.health && (
          <div>
            <div className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-1">Health</div>
            <div className="font-medium" style={{ color: customer.healthColor || 'var(--color-fg-200)' }}>
              {customer.health}
            </div>
          </div>
        )}
      </div>

      {/* Sentiment & Health Score Bar */}
      {(customer.sentiment || customer.healthScore !== undefined) && (
        <div className="mb-6 pb-6 border-b border-border">
          {customer.healthScore !== undefined && (
            <div className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400">Health Score</span>
                <span className="font-mono" style={{ color: customer.healthColor || 'var(--color-fg-200)' }}>
                  {customer.healthScore}/100
                </span>
              </div>
              <div className="h-1.5 bg-surface-2 overflow-hidden">
                <div
                  className="h-full transition-all duration-500"
                  style={{
                    width: `${customer.healthScore}%`,
                    backgroundColor: customer.healthColor || 'var(--color-accent)',
                  }}
                />
              </div>
            </div>
          )}
          {/* Sentiment label + count from trends */}
          {(customer.sentiment || sentimentTrend) && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400">Sentiment</span>
                {customer.sentiment && (
                  <span
                    className="text-[13px] font-mono font-medium px-2 py-0.5"
                    style={{
                      color: customer.sentimentColor || 'var(--color-fg-200)',
                      backgroundColor: `${customer.sentimentColor || 'var(--color-accent)'}20`,
                    }}
                  >
                    {customer.sentiment.toUpperCase()}
                  </span>
                )}
              </div>
              {/* Show actual counts from trend data */}
              {sentimentTrend && (sentimentTrend.negative_count_30d > 0 || sentimentTrend.positive_count_30d > 0) && (
                <div className="flex items-center gap-2 text-[11px] font-mono">
                  {sentimentTrend.positive_count_30d > 0 && (
                    <span className="text-signal-ok">{sentimentTrend.positive_count_30d} pos</span>
                  )}
                  {sentimentTrend.negative_count_30d > 0 && (
                    <span className="text-signal-bad">{sentimentTrend.negative_count_30d} neg</span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Activity & Sentiment Trends */}
      {(hasTrends || trendsLoading) && (
        <div className="mb-6 pb-6 border-b border-border">
          <h5 className="text-[13px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-3">
            Trends · 30 Days
          </h5>
          {trendsLoading ? (
            <div className="text-fg-400 text-sm italic">Loading trends...</div>
          ) : (
            <TrendCard
              sentiment={sentimentTrend}
              engagement={engagementTrend}
              showSparkline={true}
            />
          )}
        </div>
      )}

      {/* Sidekick Status */}
      <div className="mb-4">
        <h5 className="text-[13px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-3">
          Sidekick Status
        </h5>
        {(openItemsCount !== undefined || resolvedItemsCount !== undefined) && (
          <div className="text-fg-300 font-mono">
            {openItemsCount !== undefined && `${openItemsCount} open`}
            {openItemsCount !== undefined && resolvedItemsCount !== undefined && ' · '}
            {resolvedItemsCount !== undefined && `${resolvedItemsCount} resolved`}
          </div>
        )}
      </div>

      {/* Sidekick Items Grouped by Type */}
      {openItems.length === 0 && resolvedItems.length === 0 ? (
        <div className="py-6 px-4 text-center border border-dashed border-border bg-surface-2/30 mb-6">
          <p className="text-fg-400 italic">
            No Sidekick activity for this customer yet.
          </p>
          <p className="text-[13px] text-fg-400 mt-2">
            When agents work on this customer, items will appear here.
          </p>
        </div>
      ) : (
        <>
          {/* Questions - uses HudPane asks variant */}
          {openItems.filter(i => i.type === 'asking').length > 0 && (
            <div className="mb-6">
              {openItems.filter(i => i.type === 'asking').map(item => (
                <div key={item.id} className="hud-pane hud-pane--asks mb-3">
                  <div className="hud-pane__header hud-pane__header--asks">
                    <Zap className="w-3.5 h-3.5 fill-current" />
                    <span className="hud-pane__label">SIDEKICK ASKING</span>
                    <span className="grow" />
                    {item.isCurrentItem && (
                      <span className="hud-pane__count">YOU ARE HERE</span>
                    )}
                  </div>
                  <div className="hud-pane__body">
                    <p className="text-fg-200 mb-0">{item.question}</p>
                  </div>
                  <button className="hud-pane__cta">
                    <span>Answer →</span>
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Working */}
          {openItems.filter(i => i.type === 'working').length > 0 && (
            <div className="mb-6">
              <h5 className="text-[13px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-3">
                Sidekick · Working
              </h5>
              {openItems.filter(i => i.type === 'working').map(item => (
                <div key={item.id} className="mb-3">
                  {item.task && (
                    <SidekickWorking
                      task={item.task}
                      step={item.step || ''}
                      stepNum={item.stepNum || 1}
                      total={item.total || 8}
                      className="max-w-none"
                    />
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Observed */}
          {openItems.filter(i => i.type === 'observed').length > 0 && (
            <div className="mb-6">
              <h5 className="text-[13px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-3">
                Sidekick · Observed
              </h5>
              {openItems.filter(i => i.type === 'observed').map(item => (
                <div key={item.id} className="mb-3">
                  {item.text && (
                    <SidekickObserved className="max-w-none">
                      {item.text}
                    </SidekickObserved>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Tips */}
          {openItems.filter(i => i.type === 'tip').length > 0 && (
            <div className="mb-6">
              {openItems.filter(i => i.type === 'tip').map(item => (
                <div key={item.id} className="mb-3">
                  {item.text && (
                    <SidekickTip className="max-w-none">
                      {item.text}
                    </SidekickTip>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Resolved Items */}
      {resolvedItems.length > 0 && (
        <>
          <div className="mt-6 mb-4">
            <h5 className="text-[13px] font-mono uppercase tracking-[0.25em] text-fg-400">
              Sidekick · Resolved
            </h5>
          </div>
          {resolvedItems.map(item => (
            <div key={item.id} className="mb-4">
              {item.type === 'resolved' && (
                <SidekickResolved
                  question={item.question || ''}
                  resolution={item.resolution || ''}
                  by={item.by || 'UNKNOWN'}
                  timestamp={item.timestamp || ''}
                  className="max-w-none"
                />
              )}
            </div>
          ))}
        </>
      )}

      {/* Quick Actions */}
      <div className="mt-8 pt-6 border-t border-border">
        <h5 className="text-[13px] font-mono uppercase tracking-[0.25em] text-fg-400 mb-4">
          Quick Actions
        </h5>
        <div className="space-y-2">
          {onOpenCustomer && (
            <button
              className="w-full flex items-center justify-between px-4 py-2.5 text-[13px] font-mono uppercase tracking-[0.25em] bg-surface-2 hover:bg-border text-fg-200 border border-border transition-colors"
              onClick={onOpenCustomer}
            >
              Open Customer
              <span>→</span>
            </button>
          )}
          {onOpenSidekick && (
            <button
              className="w-full flex items-center justify-between px-4 py-2.5 text-[13px] font-mono uppercase tracking-[0.25em] bg-accent-bg hover:bg-accent/20 text-accent border border-accent/40 hover:border-accent transition-colors"
              onClick={onOpenSidekick}
            >
              Open in Sidekick
              <span>→</span>
            </button>
          )}
        </div>
      </div>
    </aside>
  );
};

export default RightRail;
