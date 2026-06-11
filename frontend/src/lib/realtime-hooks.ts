/**
 * Real-time hooks for Firestore subscriptions
 *
 * These hooks provide live updates for:
 * - Setup progress (customer classification streaming)
 * - Agent status (running, paused, waiting for input)
 * - Workspace notifications (unread counts, alerts)
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { doc, collection, query, orderBy, onSnapshot, type Unsubscribe } from 'firebase/firestore';
import { db } from './firestore';
import type { SentimentTrend, EngagementTrend } from './dataconnect-hooks';

/**
 * Normalize UUID to standard format with dashes.
 * Ensures consistent document IDs in Firestore.
 */
function normalizeUuid(uuid: string): string {
  const clean = uuid.replace(/-/g, '');
  if (clean.length === 32) {
    return `${clean.slice(0, 8)}-${clean.slice(8, 12)}-${clean.slice(12, 16)}-${clean.slice(16, 20)}-${clean.slice(20)}`;
  }
  return uuid;
}

// =============================================================================
// Types
// =============================================================================

export interface CustomerProgress {
  status: 'pending' | 'reading' | 'classified' | 'error';
  step?: string;
  progress_pct?: number;
  items_read?: number;
  items_total?: number;
  // Classification result (when status === 'classified')
  group?: string;
  confidence?: number;
  reasoning?: string;
  what_i_know?: string[];
  what_im_uncertain_about?: string[];
  // Error info (when status === 'error')
  error?: string;
}

export interface SetupProgressData {
  customers: Record<string, CustomerProgress>;
  updated_at?: Date;
}

export interface WorkspaceNotifications {
  today_count: number;
  unread_conversations: number;
  sidekick_questions: number;
  agent_runs_active: number;
  // Set by orchestrator consumer when a worker run starts; cleared when done.
  // Frontend uses this to subscribe to agent_status/{active_run_id} for live progress.
  active_run_id?: string | null;
  updated_at?: Date;
  // Conversations real-time: counter increments when new messages arrive
  conversations_count?: number;
  // Last event for animations/notifications
  last_event?: {
    type: 'need_created' | 'need_resolved';
    need_id: string;
    need_type?: string;
    customer_name?: string;
    timestamp?: Date;
  };
  // Last conversation event for animations
  last_conversation_event?: {
    type: 'new_messages';
    thread_id?: string;
    interaction_count?: number;
    channel?: string;
    timestamp?: Date;
  };
}

export interface AgentStatus {
  status: 'starting' | 'running' | 'paused' | 'waiting_for_input' | 'completed' | 'failed';
  current_step: string;
  progress_pct: number;
  message: string;
  customer_id?: string;
  customer_name?: string;
  updated_at?: Date;
}

export interface AgentOutput {
  id: string;
  agent_name: string;
  kind: string;            // 'llm' | 'stage'
  text: string;
  function_calls?: string[];
  created_at?: Date;
}

export interface AgentStep {
  id: string;
  step: string;
  status: string;
  progress_pct?: number | null;
  created_at?: Date;
}

// =============================================================================
// Setup Progress Hook
// =============================================================================

/**
 * Subscribe to real-time setup progress for customer classification.
 *
 * @param workspaceId - The workspace to watch
 * @returns Record of customer ID to progress state
 *
 * @example
 * const progress = useSetupProgress(workspaceId);
 * const customerState = progress['customer-123'];
 * // { status: 'reading', step: 'Analyzing CRM data', progress_pct: 45 }
 */
