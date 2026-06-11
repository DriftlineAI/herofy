import React, { useState, useEffect, useMemo, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Timestamp } from '@/components/ui/huds';
import { SituationRow, SidekickAsksRow, GroupedAsksPane, type GroupedAsksItem } from '@/components/ui/HudPane';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useToday, useResolveNeed, useSnoozeNeed, useCustomerIntel, useSidekickItems, useSidekickAskingItems, useCustomerTrends } from '@/lib/dataconnect-hooks';
import { useWorkspaceNotifications, useRefreshOnFocus } from '@/lib/realtime-hooks';
import { useWorkspace } from '@/lib/workspace';
import { useAuth } from '@/lib/auth';
import type { TodayQueueItem, NeedType, CustomerIntelResponse } from '@/lib/api';
import { Check, Mail, MessageSquare, Calendar, Phone, Users, Settings } from 'lucide-react';
import { Link } from 'react-router-dom';
import { RightRail, type SidekickItem, type CustomerMeta } from '@/components/sidekick';

// Map need types to display labels
const needTypeLabels: Record<NeedType, string> = {
  urgent_support: 'URGENT SUPPORT',
  going_dark: 'GOING DARK',
  stalled_milestone: 'STALLED',
  approaching_renewal: 'RENEWAL',
  open_commitment_overdue: 'OVERDUE',
  frustrated_signal: 'FRUSTRATED',
  champion_departed: 'CHAMPION LEFT',
  onboarding_behind: 'BEHIND SCHEDULE',
  renewal_at_risk: 'RENEWAL RISK',
  new_handoff: 'NEW HANDOFF',
  meeting_prep_ready: 'MEETING PREP',
  positive_signal: 'POSITIVE',
  expansion_signal: 'EXPANSION',
  check_in_due: 'CHECK IN',
  escalation: 'ESCALATION',
  plan_approval_required: 'PLAN REVIEW',
  draft_response_ready: 'DRAFT READY',
  sidekick_question: 'SIDEKICK HELP',
  uncategorized: 'ATTENTION',
};

// Format ARR for display
function formatARR(cents: number | null): string {
  if (!cents) return '';
  const amount = cents / 100;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return `$${amount}`;
}

// Format time ago
function timeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 60) return `T-${minutes}m`;
  if (hours < 24) return `T-${hours}h`;
  return `T-${days}d`;
}

// Loading skeleton component - compact cards
function LoadingSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="hud-pane animate-pulse" style={{ minHeight: 100 }}>
          <div className="hud-pane__header">
            <div className="h-3 w-48 bg-border rounded" />
            <span className="grow" />
            <div className="h-3 w-16 bg-border rounded" />
          </div>
          <div className="hud-pane__body hud-pane__body--compact">
            <div className="h-5 w-40 bg-border rounded mb-2" />
            <div className="h-4 w-full bg-surface-2 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Error display component
function ErrorDisplay({ error, onRetry }: { error: Error; onRetry: () => void }) {
  return (
    <div className="hud-pane">
      <div className="hud-pane__header">
        <span className="hud-pane__label">CONNECTION ERROR</span>
      </div>
      <div className="hud-pane__body">
        <p className="text-fg-200 mb-4">{error.message}</p>
        <button
          onClick={onRetry}
          className="btn-hud"
        >
          Retry Connection
        </button>
      </div>
    </div>
  );
}