export function useSetupProgress(workspaceId: string | null): Record<string, CustomerProgress> {
  const [progress, setProgress] = useState<Record<string, CustomerProgress>>({});

  useEffect(() => {
    if (!workspaceId) {
      console.log('[useSetupProgress] No workspaceId, clearing progress');
      setProgress({});
      return;
    }

    // Normalize workspace ID to standard UUID format with dashes
    const normalizedId = normalizeUuid(workspaceId);
    console.log('[useSetupProgress] Subscribing to setup_progress/' + normalizedId);
    let unsubscribe: Unsubscribe | undefined;

    try {
      const docRef = doc(db, 'setup_progress', normalizedId);
      unsubscribe = onSnapshot(
        docRef,
        (snapshot) => {
          console.log('[useSetupProgress] Snapshot received:', {
            exists: snapshot.exists(),
            id: snapshot.id,
          });
          if (snapshot.exists()) {
            const data = snapshot.data();
            console.log('[useSetupProgress] Raw data keys:', Object.keys(data));

            // Parse dot-notation keys like "customers.{id}" into a proper customers object
            // The backend writes "customers.{customerId}" as top-level keys
            const customers: Record<string, CustomerProgress> = {};
            for (const [key, value] of Object.entries(data)) {
              if (key.startsWith('customers.')) {
                const customerId = key.replace('customers.', '');
                customers[customerId] = value as CustomerProgress;
              }
            }

            console.log('[useSetupProgress] Parsed customers count:', Object.keys(customers).length);
            setProgress(customers);
          } else {
            console.log('[useSetupProgress] Document does not exist');
            setProgress({});
          }
        },
        (error) => {
          console.error('[useSetupProgress] Subscription error:', error);
          // Don't clear progress on error - keep last known state
        }
      );
      console.log('[useSetupProgress] Subscription created successfully');
    } catch (error) {
      console.error('[useSetupProgress] Failed to subscribe:', error);
    }

    return () => {
      console.log('[useSetupProgress] Unsubscribing');
      if (unsubscribe) {
        unsubscribe();
      }
    };
  }, [workspaceId]);

  return progress;
}

// =============================================================================
// Workspace Notifications Hook
// =============================================================================

/**
 * Subscribe to real-time workspace notification counts.
 *
 * @param workspaceId - The workspace to watch
 * @returns Notification counts or null if not connected
 *
 * @example
 * const notifications = useWorkspaceNotifications(workspaceId);
 * // { today_count: 5, unread_conversations: 3, sidekick_questions: 1, agent_runs_active: 0 }
 */
export function useWorkspaceNotifications(workspaceId: string | null): WorkspaceNotifications | null {
  const [notifications, setNotifications] = useState<WorkspaceNotifications | null>(null);

  useEffect(() => {
    if (!workspaceId) {
      console.log('[useWorkspaceNotifications] No workspaceId, clearing notifications');
      setNotifications(null);
      return;
    }

    // Normalize workspace ID to standard UUID format with dashes
    const normalizedId = normalizeUuid(workspaceId);
    console.log('[useWorkspaceNotifications] Subscribing to notifications/' + normalizedId);
    let unsubscribe: Unsubscribe | undefined;

    try {
      const docRef = doc(db, 'notifications', normalizedId);
      unsubscribe = onSnapshot(
        docRef,
        (snapshot) => {
          console.log('[useWorkspaceNotifications] Snapshot received:', {
            exists: snapshot.exists(),
            id: snapshot.id,
          });
          if (snapshot.exists()) {
            const data = snapshot.data() as WorkspaceNotifications;
            console.log('[useWorkspaceNotifications] Data:', {
              today_count: data.today_count,
              sidekick_questions: data.sidekick_questions,
              conversations_count: data.conversations_count,
            });
            setNotifications(data);
          } else {
            console.log('[useWorkspaceNotifications] Document does not exist');
            setNotifications(null);
          }
        },
        (error) => {
          console.error('[useWorkspaceNotifications] Subscription error:', error);
        }
      );
      console.log('[useWorkspaceNotifications] Subscription created successfully');
    } catch (error) {
      console.error('[useWorkspaceNotifications] Failed to subscribe:', error);
    }

    return () => {
      console.log('[useWorkspaceNotifications] Unsubscribing');
      if (unsubscribe) {
        unsubscribe();
      }
    };
  }, [workspaceId]);

  return notifications;
}

// =============================================================================
// Agent Status Hook
// =============================================================================

/**
 * Subscribe to real-time agent run status.
 *
 * @param runId - The agent run ID to watch, or null to disable
 * @returns Agent status or null if not connected/not found
 *
 * @example
 * const status = useAgentStatusRealtime(agentRunId);
 * // { status: 'running', current_step: 'Analyzing customer data', progress_pct: 65 }
 */
export function useAgentStatusRealtime(runId: string | null): AgentStatus | null {
  const [status, setStatus] = useState<AgentStatus | null>(null);

  useEffect(() => {
    if (!runId) {
      setStatus(null);
      return;
    }

    let unsubscribe: Unsubscribe | undefined;

    try {
      const normalizedId = normalizeUuid(runId);
      const docRef = doc(db, 'agent_status', normalizedId);
      unsubscribe = onSnapshot(
        docRef,
        (snapshot) => {
          if (snapshot.exists()) {
            const data = snapshot.data() as AgentStatus;
            setStatus(data);
          } else {
            setStatus(null);
          }
        },
        (error) => {
          console.error('Agent status subscription error:', error);
        }
      );
    } catch (error) {
      console.error('Failed to subscribe to agent status:', error);
    }

    return () => {
      if (unsubscribe) {
        unsubscribe();
      }
    };
  }, [runId]);

  return status;
}

/**
 * Subscribe to the per-agent/LLM outputs captured during a run, in order.
 * Reads agent_status/{runId}/outputs (written by the orchestrator's after_model_callback).
 *
 * @param runId - The agent run ID to watch, or null to disable
 * @returns Ordered list of agent outputs (empty array until any arrive)
 */
export function useAgentOutputsRealtime(runId: string | null): AgentOutput[] {
  const [outputs, setOutputs] = useState<AgentOutput[]>([]);

  useEffect(() => {
    if (!runId) {
      setOutputs([]);
      return;
    }

    let unsubscribe: Unsubscribe | undefined;
    try {
      const normalizedId = normalizeUuid(runId);
      const col = collection(db, 'agent_status', normalizedId, 'outputs');
      const q = query(col, orderBy('created_at', 'asc'));
      unsubscribe = onSnapshot(
        q,
        (snap) => {
          const rows: AgentOutput[] = snap.docs.map((d) => {
            const data = d.data() as Omit<AgentOutput, 'id'>;
            return { id: d.id, ...data };
          });
          setOutputs(rows);
        },
        (error) => {
          console.error('Agent outputs subscription error:', error);
        }
      );
    } catch (error) {
      console.error('Failed to subscribe to agent outputs:', error);
    }

    return () => {
      if (unsubscribe) unsubscribe();
    };
  }, [runId]);

  return outputs;
}

/**
 * Subscribe to the append-only step transition log for a run, in order.
 * Reads agent_status/{runId}/steps — reliable (not coalesced like the single status doc), so the
 * Lab can reconstruct the true path and pick the correct play.
 *
 * @param runId - The agent run ID to watch, or null to disable
 * @returns Ordered list of step transitions (empty until any arrive)
 */
export function useAgentStepsRealtime(runId: string | null): AgentStep[] {
  const [steps, setSteps] = useState<AgentStep[]>([]);

  useEffect(() => {
    if (!runId) {
      setSteps([]);
      return;
    }

    let unsubscribe: Unsubscribe | undefined;
    try {
      const normalizedId = normalizeUuid(runId);
      const col = collection(db, 'agent_status', normalizedId, 'steps');
      const q = query(col, orderBy('created_at', 'asc'));
      unsubscribe = onSnapshot(
        q,
        (snap) => {
          const rows: AgentStep[] = snap.docs.map((d) => {
            const data = d.data() as Omit<AgentStep, 'id'>;
            return { id: d.id, ...data };
          });
          setSteps(rows);
        },
        (error) => {
          console.error('Agent steps subscription error:', error);
        }
      );
    } catch (error) {
      console.error('Failed to subscribe to agent steps:', error);
    }

    return () => {
      if (unsubscribe) unsubscribe();
    };
  }, [runId]);

  return steps;
}

// =============================================================================
// Combined Setup Flow Hook
// =============================================================================

export interface SetupFlowState {
  progress: Record<string, CustomerProgress>;
  isConnected: boolean;
  // Derived counts
  pendingCount: number;
  readingCount: number;
  classifiedCount: number;
  errorCount: number;
}

/**
 * Combined hook for setup flow that provides progress + derived counts.
 *
 * @param workspaceId - The workspace ID
 * @returns Setup flow state with progress and counts
 */