export default function Today() {
  const { data, isLoading, error, refetch } = useToday();
  const { items: sidekickItems, isLoading: sidekickAskingLoading, refetch: refetchSidekick } = useSidekickAskingItems();
  const resolveNeed = useResolveNeed();
  const snoozeNeed = useSnoozeNeed();
  const navigate = useNavigate();
  const location = useLocation();
  const { hasCompletedSetup, isStaff } = useAuth();

  // Only workspace owners (who completed setup) or staff can manage integrations
  const canManageIntegrations = hasCompletedSetup || isStaff;

  // Real-time notifications subscription
  const { workspaceId } = useWorkspace();
  const notifications = useWorkspaceNotifications(workspaceId);
  const prevTodayCountRef = useRef<number | null>(null);

  // Refetch on mount and page focus to prevent stale data
  useRefreshOnFocus(refetch);

  // Refetch when notification count changes (new items added by agents)
  useEffect(() => {
    // Debug: log all notification updates
    if (notifications) {
      console.log('[Today] Notifications received:', {
        today_count: notifications.today_count,
        sidekick_questions: notifications.sidekick_questions,
        updated_at: notifications.updated_at,
      });
    }

    if (notifications?.today_count !== undefined) {
      const prevCount = prevTodayCountRef.current;
      const newCount = notifications.today_count;

      // Only refetch if count changed and we had a previous count
      if (prevCount !== null && prevCount !== newCount) {
        console.log('[Today] Notification count changed:', prevCount, '→', newCount, '- refetching');
        refetch().then((result) => {
          console.log('[Today] Refetch completed, needs count:', result.data?.needs?.length);
        });
        refetchSidekick();
      }

      prevTodayCountRef.current = newCount;
    }
  }, [notifications?.today_count, refetch, refetchSidekick]);

  // Refetch data when navigating back from Sidekick question submission
  useEffect(() => {
    const state = location.state as { refetch?: boolean } | null;
    if (state?.refetch) {
      // Clear the state to prevent re-fetching on subsequent renders
      navigate(location.pathname, { replace: true, state: {} });
      // Refetch both today items and sidekick items
      refetch();
      refetchSidekick();
    }
  }, [location.state, location.pathname, navigate, refetch, refetchSidekick]);

  // Merge today items with workspace-level sidekick asking items
  // Convert sidekick items to TodayQueueItem-like format with type 'sidekick_question'
  const mergedItems = useMemo(() => {
    const rawTodayItems = data?.items || [];
    console.log('[Today] mergedItems recalculating, data.items count:', rawTodayItems.length);

    // Adjust priority of sidekick_question items to appear after urgent needs
    const todayItems = rawTodayItems.map(item => {
      if (item.type === 'sidekick_question') {
        return { ...item, priority_rank: Math.max(item.priority_rank, 50) };
      }
      return item;
    });

    // Convert SidekickTodayItems to TodayQueueItem format
    // Sidekick questions should appear AFTER urgent/important needs
    const sidekickCards: (TodayQueueItem & {
      agent_run_id?: string;
      agent_questions?: any[];
      agent_context?: string;
    })[] = sidekickItems.map(item => ({
      // Need fields
      id: item.need_id || item.id, // Use need_id if available, else item id
      workspace_id: '', // Not needed for display
      customer_id: item.customer_id,
      type: 'sidekick_question' as NeedType,
      headline: item.question,
      lede: item.why || null,
      priority_rank: item.is_blocking ? 50 : 200, // Sidekick questions come after urgent needs (which are typically 1-20)
      thread_id: null,
      milestone_id: null,
      meeting_id: null,
      snoozed_until: null,
      resolved_at: null,
      agent_reasoning: '',
      created_at: item.created_at,
      // TodayQueueItem extensions
      customer_name: item.customer_name,
      customer_lifecycle: item.customer_lifecycle as any,
      customer_arr_cents: item.customer_arr ? parseInt(item.customer_arr.replace(/[^0-9]/g, '')) * 100 : null,
      recommendation_primary: null,
      recommendation_secondary: null,
      recommendation_rationale: null,
      plan_id: null,
      // Sidekick-specific fields
      agent_run_id: item.agent_run_id,
      agent_questions: item.agent_questions,
      agent_context: item.agent_context,
    }));

    // Filter out sidekick cards that already have a matching need in todayItems
    // (avoid duplicates if the Need already created a sidekick_question type)
    const existingNeedIds = new Set(todayItems.map(i => i.id));
    const newSidekickCards = sidekickCards.filter(
      card => !existingNeedIds.has(card.id)
    );

    // Combine and sort by priority (lower rank = higher priority)
    const combined = [...todayItems, ...newSidekickCards];
    combined.sort((a, b) => a.priority_rank - b.priority_rank);

    // Group items by customer - show one card per customer with count of issues
    const customerGroups = new Map<string, typeof combined>();
    for (const item of combined) {
      const existing = customerGroups.get(item.customer_id);
      if (existing) {
        existing.push(item);
      } else {
        customerGroups.set(item.customer_id, [item]);
      }
    }

    // For each customer group, use the most urgent item as the primary
    // and attach the other items for display
    const groupedItems = Array.from(customerGroups.values()).map(items => {
      // Items are already sorted by priority, so first one is most urgent
      const primary = items[0];
      return {
        ...primary,
        grouped_items: items.length > 1 ? items : undefined,
        grouped_count: items.length,
      };
    });

    // Re-sort by the primary item's priority
    groupedItems.sort((a, b) => a.priority_rank - b.priority_rank);

    return groupedItems;
  }, [data?.items, sidekickItems]);

  // Track hovered customer for right rail
  const [hoveredNeed, setHoveredNeed] = useState<TodayQueueItem | null>(null);

  // Fetch sidekick items for hovered customer
  const { data: sidekickData, isLoading: sidekickLoading } = useSidekickItems(hoveredNeed?.customer_id);

  // Fetch customer trends (sentiment + engagement) for right rail
  const { data: trendsData, isLoading: trendsLoading } = useCustomerTrends(hoveredNeed?.customer_id || null);

  // Transform sidekick data to match RightRail's expected format
  const railData = sidekickData ? {
    customer: {
      id: sidekickData.customer.id,
      name: sidekickData.customer.name,
      refcode: sidekickData.customer.refcode || '',
      tier: sidekickData.customer.tier || 'STANDARD',
      arr: sidekickData.customer.arr || '$0',
      lifecycle: sidekickData.customer.lifecycle || 'active',
      day: sidekickData.customer.day,
      health: sidekickData.customer.health,
      healthColor: sidekickData.customer.health_color,
      healthScore: sidekickData.customer.health_score,
      sentiment: sidekickData.customer.sentiment,
      sentimentColor: sidekickData.customer.sentiment_color,
      signals: sidekickData.customer.signals,
    },
    items: sidekickData.items.map(item => ({
      id: item.id,
      type: item.type as 'tip' | 'asking' | 'resolved' | 'observed' | 'working',
      question: item.question,
      resolution: item.resolution,
      text: item.text,
      task: item.task,
      step: item.step,
      stepNum: item.step_num,
      total: item.total_steps,
      by: item.resolved_by,
      timestamp: item.timestamp_label,
      isCurrentItem: item.is_current_item,
    })),
    openItemsCount: sidekickData.open_count,
    resolvedItemsCount: sidekickData.resolved_count,
  } : null;

  // Initialize hovered need from first item when data loads
  useEffect(() => {
    if (mergedItems.length > 0 && !hoveredNeed) {
      const firstItem = mergedItems[0];
      setHoveredNeed(firstItem);
    }
  }, [mergedItems, hoveredNeed]);

  const handleResolve = (needId: string) => {
    resolveNeed.mutate(needId);
  };

  const handleSnooze = (needId: string) => {
    // Snooze for 24 hours
    const snoozedUntil = new Date();
    snoozedUntil.setHours(snoozedUntil.getHours() + 24);
    snoozeNeed.mutate({ needId, snoozedUntil });
  };

  const handleHover = (item: TodayQueueItem) => {
    setHoveredNeed(item);
    // useSidekickItems will automatically fetch when hoveredNeed.customer_id changes
  };

  // Count total items across all groups (not just the number of cards)
  const activeCount = mergedItems.reduce((sum, item) => {
    const count = (item as any).grouped_count || 1;
    return sum + (item.snoozed_until ? 0 : count);
  }, 0);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-24 relative mb-12">
      <div className="col-span-1 lg:col-span-8">
        <header className="mb-6 flex items-baseline gap-4 border-b border-border pb-4">
          <h1 className="text-sm tracking-[0.3em] font-mono text-fg-400 uppercase" style={{ fontFamily: 'var(--font-mono)', textTransform: 'uppercase' }}>Current Situations</h1>
          <span className="text-accent font-mono text-lg font-bold">[{activeCount}]</span>
          <div className="ml-auto flex items-center gap-8">
            <NavLink
              to="/app/week"
              className="text-[11px] font-mono uppercase tracking-[0.2em] text-fg-400 hover:text-fg-100 transition-colors hidden sm:block border border-border px-3 py-1"
            >
              The Weekly Dispatch →
            </NavLink>
            <Timestamp time={new Date().toISOString().split('T')[0]} className="text-fg-400" />
          </div>
        </header>

        {isLoading || sidekickAskingLoading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorDisplay error={error as Error} onRetry={() => refetch()} />
        ) : mergedItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="w-20 h-20 bg-signal-ok/20 flex items-center justify-center mb-6">
              <Check className="w-10 h-10 text-signal-ok" />
            </div>

            <h2 className="text-2xl mb-2">All Clear</h2>
            <p className="text-fg-300 text-center max-w-md mb-8">
              No situations requiring your attention right now. Check back later or add customers to start monitoring.
            </p>

            <div className="flex flex-col sm:flex-row gap-4 mb-8">
              <Link
                to="/app/customers"
                className="btn-hud"
              >
                <Users className="w-4 h-4" />
                View Portfolio
              </Link>

              {canManageIntegrations && (
                <Link
                  to="/app/settings/account"
                  className="btn-hud"
                >
                  <Settings className="w-4 h-4" />
                  Connect Integrations
                </Link>
              )}
            </div>

            <div className="hud-pane max-w-lg">
              <div className="hud-pane__header">
                <span className="hud-pane__pulse" />
                <span className="hud-pane__label">SIDEKICK TIP</span>
              </div>
              <div className="hud-pane__body">
                <p className="hud-pane__story" style={{ WebkitLineClamp: 'unset' }}>
                  Connect Gmail, Slack, and Calendar to let me monitor customer signals automatically. I'll surface what needs attention here.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {(() => {
              // Separate sidekick questions from regular items
              const sidekickItems = mergedItems.filter(item => item.type === 'sidekick_question');
              const regularItems = mergedItems.filter(item => item.type !== 'sidekick_question');

              // Build grouped asks data if 2+ sidekick items
              const groupedAsksData: GroupedAsksItem[] = sidekickItems.length >= 2
                ? sidekickItems.map(item => ({
                    id: item.id,
                    customerName: item.customer_name,
                    customerId: item.customer_id,
                    context: `${item.customer_lifecycle?.replace('_', ' ') || 'Active'} · ${item.headline}`,
                    questionCount: (item as any).agent_questions?.length || 1,
                  }))
                : [];

              const totalQuestions = groupedAsksData.reduce((sum, item) => sum + item.questionCount, 0);

              return (
                <>
                  {/* Regular situation rows first */}
                  {regularItems.map((item) => {
                    const groupedCount = (item as any).grouped_count || 1;
                    // For plan approvals with a plan_id, go directly to plan approval page
                    const handleClick = () => {
                      if (item.type === 'plan_approval_required' && item.plan_id) {
                        navigate(`/app/plans/${item.plan_id}`);
                      } else {
                        navigate(`/app/customers/${item.customer_id}`);
                      }
                    };
                    return (
                      <SituationRow
                        key={item.id}
                        refCode={item.id.slice(0, 7).toUpperCase()}
                        type={needTypeLabels[item.type] || item.type}
                        lifecycle={item.customer_lifecycle?.replace('_', ' ').toUpperCase()}
                        moreCount={groupedCount > 1 ? groupedCount - 1 : undefined}
                        timestamp={timeAgo(item.created_at)}
                        customerName={item.customer_name}
                        arr={item.customer_arr_cents ? formatARR(item.customer_arr_cents) + ' ARR' : undefined}
                        headline={item.headline}
                        onClick={handleClick}
                        onHover={() => handleHover(item)}
                        isHovered={hoveredNeed?.id === item.id}
                      />
                    );
                  })}

                  {/* Grouped asks pane when 2+ sidekick items - below customer needs */}
                  {sidekickItems.length >= 2 && (
                    <GroupedAsksPane
                      items={groupedAsksData}
                      totalQuestions={totalQuestions}
                      onItemClick={(item) => navigate(`/app/needs/${item.id}`)}
                      onItemHover={(groupedItem) => {
                        // Find the original sidekick item to get full TodayQueueItem data
                        const originalItem = sidekickItems.find(s => s.customer_id === groupedItem.customerId);
                        if (originalItem) {
                          handleHover(originalItem);
                        }
                      }}
                    />
                  )}

                  {/* Single sidekick asks row when exactly 1 - below customer needs */}
                  {sidekickItems.length === 1 && (
                    <SidekickAsksRow
                      key={sidekickItems[0].id}
                      customerName={sidekickItems[0].customer_name}
                      questionCount={(sidekickItems[0] as any).agent_questions?.length || 1}
                      description={sidekickItems[0].headline}
                      timestamp={timeAgo(sidekickItems[0].created_at)}
                      onClick={() => navigate(`/app/customers/${sidekickItems[0].customer_id}`)}
                      onAnswer={() => navigate(`/app/needs/${sidekickItems[0].id}`)}
                    />
                  )}
                </>
              );
            })()}
          </div>
        )}
      </div>

      {/* Sidebar - Right Rail with Sidekick Items */}
      <div className="col-span-1 lg:col-span-4 sticky top-12 self-start hidden lg:block">
        {hoveredNeed && railData && (
          <RightRail
            key={railData.customer.id}
            customer={railData.customer}
            items={railData.items}
            openItemsCount={railData.openItemsCount}
            resolvedItemsCount={railData.resolvedItemsCount}
            sentimentTrend={trendsData?.sentiment}
            engagementTrend={trendsData?.engagement}
            trendsLoading={trendsLoading}
            onOpenCustomer={() => navigate(`/app/customers/${railData.customer.id}`)}
            onOpenSidekick={() => navigate('/app/sidekick')}
          />
        )}
        {hoveredNeed && !railData && (
          <div className="hud-pane animate-pulse">
            <div className="hud-pane__header">
              <div className="h-3 w-32 bg-border rounded" />
            </div>
            <div className="hud-pane__body">
              <div className="h-5 w-48 bg-border rounded mb-4" />
              <div className="h-4 w-full bg-surface-2 rounded" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