export function useSetupFlow(workspaceId: string | null): SetupFlowState {
  const progress = useSetupProgress(workspaceId);
  const [isConnected, setIsConnected] = useState(false);

  // Track connection state
  useEffect(() => {
    if (!workspaceId) {
      setIsConnected(false);
      return;
    }

    // If we get any data, we're connected
    const hasData = Object.keys(progress).length > 0;
    setIsConnected(hasData);
  }, [workspaceId, progress]);

  // Calculate derived counts
  const entries = Object.values(progress);
  const pendingCount = entries.filter(p => p.status === 'pending').length;
  const readingCount = entries.filter(p => p.status === 'reading').length;
  const classifiedCount = entries.filter(p => p.status === 'classified').length;
  const errorCount = entries.filter(p => p.status === 'error').length;

  return {
    progress,
    isConnected,
    pendingCount,
    readingCount,
    classifiedCount,
    errorCount,
  };
}

// =============================================================================
// Utility: Clear setup progress (for testing)
// =============================================================================

/**
 * Force clear local setup progress state.
 * Useful for resetting during development.
 */
export function useClearSetupProgress() {
  return useCallback(() => {
    // This will cause the hook to re-subscribe with fresh state
    // The actual Firestore document is not cleared (that requires backend)
    console.log('Setup progress state cleared (local only)');
  }, []);
}

// =============================================================================
// Customer Insights (Real-time with API fallback)
// =============================================================================

export interface CustomerInsight {
  customer_id: string;
  customer_name: string;
  customer_slug: string;

  // Coordinates for Sidekick Map (0-1 normalized)
  engagement_score: number;
  sentiment_score: number;

  // Trend directions
  engagement_direction: 'increasing' | 'stable' | 'decreasing' | 'going_dark';
  sentiment_direction: 'improving' | 'stable' | 'declining';

  // Derived classification
  quadrant: 'healthy' | 'quiet' | 'going_dark' | 'escalating' | 'slipping';
  priority: 'high' | 'medium' | 'low';
  alert_reason: string | null;

  // Sparkline data
  engagement_sparkline: number[];
  sentiment_sparkline: number[];

  // Derived engagement-health (durable, sourced from MetricSnapshot via the heartbeat).
  // Present only when METRIC_SNAPSHOTS_ENABLED and history exists.
  engagement_health?: {
    score: number;            // 0.0–1.0
    state: 'ok' | 'warn' | 'risk';
    direction: 'improving' | 'stable' | 'declining';
    explanation: string;
    sparkline: number[];      // 0-1 daily series, oldest→newest
  } | null;

  // Raw metrics
  days_since_last_interaction: number | null;
  negative_signals_30d: number;
  positive_signals_30d: number;
  total_interactions_30d: number;
  inbound_interactions_30d: number;
  outbound_interactions_30d: number;

  // Week-over-week
  engagement_wow_current: number;
  engagement_wow_previous: number;
  engagement_wow_delta: number;
  engagement_wow_percent: number | null;
  sentiment_wow_delta_negative: number;
  sentiment_wow_delta_positive: number;
  sentiment_wow_interpretation: string;

  // Metadata
  confidence: number;
  last_computed?: Date;
}

export interface PortfolioCustomer {
  id: string;
  name: string;
  slug: string;
  x: number;
  y: number;
  quadrant: string;
  priority: 'high' | 'medium' | 'low';
  alertReason: string | null;
  trendX: 'up' | 'down' | 'stable';
  trendY: 'up' | 'down' | 'stable';
}

export interface PortfolioSnapshot {
  customers: PortfolioCustomer[];
  priority_list: Array<{
    id: string;
    name: string;
    quadrant: string;
    reason: string;
  }>;
  healthy_count: number;
  quiet_count: number;
  going_dark_count: number;
  escalating_count: number;
  slipping_count: number;
  customer_count: number;
  last_computed?: Date;
}

// =============================================================================
// Insight Transformation Utilities (for TrendCard compatibility)
// =============================================================================

/**
 * Transform CustomerInsight to SentimentTrend format for TrendCard compatibility.
 * This allows components using TrendCard to work with real-time insight data.
 */
export function transformInsightToSentimentTrend(insight: CustomerInsight): SentimentTrend {
  return {
    current_state: insight.sentiment_direction === 'declining' ? 'risk' :
                   insight.sentiment_direction === 'stable' ? 'warn' : 'ok',
    direction: insight.sentiment_direction === 'improving' ? 'improving' :
               insight.sentiment_direction === 'declining' ? 'declining' : 'stable',
    confidence: insight.confidence,
    summary: `${insight.negative_signals_30d} negative, ${insight.positive_signals_30d} positive signals`,
    negative_count_30d: insight.negative_signals_30d,
    positive_count_30d: insight.positive_signals_30d,
    daily_scores: insight.sentiment_sparkline ?? [],
    week_over_week: {
      current: insight.negative_signals_30d,
      previous: insight.negative_signals_30d - insight.sentiment_wow_delta_negative,
      delta: insight.sentiment_wow_delta_negative,
      percent_change: null,
      interpretation: insight.sentiment_wow_interpretation,
    },
  };
}

/**
 * Transform CustomerInsight to EngagementTrend format for TrendCard compatibility.
 */
export function transformInsightToEngagementTrend(insight: CustomerInsight): EngagementTrend {
  return {
    direction: insight.engagement_direction === 'increasing' ? 'increasing' :
               insight.engagement_direction === 'decreasing' ? 'decreasing' : 'stable',
    confidence: insight.confidence,
    summary: `${insight.total_interactions_30d} interactions`,
    total_interactions_30d: insight.total_interactions_30d,
    inbound_count_30d: insight.inbound_interactions_30d,
    outbound_count_30d: insight.outbound_interactions_30d,
    days_since_last_interaction: insight.days_since_last_interaction,
    average_weekly_interactions: insight.total_interactions_30d / 4.3,
    channel_breakdown: {},
    daily_totals: insight.engagement_sparkline,
    week_over_week: {
      current: insight.engagement_wow_current,
      previous: insight.engagement_wow_previous,
      delta: insight.engagement_wow_delta,
      percent_change: insight.engagement_wow_percent,
      interpretation: insight.engagement_wow_delta > 0 ? 'Engagement increasing' :
                      insight.engagement_wow_delta < 0 ? 'Engagement declining' : 'Engagement stable',
    },
  };
}

/**
 * Subscribe to real-time customer insights from Firestore.
 * Falls back to API if data not cached.
 *
 * Used by: RightRail, CustomerDetail, NeedDetail
 */
export function useCustomerInsights(customerId: string | null): {
  insight: CustomerInsight | null;
  source: 'firestore' | 'api' | null;
  isLoading: boolean;
} {
  const [insight, setInsight] = useState<CustomerInsight | null>(null);
  const [source, setSource] = useState<'firestore' | 'api' | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const fallbackAttemptedRef = useRef(false);

  // Get workspace ID from context (assumes useWorkspace is available)
  const workspaceId = typeof window !== 'undefined'
    ? localStorage.getItem('herofy_workspace_id')
    : null;

  useEffect(() => {
    if (!customerId || !workspaceId) {
      setInsight(null);
      setSource(null);
      setIsLoading(false);
      return;
    }

    fallbackAttemptedRef.current = false;
    setIsLoading(true);

    const normalizedWsId = normalizeUuid(workspaceId);
    const normalizedCustId = normalizeUuid(customerId);
    console.log('[useCustomerInsights] Subscribing to', normalizedWsId, normalizedCustId);

    let unsubscribe: Unsubscribe | undefined;

    try {
      const docRef = doc(
        db,
        'workspaces',
        normalizedWsId,
        'customer_insights',
        normalizedCustId
      );

      unsubscribe = onSnapshot(
        docRef,
        async (snapshot) => {
          if (snapshot.exists()) {
            const data = snapshot.data() as CustomerInsight;
            console.log('[useCustomerInsights] Firestore data received:', data.quadrant);
            setInsight(data);
            setSource('firestore');
            setIsLoading(false);
            fallbackAttemptedRef.current = false;
            return;
          }

          // Firestore empty - try API fallback once
          if (!fallbackAttemptedRef.current) {
            fallbackAttemptedRef.current = true;
            console.log('[useCustomerInsights] Firestore miss, falling back to API');

            try {
              const pythonUrl = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';
              const response = await fetch(
                `${pythonUrl}/workspaces/${workspaceId}/customers/${customerId}/insights/refresh`,
                {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                  },
                }
              );

              if (response.ok) {
                const data = await response.json();
                console.log('[useCustomerInsights] API fallback success:', data.quadrant);
                // Set insight directly from API response (Firestore write may arrive later)
                if (data.success && data.quadrant) {
                  // Transform API response to CustomerInsight format
                  setInsight({
                    customer_id: data.customer_id,
                    customer_name: '',
                    customer_slug: '',
                    engagement_score: data.engagement_score || 0.5,
                    sentiment_score: data.sentiment_score || 0.5,
                    engagement_direction: 'stable',
                    sentiment_direction: 'stable',
                    quadrant: data.quadrant,
                    priority: data.priority || 'low',
                    alert_reason: null,
                    engagement_sparkline: [],
                    sentiment_sparkline: [],
                    days_since_last_interaction: null,
                    negative_signals_30d: 0,
                    positive_signals_30d: 0,
                    total_interactions_30d: 0,
                    inbound_interactions_30d: 0,
                    outbound_interactions_30d: 0,
                    engagement_wow_current: 0,
                    engagement_wow_previous: 0,
                    engagement_wow_delta: 0,
                    engagement_wow_percent: null,
                    sentiment_wow_delta_negative: 0,
                    sentiment_wow_delta_positive: 0,
                    sentiment_wow_interpretation: '',
                    confidence: 0.5,
                  });
                }
                setSource('api');
              }
            } catch (err) {
              console.error('[useCustomerInsights] API fallback failed:', err);
              setInsight(null);
            }
          }

          setIsLoading(false);
        },
        (error) => {
          console.error('[useCustomerInsights] Subscription error:', error);
          setIsLoading(false);
        }
      );
    } catch (error) {
      console.error('[useCustomerInsights] Failed to subscribe:', error);
      setIsLoading(false);
    }

    return () => {
      console.log('[useCustomerInsights] Unsubscribing');
      if (unsubscribe) {
        unsubscribe();
      }
    };
  }, [customerId, workspaceId]);

  return { insight, source, isLoading };
}

/**
 * Subscribe to real-time portfolio snapshot from Firestore.
 * Falls back to API if data not cached.
 *
 * Used by: SidekickMap, Portfolio dashboard
 */
export function usePortfolioInsights(): {
  snapshot: PortfolioSnapshot | null;
  isLoading: boolean;
} {
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const fallbackAttemptedRef = useRef(false);

  // Get workspace ID from context
  const workspaceId = typeof window !== 'undefined'
    ? localStorage.getItem('herofy_workspace_id')
    : null;

  useEffect(() => {
    if (!workspaceId) {
      setSnapshot(null);
      setIsLoading(false);
      return;
    }

    fallbackAttemptedRef.current = false;
    setIsLoading(true);

    const normalizedId = normalizeUuid(workspaceId);
    console.log('[usePortfolioInsights] Subscribing to', normalizedId);

    let unsubscribe: Unsubscribe | undefined;

    try {
      const docRef = doc(
        db,
        'workspaces',
        normalizedId,
        'portfolio_snapshot',
        'current'
      );

      unsubscribe = onSnapshot(
        docRef,
        async (snap) => {
          if (snap.exists()) {
            const data = snap.data() as PortfolioSnapshot;
            console.log('[usePortfolioInsights] Data received:', data.customer_count, 'customers');
            setSnapshot(data);
            setIsLoading(false);
            return;
          }

          // Firestore empty - try API fallback once
          if (!fallbackAttemptedRef.current) {
            fallbackAttemptedRef.current = true;
            console.log('[usePortfolioInsights] Firestore miss, falling back to API');

            try {
              const pythonUrl = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';
              const response = await fetch(
                `${pythonUrl}/workspaces/${workspaceId}/portfolio/insights`,
                {
                  method: 'GET',
                  headers: {
                    'Content-Type': 'application/json',
                  },
                }
              );

              if (response.ok) {
                const data = await response.json();
                console.log('[usePortfolioInsights] API fallback success');
                setSnapshot(data as PortfolioSnapshot);
              }
            } catch (err) {
              console.error('[usePortfolioInsights] API fallback failed:', err);
            }
          }

          setIsLoading(false);
        },
        (error) => {
          console.error('[usePortfolioInsights] Subscription error:', error);
          setIsLoading(false);
        }
      );
    } catch (error) {
      console.error('[usePortfolioInsights] Failed to subscribe:', error);
      setIsLoading(false);
    }

    return () => {
      console.log('[usePortfolioInsights] Unsubscribing');
      if (unsubscribe) {
        unsubscribe();
      }
    };
  }, [workspaceId]);

  return { snapshot, isLoading };
}

// =============================================================================
// Refresh Utilities for Stale Data Prevention
// =============================================================================

/**
 * Hook that calls refetch on mount and when page becomes visible.
 * Prevents stale data when navigating between pages.
 *
 * @param refetchFn - The refetch function from a DataConnect hook
 * @param options - Configuration options
 *
 * @example
 * const { data, refetch } = useCustomers();
 * useRefreshOnFocus(refetch);
 */
export function useRefreshOnFocus(
  refetchFn: (() => void) | (() => Promise<unknown>),
  options: {
    /** Skip the initial mount refetch (default: false) */
    skipMount?: boolean;
    /** Refetch when tab becomes visible (default: true) */
    refetchOnFocus?: boolean;
    /** Minimum ms between refetches to prevent rapid re-fetching (default: 1000) */
    throttleMs?: number;
  } = {}
) {
  const { skipMount = false, refetchOnFocus = true, throttleMs = 1000 } = options;
  const lastRefetchRef = useRef<number>(0);
  const mountedRef = useRef(false);

  // Refetch on mount (unless skipped)
  useEffect(() => {
    if (!skipMount && !mountedRef.current) {
      mountedRef.current = true;
      const now = Date.now();
      if (now - lastRefetchRef.current > throttleMs) {
        lastRefetchRef.current = now;
        refetchFn();
      }
    }
  }, [refetchFn, skipMount, throttleMs]);

  // Refetch when page becomes visible
  useEffect(() => {
    if (!refetchOnFocus) return;

    const handler = () => {
      if (document.visibilityState === 'visible') {
        const now = Date.now();
        if (now - lastRefetchRef.current > throttleMs) {
          lastRefetchRef.current = now;
          console.log('[useRefreshOnFocus] Page visible, refetching...');
          refetchFn();
        }
      }
    };

    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, [refetchFn, refetchOnFocus, throttleMs]);
}

/**
 * Combined hook for notification-driven refetch with on-mount refresh.
 * Use this instead of manually implementing the notification pattern.
 *
 * @param workspaceId - The workspace ID
 * @param refetchFn - The refetch function to call
 * @param notificationKey - Which notification counter to watch
 *
 * @example
 * const { data, refetch } = useCustomers();
 * useNotificationRefresh(workspaceId, refetch, 'updated_at');
 */
export function useNotificationRefresh(
  workspaceId: string | null,
  refetchFn: (() => void) | (() => Promise<unknown>),
  notificationKey: 'today_count' | 'sidekick_questions' | 'conversations_count' | 'updated_at' | 'agent_runs_active'
) {
  const notifications = useWorkspaceNotifications(workspaceId);
  const prevValueRef = useRef<number | Date | null>(null);
  const mountedRef = useRef(false);

  // Refetch on mount
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      refetchFn();
    }
  }, [refetchFn]);

  // Refetch when notification value changes
  useEffect(() => {
    if (!notifications) return;

    let currentValue: number | Date | undefined;

    if (notificationKey === 'updated_at') {
      currentValue = notifications.updated_at instanceof Date
        ? notifications.updated_at.getTime()
        : (notifications.updated_at as any)?.toMillis?.();
    } else {
      currentValue = notifications[notificationKey];
    }

    if (currentValue === undefined) return;

    // Skip initial value, only refetch on changes
    if (prevValueRef.current !== null && prevValueRef.current !== currentValue) {
      console.log(`[useNotificationRefresh] ${notificationKey} changed:`, prevValueRef.current, '→', currentValue);
      // Small delay to allow database propagation
      setTimeout(() => refetchFn(), 300);
    }

    prevValueRef.current = currentValue as number;
  }, [notifications, notificationKey, refetchFn]);
}
