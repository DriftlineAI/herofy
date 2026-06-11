// Adapter hooks for Firebase Data Connect
// These wrap the generated hooks and transform data to match the existing API format

import { useState, useEffect, useCallback, useMemo } from 'react';
import { getAuth } from 'firebase/auth';
import { useWorkspace } from './workspace';
import { dataConnect } from './firebase';  // Import the emulator-connected instance
import { unescapeText } from './utils';
import { deriveGrowth, initialsOf, stakeholderTone } from './renewals';
import type { AgentQuestion, Attachment, PlanMilestone, LinkedPage, CreateCustomerInput } from './api';

// Python backend URL for agent/AI operations
const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

/**
 * Make an authenticated request to the Python backend.
 * Includes Firebase ID token for auth.
 */
async function pythonRequest<T>(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  const auth = getAuth();
  await auth.authStateReady();
  const user = auth.currentUser;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (user) {
    const token = await user.getIdToken();
    headers['Authorization'] = `Bearer ${token}`;
    // Firebase Hosting overwrites Authorization when proxying to authenticated
    // Cloud Run services, so duplicate the token in a header it leaves alone.
    headers['X-Firebase-ID-Token'] = token;
  }

  const response = await fetch(`${PYTHON_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new Error(error.message || error.error?.message || 'Request failed');
  }

  return response.json();
}
import { DEFAULT_HANDBOOK_DOCS, DEFAULT_PLAYBOOKS, DEFAULT_VOICE_DOCS } from './workspace-defaults';
import {
  createHandbookDoc,
  createHandbookDocWithId,
  createPlaybook,
  createPlaybookMilestone,
  createPlaybookWithId,
  createPlaybookMilestoneWithId,
  getPlaybooks,
  getHandbook,
  getVoiceDocs,
  getWaitingRuns,
  failAgentRun,
  getTodayQueue,
  resolveNeed,
  getAgentRun,
} from '@/dataconnect-generated';
import { executeQuery } from 'firebase/data-connect';
import {
  getTodayQueueRef,
  getNeedRef,
  getSidekickAskingItemsRef,
  getThreadsRef,
  getThreadRef,
  getDraftResponseRef,
  getRiskBriefsWithStepsRef,
  getSidekickItemsRef,
  getWaitingRunsRef,
  getConversationNeedsRef,
  getResolvedConversationNeedsRef,
  getSidekickQuestionNeedsRef,
  listAgentRunsForWorkspaceRef,
} from '@/dataconnect-generated';
import {
  useGetCustomersPublic,
  useGetCustomer,
  useGetCustomerPublic,
  useGetTodayQueue,
  useGetTodayWorklist,
  useGetThreads,
  useGetThread,
  useGetMeetings,
  useGetMeeting,
  useGetHandoffs,
  useGetHandoff,
  useGetPlan,
  useGetHandbook,
  useGetHandbookDoc,
  useGetPlaybooks,
  useGetPlaybook,
  useGetAgentRun,
  useGetWaitingRuns,
  useGetRunsWithQuestions,
  useGetDraftResponse,
  useGetWorkspace,
  useCreateWorkspace as useCreateWorkspaceDC,
  useUpdateWorkspace as useUpdateWorkspaceDC,
  useCreateCustomer as useCreateCustomerDC,
  useUpdateCustomer as useUpdateCustomerDC,
  useCreateStakeholderPublic,
  useUpdateStakeholder as useUpdateStakeholderDC,
  useDeleteStakeholder as useDeleteStakeholderDC,
  useCreateMilestonePublic,
  useUpdateMilestone as useUpdateMilestoneDC,
  useDeleteMilestone as useDeleteMilestoneDC,
  useCreateGoalPublic,
  useUpdateGoal as useUpdateGoalDC,
  useDeleteGoal as useDeleteGoalDC,
  useSnoozeNeed as useSnoozeNeedDC,
  useResolveNeed as useResolveNeedDC,
  useUpdateRiskPlayStep as useUpdateRiskPlayStepDC,
  useUpdateNeedStatus as useUpdateNeedStatusDC,
  useCreateMeeting as useCreateMeetingDC,
  useUpdateMeeting as useUpdateMeetingDC,
  useApprovePlan as useApprovePlanDC,
  useRejectPlan as useRejectPlanDC,
  useMarkPlanEdited as useMarkPlanEditedDC,
  useUpdateHandbookDoc as useUpdateHandbookDocDC,
  useSubmitAgentAnswers as useSubmitAgentAnswersDC,
  useCreateThread as useCreateThreadDC,
  useUpdateThread as useUpdateThreadDC,
  useResolveThread as useResolveThreadDC,
  useCreateInteraction as useCreateInteractionDC,
  useUpdateHandoffStatus as useUpdateHandoffStatusDC,
  useApproveDraftResponse as useApproveDraftResponseDC,
  useDiscardDraftResponse as useDiscardDraftResponseDC,
  useCreatePlaybook as useCreatePlaybookDC,
  useUpdatePlaybook as useUpdatePlaybookDC,
  useDeletePlaybook as useDeletePlaybookDC,
  useCreatePlaybookMilestone as useCreatePlaybookMilestoneDC,
  useUpdatePlaybookMilestone as useUpdatePlaybookMilestoneDC,
  useDeletePlaybookMilestone as useDeletePlaybookMilestoneDC,
  // Team management (available after SDK regeneration)
  useGetPendingJoinRequests,
  useApproveJoinRequest as useApproveJoinRequestDC,
  useRejectJoinRequest as useRejectJoinRequestDC,
  useAddWorkspaceMember,
  useGetConversationNeeds,
  useGetResolvedConversationNeeds,
  useGetOrphanThreads,
  useGetQuarantinedThreads,
  useGetNeed,
  // Conversation contract: huddles + fan-out needs on a thread
  useGetThreadHuddles,
  useGetHuddle,
  useGetNeedsForThread,
  useCreateHuddle as useCreateHuddleDC,
  usePostHuddleMessage as usePostHuddleMessageDC,
  useResolveHuddle as useResolveHuddleDC,
  useGetAgentRunForBlockingNeed,
  useGetCustomerInteractions,
  useGetCustomerThreads,
  useGetSidekickAlert,
  useGetSidekickItems,
  useGetSidekickUnansweredCount,
  useGetSidekickAskingItems,
  useGetSidekickQuestionNeeds,
  useGetVoiceDocs,
  useGetVoiceDoc,
  // Playbook Catalog
  useGetPlaybookTemplates,
  useGetMilestoneBlocks,
  useAdoptPlaybookTemplate,
  useCreatePlaybookMilestoneFromBlock,
  // Health & Observations
  useGetCustomerHealth,
  useUpdateCustomerHealthUser,
  useGetGoalObservations,
  useGetCustomerGoalObservations,
  useGetCustomerHandoffWithPlan,
  useGetCustomerPlans,
  // Goal-centric architecture
  useGetGoalsWithMilestones,
  useGetCustomerProgressVectors,
  useGetCustomerStrategy,
  useGetRiskBriefsWithSteps,
  // Agent run queries (for Live Ops rail)
  useListAgentRunsForWorkspace,
  // Renewals — pipeline list + adaptive workspace
  useGetRenewalsPipeline,
  useGetRenewalWorkspace,
  useSetCustomerRenewalDate as useSetCustomerRenewalDateDC,
} from '@/dataconnect-generated/react';

import { WorkspaceRole, AgentStatus } from '@/dataconnect-generated';
import { useAuth } from './auth';

import type {
  GetCustomersPublicData,
  GetCustomerData,
  GetTodayQueueData,
  GetThreadsData,
  GetThreadData,
  GetMeetingsData,
  GetMeetingData,
  GetHandoffsData,
  GetHandoffData,
  GetPlanData,
  GetHandbookData,
  GetHandbookDocData,
  GetPlaybooksData,
  GetAgentRunData,
  GetWaitingRunsData,
  GetDraftResponseData,
  GetWorkspaceData,
  CustomerLifecycle,
  SignalKind,
  SignalState,
  BlastRadius,
  OwnerSide,
  MilestoneStatus,
  HandoffStatus,
  HandbookDocKind,
} from '@/dataconnect-generated';

import { ThreadStatus } from '@/dataconnect-generated';

import type {
  CustomerWithSignals,
  Signal,
  CustomerLifecycle as ApiCustomerLifecycle,
  SignalState as ApiSignalState,
} from './api';

// ============================================================================
// Data Transformers
// ============================================================================

/**
 * Infer the UI question type from question content when backend sends invalid type.
 * This handles cases where the LLM sends semantic types like "clarification" instead
 * of UI types like "freeform" or "pick_one".
 *
 * IMPORTANT: Be conservative - prefer freeform over yes_no to avoid misclassification.
 * Users can always type in freeform, but yes/no is limiting.
 */
function inferQuestionType(q: any, options: any[]): string {
  const questionText = (q.question || q.text || '').toLowerCase();
  const field = (q.field || '').toLowerCase();

  // If options are provided, it's a selection question
  if (options && options.length > 0) {
    // Check for multi-select indicators in the question
    const multiIndicators = ['which', 'what are', 'select all', 'choose', 'pick'];
    if (multiIndicators.some(ind => questionText.includes(ind)) && options.length > 2) {
      return 'pick_many';
    }
    return 'pick_one';
  }

  // CONSERVATIVE yes/no detection - only match very specific patterns
  // Questions like "Does X have Y?" or "Is X required?" are yes/no
  // Questions like "How will we know X?" or "What are the goals?" are NOT
  const yesNoPatterns = [
    // "Does [subject] have/need/require [thing]?" - very specific
    /^does\s+\w+\s+(have|need|require|support|use|want)/,
    // "Is [thing] required/needed/enabled?" - checking a boolean state
    /^is\s+\w+\s+(required|needed|enabled|disabled|available|supported|necessary)\??$/,
    // "Do they/you need [specific thing]?" - asking about requirement
    /^do\s+(they|you|we)\s+(need|require|have|want)\s+\w+/,
    // "Are there any [things]?" - existence check
    /^are\s+there\s+(any|existing)/,
    // "Will [thing] be [state]?" - NOT "will we know" type questions
    /^will\s+(this|it|the\s+\w+)\s+be\s+(required|needed|used)/,
  ];

  for (const pattern of yesNoPatterns) {
    if (pattern.test(questionText)) {
      return 'yes_no';
    }
  }

  // Check field name hints - only very specific boolean field names
  const booleanFields = ['requires_sso', 'needs_integration', 'has_sso', 'sso_required', 'integration_required'];
  if (booleanFields.includes(field)) {
    return 'yes_no';
  }

  // Default to freeform - safer for open-ended questions
  return 'freeform';
}

/**
 * Normalize an agent question from various backend formats.
 * Handles variations in field names, structure, and missing data.
 * Always returns a valid AgentQuestion that the UI can render.
 */
function normalizeAgentQuestion(q: any, index: number): AgentQuestion {
  // Handle various ways the question type might be specified
  // Priority: structured_type > ui_type > question_type > type > 'freeform'
  const rawType = q.structured_type || q.ui_type || q.question_type || q.type || 'freeform';

  // Normalize type to lowercase and handle common variations
  let questionType = String(rawType).toLowerCase()
    .replace(/[-_\s]/g, '_')  // Normalize separators
    .replace('pick_1', 'pick_one')
    .replace('single_select', 'pick_one')
    .replace('multi_select', 'pick_many')
    .replace('boolean', 'yes_no')
    .replace('text', 'freeform')
    .replace('textarea', 'freeform');

  // Known valid types
  const validTypes = ['freeform', 'pick_one', 'pick_many', 'pick_person', 'slider', 'yes_no', 'date'];

  // Get options early so we can use them for inference
  const options = q.options || q.metadata?.options || q.choices || q.metadata?.choices || [];

  // If type is invalid (like "clarification", "missing_data"), infer from content
  const finalType = validTypes.includes(questionType)
    ? questionType
    : inferQuestionType(q, options);

  // Build normalized metadata by checking multiple possible field names
  const metadata: Record<string, any> = {
    ...q.metadata,
    options: options.length > 0 ? options : undefined,
    people: q.people || q.metadata?.people,
    // Boolean flags
    allow_decide: q.allow_decide ?? q.allowDecide ?? q.metadata?.allow_decide ?? q.metadata?.allowDecide,
    allow_other: q.allow_other ?? q.allowOther ?? q.metadata?.allow_other ?? q.metadata?.allowOther,
    multiline: q.multiline ?? q.metadata?.multiline ?? (finalType === 'freeform' && q.long),
    // Labels
    decide_label: q.decide_label || q.decideLabel || q.metadata?.decide_label || q.metadata?.decideLabel,
    yes_label: q.yes_label || q.yesLabel || q.metadata?.yes_label || q.metadata?.yesLabel,
    no_label: q.no_label || q.noLabel || q.metadata?.no_label || q.metadata?.noLabel,
    label_low: q.label_low || q.labelLow || q.metadata?.label_low || q.metadata?.labelLow,
    label_high: q.label_high || q.labelHigh || q.metadata?.label_high || q.metadata?.labelHigh,
    // Numeric constraints
    min: q.min ?? q.metadata?.min,
    max: q.max ?? q.metadata?.max,
    default: q.default ?? q.metadata?.default ?? q.defaultValue ?? q.metadata?.defaultValue,
    step: q.step ?? q.metadata?.step,
    // Date constraints
    min_date: q.min_date || q.minDate || q.metadata?.min_date || q.metadata?.minDate,
    max_date: q.max_date || q.maxDate || q.metadata?.max_date || q.metadata?.maxDate,
    default_date: q.default_date || q.defaultDate || q.metadata?.default_date || q.metadata?.defaultDate,
    // Selection constraints
    min_selections: q.min_selections ?? q.minSelections ?? q.metadata?.min_selections ?? q.metadata?.minSelections,
    max_selections: q.max_selections ?? q.maxSelections ?? q.metadata?.max_selections ?? q.metadata?.maxSelections,
  };

  // Clean undefined values from metadata
  Object.keys(metadata).forEach(key => {
    if (metadata[key] === undefined) delete metadata[key];
  });

  return {
    id: q.id || q.field || `q${index}`,
    text: unescapeText(q.text || q.question || q.label || q.title || 'Question'),
    context: unescapeText(q.context || q.description || q.hint || ''),
    field: q.field || q.name || q.id,
    question_type: finalType as any,
    required: q.required ?? true,
    placeholder: q.placeholder || q.metadata?.placeholder,
    metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
  };
}

// Transform customer from Data Connect format to API format
function transformCustomer(dc: GetCustomersPublicData['customers'][number]): CustomerWithSignals {
  return {
    id: dc.id,
    workspace_id: '', // Not included in list query
    name: dc.name,
    slug: dc.slug,
    one_liner: dc.oneLiner ?? null,
    tier: dc.tier ?? null,
    arr_cents: dc.arrCents ? parseInt(dc.arrCents, 10) : null,
    lifecycle: dc.lifecycle as ApiCustomerLifecycle,
    days_to_renewal: dc.daysToRenewal ?? null,
    onboarding_day_current: dc.onboardingDayCurrent ?? null,
    onboarding_day_total: dc.onboardingDayTotal ?? null,
    enrichment_status: (dc as any).enrichmentStatus ?? null,
    external_source: (dc as any).externalSource ?? null,
    external_id: (dc as any).externalId ?? null,
    raw_notes: null, // Not included in list query
    linked_pages: [], // Not included in list query
    // AI Classification fields
    aiClassificationGroup: dc.aiClassificationGroup ?? null,
    aiClassificationConfidence: dc.aiClassificationConfidence ?? null,
    aiClassificationReasoning: dc.aiClassificationReasoning ?? null,
    aiClassificationWhatIKnow: dc.aiClassificationWhatIKnow ?? null,
    aiClassificationUncertainties: dc.aiClassificationUncertainties ?? null,
    aiClassificationAt: dc.aiClassificationAt ?? null,
    created_at: dc.createdAt,
    updated_at: dc.createdAt, // Use createdAt as fallback
    signals: dc.signals_on_customer.map((s, index) => ({
      id: `${dc.id}-${s.kind}-${index}`, // Generate a unique ID
      customer_id: dc.id,
      kind: s.kind as any,
      state: s.state as ApiSignalState,
      sentence: s.sentence ?? null,
      evidence_text: null,
      next_action: null,
    })),
  };
}

// ============================================================================
// Query Hooks
// ============================================================================

export function useCustomers() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  // Use the SDK hook with our emulator-connected dataConnect instance
  const query = useGetCustomersPublic(
    dataConnect,
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform the data - memoize to prevent infinite re-renders
  const transformedData = useMemo(() => {
    if (!query.data) return undefined;

    return {
      customers: query.data.customers.map(transformCustomer),
      total: query.data.customers.length,
      lifecycle_counts: query.data.customers.reduce((acc, c) => {
        acc[c.lifecycle] = (acc[c.lifecycle] || 0) + 1;
        return acc;
      }, {} as Record<string, number>),
    };
  }, [query.data]);

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useCustomer(customerId: string) {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  // Use USER query to include health tracking fields
  const query = useGetCustomer(
    { id: customerId },
    { enabled: !!customerId && !!workspaceId && !wsLoading }
  );

  // Transform to match CustomerDetailResponse - memoize to prevent infinite re-renders
  const transformedData = useMemo(() => {
    if (!query.data?.customer) return undefined;

    return {
      customer: {
        id: query.data.customer.id,
        workspace_id: workspaceId || '',
        name: query.data.customer.name,
        slug: query.data.customer.slug,
        one_liner: query.data.customer.oneLiner || null,
        tier: query.data.customer.tier || null,
        arr_cents: query.data.customer.arrCents ? parseInt(query.data.customer.arrCents) : null,
        lifecycle: query.data.customer.lifecycle,
        days_to_renewal: query.data.customer.daysToRenewal || null,
        onboarding_day_current: query.data.customer.onboardingDayCurrent || null,
        onboarding_day_total: query.data.customer.onboardingDayTotal || null,
        renewal_readiness: query.data.customer.renewalReadiness || null,
        value_realization_text: query.data.customer.valueRealizationText || null,
        enrichment_status: query.data.customer.enrichmentStatus || null,
        raw_notes: query.data.customer.rawNotes || null,
        linked_pages: (() => {
          try { return JSON.parse(query.data.customer.linkedPages || '[]'); }
          catch { return []; }
        })(),
        adapted_from_playbook_id: query.data.customer.adaptedFromPlaybookId || null,
        client_signed_date: query.data.customer.clientSignedDate || null,
        relationship_health: query.data.customer.relationshipHealth || null,
        relationship_health_score: query.data.customer.relationshipHealthScore || null,
        relationship_health_updated_by: query.data.customer.relationshipHealthUpdatedBy || null,
        relationship_health_updated_at: query.data.customer.relationshipHealthUpdatedAt || null,
        relationship_health_reason: query.data.customer.relationshipHealthReason || null,
        created_at: query.data.customer.createdAt,
        updated_at: query.data.customer.updatedAt,
      },
      stakeholders: (query.data.customer.stakeholders_on_customer || []).map(s => ({
        id: s.id,
        customer_id: customerId,
        name: s.name,
        email: s.email || null,
        role: s.role || null,
        status: s.status,
        sentiment_note: s.sentimentNote || null,
        last_interaction_at: s.lastInteractionAt || null,
      })),
      goals: (query.data.customer.goals_on_customer || []).map(g => ({
        id: g.id,
        customer_id: customerId,
        text: g.text,
        status: g.status,
        sort_order: g.sortOrder,
        source: g.source,
        source_type: g.sourceType,
        source_date: g.sourceDate,
        source_interaction_id: g.sourceInteractionId || null,
        source_thread_id: g.sourceThreadId || null,
        observations: (g.goalObservations_on_goal || []).map(obs => ({
          id: obs.id,
          text: obs.text,
          confidence: obs.confidence,
          source_type: obs.sourceType,
          observed_at: obs.observedAt,
          source_interaction: obs.sourceInteraction ? {
            id: obs.sourceInteraction.id,
            sender_name: obs.sourceInteraction.senderName || null,
            occurred_at: obs.sourceInteraction.occurredAt,
          } : null,
        })),
      })),
      signals: (query.data.customer.signals_on_customer || []).map(s => ({
        id: s.id,
        customer_id: customerId,
        kind: s.kind,
        state: s.state,
        sentence: s.sentence || null,
        evidence_text: s.evidenceText || null,
        next_action: s.nextAction || null,
        generated_at: s.generatedAt,
      })),
      milestones: (query.data.customer.milestones_on_customer || []).map(m => ({
        id: m.id,
        customer_id: customerId,
        title: m.title,
        owner_label: m.ownerLabel || null,
        owner_side: m.ownerSide,
        target_date: m.targetDate || null,
        status: m.status,
        description: m.description || null,
        blocked_reason: m.blockedReason || null,
        sort_order: m.sortOrder,
      })),
      open_needs: (query.data.customer.needs_on_customer || []).map((n: {
        id: string;
        type: string;
        headline: string;
        lede?: string | null;
        priorityRank: number;
        createdAt?: string | null;
      }) => ({
        id: n.id,
        type: n.type,
        headline: n.headline,
        lede: n.lede || null,
        priority_rank: n.priorityRank,
        created_at: n.createdAt || null,
      })),
    };
  }, [query.data, customerId, workspaceId]);

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useCustomerInteractions(customerId: string, limit: number = 100) {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetCustomerInteractions(
    {
      workspaceId: workspaceId || '',
      customerId: customerId,
      limit: limit
    },
    { enabled: !!customerId && !!workspaceId && !wsLoading }
  );

  return {
    ...query,
    isLoading: query.isLoading || wsLoading,
  };
}

// ============================================================================
// CUSTOMER HEALTH & GOAL OBSERVATIONS
// ============================================================================

export function useCustomerHealth(customerId: string) {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetCustomerHealth(
    { customerId },
    { enabled: !!customerId && !!workspaceId && !wsLoading }
  );

  return {
    ...query,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useUpdateCustomerHealth() {
  const mutation = useUpdateCustomerHealthUser();

  return {
    ...mutation,
    mutate: (data: {
      customerId: string;
      relationshipHealth: string;
      relationshipHealthScore: number;
      relationshipHealthReason: string;
    }) => {
      return mutation.mutate({
        customerId: data.customerId,
        relationshipHealth: data.relationshipHealth as any,
        relationshipHealthScore: data.relationshipHealthScore,
        relationshipHealthReason: data.relationshipHealthReason,
      });
    },
  };
}

// =============================================================================
// Customer Trends (Sentiment & Engagement)
// =============================================================================

export interface WeekOverWeekComparison {
  current: number;
  previous: number;
  delta: number;
  percent_change: number | null;
  interpretation: string;
}

export interface SentimentTrend {
  current_state: string | null;
  direction: 'improving' | 'stable' | 'declining';
  confidence: number;
  summary: string;
  negative_count_30d: number;
  positive_count_30d: number;
  week_over_week: WeekOverWeekComparison;
  // Gap-filled daily sentiment scores (0.0-1.0), oldest->newest, for sparkline.
  // Empty when no signals exist yet.
  daily_scores?: number[];
}

export interface EngagementTrend {
  direction: 'increasing' | 'stable' | 'decreasing' | 'going_dark';
  confidence: number;
  summary: string;
  total_interactions_30d: number;
  inbound_count_30d: number;
  outbound_count_30d: number;
  days_since_last_interaction: number | null;
  average_weekly_interactions: number;
  channel_breakdown: Record<string, number>;
  daily_totals: number[]; // For sparkline visualization
  week_over_week: WeekOverWeekComparison;
}

export interface CustomerTrends {
  success: boolean;
  customer_id: string;
  sentiment: SentimentTrend | null;
  engagement: EngagementTrend | null;
  message: string | null;
}

// Cache for customer trends data - prevents redundant API calls
// Key: "workspaceId:customerId:windowDays", Value: { data, timestamp }
const trendsCache = new Map<string, { data: CustomerTrends; timestamp: number }>();

// In-flight requests to prevent duplicate concurrent calls
const trendsInFlight = new Map<string, Promise<CustomerTrends>>();

// Cache duration: 60 seconds (trends don't change rapidly)
const TRENDS_CACHE_TTL_MS = 60 * 1000;

/**
 * Hook to fetch customer sentiment and engagement trends.
 *
 * Returns trend analysis over 30 days including:
 * - Sentiment direction (improving/stable/declining)
 * - Engagement direction (increasing/stable/decreasing/going_dark)
 * - Week-over-week comparisons
 * - Daily data for sparkline visualization
 *
 * Used by: RightRail, Today Queue, Customer Detail
 *
 * Features caching and request deduplication to prevent API spam.
 */
export function useCustomerTrends(customerId: string | null, windowDays: number = 30) {
  const { workspaceId, loading: wsLoading } = useWorkspace();
  const [data, setData] = useState<CustomerTrends | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Stable reference for the cache key
  const cacheKey = useMemo(() =>
    customerId && workspaceId ? `${workspaceId}:${customerId}:${windowDays}` : null,
    [customerId, workspaceId, windowDays]
  );

  const fetchTrends = useCallback(async (forceRefresh = false) => {
    if (!customerId || !workspaceId || wsLoading || !cacheKey) return;

    // Check cache first (unless force refresh)
    if (!forceRefresh) {
      const cached = trendsCache.get(cacheKey);
      if (cached && (Date.now() - cached.timestamp) < TRENDS_CACHE_TTL_MS) {
        // Cache hit - use cached data without API call
        setData(cached.data);
        return;
      }
    }

    // Check if request is already in flight for this key
    const inFlight = trendsInFlight.get(cacheKey);
    if (inFlight) {
      // Wait for existing request instead of making a new one
      try {
        const result = await inFlight;
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to fetch trends'));
      }
      return;
    }

    setIsLoading(true);
    setError(null);

    // Create the fetch promise and track it
    const fetchPromise = pythonRequest<CustomerTrends>(
      'GET',
      `/api/workspaces/${workspaceId}/customers/${customerId}/trends?window_days=${windowDays}`
    );
    trendsInFlight.set(cacheKey, fetchPromise);

    try {
      const result = await fetchPromise;

      // Cache the result
      trendsCache.set(cacheKey, { data: result, timestamp: Date.now() });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to fetch trends'));
      console.error('[useCustomerTrends] Error:', err);
    } finally {
      trendsInFlight.delete(cacheKey);
      setIsLoading(false);
    }
  }, [customerId, workspaceId, windowDays, wsLoading, cacheKey]);

  useEffect(() => {
    // On mount or when customer changes, check cache first
    if (cacheKey) {
      const cached = trendsCache.get(cacheKey);
      if (cached && (Date.now() - cached.timestamp) < TRENDS_CACHE_TTL_MS) {
        // Immediately set cached data without loading state
        setData(cached.data);
        return;
      }
    }

    fetchTrends();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey]); // Intentionally depend on stable cacheKey only - fetchTrends has guards

  return {
    data,
    isLoading: isLoading || wsLoading,
    error,
    refetch: () => fetchTrends(true), // Force refresh bypasses cache
  };
}

export function useGoalObservations(goalId: string) {
  const query = useGetGoalObservations(
    { goalId },
    { enabled: !!goalId }
  );

  return query;
}

export function useCustomerGoalObservations(customerId: string, status?: string) {
  const query = useGetCustomerGoalObservations(
    { customerId, status: status as any },
    { enabled: !!customerId }
  );

  return query;
}

export function useToday() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetTodayQueue(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Debug: log query results on every render
  console.log('[useToday] RENDER - workspaceId:', workspaceId, 'needs count:', query.data?.needs?.length, 'isLoading:', query.isLoading, 'isFetching:', query.isFetching);

  // Transform needs from Data Connect format to TodayQueueItem format
  const transformedData = query.data ? {
    items: query.data.needs.map(need => {
      const recommendation = need.needRecommendations_on_need[0];
      const agentRun = (need as any).agentRun;

      // Parse clarifying questions from agent run JSON
      let agentQuestions = null;
      if (agentRun?.clarifyingQuestions) {
        try {
          const parsed = JSON.parse(agentRun.clarifyingQuestions);
          agentQuestions = parsed.map((q: any, index: number) => ({
            id: q.field || `q${index}`,
            text: q.question,
            context: q.context,
            field_hint: q.field,
          }));
        } catch (e) {
          console.warn('Failed to parse clarifying questions:', e);
        }
      }

      return {
        id: need.id,
        workspace_id: workspaceId || '',
        customer_id: need.customer.id,
        type: need.type,
        headline: need.headline,
        lede: need.lede ?? null,
        priority_rank: need.priorityRank,
        thread_id: need.threads_on_need[0]?.id ?? null,
        milestone_id: need.milestone?.id ?? null,
        meeting_id: need.meeting?.id ?? null,
        snoozed_until: need.snoozedUntil ?? null,
        resolved_at: need.resolvedAt ?? null,
        agent_reasoning: need.agentReasoning,
        created_at: need.createdAt,
        // Joined fields
        customer_name: need.customer.name,
        customer_lifecycle: need.customer.lifecycle,
        customer_arr_cents: need.customer.arrCents ? parseInt(need.customer.arrCents, 10) : null,
        recommendation_primary: recommendation?.primaryAction ?? null,
        recommendation_secondary: recommendation?.secondaryAction ?? null,
        recommendation_rationale: recommendation?.rationale ?? null,
        plan_id: agentRun?.plan?.id ?? null,
        // Agent run fields (for sidekick questions)
        agent_run_id: agentRun?.id ?? null,
        agent_questions: agentQuestions,
      };
    }),
    count: query.data.needs.length,
    active_count: query.data.needs.filter(n => !n.resolvedAt && !n.snoozedUntil).length,
  } : undefined;

  // Log when query.data changes
  useEffect(() => {
    console.log('[useToday] DATA CHANGED - needs count:', query.data?.needs?.length);
  }, [query.data]);

  const refetch = useServerRefetch(
    () => getTodayQueueRef(dataConnect, { workspaceId: workspaceId || '' }),
    [workspaceId],
    query.refetch,
  );

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
    refetch,
  };
}

/**
 * Get today's worklist items - milestones with goal linkage that are due soon.
 * For the goal-centric Today screen Lane 2.
 */
export function useTodayWorklist() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetTodayWorklist(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Return the query data directly - transformation happens in the component
  return {
    ...query,
    data: query.data ? {
      milestones: query.data.milestones,
    } : undefined,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useThreads() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetThreads(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform threads to match ThreadDetail format
  const transformedData = query.data ? {
    threads: query.data.threads.map(t => {
      // Get the latest interaction timestamp
      const latestInteraction = t.interactions_on_thread.length > 0
        ? t.interactions_on_thread.reduce((latest, i) =>
            new Date(i.occurredAt) > new Date(latest.occurredAt) ? i : latest
          )
        : null;

      return {
        id: t.id,
        need_id: t.need?.id || '',
        customer_id: t.customer.id,
        customer_name: t.customer.name,
        customer: {
          id: t.customer.id,
          name: t.customer.name,
          slug: t.customer.slug,
          lifecycle: t.customer.lifecycle,
          arr_cents: null, // Not available in threads query
          tier: null, // Not available in threads query
        },
        need: t.need ? {
          id: t.need.id,
          type: t.need.type,
          headline: t.need.headline,
        } : null,
        need_type: t.need?.type || null,
        thread_type: t.threadType || 'customer',
        status: t.status,
        // Map thread status to workflow status
        workflow_status: t.status === 'resolved' ? 'resolved' : 'needs_response',
        blocked_reason: null,
        snoozed_until: null,
        channel: t.channel || 'email',
        subject: t.subject,
        latest_message_at: latestInteraction?.occurredAt || t.updatedAt,
        stats: {
          total_messages: t.interactions_on_thread.length,
          unread_messages: 0,
          last_response_time_hours: null,
        },
        related_threads: [],
        current_draft: null,
        sidekick: null,
        stakeholders: [],
        signals: [],
        milestones: [],
        upcoming_meetings: [],
        derailment_risks: [],
        agent_run_id: null,
      };
    }),
    count: query.data.threads.length,
  } : undefined;

  const refetch = useServerRefetch(
    () => getThreadsRef(dataConnect, { workspaceId: workspaceId || '' }),
    [workspaceId],
    query.refetch,
  );

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
    refetch,
  };
}

// ============================================================================
// Conversations (Need-Centric)
// ============================================================================

export interface ConversationNeed {
  id: string;
  type: string;
  headline: string;
  lede: string | null;
  priority_rank: number;
  status: string;
  snoozed_until: string | null;
  resolved_at: string | null;
  agent_reasoning: string | null;
  created_at: string;
  updated_at: string;
  customer_id: string;
  customer_name: string;
  customer_slug: string;
  customer_lifecycle: string;
  customer_arr_cents: number | null;
  recommendation_primary: string | null;
  recommendation_secondary: string | null;
  agent_run_id: string | null;
  agent_questions: Array<{ id: string; text: string; context?: string }> | null;
  milestone?: { id: string; title: string; status: string; target_date: string | null } | null;
  meeting?: { id: string; title: string; scheduled_at: string } | null;
  threads: Array<{
    id: string;
    subject: string | null;
    status: string;
    thread_type: string;
    channel: string;
    updated_at: string;
    latest_interaction?: {
      id: string;
      sender_name: string | null;
      summary_ai: string | null;
      occurred_at: string;
    } | null;
  }>;
}

export interface OrphanThread {
  id: string;
  subject: string | null;
  status: string;
  thread_type: string;
  channel: string;
  updated_at: string;
  customer_id: string;
  customer_name: string;
  customer_slug: string;
  latest_interaction?: {
    id: string;
    sender_name: string | null;
    summary_ai: string | null;
    occurred_at: string;
  } | null;
}

export function useConversationNeeds() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetConversationNeeds(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform needs with threads to ConversationNeed format
  const transformedData = query.data ? {
    needs: query.data.needs.map((need): ConversationNeed => {
      const recommendation = need.needRecommendations_on_need?.[0];
      const agentRun = need.agentRun;

      // Parse clarifying questions from agent run JSON
      let agentQuestions = null;
      if (agentRun?.clarifyingQuestions) {
        try {
          const parsed = JSON.parse(agentRun.clarifyingQuestions);
          agentQuestions = parsed.map((q: { question: string; context?: string; field?: string }, index: number) => ({
            id: q.field || `q${index}`,
            text: q.question,
            context: q.context,
          }));
        } catch (e) {
          console.warn('Failed to parse clarifying questions:', e);
        }
      }

      return {
        id: need.id,
        type: need.type,
        headline: need.headline,
        lede: need.lede ?? null,
        priority_rank: need.priorityRank,
        status: need.status,
        snoozed_until: need.snoozedUntil ?? null,
        resolved_at: need.resolvedAt ?? null,
        agent_reasoning: need.agentReasoning ?? null,
        created_at: need.createdAt,
        updated_at: need.updatedAt,
        customer_id: need.customer.id,
        customer_name: need.customer.name,
        customer_slug: need.customer.slug,
        customer_lifecycle: need.customer.lifecycle,
        customer_arr_cents: need.customer.arrCents ? parseInt(need.customer.arrCents, 10) : null,
        recommendation_primary: recommendation?.primaryAction ?? null,
        recommendation_secondary: recommendation?.secondaryAction ?? null,
        agent_run_id: agentRun?.id ?? null,
        agent_questions: agentQuestions,
        milestone: need.milestone ? {
          id: need.milestone.id,
          title: need.milestone.title,
          status: need.milestone.status,
          target_date: need.milestone.targetDate ?? null,
        } : null,
        meeting: need.meeting ? {
          id: need.meeting.id,
          title: need.meeting.title,
          scheduled_at: need.meeting.scheduledAt,
        } : null,
        threads: need.threads_on_need.map(t => ({
          id: t.id,
          subject: t.subject ?? null,
          status: t.status,
          thread_type: t.threadType || 'customer',
          channel: t.channel || 'email',
          updated_at: t.updatedAt,
          latest_interaction: t.interactions_on_thread[0] ? {
            id: t.interactions_on_thread[0].id,
            sender_name: t.interactions_on_thread[0].senderName ?? null,
            summary_ai: t.interactions_on_thread[0].summaryAi ?? null,
            occurred_at: t.interactions_on_thread[0].occurredAt,
          } : null,
        })),
      };
    }),
    count: query.data.needs.length,
  } : undefined;

  const refetch = useServerRefetch(
    () => getConversationNeedsRef(dataConnect, { workspaceId: workspaceId || '' }),
    [workspaceId],
    query.refetch,
  );

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
    refetch,
  };
}

/**
 * Resolved needs for the Conversations "Resolved" filter chip. Same shape as
 * `useConversationNeeds`, but sourced from `GetResolvedConversationNeeds`
 * (resolvedAt not null, newest-resolved first). Returns `{ needs, count }`.
 */
export function useResolvedConversationNeeds(options?: { enabled?: boolean }) {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetResolvedConversationNeeds(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading && (options?.enabled ?? true) }
  );

  const transformedData = query.data ? {
    needs: query.data.needs.map((need): ConversationNeed => {
      const recommendation = need.needRecommendations_on_need?.[0];
      const agentRun = need.agentRun;

      let agentQuestions = null;
      if (agentRun?.clarifyingQuestions) {
        try {
          const parsed = JSON.parse(agentRun.clarifyingQuestions);
          agentQuestions = parsed.map((q: { question: string; context?: string; field?: string }, index: number) => ({
            id: q.field || `q${index}`,
            text: q.question,
            context: q.context,
          }));
        } catch (e) {
          console.warn('Failed to parse clarifying questions:', e);
        }
      }

      return {
        id: need.id,
        type: need.type,
        headline: need.headline,
        lede: need.lede ?? null,
        priority_rank: need.priorityRank,
        status: need.status,
        snoozed_until: need.snoozedUntil ?? null,
        resolved_at: need.resolvedAt ?? null,
        agent_reasoning: need.agentReasoning ?? null,
        created_at: need.createdAt,
        updated_at: need.updatedAt,
        customer_id: need.customer.id,
        customer_name: need.customer.name,
        customer_slug: need.customer.slug,
        customer_lifecycle: need.customer.lifecycle,
        customer_arr_cents: need.customer.arrCents ? parseInt(need.customer.arrCents, 10) : null,
        recommendation_primary: recommendation?.primaryAction ?? null,
        recommendation_secondary: recommendation?.secondaryAction ?? null,
        agent_run_id: agentRun?.id ?? null,
        agent_questions: agentQuestions,
        milestone: need.milestone ? {
          id: need.milestone.id,
          title: need.milestone.title,
          status: need.milestone.status,
          target_date: need.milestone.targetDate ?? null,
        } : null,
        meeting: need.meeting ? {
          id: need.meeting.id,
          title: need.meeting.title,
          scheduled_at: need.meeting.scheduledAt,
        } : null,
        threads: need.threads_on_need.map(t => ({
          id: t.id,
          subject: t.subject ?? null,
          status: t.status,
          thread_type: t.threadType || 'customer',
          channel: t.channel || 'email',
          updated_at: t.updatedAt,
          latest_interaction: t.interactions_on_thread[0] ? {
            id: t.interactions_on_thread[0].id,
            sender_name: t.interactions_on_thread[0].senderName ?? null,
            summary_ai: t.interactions_on_thread[0].summaryAi ?? null,
            occurred_at: t.interactions_on_thread[0].occurredAt,
          } : null,
        })),
      };
    }),
    count: query.data.needs.length,
  } : undefined;

  const refetch = useServerRefetch(
    () => getResolvedConversationNeedsRef(dataConnect, { workspaceId: workspaceId || '' }),
    [workspaceId],
    query.refetch,
  );

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
    refetch,
  };
}

export function useOrphanThreads() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetOrphanThreads(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform orphan threads
  const transformedData = query.data ? {
    threads: query.data.threads.map((t): OrphanThread => ({
      id: t.id,
      subject: t.subject ?? null,
      status: t.status,
      thread_type: t.threadType || 'customer',
      channel: t.channel || 'email',
      updated_at: t.updatedAt,
      customer_id: t.customer.id,
      customer_name: t.customer.name,
      customer_slug: t.customer.slug,
      latest_interaction: t.interactions_on_thread[0] ? {
        id: t.interactions_on_thread[0].id,
        sender_name: t.interactions_on_thread[0].senderName ?? null,
        summary_ai: t.interactions_on_thread[0].summaryAi ?? null,
        occurred_at: t.interactions_on_thread[0].occurredAt,
      } : null,
    })),
    count: query.data.threads.length,
  } : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useQuarantinedThreads() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetQuarantinedThreads(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform quarantined threads
  const transformedData = query.data ? {
    threads: query.data.threads.map((t): OrphanThread => ({
      id: t.id,
      subject: t.subject ?? null,
      status: t.status,
      thread_type: t.threadType || 'quarantined',
      channel: t.channel || 'email',
      updated_at: t.updatedAt,
      customer_id: t.customer.id,
      customer_name: t.customer.name,
      customer_slug: t.customer.slug,
      latest_interaction: t.interactions_on_thread[0] ? {
        id: t.interactions_on_thread[0].id,
        sender_name: t.interactions_on_thread[0].senderName ?? null,
        summary_ai: t.interactions_on_thread[0].bodyEncrypted ?? null, // body for preview
        occurred_at: t.interactions_on_thread[0].occurredAt,
      } : null,
    })),
    count: query.data.threads.length,
  } : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useNeed(needId: string) {
  const query = useGetNeed(
    { id: needId },
    { enabled: !!needId }
  );

  // Transform need data to include all relationships
  const transformedData = query.data?.need ? {
    need: {
      id: query.data.need.id,
      type: query.data.need.type,
      headline: query.data.need.headline,
      lede: query.data.need.lede ?? null,
      priority_rank: query.data.need.priorityRank,
      focus_section: query.data.need.focusSection ?? null,
      snoozed_until: query.data.need.snoozedUntil ?? null,
      resolved_at: query.data.need.resolvedAt ?? null,
      source: query.data.need.source ?? null,
      agent_reasoning: query.data.need.agentReasoning ?? null,
      created_at: query.data.need.createdAt,
      updated_at: query.data.need.updatedAt,
      customer: query.data.need.customer ? {
        id: query.data.need.customer.id,
        name: query.data.need.customer.name,
        slug: query.data.need.customer.slug,
        lifecycle: query.data.need.customer.lifecycle,
        arr_cents: query.data.need.customer.arrCents ? parseInt(query.data.need.customer.arrCents, 10) : null,
        tier: query.data.need.customer.tier ?? null,
      } : null,
      milestone: query.data.need.milestone ? {
        id: query.data.need.milestone.id,
        title: query.data.need.milestone.title,
        status: query.data.need.milestone.status,
        target_date: query.data.need.milestone.targetDate ?? null,
        description: query.data.need.milestone.description ?? null,
        blocked_reason: query.data.need.milestone.blockedReason ?? null,
      } : null,
      meeting: query.data.need.meeting ? {
        id: query.data.need.meeting.id,
        title: query.data.need.meeting.title,
        scheduled_at: query.data.need.meeting.scheduledAt,
        duration_minutes: query.data.need.meeting.durationMinutes ?? 30,
      } : null,
      agent_run: query.data.need.agentRun ? {
        id: query.data.need.agentRun.id,
        agent_name: query.data.need.agentRun.agentName ?? null,
        status: query.data.need.agentRun.status,
        clarifying_questions: query.data.need.agentRun.clarifyingQuestions ?? null,
        current_step: query.data.need.agentRun.currentStep ?? null,
        plan: query.data.need.agentRun.plan ? {
          id: query.data.need.agentRun.plan.id,
          status: query.data.need.agentRun.plan.status,
          headline: query.data.need.agentRun.plan.headline ?? null,
        } : null,
      } : null,
      // Draft reply linked to this need (e.g. from the Support play). `draft` is the active
      // compose draft — ONLY a pending_review one, so an already-sent/discarded draft never
      // resurfaces in the reply box. Full history (incl. sent) stays in `drafts`. Keyed on the
      // need (not the thread), so the need/conversation screen can render it even with no thread.
      thread_id: query.data.need.thread?.id ?? null,
      draft: (() => {
        const d = (query.data.need.draftResponses_on_surfacedInNeed ?? [])
          .find(x => x.status === 'pending_review');
        return d ? {
          id: d.id,
          subject: d.subject ?? null,
          body: d.body,
          citations: d.citations ?? null,
          edited_body: d.editedBody ?? null,
          status: d.status,
          generated_at: d.generatedAt,
          thread_id: d.thread?.id ?? null,
        } : null;
      })(),
      drafts: (query.data.need.draftResponses_on_surfacedInNeed ?? []).map(d => ({
        id: d.id,
        subject: d.subject ?? null,
        body: d.body,
        citations: d.citations ?? null,
        edited_body: d.editedBody ?? null,
        status: d.status,
        generated_at: d.generatedAt,
        thread_id: d.thread?.id ?? null,
      })),
      recommendations: query.data.need.needRecommendations_on_need?.map(r => ({
        id: r.id,
        primary_action: r.primaryAction ?? null,
        secondary_action: r.secondaryAction ?? null,
        rationale: r.rationale ?? null,
        confidence_text: r.confidenceText ?? null,
      })) || [],
      evidences: query.data.need.needEvidences_on_need?.map(e => ({
        id: e.id,
        interaction: e.interaction ? {
          id: e.interaction.id,
          subject: e.interaction.subject ?? null,
          summary_ai: e.interaction.summaryAi ?? null,
          occurred_at: e.interaction.occurredAt,
        } : null,
        meeting: e.meeting ? {
          id: e.meeting.id,
          title: e.meeting.title,
          scheduled_at: e.meeting.scheduledAt,
        } : null,
      })) || [],
      threads: query.data.need.threads_on_need?.map(t => ({
        id: t.id,
        subject: t.subject ?? null,
        thread_type: t.threadType || 'customer',
        status: t.status,
        channel: t.channel || 'email',
        updated_at: t.updatedAt,
      })) || [],
    },
  } : undefined;

  const refetch = useServerRefetch(
    () => getNeedRef(dataConnect, { id: needId }),
    [needId],
    query.refetch,
  );

  return {
    ...query,
    data: transformedData,
    refetch,
  };
}

/**
 * Hook to fetch threads for a specific customer.
 * Used as a fallback when a need has no directly linked threads.
 * Returns the customer's most recent threads.
 */
export function useCustomerThreads(customerId: string | null) {
  const query = useGetCustomerThreads(
    { customerId: customerId || '' },
    { enabled: !!customerId }
  );

  // Transform threads to match expected format
  const transformedData = query.data?.threads ? {
    threads: query.data.threads.map(t => ({
      id: t.id,
      subject: t.subject ?? null,
      thread_type: t.threadType || 'customer',
      status: t.status,
      channel: t.channel || 'email',
      updated_at: t.updatedAt,
      latest_interaction: t.interactions_on_thread?.[0] ? {
        summary_ai: t.interactions_on_thread[0].summaryAi ?? null,
        occurred_at: t.interactions_on_thread[0].occurredAt,
      } : null,
    })),
  } : undefined;

  return {
    ...query,
    data: transformedData,
  };
}

export function useThread(threadId: string) {
  const query = useGetThread(
    { id: threadId },
    { enabled: !!threadId }
  );

  // Transform thread data to match expected format
  const transformedData = query.data?.thread ? {
    thread: {
      id: query.data.thread.id,
      subject: query.data.thread.subject || '',
      status: query.data.thread.status,
      // Map thread status to workflow status
      workflow_status: query.data.thread.status === 'resolved' ? 'resolved' : 'needs_response',
      blocked_reason: null,
      snoozed_until: null,
      channel: query.data.thread.channel || 'email',
      thread_type: query.data.thread.threadType || 'customer',
      category: query.data.thread.category,
      ai_category_suggestion: query.data.thread.aiCategorySuggestion,
      origin_detail: query.data.thread.originDetail,
      archived_at: query.data.thread.archivedAt,
      resolved_at: query.data.thread.resolvedAt,
      created_at: query.data.thread.createdAt,
      updated_at: query.data.thread.updatedAt,
      customer_id: query.data.thread.customer.id,
      customer_name: query.data.thread.customer.name,
      customer_slug: query.data.thread.customer.slug,
      customer: {
        id: query.data.thread.customer.id,
        name: query.data.thread.customer.name,
        slug: query.data.thread.customer.slug,
        lifecycle: query.data.thread.customer.lifecycle,
        arr_cents: query.data.thread.customer.arrCents ? parseInt(query.data.thread.customer.arrCents) : null,
        tier: query.data.thread.customer.tier || null,
      },
      need_id: query.data.thread.need?.id || '',
      need_type: query.data.thread.need?.type || null,
      need: query.data.thread.need ? {
        id: query.data.thread.need.id,
        type: query.data.thread.need.type,
        headline: query.data.thread.need.headline,
        lede: query.data.thread.need.lede,
        priority_rank: query.data.thread.need.priorityRank,
        agent_reasoning: query.data.thread.need.agentReasoning,
      } : null,
      assigned_user: query.data.thread.assignedUser ? {
        id: query.data.thread.assignedUser.id,
        display_name: query.data.thread.assignedUser.displayName,
        email: query.data.thread.assignedUser.email,
      } : undefined,
      latest_message_at: query.data.thread.updatedAt,
      stats: {
        message_count: 0,
        our_message_count: 0,
        their_message_count: 0,
        unread_count: 0,
      },
      related_threads: [],
      current_draft: null,
      sidekick: null,
      stakeholders: [],
      signals: [],
      milestones: [],
      upcoming_meetings: [],
      derailment_risks: [],
      agent_run_id: null,
    },
  } : undefined;

  const refetch = useServerRefetch(
    () => getThreadRef(dataConnect, { id: threadId }),
    [threadId],
    query.refetch,
  );

  return {
    ...query,
    data: transformedData,
    refetch,
  };
}

// Get thread messages (extracted from thread interactions)
export function useThreadMessages(threadId: string) {
  const query = useGetThread(
    { id: threadId },
    { enabled: !!threadId }
  );

  // Transform interactions to messages format
  // Note: Some fields are not available in the query and will use defaults
  const transformedData = query.data?.thread ? {
    messages: (query.data.thread.interactions_on_thread || []).map(i => ({
      id: i.id,
      thread_id: threadId,
      channel: i.channel,
      direction: i.direction,
      sender_name: i.senderName || '',
      sender_email: null, // Not available in query
      recipient_names: null, // Not available in query
      subject: i.subject || '',
      body: i.bodyEncrypted || '', // Field is named bodyEncrypted in schema
      content: i.bodyEncrypted || '', // Alias for components expecting content
      html_content: null, // Not available
      occurred_at: i.occurredAt,
      raw_source_id: null, // Not available in query
      sentiment: null, // Not available in query
      ai_summary: i.summaryAi || null,
      extracted_facts: [],
      attachments: [],
      mentions: [],
      created_at: i.occurredAt, // Use occurred_at as fallback
    })),
  } : undefined;

  const refetch = useServerRefetch(
    () => getThreadRef(dataConnect, { id: threadId }),
    [threadId],
    query.refetch,
  );

  return {
    ...query,
    data: transformedData,
    refetch,
  };
}

export function useMeetings() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetMeetings(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform meetings to match Meeting format
  const transformedData = query.data ? {
    meetings: query.data.meetings.map(m => {
      // Parse attendees from JSON strings
      const parseAttendees = (jsonStr: string | null | undefined): Array<{ name: string; email: string }> => {
        if (!jsonStr) return [];
        try {
          const parsed = JSON.parse(jsonStr);
          return Array.isArray(parsed) ? parsed : [];
        } catch {
          return [];
        }
      };

      return {
        id: m.id,
        workspace_id: workspaceId || '',
        customer_id: m.customer.id,
        customer_name: m.customer.name,
        need_id: m.need?.id || null,
        need: m.need ? {
          id: m.need.id,
          type: m.need.type,
          headline: m.need.headline,
          // Provide defaults for required fields not in query
          workspace_id: workspaceId || '',
          customer_id: m.customer.id,
          thread_id: null,
          milestone_id: null,
          lede: '',
          priority_rank: 0,
          status: 'needs_response',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        } as any : null,
        title: m.title,
        type: (m.type || 'other') as 'qbr' | 'renewal' | 'check_in' | 'onboarding' | 'kickoff' | 'support' | 'other',
        scheduled_at: m.scheduledAt,
        duration_minutes: m.durationMinutes || 30,
        source: m.source,
        external_event_id: null,
        attendees_ours: parseAttendees(m.attendeesOurs),
        attendees_theirs: parseAttendees(m.attendeesTheirs),
        status: (m.status || 'scheduled') as 'scheduled' | 'completed' | 'cancelled',
        brief: null,
      };
    }),
    count: query.data.meetings.length,
  } : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useMeeting(meetingId: string) {
  const { workspaceId } = useWorkspace();
  const query = useGetMeeting(
    { id: meetingId },
    { enabled: !!meetingId }
  );

  // Transform meeting to match Meeting format
  const transformedData = query.data?.meeting ? (() => {
    const m = query.data.meeting;

    // Parse attendees JSON strings
    let attendeesOurs: any[] = [];
    let attendeesTheirs: any[] = [];
    try { attendeesOurs = m.attendeesOurs ? JSON.parse(m.attendeesOurs as any) : []; } catch {}
    try { attendeesTheirs = m.attendeesTheirs ? JSON.parse(m.attendeesTheirs as any) : []; } catch {}

    // Transform MeetingBrief from DC to API shape
    const rawBrief = (m as any).meetingBriefs_on_meeting?.[0] ?? null;
    const brief = rawBrief ? {
      id: rawBrief.id,
      meeting_id: m.id,
      progress_narrative: rawBrief.progressNarrative ?? null,
      progress_facts: (() => { try { return rawBrief.progressFacts ? JSON.parse(rawBrief.progressFacts) : null; } catch { return null; } })(),
      friction: rawBrief.friction ?? null,
      talking_points: (() => { try { return rawBrief.talkingPoints ? JSON.parse(rawBrief.talkingPoints) : null; } catch { return null; } })(),
      value_delivered: rawBrief.valueDelivered ?? null,
      risk_to_renewal: rawBrief.riskToRenewal ?? null,
      expansion_signals: rawBrief.expansionSignals ?? null,
      pricing_context: rawBrief.pricingContext ?? null,
      followup_email: (() => { try { return rawBrief.followupEmail ? JSON.parse(rawBrief.followupEmail) : null; } catch { return null; } })(),
      generated_at: rawBrief.generatedAt ?? null,
    } : null;

    // Build customer context from rich GetMeeting response
    const cust = m.customer as any;
    const context = {
      arr_cents: cust.arrCents ?? null,
      one_liner: cust.oneLiner ?? null,
      stakeholders: (cust.stakeholders_on_customer ?? []).map((s: any) => ({
        id: s.id,
        name: s.name,
        email: s.email,
        role: s.role,
        status: s.status,
        sentiment_note: s.sentimentNote ?? null,
      })),
      signals: (cust.signals_on_customer ?? []).map((s: any) => ({
        kind: s.kind,
        state: s.state,
        sentence: s.sentence,
      })),
      milestones: (cust.milestones_on_customer ?? []).map((ms: any) => ({
        id: ms.id,
        title: ms.title,
        status: ms.status,
        target_date: ms.targetDate ?? null,
        goal_rationale: ms.goalRationale ?? null,
        goal: ms.goal ? { id: ms.goal.id, text: ms.goal.text, is_primary: ms.goal.isPrimary } : null,
      })),
      commitments: (cust.commitments_on_customer ?? []).map((c: any) => ({
        id: c.id,
        side: c.side,
        text: c.text,
        due_label: c.dueLabel ?? null,
        stake: c.stake ?? null,
        stake_holder: c.stakeHolder ? { id: c.stakeHolder.id, name: c.stakeHolder.name } : null,
      })),
    };

    return {
      meeting: {
        id: m.id,
        workspace_id: workspaceId || '',
        customer_id: m.customer.id,
        customer_name: m.customer.name,
        need_id: m.need?.id || null,
        need: m.need ? {
          id: m.need.id,
          type: m.need.type,
          headline: m.need.headline,
          workspace_id: workspaceId || '',
          customer_id: m.customer.id,
          thread_id: null,
          milestone_id: null,
          lede: (m.need as any).lede || '',
          priority_rank: 0,
          status: 'needs_response',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        } as any : null,
        title: m.title,
        type: (m.type || 'other') as 'qbr' | 'renewal' | 'check_in' | 'onboarding' | 'kickoff' | 'support' | 'other',
        scheduled_at: m.scheduledAt,
        duration_minutes: m.durationMinutes || 30,
        source: m.source,
        external_event_id: (m as any).externalEventId ?? null,
        attendees_ours: attendeesOurs,
        attendees_theirs: attendeesTheirs,
        status: (m.status || 'scheduled') as 'scheduled' | 'completed' | 'cancelled',
        brief,
        context,
      },
    };
  })() : undefined;

  return {
    ...query,
    data: transformedData,
  };
}

export function useHandoffs(status?: string) {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetHandoffs(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform and filter by status
  const transformedData = query.data ? {
    briefs: query.data.handoffBriefs
      .filter(h => !status || h.status === status)
      .map(h => ({
        id: h.id,
        workspace_id: workspaceId || '',
        status: h.status,
        captured_at: h.capturedAt,
        day_current: h.dayCurrent,
        day_total: h.dayTotal,
        notion_deal_id: h.notionDealId,
        notion_deal_url: h.notionDealUrl,
        customer_id: h.customer?.id || null,
        customer_name: h.customer?.name || null,
        confirmed_by: h.confirmedByUser?.displayName || null,
        confirmed_at: h.confirmedAt || null,
        // These come from detail query, not list - provide defaults
        body: null,
        sales_commitments: [],
        technical_context: [],
        reality_check_confidence: null,
        reality_check_risks: null,
        user_corrections: null,
        created_at: h.capturedAt, // Use captured_at as fallback
      })),
    count: query.data.handoffBriefs.filter(h => !status || h.status === status).length,
  } : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useHandoff(briefId: string) {
  const query = useGetHandoff(
    { id: briefId },
    { enabled: !!briefId }
  );

  // Transform to match expected format (brief, plan, open_questions)
  const transformedData = query.data?.handoffBrief ? {
    brief: {
      id: query.data.handoffBrief.id,
      status: query.data.handoffBrief.status,
      body: query.data.handoffBrief.body || null,
      captured_at: query.data.handoffBrief.capturedAt,
      day_current: query.data.handoffBrief.dayCurrent,
      day_total: query.data.handoffBrief.dayTotal,
      sales_commitments: query.data.handoffBrief.salesCommitments
        ? JSON.parse(query.data.handoffBrief.salesCommitments)
        : [],
      technical_context: query.data.handoffBrief.technicalContext
        ? JSON.parse(query.data.handoffBrief.technicalContext)
        : [],
      reality_check_confidence: query.data.handoffBrief.realityCheckConfidence || '',
      reality_check_risks: query.data.handoffBrief.realityCheckRisks || '',
      notion_deal_id: query.data.handoffBrief.notionDealId,
      notion_deal_url: query.data.handoffBrief.notionDealUrl,
      confirmed_by: query.data.handoffBrief.confirmedByUser?.displayName || null,
      confirmed_at: query.data.handoffBrief.confirmedAt,
      customer: query.data.handoffBrief.customer ? {
        id: query.data.handoffBrief.customer.id,
        name: query.data.handoffBrief.customer.name,
        slug: query.data.handoffBrief.customer.slug,
        lifecycle: query.data.handoffBrief.customer.lifecycle,
      } : undefined,
    },
    plan: query.data.handoffBrief.aiPlans_on_brief?.[0] ? {
      id: query.data.handoffBrief.aiPlans_on_brief[0].id,
      archetype_name: query.data.handoffBrief.aiPlans_on_brief[0].archetypeName,
      milestone_count: query.data.handoffBrief.aiPlans_on_brief[0].milestoneCount,
      duration_label: query.data.handoffBrief.aiPlans_on_brief[0].durationLabel,
      rationale: query.data.handoffBrief.aiPlans_on_brief[0].rationale,
      headline: query.data.handoffBrief.aiPlans_on_brief[0].headline,
      milestones: query.data.handoffBrief.aiPlans_on_brief[0].milestones
        ? JSON.parse(query.data.handoffBrief.aiPlans_on_brief[0].milestones)
        : [],
      status: query.data.handoffBrief.aiPlans_on_brief[0].status,
      human_edited: query.data.handoffBrief.aiPlans_on_brief[0].humanEdited,
      regeneration_count: query.data.handoffBrief.aiPlans_on_brief[0].regenerationCount,
      approved_by: query.data.handoffBrief.aiPlans_on_brief[0].approvedByUser?.displayName,
      approved_at: query.data.handoffBrief.aiPlans_on_brief[0].approvedAt,
      rejection_reason: query.data.handoffBrief.aiPlans_on_brief[0].rejectionReason,
    } : null,
    open_questions: (query.data.handoffBrief.handoffOpenQuestions_on_brief || []).map(q => ({
      id: q.id,
      brief_id: query.data.handoffBrief.id,
      text: unescapeText(q.text || ''),
      resolved: q.resolved,
    })),
  } : undefined;

  return {
    ...query,
    data: transformedData,
  };
}

export function usePlan(planId: string) {
  const query = useGetPlan(
    { id: planId },
    { enabled: !!planId }
  );

  // Transform to match expected structure for PlanApproval component
  // Provides defaults for fields not included in the GraphQL query
  const transformedData = useMemo(() => {
    const aiPlan = query.data?.aiPlan;
    if (!aiPlan) return undefined;

    // Use milestones JSON if available, otherwise fall back to customer's milestone records
    let milestones: PlanMilestone[] = [];
    if (aiPlan.milestones) {
      milestones = JSON.parse(aiPlan.milestones);
    } else if (aiPlan.customer?.milestones_on_customer) {
      // Convert Milestone records to PlanMilestone format
      milestones = aiPlan.customer.milestones_on_customer.map((m) => ({
        title: m.title,
        owner_side: m.ownerSide as OwnerSide,
        target_days: 7, // Default, actual date is in targetDate
        description: m.description || null,
      }));
    }

    return {
      plan: {
        id: aiPlan.id,
        workspace_id: '', // Not needed for display
        customer_id: aiPlan.customer?.id || null,
        brief_id: aiPlan.brief?.id || null,
        archetype_name: aiPlan.archetypeName,
        milestone_count: aiPlan.milestoneCount,
        duration_label: aiPlan.durationLabel,
        rationale: aiPlan.rationale,
        headline: aiPlan.headline,
        milestones,
        status: aiPlan.status,
        human_edited: aiPlan.humanEdited,
        regeneration_count: aiPlan.regenerationCount,
        generated_at: aiPlan.generatedAt,
        rejection_reason: aiPlan.rejectionReason,
        approved_by: aiPlan.approvedByUser?.displayName || null,
        approved_by_user_id: aiPlan.approvedByUser?.id || null,
        approved_at: aiPlan.approvedAt,
        created_at: aiPlan.createdAt,
        updated_at: aiPlan.createdAt, // Use createdAt as fallback
        model: '',
        prompt_version: '',
        inputs_hash: '',
        handbook_version_id: '',
      },
      brief: aiPlan.brief ? {
        id: aiPlan.brief.id,
        workspace_id: '', // Not needed for display
        customer_id: aiPlan.customer?.id || null,
        captured_at: '',
        body: aiPlan.brief.body || null,
        sales_commitments: aiPlan.brief.salesCommitments
          ? JSON.parse(aiPlan.brief.salesCommitments)
          : [],
        technical_context: aiPlan.brief.technicalContext
          ? JSON.parse(aiPlan.brief.technicalContext)
          : [],
        day_current: aiPlan.brief.dayCurrent,
        day_total: aiPlan.brief.dayTotal,
        reality_check_confidence: null, // Not in query, provide default
        reality_check_risks: null, // Not in query, provide default
        status: 'confirmed' as 'draft' | 'confirmed' | 'needs_correction', // Default status
        user_corrections: null, // Not in query
        notion_deal_id: null,
        notion_deal_url: null,
        created_at: '',
      } : null,
      customer: aiPlan.customer ? {
        id: aiPlan.customer.id,
        name: aiPlan.customer.name,
        slug: aiPlan.customer.slug,
      } : null,
    };
  }, [query.data]);

  return {
    ...query,
    data: transformedData,
  };
}

/**
 * Get the handoff brief and associated AI plan for a customer.
 * Used for the Brief tab in CustomerDetail.
 */
export function useCustomerHandoffWithPlan(customerId: string | null) {
  const query = useGetCustomerHandoffWithPlan(
    { customerId: customerId || '' },
    { enabled: !!customerId }
  );

  const transformedData = useMemo(() => {
    const brief = query.data?.handoffBriefs?.[0];
    if (!brief) return null;

    // Get the most recent plan (already ordered by generatedAt DESC)
    const plan = brief.aiPlans_on_brief?.[0];

    return {
      brief: {
        id: brief.id,
        status: brief.status,
        body: brief.body,  // Markdown content from agent
        day_current: brief.dayCurrent,
        day_total: brief.dayTotal,
        sales_commitments: brief.salesCommitments
          ? JSON.parse(brief.salesCommitments)
          : [],
        technical_context: brief.technicalContext
          ? JSON.parse(brief.technicalContext)
          : [],
        reality_check_confidence: brief.realityCheckConfidence,
        reality_check_risks: brief.realityCheckRisks,
        notion_deal_id: brief.notionDealId,
        notion_deal_url: brief.notionDealUrl,
        created_at: brief.createdAt,
      },
      open_questions: (brief.handoffOpenQuestions_on_brief || []).map(q => ({
        id: q.id,
        text: unescapeText(q.text || ''),
        resolved: q.resolved,
        created_at: q.createdAt,
      })),
      plan: plan ? {
        id: plan.id,
        archetype_name: plan.archetypeName,
        milestone_count: plan.milestoneCount,
        duration_label: plan.durationLabel,
        rationale: plan.rationale,
        headline: plan.headline,
        milestones: plan.milestones ? JSON.parse(plan.milestones) : [],
        status: plan.status,
        human_edited: plan.humanEdited,
        regeneration_count: plan.regenerationCount,
        generated_at: plan.generatedAt,
        approved_by: plan.approvedByUser?.displayName || null,
        approved_at: plan.approvedAt,
        rejection_reason: plan.rejectionReason,
      } : null,
    };
  }, [query.data]);

  return {
    ...query,
    data: transformedData,
  };
}

/**
 * Get plans directly for a customer (not via brief relationship).
 * Use this when plans may be created without a handoff brief.
 */
export function useCustomerPlans(customerId: string | null) {
  const query = useGetCustomerPlans(
    { customerId: customerId || '' },
    { enabled: !!customerId }
  );

  const transformedData = useMemo(() => {
    const plans = query.data?.aiPlans;
    if (!plans || plans.length === 0) return null;

    return {
      plans: plans.map(plan => ({
        id: plan.id,
        archetype_name: plan.archetypeName,
        milestone_count: plan.milestoneCount,
        duration_label: plan.durationLabel,
        rationale: plan.rationale,
        headline: plan.headline,
        milestones: plan.milestones ? JSON.parse(plan.milestones) : [],
        status: plan.status,
        human_edited: plan.humanEdited,
        regeneration_count: plan.regenerationCount,
        generated_at: plan.generatedAt,
        approved_by: plan.approvedByUser?.displayName || null,
        approved_at: plan.approvedAt,
        rejection_reason: plan.rejectionReason,
        has_brief: !!plan.brief?.id,
      })),
      // Get the most recent pending plan (for display in UI)
      pending_plan: plans.find(p => p.status === 'pending_approval') ? {
        id: plans.find(p => p.status === 'pending_approval')!.id,
        archetype_name: plans.find(p => p.status === 'pending_approval')!.archetypeName,
        milestone_count: plans.find(p => p.status === 'pending_approval')!.milestoneCount,
        duration_label: plans.find(p => p.status === 'pending_approval')!.durationLabel,
        headline: plans.find(p => p.status === 'pending_approval')!.headline,
        status: 'pending_approval' as const,
      } : null,
    };
  }, [query.data]);

  return {
    ...query,
    data: transformedData,
  };
}

/**
 * Get goals with their milestones for a customer.
 * Used in the Plans tab for the goal-centric view.
 */
export function useGoalsWithMilestones(customerId: string | null) {
  const { workspaceId } = useWorkspace();

  const query = useGetGoalsWithMilestones(
    { customerId: customerId || '', workspaceId: workspaceId || '' },
    { enabled: !!customerId && !!workspaceId }
  );

  return {
    ...query,
    data: query.data ? {
      goals: query.data.goals.map(goal => ({
        id: goal.id,
        text: goal.text,
        status: goal.status,
        isPrimary: goal.isPrimary,
        source: goal.source || 'manually added',
        sourceType: goal.sourceType || 'manual',
        sourceDate: goal.sourceDate,
        createdAt: goal.createdAt,
        milestones: goal.milestones_on_goal.map(m => ({
          id: m.id,
          title: m.title,
          description: m.description,
          ownerSide: m.ownerSide,
          targetDate: m.targetDate,
          status: m.status,
          sortOrder: m.sortOrder,
          goalRationale: m.goalRationale,
        })),
      })),
    } : undefined,
  };
}

/**
 * Get progress vectors for a customer (across all goals).
 * Used in the Plans tab for the vectors of progress view.
 */
export function useProgressVectorsForCustomer(customerId: string | null) {
  const query = useGetCustomerProgressVectors(
    { customerId: customerId || '' },
    { enabled: !!customerId }
  );

  return {
    ...query,
    data: query.data ? {
      vectors: query.data.progressVectors.map(v => ({
        id: v.id,
        category: v.category,
        description: v.description,
        currentState: v.currentState,
        progress: v.progress,
        targetProgress: v.targetProgress,
        targetLabel: v.targetLabel,
        unlocks: v.unlocks,
        assessmentReason: v.assessmentReason,
        lastAssessedAt: v.lastAssessedAt,
        lastAssessedBy: v.lastAssessedBy,
        goal: v.goal ? {
          id: v.goal.id,
          text: v.goal.text,
          isPrimary: v.goal.isPrimary,
        } : null,
      })),
    } : undefined,
  };
}

/**
 * Get the orchestrator's Risk/Save play output for a customer — the RiskBrief plus its
 * ordered save-play steps. Used by CustomerDetail's RiskSavePlayCard (renders briefs[0]).
 */
export function useRiskBriefsForCustomer(customerId: string | null) {
  const query = useGetRiskBriefsWithSteps(
    { customerId: customerId || '' },
    { enabled: !!customerId }
  );

  const refetch = useServerRefetch(
    () => getRiskBriefsWithStepsRef(dataConnect, { customerId: customerId || '' }),
    [customerId],
    query.refetch,
  );

  return {
    ...query,
    refetch,
    data: query.data ? {
      briefs: query.data.riskBriefs.map(b => ({
        id: b.id,
        whatChanged: b.whatChanged,
        evidenceText: b.evidenceText,
        play: b.play,
        generatedAt: b.generatedAt,
        createdAt: b.createdAt,
        steps: (b.riskPlaySteps_on_brief || []).map(s => ({
          id: s.id,
          label: s.label,
          rationale: s.rationale,
          done: s.done,
          notes: s.notes ?? null,
          sortOrder: s.sortOrder,
        })),
      })),
    } : undefined,
  };
}

/** Mark a save-play step done / not-done and attach optional CSM findings. */
export function useUpdateRiskPlayStep() {
  const mutation = useUpdateRiskPlayStepDC();
  return {
    ...mutation,
    mutateAsync: (args: { id: string; done: boolean; notes?: string | null }) =>
      mutation.mutateAsync({ id: args.id, done: args.done, notes: args.notes ?? undefined }),
  };
}

/**
 * Get the customer strategy document.
 * Used in the Plans tab for the Strategy Memo lens.
 */
export function useCustomerStrategy(customerId: string | null) {
  const query = useGetCustomerStrategy(
    { customerId: customerId || '' },
    { enabled: !!customerId }
  );

  return {
    ...query,
    data: query.data?.customerStrategies?.[0] ? {
      strategy: {
        id: query.data.customerStrategies[0].id,
        body: query.data.customerStrategies[0].body,
        lastUpdatedBy: query.data.customerStrategies[0].lastUpdatedBy,
        createdAt: query.data.customerStrategies[0].createdAt,
        updatedAt: query.data.customerStrategies[0].updatedAt,
      },
    } : undefined,
  };
}

export function useHandbook() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetHandbook(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform to match expected format
  const transformedData = query.data ? {
    docs: query.data.handbookDocs.map(doc => ({
      id: doc.id,
      workspace_id: workspaceId || '',
      slug: doc.slug,
      title: doc.title,
      description: doc.description || null,
      blast_radius: doc.blastRadius,
      body: '', // Not included in list query
      updated_at: doc.updatedAt,
    })),
    count: query.data.handbookDocs.length,
  } : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useHandbookDoc(slug: string) {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetHandbookDoc(
    { workspaceId: workspaceId || '', slug },
    { enabled: !!workspaceId && !!slug && !wsLoading }
  );

  // Transform to match expected format
  const doc = query.data?.handbookDocs?.[0];
  const transformedData = doc ? {
    doc: {
      id: doc.id,
      slug: doc.slug,
      title: doc.title,
      description: doc.description || null,
      body: doc.body,
      blast_radius: doc.blastRadius,
      created_at: doc.createdAt,
      updated_at: doc.updatedAt,
    },
    versions: doc.handbookVersions_on_doc?.map(v => ({
      id: v.id,
      body: v.body,
      edited_at: v.editedAt,
      edited_by_user_id: v.editedByUser?.displayName || null,
    })) || [],
  } : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

// ============================================================================
// Voice Documents
// ============================================================================

export interface VoiceDoc {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  body: string;
  kind: 'DOCUMENT' | 'VOICE_CORE' | 'VOICE_FOUNDATION' | 'VOICE_SCENARIO';
  inherits_from: { id: string; slug: string; title: string; body?: string } | null;
  trigger_expr: string | null;
  affects_surfaces: string | null;
  pinned: boolean;
  chapter_num: number | null;
  used_in_drafts_today: number;
  blast_radius: 'low' | 'medium' | 'high';
  created_at: string;
  updated_at: string;
}

export function useVoiceDocs() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetVoiceDocs(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform and group by kind
  const transformedData = query.data ? (() => {
    const docs = query.data.handbookDocs.map(doc => ({
      id: doc.id,
      slug: doc.slug,
      title: doc.title,
      description: doc.description || null,
      body: doc.body,
      kind: doc.kind as VoiceDoc['kind'],
      inherits_from: doc.inheritsFrom ? {
        id: doc.inheritsFrom.id,
        slug: doc.inheritsFrom.slug,
        title: doc.inheritsFrom.title,
      } : null,
      trigger_expr: doc.triggerExpr || null,
      affects_surfaces: doc.affectsSurfaces || null,
      pinned: doc.pinned || false,
      chapter_num: doc.chapterNum || null,
      used_in_drafts_today: doc.usedInDraftsToday || 0,
      blast_radius: doc.blastRadius as VoiceDoc['blast_radius'],
      created_at: doc.createdAt,
      updated_at: doc.updatedAt,
    }));

    return {
      all: docs,
      core: docs.find(d => d.kind === 'VOICE_CORE') || null,
      foundations: docs
        .filter(d => d.kind === 'VOICE_FOUNDATION')
        .sort((a, b) => (a.chapter_num || 0) - (b.chapter_num || 0)),
      scenarios: docs.filter(d => d.kind === 'VOICE_SCENARIO'),
      count: docs.length,
    };
  })() : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useVoiceDoc(slug: string) {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetVoiceDoc(
    { workspaceId: workspaceId || '', slug },
    { enabled: !!workspaceId && !!slug && !wsLoading }
  );

  // Transform to match expected format
  const doc = query.data?.handbookDocs?.[0];
  const transformedData = doc ? {
    doc: {
      id: doc.id,
      slug: doc.slug,
      title: doc.title,
      description: doc.description || null,
      body: doc.body,
      kind: doc.kind as VoiceDoc['kind'],
      inherits_from: doc.inheritsFrom ? {
        id: doc.inheritsFrom.id,
        slug: doc.inheritsFrom.slug,
        title: doc.inheritsFrom.title,
        body: doc.inheritsFrom.body,
      } : null,
      trigger_expr: doc.triggerExpr || null,
      affects_surfaces: doc.affectsSurfaces || null,
      pinned: doc.pinned || false,
      chapter_num: doc.chapterNum || null,
      used_in_drafts_today: doc.usedInDraftsToday || 0,
      blast_radius: doc.blastRadius as VoiceDoc['blast_radius'],
      created_at: doc.createdAt,
      updated_at: doc.updatedAt,
    },
    versions: doc.handbookVersions_on_doc?.map(v => ({
      id: v.id,
      body: v.body,
      edited_at: v.editedAt,
      edited_by_user_id: v.editedByUser?.displayName || null,
    })) || [],
  } : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

// ============================================================================
// Playbooks
// ============================================================================

export function usePlaybooks() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetPlaybooks(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform to match expected format
  const transformedData = query.data ? {
    playbooks: query.data.playbooks.map(p => ({
      id: p.id,
      name: p.name,
      archetype: p.archetype || null,
      fit_note: p.fitNote || null,
      scenario: p.scenario || 'onboarding',
      drawn_from_count: p.drawnFromCount,
      milestones: p.playbookMilestones_on_playbook?.map(m => ({
        id: m.id,
        title: m.title,
        owner_side: m.ownerSide,
        duration_days: m.durationDays,
        description: m.description || null,
        sort_order: m.sortOrder,
      })) || [],
    })),
    count: query.data.playbooks.length,
  } : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

/**
 * Get a single playbook by ID
 */
export function usePlaybook(playbookId: string | null | undefined) {
  const { loading: wsLoading } = useWorkspace();

  const query = useGetPlaybook(
    { id: playbookId || '' },
    { enabled: !!playbookId && !wsLoading }
  );

  // Transform to match expected format
  const transformedData = query.data?.playbook ? {
    id: query.data.playbook.id,
    name: query.data.playbook.name,
    archetype: query.data.playbook.archetype || null,
    fit_note: query.data.playbook.fitNote || null,
    scenario: query.data.playbook.scenario || 'onboarding',
    drawn_from_count: query.data.playbook.drawnFromCount,
    milestones: query.data.playbook.playbookMilestones_on_playbook?.map(m => ({
      id: m.id,
      title: m.title,
      owner_side: m.ownerSide,
      duration_days: m.durationDays,
      description: m.description || null,
      sort_order: m.sortOrder,
    })) || [],
  } : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

export function useCreatePlaybookHook() {
  const { workspaceId } = useWorkspace();
  const mutation = useCreatePlaybookDC();

  return {
    ...mutation,
    mutateAsync: async (data: { name: string; archetype?: string; fitNote?: string; scenario?: 'onboarding' | 'renewal' | 'risk' }) => {
      if (!workspaceId) throw new Error('No workspace selected');
      return mutation.mutateAsync({
        workspaceId,
        name: data.name,
        archetype: data.archetype,
        fitNote: data.fitNote,
        scenario: data.scenario as any,
      });
    },
  };
}

export function useUpdatePlaybook() {
  return useUpdatePlaybookDC();
}

export function useDeletePlaybook() {
  return useDeletePlaybookDC();
}

export function useCreatePlaybookMilestoneHook() {
  const mutation = useCreatePlaybookMilestoneDC();
  return mutation;
}

export function useUpdatePlaybookMilestone() {
  return useUpdatePlaybookMilestoneDC();
}

export function useDeletePlaybookMilestone() {
  return useDeletePlaybookMilestoneDC();
}

// ============================================================================
// Playbook Catalog (Global Templates)
// ============================================================================

export interface PlaybookTemplateBlock {
  slug: string;
  name: string;
  description: string | null;
  ownerSide: string;
  typicalDays: number;
  minDays: number | null;
  maxDays: number | null;
  category: string;
  prerequisites: string | null;
  tags: string | null;
  sortOrder: number;
  durationOverride: number | null;
  isRequired: boolean;
}

export interface PlaybookTemplate {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  complexity: string;
  estimatedDays: number;
  fitCriteria: string | null;
  sortOrder: number;
  blocks: PlaybookTemplateBlock[];
}

/**
 * Hook to fetch global playbook templates from the catalog.
 * These are available to all workspaces.
 */
export function usePlaybookTemplates() {
  const query = useGetPlaybookTemplates();

  // Transform to a cleaner format
  const templates: PlaybookTemplate[] = useMemo(() => {
    if (!query.data?.playbookTemplates) return [];

    return query.data.playbookTemplates.map(t => ({
      id: t.id,
      slug: t.slug,
      name: t.name,
      description: t.description || null,
      complexity: t.complexity,
      estimatedDays: t.estimatedDays,
      fitCriteria: t.fitCriteria || null,
      sortOrder: t.sortOrder,
      blocks: (t.playbookTemplateBlocks_on_template || []).map(tb => ({
        slug: tb.block.slug,
        name: tb.block.name,
        description: tb.block.description || null,
        ownerSide: tb.block.ownerSide,
        typicalDays: tb.block.typicalDays,
        minDays: tb.block.minDays,
        maxDays: tb.block.maxDays,
        category: tb.block.category,
        prerequisites: tb.block.prerequisites || null,
        tags: tb.block.tags || null,
        sortOrder: tb.sortOrder,
        durationOverride: tb.durationOverride,
        isRequired: tb.isRequired,
      })),
    }));
  }, [query.data]);

  return {
    ...query,
    templates,
    isLoading: query.isLoading,
  };
}

/**
 * Hook to fetch milestone blocks from the catalog.
 * Used for composing custom playbooks.
 */
export function useMilestoneBlocks() {
  const query = useGetMilestoneBlocks();

  const blocks = useMemo(() => {
    if (!query.data?.milestoneBlocks) return [];

    return query.data.milestoneBlocks.map(b => ({
      id: b.id,
      slug: b.slug,
      name: b.name,
      description: b.description || null,
      ownerSide: b.ownerSide,
      typicalDays: b.typicalDays,
      minDays: b.minDays,
      maxDays: b.maxDays,
      category: b.category,
      prerequisites: b.prerequisites ? JSON.parse(b.prerequisites) : [],
      tags: b.tags ? JSON.parse(b.tags) : [],
      sortOrder: b.sortOrder,
    }));
  }, [query.data]);

  return {
    ...query,
    blocks,
    isLoading: query.isLoading,
  };
}

/**
 * Adopt a template to the workspace - creates a workspace playbook from a template.
 */
export function useAdoptTemplate() {
  const { workspaceId } = useWorkspace();
  const adoptMutation = useAdoptPlaybookTemplate();
  const createMilestoneMutation = useCreatePlaybookMilestoneFromBlock();

  const adoptTemplate = useCallback(async (
    template: PlaybookTemplate,
    customName?: string,
  ) => {
    if (!workspaceId) throw new Error('No workspace selected');

    // Create the playbook
    const result = await adoptMutation.mutateAsync({
      workspaceId,
      name: customName || template.name,
      archetype: template.complexity === 'simple' ? 'Quick' :
                 template.complexity === 'complex' ? 'Enterprise' : 'Standard',
      fitNote: template.description || undefined,
      adoptedFromTemplateId: template.id,
    });

    const playbookId = result.playbook_insert.id;

    // Create milestones from blocks
    // Import OwnerSide enum dynamically to avoid circular deps
    const { OwnerSide } = await import('@/dataconnect-generated');

    for (const block of template.blocks) {
      // Map string to enum value
      const ownerSideEnum = block.ownerSide === 'us' ? OwnerSide.us :
                            block.ownerSide === 'customer' ? OwnerSide.customer :
                            OwnerSide.joint;

      await createMilestoneMutation.mutateAsync({
        playbookId,
        title: block.name,
        ownerSide: ownerSideEnum,
        durationDays: block.durationOverride || block.typicalDays,
        description: block.description || undefined,
        sortOrder: block.sortOrder,
        sourceBlockId: undefined, // TODO: Get block ID from the query
      });
    }

    return { playbookId };
  }, [workspaceId, adoptMutation, createMilestoneMutation]);

  return {
    adoptTemplate,
    isLoading: adoptMutation.isPending || createMilestoneMutation.isPending,
  };
}

// ============================================================================
// Agent Runs
// ============================================================================

export function useAgentRun(runId: string) {
  const query = useGetAgentRun(
    { id: runId },
    { enabled: !!runId }
  );

  // Memoize the transformation to prevent infinite re-renders
  const transformedData = useMemo(() => {
    if (!query.data?.agentRun) return undefined;

    const agentRun = query.data.agentRun;

    // Parse clarifyingQuestions JSON into questions array (blocking questions)
    let questions: AgentQuestion[] = [];
    if (agentRun.clarifyingQuestions) {
      try {
        const parsed = JSON.parse(agentRun.clarifyingQuestions);
        questions = parsed.map((q: any, index: number) => normalizeAgentQuestion(q, index));
      } catch (e) {
        console.warn('Failed to parse clarifying questions:', e);
      }
    }

    // If no clarifyingQuestions, fall back to handoffQuestions (non-blocking questions)
    if (questions.length === 0 && agentRun.handoffQuestions_on_agentRun?.length > 0) {
      questions = agentRun.handoffQuestions_on_agentRun.map((q): AgentQuestion => {
        // Parse metadata if present
        let metadata: Record<string, unknown> | undefined;
        if (q.metadata) {
          try {
            metadata = JSON.parse(q.metadata);
          } catch {
            // Ignore parse errors
          }
        }
        return {
          id: q.id,
          text: q.question,
          question_type: (q.questionType as AgentQuestion['question_type']) || 'freeform',
          metadata,
        };
      });
    }

    return {
      run: {
        id: agentRun.id,
        agent_name: agentRun.agentName,
        status: agentRun.status,
        trigger_type: agentRun.triggerType,
        triggered_by: agentRun.triggeredBy,
        input_params: agentRun.inputParams,
        current_step: agentRun.currentStep,
        context_snapshot: agentRun.contextSnapshot,
        confidence_level: agentRun.confidenceLevel,
        confidence_score: agentRun.confidenceScore,
        confidence_reasons: agentRun.confidenceReasons,
        paused_at: agentRun.pausedAt,
        pause_reason: agentRun.pauseReason,
        resumed_at: agentRun.resumedAt,
        resume_answers: agentRun.resumeAnswers,
        result: agentRun.result,
        error_message: agentRun.errorMessage,
        used_fallback: agentRun.usedFallback,
        fallback_reason: agentRun.fallbackReason,
        started_at: agentRun.startedAt,
        completed_at: agentRun.completedAt,
        duration_ms: agentRun.durationMs,
        created_at: agentRun.createdAt,
        customer_id: agentRun.customer?.id,
        customer_name: agentRun.customer?.name,
        questions,
      },
      customer_name: agentRun.customer?.name,
    };
  }, [query.data]);

  return {
    ...query,
    data: transformedData,
  };
}

export function useWaitingRuns() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetWaitingRuns(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  const refetch = useServerRefetch(
    () => getWaitingRunsRef(dataConnect, { workspaceId: workspaceId || '' }),
    [workspaceId],
    query.refetch,
  );

  return {
    ...query,
    isLoading: query.isLoading || wsLoading,
    refetch,
  };
}

export function useThreadDraft(threadId: string) {
  const query = useGetDraftResponse(
    { threadId },
    { enabled: !!threadId }
  );

  // Transform the response to expose the first draft as 'draft'
  const transformedData = query.data ? {
    draft: query.data.draftResponses?.[0] || null,
  } : undefined;

  const refetch = useServerRefetch(
    () => getDraftResponseRef(dataConnect, { threadId }),
    [threadId],
    query.refetch,
  );

  return {
    ...query,
    data: transformedData,
    refetch,
  };
}

// ============================================================================
// Conversation contract: Huddles (internal discussion) + fan-out Needs on a thread
// ============================================================================

/** All un-resolved Needs anchored to a thread (fan-out: a thread can carry several). */
export function useNeedsForThread(threadId: string) {
  const query = useGetNeedsForThread({ threadId }, { enabled: !!threadId });
  return {
    ...query,
    data: query.data ? {
      needs: query.data.needs.map(n => ({
        id: n.id, type: n.type, headline: n.headline, lede: n.lede ?? null,
        priority_rank: n.priorityRank, created_at: n.createdAt,
      })),
    } : undefined,
  };
}

const _mapHuddle = (h: any) => ({
  id: h.id,
  title: h.title ?? null,
  status: h.status,
  anchor_interaction_id: h.anchorInteraction?.id ?? null,
  thread_id: h.thread?.id ?? null,
  created_by: h.createdByUser?.displayName ?? null,
  created_at: h.createdAt,
  resolved_at: h.resolvedAt ?? null,
  messages: (h.huddleMessages_on_huddle ?? []).map((m: any) => ({
    id: m.id,
    author_kind: m.authorKind,                         // "user" | "agent" (@sidekick)
    author_name: m.authorUser?.displayName ?? (m.authorKind === 'agent' ? 'Sidekick' : null),
    body: m.body,
    mentions: m.mentions ? JSON.parse(m.mentions) : [],
    created_at: m.createdAt,
  })),
});

/** Huddles on a thread (with messages). */
export function useThreadHuddles(threadId: string) {
  const query = useGetThreadHuddles({ threadId }, { enabled: !!threadId });
  return {
    ...query,
    data: query.data ? { huddles: query.data.huddles.map(_mapHuddle) } : undefined,
  };
}

/** A single huddle with its messages. */
export function useHuddle(huddleId: string) {
  const query = useGetHuddle({ id: huddleId }, { enabled: !!huddleId });
  return {
    ...query,
    data: query.data?.huddle ? { huddle: _mapHuddle(query.data.huddle) } : undefined,
  };
}

/** Open a new huddle on a thread (optionally anchored to a message). */
export function useCreateHuddle() {
  const mutation = useCreateHuddleDC();
  return {
    ...mutation,
    mutateAsync: (args: { workspaceId: string; customerId: string; threadId: string;
                          anchorInteractionId?: string | null; title?: string | null;
                          createdByUserId?: string | null }) =>
      mutation.mutateAsync({
        workspaceId: args.workspaceId, customerId: args.customerId, threadId: args.threadId,
        anchorInteractionId: args.anchorInteractionId ?? undefined,
        title: args.title ?? undefined, createdByUserId: args.createdByUserId ?? undefined,
      }),
  };
}

/** Post a message into a huddle (authorKind "user", or "agent" for @sidekick replies). */
export function usePostHuddleMessage() {
  const mutation = usePostHuddleMessageDC();
  return {
    ...mutation,
    mutateAsync: (args: { huddleId: string; body: string; authorUserId?: string | null;
                          authorKind?: 'user' | 'agent'; mentions?: string[] }) =>
      mutation.mutateAsync({
        huddleId: args.huddleId, body: args.body,
        authorUserId: args.authorUserId ?? undefined,
        authorKind: args.authorKind ?? 'user',
        mentions: args.mentions ? JSON.stringify(args.mentions) : undefined,
      }),
  };
}

/** Mark a huddle resolved. */
export function useResolveHuddle() {
  const mutation = useResolveHuddleDC();
  return {
    ...mutation,
    mutateAsync: (huddleId: string) => mutation.mutateAsync({ id: huddleId }),
  };
}

// ============================================================================
// Mutation Hooks
// ============================================================================

type MutationOptions<TData> = {
  onSuccess?: (data: TData) => void;
  onError?: (error: Error) => void;
  onSettled?: () => void;
};

export function useCreateCustomer() {
  const { workspaceId } = useWorkspace();
  const mutation = useCreateCustomerDC();

  return {
    ...mutation,
    mutate: (
      data: CreateCustomerInput,
      options?: MutationOptions<{ customer: { id: string } }>
    ) => {
      if (!workspaceId) throw new Error('No workspace ID');
      mutation.mutate(
        {
          workspaceId,
          name: data.name,
          slug: data.slug || data.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, ''),
          oneLiner: data.one_liner,
          tier: data.tier,
          arrCents: data.arr_cents?.toString(),
          lifecycle: data.lifecycle as CustomerLifecycle | undefined,
          rawNotes: data.raw_notes,
        },
        {
          onSuccess: (result) => {
            options?.onSuccess?.({ customer: { id: result.customer_insert.id } });
          },
          onError: options?.onError,
          onSettled: options?.onSettled,
        }
      );
    },
    mutateAsync: async (data: CreateCustomerInput) => {
      if (!workspaceId) throw new Error('No workspace ID');
      const result = await mutation.mutateAsync({
        workspaceId,
        name: data.name,
        slug: data.slug || data.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, ''),
        oneLiner: data.one_liner,
        tier: data.tier,
        arrCents: data.arr_cents?.toString(),
        lifecycle: data.lifecycle as CustomerLifecycle | undefined,
        rawNotes: data.raw_notes,
      });
      // Return in expected format
      return { customer: { id: result.customer_insert.id } };
    },
  };
}

export function useUpdateCustomer() {
  const mutation = useUpdateCustomerDC();

  return {
    ...mutation,
    mutate: ({ customerId, data }: { customerId: string; data: Partial<{ name: string; one_liner?: string; tier?: string; arr_cents?: number; lifecycle?: string; raw_notes?: string }> }) => {      mutation.mutate({
        id: customerId,
        name: data.name,
        oneLiner: data.one_liner,
        tier: data.tier,
        arrCents: data.arr_cents?.toString(),
        lifecycle: data.lifecycle as CustomerLifecycle,
        rawNotes: data.raw_notes,
      });
    },
    mutateAsync: async ({ customerId, data }: { customerId: string; data: Partial<{ name: string; one_liner?: string; tier?: string; arr_cents?: number; lifecycle?: string; raw_notes?: string }> }) => {
      return mutation.mutateAsync({
        id: customerId,
        name: data.name,
        oneLiner: data.one_liner,
        tier: data.tier,
        arrCents: data.arr_cents?.toString(),
        lifecycle: data.lifecycle as CustomerLifecycle,
        rawNotes: data.raw_notes,
      });
    },
  };
}

export function useSnoozeNeed() {
  const mutation = useSnoozeNeedDC();

  return {
    ...mutation,
    mutate: ({ needId, snoozedUntil }: { needId: string; snoozedUntil: Date }) => {
      mutation.mutate({
        id: needId,
        snoozedUntil: snoozedUntil.toISOString(),
      });
    },
  };
}

export function useResolveNeed() {
  const mutation = useResolveNeedDC();

  return {
    ...mutation,
    mutate: (needId: string) => {
      mutation.mutate({ id: needId });
    },
  };
}

export type WorkflowStatusValue =
  | 'needs_response'
  | 'awaiting_customer'
  | 'blocked'
  | 'snoozed'
  | 'resolved';

// Set a Need's workflow status directly (the transitions resolve/snooze don't
// cover — e.g. moving to awaiting_customer after a reply goes out).
export function useUpdateNeedStatus() {
  const mutation = useUpdateNeedStatusDC();
  // The generated mutation's `status` is the SDK's WorkflowStatus literal union;
  // derive it from the mutation itself so we never drift from the generated type.
  type StatusVar = Parameters<typeof mutation.mutate>[0]['status'];

  return {
    ...mutation,
    mutate: ({ needId, status }: { needId: string; status: WorkflowStatusValue }) => {
      mutation.mutate({ id: needId, status: status as StatusVar });
    },
    mutateAsync: async ({ needId, status }: { needId: string; status: WorkflowStatusValue }) => {
      return mutation.mutateAsync({ id: needId, status: status as StatusVar });
    },
  };
}

export function useCreateStakeholder() {
  const { workspaceId } = useWorkspace();
  const mutation = useCreateStakeholderPublic();

  type MutationOptions = { onSuccess?: () => void; onError?: (err: unknown) => void };

  return {
    ...mutation,
    mutate: (
      { customerId, data }: { customerId: string; data: { name: string; email?: string; role?: string } },
      options?: MutationOptions
    ) => {
      if (!workspaceId) throw new Error('No workspace ID');
      mutation.mutate(
        {
          workspaceId,
          customerId,
          name: data.name,
          email: data.email,
          role: data.role,
        },
        options
      );
    },
  };
}

export function useUpdateStakeholder() {
  const mutation = useUpdateStakeholderDC();

  type MutationOptions = { onSuccess?: () => void; onError?: (err: unknown) => void };

  return {
    ...mutation,
    mutate: (
      { stakeholderId, data }: { stakeholderId: string; customerId: string; data: { name?: string; email?: string; role?: string; status?: string } },
      options?: MutationOptions
    ) => {
      mutation.mutate(
        {
          id: stakeholderId,
          name: data.name,
          email: data.email,
          role: data.role,
        },
        options
      );
    },
  };
}

export function useDeleteStakeholder() {
  const mutation = useDeleteStakeholderDC();

  type MutationOptions = { onSuccess?: () => void; onError?: (err: unknown) => void };

  return {
    ...mutation,
    mutate: (
      { stakeholderId }: { stakeholderId: string; customerId: string },
      options?: MutationOptions
    ) => {
      mutation.mutate({ id: stakeholderId }, options);
    },
  };
}

export function useCreateMilestone() {
  const { workspaceId } = useWorkspace();
  const mutation = useCreateMilestonePublic();

  type MutationOptions = { onSuccess?: () => void; onError?: (err: unknown) => void };

  return {
    ...mutation,
    mutate: (
      { customerId, goalId, data }: {
        customerId: string;
        goalId?: string;  // link the step to a plan's anchoring Goal
        data: { title: string; target_date?: string; owner_side?: string; status?: string; description?: string };
      },
      options?: MutationOptions
    ) => {
      if (!workspaceId) throw new Error('No workspace ID');
      const ownerSide = (data.owner_side || 'joint').toLowerCase();
      mutation.mutate(
        {
          workspaceId,
          customerId,
          title: data.title,
          ownerSide: (['us', 'customer', 'joint'].includes(ownerSide) ? ownerSide : 'joint') as OwnerSide,
          targetDate: data.target_date,
          status: (data.status as MilestoneStatus | undefined),
          goalId,
          goalRationale: data.description,
        },
        options
      );
    },
  };
}

export function useUpdateMilestone() {
  const mutation = useUpdateMilestoneDC();

  type MutationOptions = { onSuccess?: () => void; onError?: (err: unknown) => void };

  return {
    ...mutation,
    mutate: (
      { milestoneId, data }: { milestoneId: string; customerId: string; data: { title?: string; status?: string; target_date?: string } },
      options?: MutationOptions
    ) => {
      mutation.mutate(
        {
          id: milestoneId,
          title: data.title,
          targetDate: data.target_date,
        },
        options
      );
    },
  };
}

export function useDeleteMilestone() {
  const mutation = useDeleteMilestoneDC();

  type MutationOptions = { onSuccess?: () => void; onError?: (err: unknown) => void };

  return {
    ...mutation,
    mutate: (
      { milestoneId }: { milestoneId: string; customerId: string },
      options?: MutationOptions
    ) => {
      mutation.mutate({ id: milestoneId }, options);
    },
  };
}

type GoalMutationOptions = { onSuccess?: () => void; onError?: (err: unknown) => void };

export function useCreateGoal() {
  const { workspaceId } = useWorkspace();
  const mutation = useCreateGoalPublic();

  return {
    ...mutation,
    mutate: (
      { customerId, data }: { customerId: string; data: { text: string } },
      options?: GoalMutationOptions
    ) => {
      if (!workspaceId) throw new Error('No workspace ID');
      mutation.mutate({
        workspaceId,
        customerId,
        text: data.text,
      }, options);
    },
  };
}

export function useUpdateGoal() {
  const mutation = useUpdateGoalDC();

  return {
    ...mutation,
    mutate: (
      { goalId, data }: { goalId: string; customerId: string; data: { text?: string; status?: string } },
      options?: GoalMutationOptions
    ) => {
      mutation.mutate({
        id: goalId,
        text: data.text,
      }, options);
    },
  };
}

export function useDeleteGoal() {
  const mutation = useDeleteGoalDC();

  return {
    ...mutation,
    mutate: (
      { goalId }: { goalId: string; customerId: string },
      options?: GoalMutationOptions
    ) => {
      mutation.mutate({ id: goalId }, options);
    },
  };
}

export function useApprovePlan() {
  const { workspaceId } = useWorkspace();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const mutate = useCallback(
    async (
      { planId }: { planId: string; milestones?: unknown[] },
      options?: { onSuccess?: () => void; onError?: (err: Error) => void }
    ) => {
      if (!workspaceId) {
        const err = new Error('No workspace selected');
        setError(err);
        options?.onError?.(err);
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        // Call backend endpoint that handles both approval + milestone creation
        await pythonRequest<{
          success: boolean;
          plan_id: string;
          milestones_created: number;
          message?: string;
        }>(
          'POST',
          `/api/workspaces/${workspaceId}/plans/${planId}/approve-and-activate`
        );

        options?.onSuccess?.();
      } catch (err) {
        const error = err instanceof Error ? err : new Error('Failed to approve plan');
        setError(error);
        options?.onError?.(error);
      } finally {
        setIsLoading(false);
      }
    },
    [workspaceId]
  );

  return {
    mutate,
    isLoading,
    error,
    isPending: isLoading,
  };
}

export function useRejectPlan() {
  const mutation = useRejectPlanDC();

  return {
    ...mutation,
    mutate: (
      { planId, rejectionReason }: { planId: string; rejectionReason: string },
      options?: { onSuccess?: () => void; onError?: (err: Error) => void }
    ) => {
      mutation.mutate({ id: planId, rejectionReason }, {
        onSuccess: options?.onSuccess,
        onError: options?.onError,
      });
    },
  };
}

export function useCreateMeeting() {
  const { workspaceId } = useWorkspace();
  const mutation = useCreateMeetingDC();

  return {
    ...mutation,
    mutate: (data: { customer_id: string; title: string; scheduled_at: string; meeting_type?: string }) => {
      if (!workspaceId) throw new Error('No workspace ID');
      mutation.mutate({
        workspaceId,
        customerId: data.customer_id,
        title: data.title,
        scheduledAt: data.scheduled_at,
      });
    },
  };
}

export function useUpdateMeeting() {
  const mutation = useUpdateMeetingDC();

  return {
    ...mutation,
    mutate: ({ meetingId, data }: {
      meetingId: string;
      data: {
        title?: string;
        scheduled_at?: string;
        status?: string;
        prep_notes?: string;
        live_notes?: string;
        followup_notes?: string;
      }
    }) => {
      // Note: prep_notes, live_notes, followup_notes would require a MeetingBrief mutation
      // For now, just update the meeting fields that are supported
      mutation.mutate({
        id: meetingId,
        title: data.title,
        scheduledAt: data.scheduled_at,
      });
    },
    isPending: mutation.isPending,
  };
}

export function useUpdateHandbookDoc() {
  const mutation = useUpdateHandbookDocDC();

  return {
    ...mutation,
    mutate: (
      vars: { id: string; body: string; title?: string; description?: string },
      options?: { onSuccess?: () => void }
    ) => {
      mutation.mutate(vars, options);
    },
  };
}

export function useSubmitAgentAnswers() {
  const { workspaceId } = useWorkspace();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const submitAnswers = async ({ runId, data }: { runId: string; data: { answers: Record<string, string> } }) => {
    // The backend /answers endpoint owns the full resume lifecycle (it flips status to "resuming",
    // stores the answers, resolves the blocking need, and dispatches the actual resume). Do NOT
    // pre-set status to "resuming" via a DataConnect mutation here: the backend treats a run that's
    // already "resuming" as a duplicate and short-circuits, so the resume (and any action it drives,
    // e.g. sending the approved draft) never runs.
    setIsPending(true);
    setError(null);
    try {
      await pythonRequest('POST', `/api/workspaces/${workspaceId}/agent-runs/${runId}/answers`, {
        answers: Object.entries(data.answers).map(([question_id, answer]) => ({
          question_id,
          answer,
        })),
      });
    } catch (err) {
      const e = err instanceof Error ? err : new Error('Failed to submit answers');
      setError(e);
      throw e;
    } finally {
      setIsPending(false);
    }
  };

  return {
    mutate: submitAnswers,
    mutateAsync: submitAnswers,
    isPending,
    isError: !!error,
    error,
  };
}

// Workspace creation (used during onboarding)
export function useCreateWorkspace() {
  const mutation = useCreateWorkspaceDC();

  return {
    ...mutation,
    mutateAsync: async (data: { name: string; slug?: string }) => {
      const slug = data.slug || data.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
      const result = await mutation.mutateAsync({
        name: data.name,
        slug,
      });
      return { workspace: { id: result.workspace_insert.id } };
    },
  };
}

// Workspace update (used during onboarding to rename existing workspace)
export function useUpdateWorkspace() {
  const mutation = useUpdateWorkspaceDC();

  return {
    ...mutation,
    mutateAsync: async (data: { id: string; name: string; slug?: string }) => {
      const slug = data.slug || data.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
      await mutation.mutateAsync({
        id: data.id,
        name: data.name,
        slug,
      });
    },
  };
}

// Mutex to prevent concurrent seeding operations
const seedingMutex: Map<string, Promise<void>> = new Map();

// Seed default handbook docs, voice docs, and playbooks for a new workspace
// Each category is seeded independently - existing data in one category doesn't block others
export async function seedWorkspaceDefaults(workspaceId: string): Promise<void> {
  // Check if seeding is already in progress for this workspace
  const existing = seedingMutex.get(workspaceId);
  if (existing) {
    console.log('[seedWorkspaceDefaults] Seeding already in progress for workspace:', workspaceId);
    return existing;
  }

  console.log('[seedWorkspaceDefaults] Starting seeding for workspace:', workspaceId);

  // Track what needs seeding
  let needsHandbookDocs = true;
  let needsVoiceDocs = true;
  let needsPlaybooks = true;

  // Wrap the actual seeding logic in a promise and store in mutex immediately
  const doSeeding = async () => {
    // Check existing handbook docs (kind = DOCUMENT or null)
    try {
      const existingHandbook = await getHandbook({ workspaceId });
      // Only skip if we have regular handbook docs (not voice docs)
      const regularDocs = existingHandbook.data.handbookDocs.filter(
        (d) => !d.kind || d.kind === 'DOCUMENT'
      );
      if (regularDocs.length > 0) {
        console.log('[seedWorkspaceDefaults] Handbook docs already exist, skipping');
        needsHandbookDocs = false;
      }
    } catch (err) {
      console.error('[seedWorkspaceDefaults] Failed to check existing handbook:', err);
    }

    // Check existing voice docs (kind = VOICE_*)
    try {
      const existingVoice = await getVoiceDocs({ workspaceId });
      if (existingVoice.data.handbookDocs.length > 0) {
        console.log('[seedWorkspaceDefaults] Voice docs already exist, skipping');
        needsVoiceDocs = false;
      }
    } catch (err) {
      console.error('[seedWorkspaceDefaults] Failed to check existing voice docs:', err);
    }

    // Check existing playbooks
    try {
      const existingPlaybooks = await getPlaybooks({ workspaceId });
      if (existingPlaybooks.data.playbooks.length > 0) {
        console.log('[seedWorkspaceDefaults] Playbooks already exist, skipping');
        needsPlaybooks = false;
      }
    } catch (err) {
      console.error('[seedWorkspaceDefaults] Failed to check existing playbooks:', err);
    }

    // Seed handbook docs if needed
    if (needsHandbookDocs) {
      console.log('[seedWorkspaceDefaults] Creating', DEFAULT_HANDBOOK_DOCS.length, 'handbook docs...');
      for (const doc of DEFAULT_HANDBOOK_DOCS) {
        try {
          const docId = crypto.randomUUID();
          await createHandbookDocWithId({
            id: docId,
            workspaceId,
            slug: doc.slug,
            title: doc.title,
            description: doc.description,
            body: doc.body,
            blastRadius: doc.blastRadius as BlastRadius,
          });
          console.log('[seedWorkspaceDefaults] Created handbook doc:', doc.slug);
        } catch (err) {
          console.error('[seedWorkspaceDefaults] Failed to create handbook doc:', doc.slug, err);
        }
      }
    }

    // Seed voice docs if needed
    if (needsVoiceDocs) {
      console.log('[seedWorkspaceDefaults] Creating', DEFAULT_VOICE_DOCS.length, 'voice docs...');
      for (const doc of DEFAULT_VOICE_DOCS) {
        try {
          const docId = crypto.randomUUID();
          await createHandbookDocWithId({
            id: docId,
            workspaceId,
            slug: doc.slug,
            title: doc.title,
            description: doc.description,
            body: doc.body,
            blastRadius: doc.blastRadius as BlastRadius,
            kind: doc.kind as HandbookDocKind,
            pinned: doc.pinned || false,
            chapterNum: doc.chapterNum || null,
            affectsSurfaces: doc.affectsSurfaces || null,
          });
          console.log('[seedWorkspaceDefaults] Created voice doc:', doc.slug);
        } catch (err) {
          console.error('[seedWorkspaceDefaults] Failed to create voice doc:', doc.slug, err);
        }
      }
    }

    // Seed playbooks if needed
    if (!needsPlaybooks) {
      console.log('[seedWorkspaceDefaults] Seeding complete (playbooks already existed)');
      return;
    }

    console.log('[seedWorkspaceDefaults] Creating', DEFAULT_PLAYBOOKS.length, 'playbooks...');
    for (const playbook of DEFAULT_PLAYBOOKS) {
      try {
        // Generate UUID for playbook
        const playbookId = crypto.randomUUID();

        await createPlaybookWithId({
          id: playbookId,
          workspaceId,
          name: playbook.name,
          archetype: playbook.archetype,
          fitNote: playbook.fitNote,
          scenario: playbook.scenario as any,
        });
        console.log('[seedWorkspaceDefaults] Created playbook:', playbook.name, playbookId);

        // Create milestones for this playbook
        for (const milestone of playbook.milestones) {
          try {
            const milestoneId = crypto.randomUUID();
            await createPlaybookMilestoneWithId({
              id: milestoneId,
              playbookId,
              title: milestone.title,
              ownerSide: milestone.ownerSide as OwnerSide,
              durationDays: milestone.durationDays,
              description: milestone.description,
              sortOrder: milestone.sortOrder,
            });
          } catch (milestoneErr) {
            console.error('[seedWorkspaceDefaults] Failed to create milestone:', milestone.title, milestoneErr);
          }
        }
        console.log('[seedWorkspaceDefaults] Created', playbook.milestones.length, 'milestones for', playbook.name);
      } catch (err) {
        console.error('[seedWorkspaceDefaults] Failed to create playbook:', playbook.name, err);
      }
    }

    console.log('[seedWorkspaceDefaults] Seeding complete');
  };

  // Store the promise in the mutex BEFORE starting execution to prevent race
  const seedingPromise = doSeeding();
  seedingMutex.set(workspaceId, seedingPromise);

  try {
    await seedingPromise;
  } finally {
    // Clean up the mutex after completion
    seedingMutex.delete(workspaceId);
  }
}

// Dashboard stats computed from available data
export function useDashboard() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  // Fetch customers and handoffs to compute stats
  const customersQuery = useGetCustomersPublic(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  const handoffsQuery = useGetHandoffs(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  const todayQuery = useGetTodayQueue(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Compute stats from the data
  const stats = customersQuery.data && handoffsQuery.data && todayQuery.data ? {
    // Escalations: at_risk customers
    escalations: customersQuery.data.customers.filter(c => c.lifecycle === 'at_risk').length,

    // Active onboardings
    active_onboardings: customersQuery.data.customers.filter(c => c.lifecycle === 'onboarding').length,

    // Renewals in 30 days
    renewals_30_days: customersQuery.data.customers.filter(c =>
      c.lifecycle === 'renewing' || (c.daysToRenewal !== null && c.daysToRenewal <= 30)
    ).length,

    // Pending approvals: handoffs with draft status + needs requiring plan approval
    pending_approvals:
      handoffsQuery.data.handoffBriefs.filter(h => h.status === 'draft').length +
      todayQuery.data.needs.filter(n => n.type === 'plan_approval_required').length,

    // Total ARR
    total_arr_cents: customersQuery.data.customers.reduce((sum, c) => {
      return sum + (c.arrCents ? parseInt(c.arrCents, 10) : 0);
    }, 0),
  } : undefined;

  const isLoading = wsLoading || customersQuery.isLoading || handoffsQuery.isLoading || todayQuery.isLoading;
  const error = customersQuery.error || handoffsQuery.error || todayQuery.error;

  return {
    data: stats,
    isLoading,
    error,
  };
}

// ============================================================================
// Additional Hooks for Detail Pages
// ============================================================================

// Update handoff status (for confirm/reject)
export function useUpdateHandoff() {
  const mutation = useUpdateHandoffStatusDC();

  type MutationOptions = { onSuccess?: () => void; onError?: (err: unknown) => void };

  return {
    ...mutation,
    mutate: (
      { briefId, data }: {
        briefId: string;
        data: {
          status?: string;
          sales_commitments?: unknown[];
          technical_context?: unknown[];
          reality_check_confidence?: string;
          reality_check_risks?: string;
        }
      },
      options?: MutationOptions
    ) => {
      // Store additional fields as userCorrections JSON if they exist
      const userCorrections = (data.sales_commitments || data.technical_context || data.reality_check_confidence || data.reality_check_risks)
        ? JSON.stringify({
            sales_commitments: data.sales_commitments,
            technical_context: data.technical_context,
            reality_check_confidence: data.reality_check_confidence,
            reality_check_risks: data.reality_check_risks,
          })
        : undefined;

      mutation.mutate(
        {
          id: briefId,
          status: (data.status || 'draft') as HandoffStatus,
          userCorrections,
        },
        options
      );
    },
    isPending: mutation.isPending,
  };
}

// Confirm handoff (change status to confirmed)
export function useConfirmHandoff() {
  const mutation = useUpdateHandoffStatusDC();

  type MutationOptions = { onSuccess?: () => void; onError?: (err: unknown) => void };

  return {
    ...mutation,
    mutate: (briefId: string, options?: MutationOptions) => {
      mutation.mutate(
        {
          id: briefId,
          status: 'confirmed' as HandoffStatus,
        },
        options
      );
    },
    isPending: mutation.isPending,
  };
}

// Update plan (mark as edited)
export function useUpdatePlan() {
  const mutation = useMarkPlanEditedDC();

  return {
    ...mutation,
    mutate: ({ planId, milestones }: { planId: string; milestones?: unknown[] }) => {
      mutation.mutate({
        id: planId,
        milestones: JSON.stringify(milestones || []),
      });
    },
    isPending: mutation.isPending,
  };
}

// Update workflow status for threads
export function useUpdateWorkflowStatus() {
  const mutation = useUpdateThreadDC();

  return {
    ...mutation,
    mutate: ({ threadId, data }: { threadId: string; data?: { workflow_status?: string; blocked_reason?: string; snoozed_until?: string } }) => {
      // Map workflow status to ThreadStatus enum
      const threadStatus = data?.workflow_status === 'resolved' ? ThreadStatus.resolved :
                           data?.workflow_status === 'archived' ? ThreadStatus.archived :
                           ThreadStatus.open;
      // Note: blocked_reason and snoozed_until are not supported by the DataConnect mutation
      // These would need to be implemented separately
      mutation.mutate({
        id: threadId,
        status: threadStatus,
      });
    },
    mutateAsync: async ({ threadId, data }: { threadId: string; data?: { workflow_status?: string; blocked_reason?: string; snoozed_until?: string } }) => {
      const threadStatus = data?.workflow_status === 'resolved' ? ThreadStatus.resolved :
                           data?.workflow_status === 'archived' ? ThreadStatus.archived :
                           ThreadStatus.open;
      // Note: blocked_reason and snoozed_until are not supported by the DataConnect mutation
      return mutation.mutateAsync({
        id: threadId,
        status: threadStatus,
      });
    },
    isPending: mutation.isPending,
  };
}

// Resolve thread
export function useResolveThreadHook() {
  const mutation = useResolveThreadDC();

  return {
    ...mutation,
    mutate: (threadId: string) => {
      mutation.mutate({ id: threadId });
    },
  };
}

// Send message (create interaction)
// Note: This is a simplified implementation. Full implementation would need workspaceId and customerId.
export function useSendMessage() {
  const { workspaceId } = useWorkspace();

  return {
    mutate: ({ threadId, data }: { threadId: string; data: { content?: string; is_internal?: boolean; mentions?: string[] } }) => {
      console.log('[useSendMessage] Would send message to thread:', threadId, data);
      // Real implementation would call createInteraction with workspaceId, customerId, etc.
    },
    mutateAsync: async ({ threadId, data }: { threadId: string; data: { content?: string; is_internal?: boolean; mentions?: string[] } }) => {
      console.log('[useSendMessage] Would send message to thread:', threadId, data);
      // Real implementation would call createInteraction with workspaceId, customerId, etc.
      return { id: 'placeholder', success: true };
    },
    isPending: false,
    isError: false,
    error: null,
  };
}

// Accept draft response
export function useAcceptDraft() {
  const mutation = useApproveDraftResponseDC();

  return {
    ...mutation,
    mutate: ({ draftId, editedContent }: { threadId: string; draftId: string; editedContent?: string }) => {
      mutation.mutate({
        id: draftId,
        editedBody: editedContent,
      });
    },
    mutateAsync: async ({ draftId, editedContent }: { threadId: string; draftId: string; editedContent?: string }) => {
      return mutation.mutateAsync({
        id: draftId,
        editedBody: editedContent,
      });
    },
    isPending: mutation.isPending,
  };
}

// Reject draft response
export function useRejectDraft() {
  const mutation = useDiscardDraftResponseDC();

  return {
    ...mutation,
    mutate: ({ draftId }: { threadId?: string; draftId: string }) => {
      mutation.mutate({ id: draftId });
    },
    mutateAsync: async ({ draftId }: { threadId?: string; draftId: string }) => {
      return mutation.mutateAsync({ id: draftId });
    },
    isPending: mutation.isPending,
  };
}

// Skip agent questions (just resume without answers)
export function useSkipAgentQuestions() {
  const { workspaceId } = useWorkspace();
  const mutation = useSubmitAgentAnswersDC();

  return {
    ...mutation,
    mutateAsync: async (runId: string) => {
      // Update database
      const result = await mutation.mutateAsync({
        id: runId,
        resumeAnswers: JSON.stringify({ skipped: true }),
      });

      // Trigger Python to resume agent in draft mode
      try {
        await pythonRequest('POST', `/api/workspaces/${workspaceId}/agent-runs/${runId}/skip`, {});
      } catch (err) {
        console.error('[useSkipAgentQuestions] Python API error:', err);
      }

      return result;
    },
  };
}

// Get workspace members (team members)
export function useTeamMembers() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetWorkspace(
    { id: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform to team members format
  const transformedData = query.data?.workspace ? {
    members: query.data.workspace.workspaceMembers_on_workspace?.map(m => ({
      id: m.user.id,
      user_id: m.user.id,
      name: m.user.displayName || m.user.email, // Add name field for TeamMember compatibility
      display_name: m.user.displayName,
      email: m.user.email,
      role: m.role,
      joined_at: m.joinedAt,
    })) || [],
  } : undefined;

  return {
    ...query,
    data: transformedData,
    isLoading: query.isLoading || wsLoading,
  };
}

// Request AI draft for a thread
export function useRequestDraft() {
  const { workspaceId } = useWorkspace();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const mutate = async ({ threadId, data }: { threadId: string; data?: { instructions?: string; vibe_input?: string } }) => {
    setIsPending(true);
    setError(null);
    try {
      await pythonRequest('POST', `/api/workspaces/${workspaceId}/threads/${threadId}/draft/generate`, {
        instructions: data?.instructions,
        vibe_input: data?.vibe_input,
      });
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to request draft'));
      console.error('[useRequestDraft] Error:', err);
    } finally {
      setIsPending(false);
    }
  };

  const mutateAsync = async ({ threadId, data }: { threadId: string; data?: { instructions?: string; vibe_input?: string } }) => {
    setIsPending(true);
    setError(null);
    try {
      const result = await pythonRequest<{ success: boolean; draft_id?: string; draft_body?: string }>('POST', `/api/workspaces/${workspaceId}/threads/${threadId}/draft/generate`, {
        instructions: data?.instructions,
        vibe_input: data?.vibe_input,
      });
      return result;
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to request draft'));
      throw err;
    } finally {
      setIsPending(false);
    }
  };

  return {
    mutate,
    mutateAsync,
    isPending,
    isError: !!error,
    error,
  };
}

/**
 * Send a reviewed draft. Calls the backend send action (simulates the send — no real email yet):
 * marks the draft sent, posts it as an outbound message on the thread, moves the Need to
 * awaiting_customer, and auto-completes the matching save-play step.
 */
export function useSendDraft() {
  const { workspaceId } = useWorkspace();
  const [isPending, setIsPending] = useState(false);

  const mutateAsync = async ({ threadId, editedContent }: { threadId: string; editedContent?: string }) => {
    setIsPending(true);
    try {
      return await pythonRequest<{ status: string }>(
        'POST',
        `/api/workspaces/${workspaceId}/threads/${threadId}/draft/send`,
        { edited_body: editedContent },
      );
    } finally {
      setIsPending(false);
    }
  };

  return { mutateAsync, isPending };
}

// Upload attachment (placeholder)
export function useUploadAttachment() {
  return {
    mutate: ({ threadId, file }: { threadId: string; file: File }) => {
      console.log('[useUploadAttachment] Would upload file to thread:', threadId, file.name);
    },
    mutateAsync: async ({ threadId, file }: { threadId: string; file: File }): Promise<Attachment> => {
      console.log('[useUploadAttachment] Would upload file to thread:', threadId, file.name);
      return {
        id: 'placeholder-' + Date.now(),
        filename: file.name,
        mime_type: file.type,
        size_bytes: file.size,
        url: '#placeholder'
      };
    },
    isPending: false,
    isError: false,
    error: null,
  };
}

// Regenerate AI plan
export function useRegeneratePlan() {
  const { workspaceId } = useWorkspace();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const mutate = async (
    planId: string,
    options?: { onSuccess?: () => void; onError?: (err: Error) => void }
  ) => {
    setIsPending(true);
    setError(null);
    try {
      await pythonRequest('POST', `/api/workspaces/${workspaceId}/plans/${planId}/regenerate`, {});
      options?.onSuccess?.();
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to regenerate plan');
      setError(error);
      console.error('[useRegeneratePlan] Error:', err);
      options?.onError?.(error);
    } finally {
      setIsPending(false);
    }
  };

  const mutateAsync = async (planId: string) => {
    setIsPending(true);
    setError(null);
    try {
      const result = await pythonRequest<{ success: boolean; plan_id?: string }>('POST', `/api/workspaces/${workspaceId}/plans/${planId}/regenerate`, {});
      return result;
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to regenerate plan'));
      throw err;
    } finally {
      setIsPending(false);
    }
  };

  return {
    mutate,
    mutateAsync,
    isPending,
    isError: !!error,
    error,
  };
}

// Customer Intel (mock - AI-powered feature not yet implemented)
export function useCustomerIntel(customerId: string) {
  // Mock customer intel data
  const mockIntel = {
    customer_name: 'Customer',
    engagement: {
      level: 'Moderate' as 'Strong' | 'Moderate' | 'Weak' | 'Unknown',
      activity_bars: [0.8, 0.6, 0.9, 0.7, 0.5, 0.8, 0.6],
      description: 'Regular engagement with some variation',
      evidence: null,
    },
    transmissions: [],
    sentiment: {
      state: 'neutral' as 'positive' | 'neutral' | 'negative',
      quote: null,
      summary: 'No recent sentiment signals',
    },
  };

  return {
    data: mockIntel,
    isLoading: false,
    isError: false,
    error: null,
  };
}

// ============================================================================
// Integrations
// ============================================================================

import type { IntegrationType, Integration, IntegrationsListResponse, OAuthStartResponse } from './api';

// Re-export integration types for use in other modules
export type { IntegrationType, Integration };

/**
 * Hook to fetch integrations for the current workspace.
 */
export function useIntegrations() {
  const { workspaceId } = useWorkspace();
  const [data, setData] = useState<Integration[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    if (!workspaceId) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await pythonRequest<IntegrationsListResponse>(
        'GET',
        `/integrations?workspace_id=${workspaceId}`
      );
      setData(response.integrations);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to fetch integrations'));
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  // Fetch on mount and when workspaceId changes
  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, isLoading, error, refetch };
}

/**
 * Hook to get integration status.
 */
export function useIntegrationStatus(provider: IntegrationType) {
  const { workspaceId } = useWorkspace();
  const [data, setData] = useState<{
    integration_type: string;
    status: string;
    connected: boolean;
    last_sync_at: string | null;
    last_error: string | null;
  } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    if (!workspaceId) {
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const result = await pythonRequest<{
        integration_type: string;
        status: string;
        connected: boolean;
        last_sync_at: string | null;
        last_error: string | null;
      }>(
        'GET',
        `/integrations/${provider}/status?workspace_id=${workspaceId}`
      );
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to fetch integration status'));
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, provider]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, isLoading, error, refetch };
}

/**
 * Hook to connect an integration (start OAuth flow).
 */
export function useConnectIntegration() {
  const { workspaceId } = useWorkspace();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const connect = async (provider: IntegrationType) => {
    if (!workspaceId) {
      throw new Error('No workspace selected');
    }

    setIsPending(true);
    setError(null);

    try {
      // Get the OAuth URL from the backend
      const response = await pythonRequest<OAuthStartResponse>(
        'GET',
        `/integrations/${provider}/auth/url?workspace_id=${workspaceId}`
      );

      // Open in a popup or redirect
      window.location.href = response.authorization_url;
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to start OAuth flow');
      setError(err);
      throw err;
    } finally {
      setIsPending(false);
    }
  };

  return { connect, isPending, error };
}

/**
 * Hook to disconnect an integration.
 */
export function useDisconnectIntegration() {
  const { workspaceId } = useWorkspace();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const disconnect = async (provider: IntegrationType) => {
    if (!workspaceId) {
      throw new Error('No workspace selected');
    }

    setIsPending(true);
    setError(null);

    try {
      await pythonRequest(
        'DELETE',
        `/integrations/${provider}?workspace_id=${workspaceId}`
      );
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to disconnect integration');
      setError(err);
      throw err;
    } finally {
      setIsPending(false);
    }
  };

  return { disconnect, isPending, error };
}

// Re-export types that components might need
export type { CustomerLifecycle, SignalKind, SignalState };

// ============================================================================
// Team Management
// ============================================================================

export interface JoinRequest {
  id: string;
  userId: string;
  userEmail: string;
  status: 'pending' | 'approved' | 'rejected';
  createdAt: string;
}

export interface TeamMember {
  userId: string;
  email: string;
  displayName: string | null;
  avatarUrl: string | null;
  role: 'owner' | 'admin' | 'member';
  joinedAt: string;
}

/**
 * Hook to fetch pending join requests for the current workspace.
 */
export function usePendingJoinRequests() {
  const { workspaceId } = useWorkspace();
  const query = useGetPendingJoinRequests(
    workspaceId ? { workspaceId } : undefined
  );

  const requests: JoinRequest[] = (query.data?.workspaceJoinRequests || []).map(r => ({
    id: r.id,
    userId: r.userId,
    userEmail: r.userEmail,
    status: r.status as JoinRequest['status'],
    createdAt: r.createdAt,
  }));

  return {
    data: requests,
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
  };
}

/**
 * Hook to approve a join request.
 */
export function useApproveJoinRequest() {
  const { user } = useAuth();
  const approveMutation = useApproveJoinRequestDC();
  const addMemberMutation = useAddWorkspaceMember();

  const approve = async (request: JoinRequest, workspaceId: string) => {
    if (!user?.uid) throw new Error('Not authenticated');

    // First approve the request
    await approveMutation.mutateAsync({
      requestId: request.id,
      reviewedByUserId: user.uid,
    });

    // Then add the user to the workspace
    await addMemberMutation.mutateAsync({
      workspaceId,
      userId: request.userId,
      role: WorkspaceRole.member, // Default to member role
    });
  };

  return {
    approve,
    isPending: approveMutation.isPending || addMemberMutation.isPending,
    error: approveMutation.error || addMemberMutation.error,
  };
}

/**
 * Hook to reject a join request.
 */
export function useRejectJoinRequest() {
  const { user } = useAuth();
  const rejectMutation = useRejectJoinRequestDC();

  const reject = async (requestId: string) => {
    if (!user?.uid) throw new Error('Not authenticated');

    await rejectMutation.mutateAsync({
      requestId,
      reviewedByUserId: user.uid,
    });
  };

  return {
    reject,
    isPending: rejectMutation.isPending,
    error: rejectMutation.error,
  };
}

// ============================================================================
// Integration Sync Hooks
// ============================================================================

interface SyncResponse {
  success: boolean;
  message: string;
  updated_fields: string[];
  source?: string;
}

interface SyncAllResponse {
  success: boolean;
  synced_count: number;
  skipped_count: number;
  error_count: number;
  errors: string[];
}

/**
 * Hook to manually sync/refresh data from a single external page.
 * Use this to pull latest data without polling.
 */
export function useSyncPage() {
  const { workspaceId } = useWorkspace();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const sync = async (pageId: string, source: string = 'notion'): Promise<SyncResponse> => {
    if (!workspaceId) throw new Error('No workspace selected');

    setIsPending(true);
    setError(null);

    try {
      const result = await pythonRequest<SyncResponse>(
        'POST',
        `/integrations/sync/${pageId}?workspace_id=${workspaceId}&source=${source}`,
      );
      return result;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Sync failed');
      setError(error);
      throw error;
    } finally {
      setIsPending(false);
    }
  };

  return {
    sync,
    isPending,
    error,
  };
}

/**
 * Hook to sync all customers from their external sources.
 * Iterates through customers with external_source set and refreshes them.
 */
export function useSyncAllCustomers() {
  const { workspaceId } = useWorkspace();
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const syncAll = async (): Promise<SyncAllResponse> => {
    if (!workspaceId) throw new Error('No workspace selected');

    setIsPending(true);
    setError(null);

    try {
      const result = await pythonRequest<SyncAllResponse>(
        'POST',
        `/integrations/sync/all?workspace_id=${workspaceId}`,
      );
      return result;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Sync failed');
      setError(error);
      throw error;
    } finally {
      setIsPending(false);
    }
  };

  return {
    syncAll,
    isPending,
    error,
  };
}

// Alias for backwards compatibility
export const useSyncNotionPage = useSyncPage;

// ============================================================================
// Notion Databases
// ============================================================================

export interface NotionDatabase {
  id: string;
  name: string;
  icon: string | null;
  url: string | null;
}

export interface NotionDatabasesResponse {
  databases: NotionDatabase[];
}

/**
 * Hook to fetch Notion databases shared with the integration.
 * Only fetches when Notion is connected.
 */
export function useNotionDatabases(options?: { enabled?: boolean }) {
  const { workspaceId } = useWorkspace();
  const [data, setData] = useState<NotionDatabase[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const enabled = options?.enabled ?? true;

  const fetchDatabases = useCallback(async () => {
    if (!workspaceId || !enabled) return;

    setIsLoading(true);
    setError(null);

    try {
      const result = await pythonRequest<NotionDatabasesResponse>(
        'GET',
        `/integrations/notion/databases?workspace_id=${workspaceId}`
      );
      setData(result.databases || []);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to fetch Notion databases'));
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, enabled]);

  useEffect(() => {
    if (enabled && workspaceId) {
      fetchDatabases();
    }
  }, [enabled, workspaceId, fetchDatabases]);

  return {
    data,
    isLoading,
    error,
    refetch: fetchDatabases,
  };
}

/**
 * Normalize a property name for matching (lowercase, remove underscores/spaces/dashes)
 */
function normalizePropertyName(name: string): string {
  return name.toLowerCase().replace(/[_\-\s]/g, '');
}

/**
 * Detect Notion database properties and create smart field mappings.
 * Looks for common variations of customer field names.
 * Handles underscores, spaces, dashes in property names.
 */
async function detectFieldMappings(workspaceId: string, databaseId: string) {
  // Fetch database schema to see available properties
  const schema = await pythonRequest<{
    id: string;
    name: string;
    properties: Array<{ name: string; type: string; options?: string[] }>;
  }>(
    'GET',
    `/integrations/notion/databases/${databaseId}/schema?workspace_id=${workspaceId}`
  );

  const properties = schema.properties.map(p => p.name);
  const mappings: Array<{ notion_property: string; herofy_field: string }> = [];

  // Name field patterns (required) - matches: name, company_name, customer_name, account_name, etc.
  const namePatterns = ['name', 'title', 'company', 'companyname', 'customername', 'accountname', 'clientname', 'organization', 'org'];
  const nameField = properties.find(p => {
    const normalized = normalizePropertyName(p);
    return namePatterns.some(pattern => normalized === pattern || normalized.endsWith(pattern));
  });
  if (nameField) {
    mappings.push({ notion_property: nameField, herofy_field: 'name' });
  }

  // Lifecycle/stage patterns - matches: stage, lifecycle, status, customer_stage, etc.
  const lifecyclePatterns = ['stage', 'lifecycle', 'status', 'phase', 'state', 'customerstage', 'accountstage'];
  const lifecycleField = properties.find(p => {
    const normalized = normalizePropertyName(p);
    return lifecyclePatterns.some(pattern => normalized === pattern || normalized.endsWith(pattern));
  });
  if (lifecycleField) {
    mappings.push({ notion_property: lifecycleField, herofy_field: 'lifecycle' });
  }

  // Tier patterns - matches: tier, plan, package, customer_tier, etc.
  const tierPatterns = ['tier', 'plan', 'package', 'level', 'segment', 'customertier', 'accounttier'];
  const tierField = properties.find(p => {
    const normalized = normalizePropertyName(p);
    return tierPatterns.some(pattern => normalized === pattern || normalized.endsWith(pattern));
  });
  if (tierField) {
    mappings.push({ notion_property: tierField, herofy_field: 'tier' });
  }

  // ARR patterns - matches: arr, revenue, mrr, contract_value, etc.
  const arrPatterns = ['arr', 'revenue', 'mrr', 'contract', 'value', 'contractvalue', 'annualrevenue'];
  const arrField = properties.find(p => {
    const normalized = normalizePropertyName(p);
    return arrPatterns.some(pattern => normalized === pattern || normalized.endsWith(pattern));
  });
  if (arrField) {
    mappings.push({ notion_property: arrField, herofy_field: 'arr' });
  }

  return { mappings, availableProperties: properties };
}

export interface ImportResult {
  customers: Array<{ id: string; name: string; tier?: string; lifecycle?: string }>;
  errors: string[];
  imported_count: number;
  availableProperties?: string[];
  detectedMappings?: Array<{ notion_property: string; herofy_field: string }>;
  databaseId?: string;
}

/**
 * Hook to fetch Notion database schema (property names).
 */
export interface NotionPropertySchema {
  name: string;
  type: string;
  options?: string[];
}

export function useNotionDatabaseSchema() {
  const { workspaceId } = useWorkspace();

  // Fetch just property names (for backwards compatibility)
  const fetchSchema = useCallback(async (databaseId: string): Promise<string[]> => {
    if (!workspaceId) throw new Error('No workspace ID');

    try {
      const schema = await pythonRequest<{
        name: string;
        properties: NotionPropertySchema[];
      }>(
        'GET',
        `/integrations/notion/databases/${databaseId}/schema?workspace_id=${workspaceId}`
      );
      return schema.properties.map(p => p.name);
    } catch (e) {
      console.error('Failed to fetch Notion schema:', e);
      return [];
    }
  }, [workspaceId]);

  // Fetch full schema with options (for bucket preview)
  const fetchFullSchema = useCallback(async (databaseId: string): Promise<NotionPropertySchema[]> => {
    if (!workspaceId) throw new Error('No workspace ID');

    try {
      const schema = await pythonRequest<{
        name: string;
        properties: NotionPropertySchema[];
      }>(
        'GET',
        `/integrations/notion/databases/${databaseId}/schema?workspace_id=${workspaceId}`
      );
      return schema.properties;
    } catch (e) {
      console.error('Failed to fetch Notion schema:', e);
      return [];
    }
  }, [workspaceId]);

  return { fetchSchema, fetchFullSchema };
}

/**
 * Hook to clear all customers for the current workspace (for testing).
 */
export function useClearCustomers() {
  const { workspaceId } = useWorkspace();
  const [isLoading, setIsLoading] = useState(false);

  const clearCustomers = useCallback(async () => {
    if (!workspaceId) throw new Error('No workspace ID');

    setIsLoading(true);
    try {
      const { deleteAllCustomersForWorkspace } = await import('@herofy/dataconnect');
      await deleteAllCustomersForWorkspace({ workspaceId });
      console.log('✓ All customers cleared for workspace:', workspaceId);
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  return { clearCustomers, isLoading };
}

/**
 * Hook to import customers from a Notion database.
 * Auto-detects field mappings based on common property names.
 */
export function useImportNotionCustomers() {
  const { workspaceId } = useWorkspace();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const importCustomers = useCallback(async (databaseId: string): Promise<ImportResult> => {
    if (!workspaceId) throw new Error('No workspace ID');

    setIsLoading(true);
    setError(null);

    try {
      // Detect field mappings from the database schema
      const { mappings, availableProperties } = await detectFieldMappings(workspaceId, databaseId);

      if (mappings.length === 0 || !mappings.some(m => m.herofy_field === 'name')) {
        // Return failure with available properties so UI can show them
        return {
          customers: [],
          errors: [`Could not auto-detect customer name field. We look for: Name, Title, Company, Customer, Account, Client, Organization (case-insensitive, with or without underscores)`],
          imported_count: 0,
          availableProperties,
          detectedMappings: mappings,
          databaseId,
        };
      }

      console.log('Detected field mappings:', mappings);
      console.log('Available properties:', availableProperties);

      const result = await pythonRequest<{
        customers: Array<{ id: string; name: string; tier?: string; lifecycle?: string }>;
        errors: string[];
        imported_count: number;
      }>(
        'POST',
        `/integrations/notion/import?workspace_id=${workspaceId}`,
        {
          database_id: databaseId,
          field_mappings: mappings,
          status_field: null,
          import_status_values: [],
          skip_enrichment: true,  // Skip during setup, trigger at handoff stage
        }
      );

      return {
        ...result,
        availableProperties,
        detectedMappings: mappings,
        databaseId,
      };
    } catch (e) {
      const errorObj = e instanceof Error ? e : new Error('Failed to import customers');
      setError(errorObj);
      throw errorObj;
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  /**
   * Re-import customers with a specific column mapped to lifecycle.
   * This updates existing customers via upsert.
   */
  const reimportWithLifecycleColumn = useCallback(async (
    databaseId: string,
    lifecycleColumn: string
  ): Promise<ImportResult> => {
    if (!workspaceId) throw new Error('No workspace ID');

    setIsLoading(true);
    setError(null);

    try {
      // Get base mappings from auto-detection
      const { mappings: baseMappings, availableProperties } = await detectFieldMappings(workspaceId, databaseId);

      // Remove any existing lifecycle mapping and add our manual one
      const mappings = baseMappings.filter(m => m.herofy_field !== 'lifecycle');
      mappings.push({ notion_property: lifecycleColumn, herofy_field: 'lifecycle' });

      console.log('Re-importing with manual lifecycle mapping:', lifecycleColumn);
      console.log('Full mappings:', mappings);

      const result = await pythonRequest<{
        customers: Array<{ id: string; name: string; tier?: string; lifecycle?: string }>;
        errors: string[];
        imported_count: number;
      }>(
        'POST',
        `/integrations/notion/import?workspace_id=${workspaceId}`,
        {
          database_id: databaseId,
          field_mappings: mappings,
          status_field: null,
          import_status_values: [],
          skip_enrichment: true,  // Skip during setup, trigger at handoff stage
        }
      );

      console.log('Re-import result:', result);
      console.log('Customers with lifecycle:', result.customers?.map(c => ({ name: c.name, lifecycle: c.lifecycle })));

      return {
        ...result,
        availableProperties,
        detectedMappings: mappings,
        databaseId,
      };
    } catch (e) {
      const errorObj = e instanceof Error ? e : new Error('Failed to re-import customers');
      setError(errorObj);
      throw errorObj;
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  return {
    importCustomers,
    reimportWithLifecycleColumn,
    isLoading,
    error,
  };
}

// ============================================================================
// Notion Page Linking (Multi-page support)
// ============================================================================

export interface NotionPageResult {
  id: string;
  title: string;
  url: string;
  icon: string | null;
  last_edited: string | null;
  parent_type: string | null;
}

// LinkedPage is imported from api.ts and re-exported for consumers
export type { LinkedPage };

/**
 * Hook to search Notion pages the user can access.
 * Used by the "Browse Notion pages" modal.
 */
export function useSearchNotionPages() {
  const { workspaceId } = useWorkspace();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const searchPages = useCallback(async (query?: string, cursor?: string): Promise<{
    pages: NotionPageResult[];
    has_more: boolean;
    next_cursor: string | null;
  }> => {
    if (!workspaceId) throw new Error('No workspace ID');

    setIsLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({ workspace_id: workspaceId });
      if (query) params.set('query', query);
      if (cursor) params.set('cursor', cursor);

      const result = await pythonRequest<{
        pages: NotionPageResult[];
        has_more: boolean;
        next_cursor: string | null;
      }>('GET', `/integrations/notion/pages?${params}`);

      return result;
    } catch (e) {
      const errorObj = e instanceof Error ? e : new Error('Failed to search Notion pages');
      setError(errorObj);
      throw errorObj;
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  return {
    searchPages,
    isLoading,
    error,
  };
}

/**
 * Hook to validate a pasted Notion link and check access.
 */
export function useValidateNotionLink() {
  const { workspaceId } = useWorkspace();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const validateLink = useCallback(async (url: string): Promise<{
    valid: boolean;
    has_access: boolean;
    page_id: string | null;
    title: string | null;
    url: string | null;
    error: string | null;
  }> => {
    if (!workspaceId) throw new Error('No workspace ID');

    setIsLoading(true);
    setError(null);

    try {
      const result = await pythonRequest<{
        valid: boolean;
        has_access: boolean;
        page_id: string | null;
        title: string | null;
        url: string | null;
        error: string | null;
      }>('POST', `/integrations/notion/pages/validate?workspace_id=${workspaceId}`, { url });

      return result;
    } catch (e) {
      const errorObj = e instanceof Error ? e : new Error('Failed to validate Notion link');
      setError(errorObj);
      throw errorObj;
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  return {
    validateLink,
    isLoading,
    error,
  };
}

/**
 * Hook to link an external page to a customer.
 * Used for handoff docs, trackers, notes, etc.
 */
export function useLinkPageToCustomer() {
  const { workspaceId } = useWorkspace();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const linkPage = useCallback(async (
    customerId: string,
    page: {
      source: string;
      page_id: string;
      page_type: string;  // "handoff" | "tracker" | "notes" | "other"
      url: string;
      title: string;
    }
  ): Promise<{ success: boolean; linked_pages: LinkedPage[] }> => {
    if (!workspaceId) throw new Error('No workspace ID');

    setIsLoading(true);
    setError(null);

    try {
      const result = await pythonRequest<{
        success: boolean;
        linked_pages: LinkedPage[];
      }>('POST', `/integrations/customers/${customerId}/linked-pages?workspace_id=${workspaceId}`, page);

      return result;
    } catch (e) {
      const errorObj = e instanceof Error ? e : new Error('Failed to link page');
      setError(errorObj);
      throw errorObj;
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  return {
    linkPage,
    isLoading,
    error,
  };
}

export function useUnlinkPageFromCustomer() {
  const { workspaceId } = useWorkspace();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const unlinkPage = useCallback(async (
    customerId: string,
    pageId: string  // Can be page ID or title
  ): Promise<{ success: boolean; linked_pages: LinkedPage[] }> => {
    if (!workspaceId) throw new Error('No workspace ID');

    setIsLoading(true);
    setError(null);

    try {
      const result = await pythonRequest<{
        success: boolean;
        linked_pages: LinkedPage[];
      }>('DELETE', `/integrations/customers/${customerId}/linked-pages/${encodeURIComponent(pageId)}?workspace_id=${workspaceId}`);

      return result;
    } catch (e) {
      const errorObj = e instanceof Error ? e : new Error('Failed to unlink page');
      setError(errorObj);
      throw errorObj;
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  return {
    unlinkPage,
    isLoading,
    error,
  };
}

// ============================================================================
// Customer Classification (AI-powered)
// ============================================================================

export interface CustomerClassification {
  customer_id: string;
  group: 'not_yet_customer' | 'new_customer' | 'pointer_needed' | 'ready_to_confirm';
  confidence: number;
  reasoning: string;
  what_i_know: string[];
  what_im_uncertain_about: string[];
  suggested_playbook?: string;
  playbook_code?: string;
  current_state?: string;
  next_milestone?: string;
}

export interface ClassifyCustomersResult {
  success: boolean;
  classifications: CustomerClassification[];
  message?: string;
}

/**
 * Hook to classify customers using AI during setup.
 * Analyzes CRM data + linked Notion pages to determine groupings.
 * Persists classifications to localStorage for refresh resilience.
 */
export function useClassifyCustomers() {
  const { workspaceId } = useWorkspace();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [classifications, setClassifications] = useState<Map<string, CustomerClassification>>(new Map());
  const [hasLoadedFromStorage, setHasLoadedFromStorage] = useState(false);

  // Storage key for this workspace's classifications
  const storageKey = workspaceId ? `herofy_classifications_${workspaceId}` : null;

  // Load from localStorage when workspaceId becomes available
  useEffect(() => {
    if (!storageKey || hasLoadedFromStorage) return;
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored) as Record<string, CustomerClassification>;
        const loadedMap = new Map<string, CustomerClassification>(Object.entries(parsed));
        console.log('Loaded classifications from localStorage:', loadedMap.size);
        setClassifications(loadedMap);
      }
    } catch (e) {
      console.warn('Failed to load classifications from localStorage:', e);
    }
    setHasLoadedFromStorage(true);
  }, [storageKey, hasLoadedFromStorage]);

  // Persist to localStorage whenever classifications change
  useEffect(() => {
    if (!storageKey || classifications.size === 0 || !hasLoadedFromStorage) return;
    try {
      const obj = Object.fromEntries(classifications);
      localStorage.setItem(storageKey, JSON.stringify(obj));
      console.log('Saved classifications to localStorage:', classifications.size);
    } catch (e) {
      console.warn('Failed to save classifications to localStorage:', e);
    }
  }, [storageKey, classifications, hasLoadedFromStorage]);

  const classifyCustomers = useCallback(async (customerIds?: string[]): Promise<ClassifyCustomersResult> => {
    if (!workspaceId) {
      throw new Error('No workspace selected');
    }

    setIsLoading(true);
    setError(null);

    try {
      // Get auth token
      const auth = getAuth();
      const user = auth.currentUser;
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (user) {
        const token = await user.getIdToken();
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(
        `${import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081'}/api/workspaces/${workspaceId}/ai/classify-customers`,
        {
          method: 'POST',
          headers,
          body: JSON.stringify({
            customer_ids: customerIds,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`Classification failed: ${response.statusText}`);
      }

      const result: ClassifyCustomersResult = await response.json();

      // Update the classifications map
      if (result.success && result.classifications) {
        const newMap = new Map(classifications);
        for (const c of result.classifications) {
          newMap.set(c.customer_id, c);
        }
        setClassifications(newMap);
      }

      return result;
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Classification failed');
      setError(err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, classifications]);

  // Get classification for a specific customer
  const getClassification = useCallback((customerId: string): CustomerClassification | undefined => {
    return classifications.get(customerId);
  }, [classifications]);

  // Get all customers by group
  const getCustomersByGroup = useCallback((group: CustomerClassification['group']): CustomerClassification[] => {
    return Array.from(classifications.values()).filter(c => c.group === group);
  }, [classifications]);

  // Clear all classifications (for re-import or testing)
  const clearClassifications = useCallback(() => {
    setClassifications(new Map());
    if (storageKey) {
      localStorage.removeItem(storageKey);
    }
  }, [storageKey]);

  // Manually update a customer's classification (for user overrides)
  const updateClassification = useCallback(async (
    customerId: string,
    group: CustomerClassification['group'],
    reasoning?: string
  ): Promise<void> => {
    if (!workspaceId) {
      throw new Error('No workspace selected');
    }

    // Get auth token
    const auth = getAuth();
    const user = auth.currentUser;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (user) {
      const token = await user.getIdToken();
      headers['Authorization'] = `Bearer ${token}`;
    }

    // Call backend to update classification
    const response = await fetch(
      `${import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081'}/api/workspaces/${workspaceId}/customers/${customerId}/classification`,
      {
        method: 'PUT',
        headers,
        body: JSON.stringify({
          group,
          confidence: 100, // User override is 100% confidence
          reasoning: reasoning || `Manually set to ${group} by user`,
        }),
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to update classification: ${response.statusText}`);
    }

    // Update local state
    const newClassification: CustomerClassification = {
      customer_id: customerId,
      group,
      confidence: 100,
      reasoning: reasoning || `Manually set to ${group} by user`,
      what_i_know: [],
      what_im_uncertain_about: [],
    };
    setClassifications(prev => {
      const newMap = new Map(prev);
      newMap.set(customerId, newClassification);
      return newMap;
    });
  }, [workspaceId]);

  return {
    classifyCustomers,
    getClassification,
    getCustomersByGroup,
    clearClassifications,
    updateClassification,
    classifications,
    hasLoadedFromStorage,
    isLoading,
    error,
  };
}

/**
 * Hook for streaming customer classification with real-time Firestore updates.
 *
 * Unlike useClassifyCustomers which does batch classification, this hook:
 * 1. Starts classification in the background
 * 2. Returns immediately
 * 3. Progress is tracked via useSetupProgress from realtime-hooks.ts
 */
export function useClassifyCustomersStreaming() {
  const { workspaceId } = useWorkspace();
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [startedAt, setStartedAt] = useState<Date | null>(null);

  const startClassification = useCallback(async (customerIds?: string[]): Promise<{
    success: boolean;
    customerCount: number;
    message?: string;
  }> => {
    if (!workspaceId) {
      throw new Error('No workspace selected');
    }

    setIsStarting(true);
    setError(null);

    try {
      const result = await pythonRequest<{
        success: boolean;
        workspace_id: string;
        customer_count: number;
        message?: string;
      }>('POST', `/api/workspaces/${workspaceId}/ai/classify-customers-streaming`, {
        customer_ids: customerIds,
      });

      if (result.success) {
        setStartedAt(new Date());
      }

      return {
        success: result.success,
        customerCount: result.customer_count,
        message: result.message,
      };
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to start classification');
      setError(err);
      throw err;
    } finally {
      setIsStarting(false);
    }
  }, [workspaceId]);

  return {
    startClassification,
    isStarting,
    startedAt,
    error,
  };
}

// ============================================================================
// Weekly Dispatch
// ============================================================================

export interface WeeklyDayItem {
  id: string;
  title: string;
  type: 'meeting' | 'need' | 'handoff';
  customer_name: string;
  scheduled_at?: string;
}

export interface WeeklyDay {
  day: string;
  date: string;
  count: number;
  items: WeeklyDayItem[];
}

export interface WeeklyDispatchData {
  days: WeeklyDay[];
  resolved_summary: string | null;
  carried_forward_summary: string | null;
}

/**
 * Hook to fetch weekly dispatch data - meetings and key activities grouped by day.
 */
export function useWeeklyDispatch() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const meetingsQuery = useGetMeetings(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform meetings data into weekly format
  const transformedData = useMemo((): WeeklyDispatchData | undefined => {
    if (!meetingsQuery.data) return undefined;

    // Get the current week's Monday and Friday
    const now = new Date();
    const currentDay = now.getDay();
    const monday = new Date(now);
    monday.setDate(now.getDate() - (currentDay === 0 ? 6 : currentDay - 1));
    monday.setHours(0, 0, 0, 0);

    const friday = new Date(monday);
    friday.setDate(monday.getDate() + 4);
    friday.setHours(23, 59, 59, 999);

    // Day names for the week
    const dayNames = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY'];

    // Initialize days array
    const days: WeeklyDay[] = dayNames.map((day, index) => {
      const date = new Date(monday);
      date.setDate(monday.getDate() + index);
      return {
        day,
        date: date.toISOString().split('T')[0],
        count: 0,
        items: [],
      };
    });

    // Group meetings by day
    meetingsQuery.data.meetings.forEach(meeting => {
      const meetingDate = new Date(meeting.scheduledAt);

      // Check if meeting is in this week
      if (meetingDate >= monday && meetingDate <= friday) {
        const dayIndex = meetingDate.getDay() - 1; // Monday = 0

        if (dayIndex >= 0 && dayIndex < 5) {
          days[dayIndex].items.push({
            id: meeting.id,
            title: meeting.title,
            type: 'meeting',
            customer_name: meeting.customer.name,
            scheduled_at: meeting.scheduledAt,
          });
          days[dayIndex].count++;
        }
      }
    });

    // Sort items within each day by scheduled time
    days.forEach(day => {
      day.items.sort((a, b) => {
        if (!a.scheduled_at || !b.scheduled_at) return 0;
        return new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime();
      });
    });

    return {
      days,
      resolved_summary: null,
      carried_forward_summary: null,
    };
  }, [meetingsQuery.data]);

  return {
    data: transformedData,
    isLoading: meetingsQuery.isLoading || wsLoading,
    error: meetingsQuery.error,
    refetch: meetingsQuery.refetch,
  };
}

// Hook to find agent runs with pending questions that are blocking a specific need
export function useAgentRunForBlockingNeed(needId: string | null) {
  const query = useGetAgentRunForBlockingNeed(
    { needId: needId || '' },
    { enabled: !!needId }
  );

  const transformedData = useMemo(() => {
    const agentRuns = query.data?.agentRuns || [];
    if (agentRuns.length === 0) return null;

    const run = agentRuns[0];
    let questions: AgentQuestion[] = [];

    if (run.clarifyingQuestions) {
      try {
        const parsed = JSON.parse(run.clarifyingQuestions);
        // Use shared normalizer for consistent handling of AI variations
        questions = parsed.map((q: any, index: number) => normalizeAgentQuestion(q, index));
      } catch (e) {
        console.warn('Failed to parse clarifying questions:', e);
      }
    }

    return {
      agent_run_id: run.id,
      agent_name: run.agentName,
      status: run.status,
      current_step: run.currentStep,
      questions,
      customer_name: run.customer?.name,
    };
  }, [query.data]);

  return {
    ...query,
    data: transformedData,
  };
}

// ============================================================================
// Sidekick Hooks (AI Native System)
// ============================================================================

export interface SidekickUnansweredCount {
  count: number;
  breakdown: {
    critical: number;
    normal: number;
  };
}

export interface SidekickAlertItem {
  id: string;
  text: string;
  is_blocking: boolean;
  agent_run_id?: string;
  question?: string | null;
  headline?: string | null;
  context?: string | null;
}

export interface SidekickAlert {
  has_questions: boolean;
  count: number;
  items: SidekickAlertItem[];
}

export interface SidekickItem {
  id: string;
  type: 'tip' | 'asking' | 'observed' | 'working' | 'resolved';
  text?: string;
  question?: string;
  why?: string;
  is_blocking?: boolean;
  task?: string;
  step?: string;
  step_num?: number;
  total_steps?: number;
  resolution?: string;
  resolved_by?: string;
  resolved_at?: string;
  timestamp_label?: string;
  is_current_item?: boolean;
  agent_run_id?: string;
  created_at: string;
}

export interface SidekickCustomerMeta {
  id: string;
  name: string;
  refcode?: string;
  tier?: string;
  arr?: string;
  lifecycle?: string;
  day?: string;
  health?: string;
  health_color?: string;
  health_score?: number;
  sentiment?: string;
  sentiment_color?: string;
  signals?: Array<{ kind: string; state: string; sentence: string }>;
}

export interface SidekickItemsResponse {
  customer: SidekickCustomerMeta;
  items: SidekickItem[];
  open_count: number;
  resolved_count: number;
}

/**
 * Hook to fetch unanswered sidekick questions count (for nav badge).
 * Uses DataConnect GetSidekickUnansweredCount query.
 */
export function useSidekickUnansweredCount() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetSidekickUnansweredCount(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Count asking items that haven't been resolved
  const count = useMemo(() => {
    if (!query.data?.sidekickItems) return 0;
    return query.data.sidekickItems.length;
  }, [query.data]);

  return {
    data: { count },
    isLoading: query.isLoading || wsLoading,
    error: query.error,
    refetch: query.refetch,
  };
}

/**
 * Hook to fetch sidekick alert for a customer (for contextual banner).
 */
export function useSidekickAlert(customerId: string | undefined) {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetSidekickAlert(
    { workspaceId: workspaceId || '', customerId: customerId || '' },
    { enabled: !!workspaceId && !!customerId && !wsLoading }
  );

  // Transform to expected SidekickAlert format
  const data = useMemo((): SidekickAlert | null => {
    if (!query.data?.sidekickItems?.length) return null;

    return {
      has_questions: query.data.sidekickItems.length > 0,
      count: query.data.sidekickItems.length,
      items: query.data.sidekickItems.map(item => ({
        id: item.id,
        text: item.question || '',
        is_blocking: item.isBlocking || false,
        agent_run_id: item.agentRun?.id || undefined,
      })),
    };
  }, [query.data]);

  return {
    data,
    isLoading: query.isLoading || wsLoading,
    error: query.error,
    refetch: query.refetch,
  };
}

/**
 * Hook to fetch all sidekick items for a customer (for right rail).
 */
export function useSidekickItems(customerId: string | undefined, _currentItemId?: string) {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetSidekickItems(
    { workspaceId: workspaceId || '', customerId: customerId || '' },
    { enabled: !!workspaceId && !!customerId && !wsLoading }
  );

  // Transform to expected SidekickItemsResponse format
  const data = useMemo((): SidekickItemsResponse | null => {
    if (!query.data) return null;

    const customer = query.data.customer;
    const items = query.data.sidekickItems || [];

    // Count open vs resolved
    const openItems = items.filter(item => !item.resolvedAt);
    const resolvedItems = items.filter(item => item.resolvedAt);

    // Helper to get health display values
    const getHealthDisplay = (health: string | null, score: number | null) => {
      const displayScore = score ?? 50;
      const healthLabels: Record<string, string> = {
        strong: 'Strong',
        healthy: 'Healthy',
        stable: 'Stable',
        at_risk: 'At Risk',
        deteriorating: 'Deteriorating',
      };
      const healthColors: Record<string, string> = {
        strong: '#10b981',
        healthy: '#10b981',
        stable: '#e5dcc8',
        at_risk: '#d96942',
        deteriorating: '#d96942',
      };
      const healthKey = health || 'stable';
      return {
        label: `${healthLabels[healthKey] || 'Stable'} (${displayScore})`,
        color: healthColors[healthKey] || '#e5dcc8',
        score: displayScore,
      };
    };

    // Helper to get sentiment from signals
    const getSentimentFromSignals = (signals: Array<{ kind: string; state: string }> | undefined) => {
      if (!signals) return null;
      const sentimentSignal = signals.find(s => s.kind === 'sentiment');
      if (!sentimentSignal) return null;
      const stateLabels: Record<string, { label: string; color: string }> = {
        ok: { label: 'Positive', color: '#10b981' },
        warn: { label: 'Guarded', color: '#f59e0b' },
        risk: { label: 'Negative', color: '#d96942' },
      };
      return stateLabels[sentimentSignal.state] || null;
    };

    const healthDisplay = customer ? getHealthDisplay(customer.relationshipHealth, customer.relationshipHealthScore) : null;
    const sentiment = customer ? getSentimentFromSignals(customer.signals_on_customer) : null;

    return {
      customer: customer ? {
        id: customer.id,
        name: customer.name,
        refcode: customer.slug?.toUpperCase().slice(0, 8),
        tier: customer.tier || undefined,
        arr: customer.arrCents ? `$${(Number(customer.arrCents) / 100).toLocaleString()}` : undefined,
        lifecycle: customer.lifecycle,
        day: customer.onboardingDayCurrent && customer.onboardingDayTotal
          ? `${customer.onboardingDayCurrent}/${customer.onboardingDayTotal}`
          : undefined,
        // Health data
        health: healthDisplay?.label,
        health_color: healthDisplay?.color,
        health_score: healthDisplay?.score,
        // Sentiment from signals
        sentiment: sentiment?.label,
        sentiment_color: sentiment?.color,
        // Raw signals for more detailed display
        signals: customer.signals_on_customer?.map(s => ({
          kind: s.kind,
          state: s.state,
          sentence: s.sentence,
        })),
      } : {
        id: customerId || '',
        name: 'Unknown Customer',
      },
      items: items.map((item): SidekickItem => {
        const result: SidekickItem = {
          id: item.id,
          type: item.type as SidekickItem['type'],
          created_at: item.createdAt,
        };
        if (item.text) result.text = item.text;
        if (item.question) result.question = item.question;
        if (item.why) result.why = item.why;
        if (item.isBlocking != null) result.is_blocking = item.isBlocking;
        if (item.task) result.task = item.task;
        if (item.step) result.step = item.step;
        if (item.stepNum != null) result.step_num = item.stepNum;
        if (item.totalSteps != null) result.total_steps = item.totalSteps;
        if (item.resolution) result.resolution = item.resolution;
        if (item.resolvedAt) result.resolved_at = item.resolvedAt;
        if (item.resolvedByUser?.displayName) result.resolved_by = item.resolvedByUser.displayName;
        if (item.agentRun?.id) result.agent_run_id = item.agentRun.id;
        if (item.timestampLabel) result.timestamp_label = item.timestampLabel;
        return result;
      }),
      open_count: openItems.length,
      resolved_count: resolvedItems.length,
    };
  }, [query.data, customerId]);

  const refetch = useServerRefetch(
    () => getSidekickItemsRef(dataConnect, { workspaceId: workspaceId || '', customerId: customerId || '' }),
    [workspaceId, customerId],
    query.refetch,
  );

  return {
    data,
    isLoading: query.isLoading || wsLoading,
    error: query.error,
    refetch,
  };
}

/**
 * Item format for Today queue sidekick cards.
 * Represents a workspace-level asking SidekickItem.
 */
export interface SidekickTodayItem {
  id: string;
  question: string;
  why?: string;
  is_blocking: boolean;
  created_at: string;
  customer_id: string;
  customer_name: string;
  customer_refcode: string;
  customer_tier?: string;
  customer_arr?: string;
  customer_lifecycle: string;
  agent_run_id?: string;
  agent_name?: string;
  agent_questions?: AgentQuestion[];
  agent_context?: string;
  need_id?: string;
  need_headline?: string;
}

/**
 * Hook to fetch all unresolved asking SidekickItems workspace-wide (for Today queue).
 * Returns items formatted for mixing into the Today queue display.
 */
export function useSidekickAskingItems() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetSidekickAskingItems(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform to SidekickTodayItem format
  const items = useMemo((): SidekickTodayItem[] => {
    if (!query.data?.sidekickItems) return [];

    return query.data.sidekickItems.map((item): SidekickTodayItem => {
      // Parse clarifying questions from agent run if available
      let agentQuestions: AgentQuestion[] = [];
      if (item.agentRun?.clarifyingQuestions) {
        try {
          const parsed = JSON.parse(item.agentRun.clarifyingQuestions);
          agentQuestions = Array.isArray(parsed) ? parsed.map((q: any, idx: number) => ({
            id: q.id || `q-${idx}`,
            text: unescapeText(q.text || q.question || ''),
            type: q.type || 'freeform',
            options: q.options || [],
          })) : [];
        } catch {
          agentQuestions = [];
        }
      }

      return {
        id: item.id,
        question: item.question || '',
        why: item.why || undefined,
        is_blocking: item.isBlocking ?? true,
        created_at: item.createdAt,
        customer_id: item.customer?.id || '',
        customer_name: item.customer?.name || 'Unknown Customer',
        customer_refcode: item.customer?.slug?.toUpperCase().slice(0, 8) || '',
        customer_tier: item.customer?.tier || undefined,
        customer_arr: item.customer?.arrCents
          ? `$${(Number(item.customer.arrCents) / 100).toLocaleString()}`
          : undefined,
        customer_lifecycle: item.customer?.lifecycle || 'active',
        agent_run_id: item.agentRun?.id || undefined,
        agent_name: item.agentRun?.agentName || undefined,
        agent_questions: agentQuestions.length > 0 ? agentQuestions : undefined,
        agent_context: item.agentRun?.pauseReason || undefined,
        need_id: item.need?.id || undefined,
        need_headline: item.need?.headline || undefined,
      };
    });
  }, [query.data]);

  const refetch = useServerRefetch(
    () => getSidekickAskingItemsRef(dataConnect, { workspaceId: workspaceId || '' }),
    [workspaceId],
    query.refetch,
  );

  return {
    items,
    isLoading: query.isLoading || wsLoading,
    error: query.error,
    refetch,
  };
}

/**
 * Demo guide: fire the organic morning sweep + drain for a workspace.
 * Runs the going-dark detector (one Quietfield catch in the seeded fixture) and
 * drains the queue so the Risk/Save play runs to its HITL pause. Reachable by the
 * anonymous demo user (the backend demo guard allows it when DEMO_ENABLED).
 */
export async function runDemoSweep(workspaceId: string): Promise<{
  workspace_id: string;
  sweep?: { signals_created?: number; errors?: number } | null;
  drain?: Record<string, unknown> | null;
}> {
  return pythonRequest('POST', '/agents/pipeline-test', {
    workspace_id: workspaceId,
    steps: ['sweep', 'drain'],
  });
}

/**
 * SERVER_ONLY fetch of a single generated query ref. `executeQuery` defaults to PREFER_CACHE,
 * which client-side mutations update but BACKEND (agent) writes never touch — so a hook's
 * refetch() (also PREFER_CACHE) returns stale rows after an agent run until a full reload. A
 * SERVER_ONLY fetch hits the server and refreshes the shared DC cache for this ref.
 */
async function serverFetchRef(ref: unknown): Promise<void> {
  // executeQuery's options arg (incl. fetchPolicy) is runtime-supported; cast to stay type-safe
  // across SDK versions whose published types may not surface the option yet.
  try {
    await (executeQuery as (r: unknown, o?: unknown) => Promise<unknown>)(ref, { fetchPolicy: 'SERVER_ONLY' });
  } catch {
    /* non-fatal — fall back to the cached refetch */
  }
}

/**
 * Wrap a generated query's refetch so it FIRST refreshes the shared DC cache from the server
 * (see serverFetchRef), THEN runs the hook's refetch to pull the fresh data into React Query.
 * Agent-affected adapter hooks use this so every refetch path (focus, mutation onSuccess,
 * notification-driven) reflects backend writes — not just a full page reload. The returned
 * function is stable across renders (memoized on the ref + the underlying refetch).
 */
function useServerRefetch(
  refFactory: () => unknown,
  deps: unknown[],
  refetch: () => Promise<unknown>,
): () => Promise<unknown> {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const ref = useMemo(refFactory, deps);
  return useCallback(async () => {
    await serverFetchRef(ref);
    return refetch();
  }, [ref, refetch]);
}

// ============================================================================
// Sidekick Questions Queue (Mission Control)
// ============================================================================

export interface SidekickQuestionItem {
  id: string;
  text: string;
  context?: string;
  question_type?: string;
}

export interface SidekickQueueItem {
  id: string;           // Primary ID (agent_run_id when deduped, or need_id)
  need_id: string;      // The first/primary need being resolved
  run_id: string;       // Agent run for answering questions
  customer_id: string;
  customer_name: string;  // Display name (may be "X + N more" if multiple)
  customer_arr_cents: number | null;  // Customer ARR in cents (for telemetry)
  refcode: string;
  question_count: number;
  questions_preview: string[];
  questions: SidekickQuestionItem[];
  created_at: string;
  agent_type: string;
  context: string;
  is_blocking?: boolean;  // False for non-blocking questions (sales side-asks, kickoff items)
  // When multiple needs share the same agent run:
  affected_customers?: string[];   // All customer names linked to this run
  affected_need_ids?: string[];    // All need IDs that will be resolved
}

export interface SidekickQuestionsResponse {
  items: SidekickQueueItem[];
  total: number;
}

// Type for clarifying questions from agent runs
interface ClarifyingQuestion {
  id: string;
  text: string;
  type?: string;
  options?: string[];
}

/**
 * Hook to fetch all sidekick questions (for Sidekick page).
 *
 * Queries NEEDS of type sidekick_question (which have customer info),
 * then gets questions from their linked agent runs.
 *
 * Data structure:
 * - Needs have: customer info, headline, linked agentRun
 * - AgentRuns have: clarifyingQuestions (JSON), status
 * - Customer info is on the Need, NOT on the AgentRun
 */
export function useSidekickQuestions() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  // Query both sources: needs (blocking) and sidekickItems (blocking + non-blocking)
  const needsQuery = useGetSidekickQuestionNeeds(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  const itemsQuery = useGetSidekickAskingItems(
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  // Transform needs into SidekickQueueItem format
  // IMPORTANT: Dedupe by agent_run_id since multiple needs may share the same run
  // When one run is answered, all linked needs will be resolved
  const transformedData = useMemo(() => {
    const needsData = needsQuery.data?.needs || [];
    const sidekickItems = itemsQuery.data?.sidekickItems || [];

    // Track processed run IDs to avoid duplicates
    const processedRunIds = new Set<string>();
    const items: SidekickQueueItem[] = [];

    // FIRST: Process needs (blocking questions from sidekick_question needs)
    const needsWithQuestions = needsData.filter(need => {
      const agentRun = need.agentRun;
      if (!agentRun?.clarifyingQuestions) return false;
      try {
        const parsed = JSON.parse(agentRun.clarifyingQuestions);
        return Array.isArray(parsed) && parsed.length > 0;
      } catch {
        return false;
      }
    });

    // Group needs by agent_run_id to dedupe
    const runToNeeds = new Map<string, typeof needsWithQuestions>();
    for (const need of needsWithQuestions) {
      const runId = need.agentRun?.id || 'no-run';
      if (!runToNeeds.has(runId)) {
        runToNeeds.set(runId, []);
      }
      runToNeeds.get(runId)!.push(need);
    }

    // Create items from needs
    for (const [runId, needs] of runToNeeds.entries()) {
      processedRunIds.add(runId);
      const firstNeed = needs[0];
      const agentRun = firstNeed.agentRun;

      // Parse questions from the shared agent run
      let questions: any[] = [];
      if (agentRun?.clarifyingQuestions) {
        try {
          const parsed = JSON.parse(agentRun.clarifyingQuestions || '[]');
          questions = Array.isArray(parsed) ? parsed : [];
        } catch {
          questions = [];
        }
      }

      // Collect all unique customer names for this run
      const customerNames = [...new Set(needs.map(n => n.customer?.name).filter(Boolean))] as string[];
      const customerIds = [...new Set(needs.map(n => n.customer?.id).filter(Boolean))] as string[];
      const customerArrCents = firstNeed.customer?.arrCents ? parseInt(firstNeed.customer.arrCents, 10) : null;

      const refcode = `SK-${runId.slice(0, 8).toUpperCase()}`;
      const customerDisplay = customerNames.length > 1
        ? `${customerNames[0]} + ${customerNames.length - 1} more`
        : customerNames[0] || 'Unknown Customer';

      items.push({
        id: runId,
        refcode,
        created_at: firstNeed.createdAt || new Date().toISOString(),
        customer_name: customerDisplay,
        customer_id: customerIds[0] || '',
        customer_arr_cents: customerArrCents,
        agent_type: agentRun?.agentName || 'sidekick',
        context: firstNeed.lede || agentRun?.pauseReason || 'Sidekick needs input to proceed',
        questions_preview: questions.slice(0, 3).map(q => unescapeText(q.text || q.question || '')),
        questions: questions.map(q => ({
          id: q.id || q.field || 'unknown',
          text: unescapeText(q.text || q.question || ''),
          question_type: q.type || q.question_type || 'text',
        })),
        question_count: questions.length,
        run_id: runId !== 'no-run' ? runId : '',
        need_id: firstNeed.id,
        affected_customers: customerNames,
        affected_need_ids: needs.map(n => n.id),
      });
    }

    // SECOND: Process sidekickItems (includes non-blocking questions)
    for (const item of sidekickItems) {
      const runId = item.agentRun?.id || `item-${item.id}`;

      // Skip if already processed from needs
      if (processedRunIds.has(runId)) continue;
      processedRunIds.add(runId);

      // Parse questions from agent run
      let questions: any[] = [];
      if (item.agentRun?.clarifyingQuestions) {
        try {
          const parsed = JSON.parse(item.agentRun.clarifyingQuestions || '[]');
          questions = Array.isArray(parsed) ? parsed : [];
        } catch {
          questions = [];
        }
      }

      // If no parsed questions, create one from the item itself
      if (questions.length === 0 && item.question) {
        questions = [{ id: item.id, text: item.question, type: 'text' }];
      }

      const refcode = `SK-${runId.slice(0, 8).toUpperCase()}`;
      const isBlocking = item.isBlocking ?? true;

      items.push({
        id: runId,
        refcode,
        created_at: item.createdAt || new Date().toISOString(),
        customer_name: item.customer?.name || 'Unknown Customer',
        customer_id: item.customer?.id || '',
        customer_arr_cents: item.customer?.arrCents ? parseInt(item.customer.arrCents, 10) : null,
        agent_type: item.agentRun?.agentName || 'sidekick',
        context: item.why || item.agentRun?.pauseReason || (isBlocking ? 'Sidekick needs input to proceed' : 'Non-blocking question for follow-up'),
        questions_preview: questions.slice(0, 3).map(q => unescapeText(q.text || q.question || '')),
        questions: questions.map(q => ({
          id: q.id || q.field || 'unknown',
          text: unescapeText(q.text || q.question || ''),
          question_type: q.type || q.question_type || 'text',
        })),
        question_count: questions.length,
        run_id: item.agentRun?.id || '',
        need_id: item.need?.id || '',
        affected_customers: item.customer?.name ? [item.customer.name] : [],
        affected_need_ids: item.need?.id ? [item.need.id] : [],
        is_blocking: isBlocking,
      });
    }

    // Sort: blocking first, then by created_at desc
    items.sort((a, b) => {
      const aBlocking = a.is_blocking !== false;
      const bBlocking = b.is_blocking !== false;
      if (aBlocking !== bBlocking) return aBlocking ? -1 : 1;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });

    return { items, total: items.length };
  }, [needsQuery.data, itemsQuery.data]);

  const refetch = useCallback(async () => {
    // SERVER_ONLY refresh both sources past the DC client cache (agent writes don't update it).
    await Promise.allSettled([
      serverFetchRef(getSidekickQuestionNeedsRef(dataConnect, { workspaceId: workspaceId || '' })),
      serverFetchRef(getSidekickAskingItemsRef(dataConnect, { workspaceId: workspaceId || '' })),
    ]);
    needsQuery.refetch();
    itemsQuery.refetch();
  }, [workspaceId, needsQuery.refetch, itemsQuery.refetch]);

  return {
    data: transformedData,
    isLoading: needsQuery.isLoading || itemsQuery.isLoading || wsLoading,
    error: needsQuery.error || itemsQuery.error,
    refetch,
  };
}

// =============================================================================
// Live Ops Rail — running agents + recently resolved
// =============================================================================

export interface RunningAgentItem {
  id: string;
  agent_name: string;
  customer_name: string;
  current_step: string | null;
  started_at: string | null;
}

export function useRunningAgents() {
  const { workspaceId, loading: wsLoading } = useWorkspace();
  const query = useListAgentRunsForWorkspace(
    { workspaceId: workspaceId || '', status: AgentStatus.running, limit: 10 },
    { enabled: !!workspaceId && !wsLoading }
  );
  const items: RunningAgentItem[] = (query.data?.agentRuns || []).map(r => ({
    id: r.id,
    agent_name: r.agentName,
    customer_name: r.customer?.name || 'Unknown',
    current_step: r.currentStep || null,
    started_at: r.startedAt || null,
  }));
  const refetch = useServerRefetch(
    () => listAgentRunsForWorkspaceRef(dataConnect, { workspaceId: workspaceId || '', status: AgentStatus.running, limit: 10 }),
    [workspaceId],
    query.refetch,
  );
  return { data: items, isLoading: query.isLoading, refetch };
}

export interface ResolvedRunItem {
  id: string;
  agent_name: string;
  customer_name: string;
  completed_at: string;
}

export function useRecentlyResolvedRuns() {
  const { workspaceId, loading: wsLoading } = useWorkspace();
  const query = useListAgentRunsForWorkspace(
    { workspaceId: workspaceId || '', status: AgentStatus.completed, limit: 50 },
    { enabled: !!workspaceId && !wsLoading }
  );
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  const items: ResolvedRunItem[] = (query.data?.agentRuns || [])
    .filter(r => r.completedAt && new Date(r.completedAt).getTime() > cutoff)
    .map(r => ({
      id: r.id,
      agent_name: r.agentName,
      customer_name: r.customer?.name || 'Unknown',
      completed_at: r.completedAt!,
    }));
  const refetch = useServerRefetch(
    () => listAgentRunsForWorkspaceRef(dataConnect, { workspaceId: workspaceId || '', status: AgentStatus.completed, limit: 50 }),
    [workspaceId],
    query.refetch,
  );
  return { data: items, isLoading: query.isLoading, refetch };
}

// =============================================================================
// Notification Resync
// =============================================================================

/**
 * Resync Firestore notification counts with the database.
 *
 * Use this when real-time counts get out of sync, e.g., after a database wipe.
 * Can be called from browser console: await window.resyncNotifications()
 *
 * @param workspaceIdOverride - Optional workspace ID override (auto-detected if not provided)
 */
export async function resyncNotifications(workspaceIdOverride?: string): Promise<{
  today_count: number;
  sidekick_questions: number;
}> {
  const auth = getAuth();
  const user = auth.currentUser;

  if (!user) {
    throw new Error('Not authenticated');
  }

  // Get workspace ID - try multiple sources
  let workspaceId = workspaceIdOverride;

  if (!workspaceId) {
    // Try user-specific key first (how WorkspaceProvider stores it)
    workspaceId = localStorage.getItem(`herofy_workspace_id_${user.uid}`);
  }

  if (!workspaceId) {
    // Fall back to default workspace ID (for dev)
    workspaceId = '11111111-1111-1111-1111-111111111111';
    console.log('[resyncNotifications] Using default workspace ID:', workspaceId);
  }

  const token = await user.getIdToken();
  const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

  console.log('[resyncNotifications] Calling resync for workspace:', workspaceId);

  const response = await fetch(`${PYTHON_URL}/api/workspaces/${workspaceId}/notifications/resync`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Resync failed' }));
    throw new Error(error.message || error.detail || 'Resync failed');
  }

  const result = await response.json();
  console.log('[resyncNotifications] Counts refreshed:', result);
  return result;
}

/**
 * Debug function to inspect sidekick data from DataConnect.
 * Call from browser console: await window.debugSidekickData()
 */
export async function debugSidekickData(): Promise<void> {
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');

  let workspaceId = localStorage.getItem(`herofy_workspace_id_${user.uid}`);
  if (!workspaceId) {
    workspaceId = '11111111-1111-1111-1111-111111111111';
  }

  console.log('=== SIDEKICK DEBUG ===');
  console.log('Workspace ID:', workspaceId);

  // Import the queries we need
  const { getRunsWithQuestions, getSidekickQuestionNeeds, getTodayQueue, getAllAgentRuns } = await import('@/dataconnect-generated');

  // Query 0: ALL agent runs (to see everything)
  console.log('\n--- ALL Agent Runs (GetAllAgentRuns) ---');
  try {
    const allRunsResult = await getAllAgentRuns({ workspaceId });
    const allRuns = allRunsResult.data?.agentRuns || [];
    console.log('Total agent runs in workspace:', allRuns.length);
    allRuns.forEach((run, i) => {
      console.log(`Run ${i + 1}:`, {
        id: run.id,
        status: run.status,
        agentName: run.agentName,
        customer: run.customer,
        blockingNeed: run.blockingNeed,
        hasQuestions: !!run.clarifyingQuestions,
        questionsLength: run.clarifyingQuestions?.length || 0,
        errorMessage: run.errorMessage,
        createdAt: run.createdAt,
      });
    });
  } catch (e) {
    console.error('Error querying all runs:', e);
  }

  // Query 1: Agent runs with questions (filtered)
  console.log('\n--- Agent Runs with Questions (GetRunsWithQuestions) ---');
  try {
    const runsResult = await getRunsWithQuestions({ workspaceId });
    const runs = runsResult.data?.agentRuns || [];
    console.log('Filtered runs with questions:', runs.length);
    runs.forEach((run, i) => {
      console.log(`Run ${i + 1}:`, {
        id: run.id,
        status: run.status,
        agentName: run.agentName,
        customer: run.customer,
        hasQuestions: !!run.clarifyingQuestions,
        questionsPreview: run.clarifyingQuestions?.substring(0, 100),
      });
    });
  } catch (e) {
    console.error('Error querying runs:', e);
  }

  // Query 2: Sidekick question needs
  console.log('\n--- Sidekick Question Needs (GetSidekickQuestionNeeds) ---');
  try {
    const needsResult = await getSidekickQuestionNeeds({ workspaceId });
    const needs = needsResult.data?.needs || [];
    console.log('Total needs:', needs.length);
    needs.forEach((need, i) => {
      console.log(`Need ${i + 1}:`, {
        id: need.id,
        type: need.type,
        headline: need.headline,
        customer: need.customer,
        agentRun: need.agentRun ? {
          id: need.agentRun.id,
          status: need.agentRun.status,
          hasQuestions: !!need.agentRun.clarifyingQuestions,
        } : null,
      });
    });
  } catch (e) {
    console.error('Error querying needs:', e);
  }

  // Query 3: Today queue (to see what's showing there)
  console.log('\n--- Today Queue (GetTodayQueue) ---');
  try {
    const todayResult = await getTodayQueue({ workspaceId });
    const todayNeeds = todayResult.data?.needs || [];
    console.log('Total today items:', todayNeeds.length);
    const sidekickNeeds = todayNeeds.filter(n => n.type === 'sidekick_question');
    console.log('Sidekick question items in Today:', sidekickNeeds.length);
    sidekickNeeds.forEach((need, i) => {
      console.log(`Sidekick Need ${i + 1}:`, {
        id: need.id,
        headline: need.headline,
        customer: need.customer,
      });
    });
  } catch (e) {
    console.error('Error querying today:', e);
  }

  console.log('\n=== END DEBUG ===');
}

// Expose debug function globally
/**
 * Find sidekick needs that are stuck (have agent runs without questions).
 * These likely need the handoff agent to be retriggered.
 *
 * Call from browser console: await window.findStuckNeeds()
 */
export async function findStuckNeeds(): Promise<{
  stuck: Array<{ needId: string; customerId: string; customerName: string; agentRunId: string; agentRunStatus: string }>;
  ready: Array<{ needId: string; customerName: string; questionCount: number }>;
}> {
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');

  let workspaceId = localStorage.getItem(`herofy_workspace_id_${user.uid}`);
  if (!workspaceId) {
    workspaceId = '11111111-1111-1111-1111-111111111111';
  }

  const { getSidekickQuestionNeeds } = await import('@/dataconnect-generated');
  const result = await getSidekickQuestionNeeds({ workspaceId });
  const needs = result.data?.needs || [];

  const stuck: Array<{ needId: string; customerId: string; customerName: string; agentRunId: string; agentRunStatus: string }> = [];
  const ready: Array<{ needId: string; customerName: string; questionCount: number }> = [];

  for (const need of needs) {
    const agentRun = need.agentRun;
    let hasQuestions = false;
    let questionCount = 0;

    if (agentRun?.clarifyingQuestions) {
      try {
        const parsed = JSON.parse(agentRun.clarifyingQuestions);
        hasQuestions = Array.isArray(parsed) && parsed.length > 0;
        questionCount = parsed.length;
      } catch {
        hasQuestions = false;
      }
    }

    if (hasQuestions) {
      ready.push({
        needId: need.id,
        customerName: need.customer?.name || 'Unknown',
        questionCount,
      });
    } else {
      stuck.push({
        needId: need.id,
        customerId: need.customer?.id || '',
        customerName: need.customer?.name || 'Unknown',
        agentRunId: agentRun?.id || '',
        agentRunStatus: agentRun?.status || 'no_run',
      });
    }
  }

  console.log('=== STUCK NEEDS ANALYSIS ===');
  console.log(`Ready (have questions): ${ready.length}`);
  ready.forEach(r => console.log(`  - ${r.customerName}: ${r.questionCount} questions`));
  console.log(`Stuck (no questions): ${stuck.length}`);
  stuck.forEach(s => console.log(`  - ${s.customerName}: run=${s.agentRunId?.slice(0,8) || 'none'}, status=${s.agentRunStatus}`));
  console.log('\nTo recover, retrigger handoff_auto for these customer IDs:');
  stuck.forEach(s => console.log(`  ${s.customerId} (${s.customerName})`));

  return { stuck, ready };
}

/**
 * Recover stuck sidekick needs by retriggering the handoff agent.
 *
 * Call from browser console: await window.recoverStuckNeeds()
 *
 * This will:
 * 1. Find needs with agent runs that have no questions
 * 2. Fail the old stuck runs
 * 3. Trigger new handoff_auto runs for each customer
 */
export async function recoverStuckNeeds(): Promise<{
  recovered: number;
  failed: number;
  details: Array<{ need_id: string; customer_name?: string; status: string; error?: string }>;
  debug: Array<{ need_id: string; customer_name?: string; agent_run_id?: string; agent_run_status?: string; has_questions: boolean; question_count: number }>;
}> {
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');

  let workspaceId = localStorage.getItem(`herofy_workspace_id_${user.uid}`);
  if (!workspaceId) {
    workspaceId = '11111111-1111-1111-1111-111111111111';
  }

  const token = await user.getIdToken();
  const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

  console.log('[recoverStuckNeeds] Starting recovery for workspace:', workspaceId);

  const response = await fetch(`${PYTHON_URL}/api/workspaces/${workspaceId}/recover-stuck-needs`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new Error(error.message || error.error?.message || 'Recovery failed');
  }

  const result = await response.json();

  // Log debug info first to understand the data
  console.log('=== DEBUG: ALL NEEDS CHECKED ===');
  if (result.debug?.length) {
    console.table(result.debug);
  } else {
    console.log('(no debug info returned)');
  }

  console.log('=== RECOVERY COMPLETE ===');
  console.log(`Recovered: ${result.recovered}`);
  console.log(`Failed: ${result.failed}`);
  result.details?.forEach((d: any) => {
    if (d.status === 'recovered') {
      console.log(`  ✓ ${d.customer_name}: new run ${d.new_run_id?.slice(0, 8)}`);
    } else {
      console.log(`  ✗ ${d.customer_name || d.need_id}: ${d.error || d.reason || 'unknown error'}`);
    }
  });

  return result;
}

/**
 * Clean up bad sidekick data (needs, agent runs, sidekick items).
 * Use this to clear corrupted data before testing the concurrency fix.
 *
 * Call from browser console: await window.cleanupSidekickData()
 */
export async function cleanupSidekickData(): Promise<{
  needs_deleted: number;
  agent_runs_deleted: number;
  sidekick_items_deleted: number;
}> {
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');

  let workspaceId = localStorage.getItem(`herofy_workspace_id_${user.uid}`);
  if (!workspaceId) {
    workspaceId = '11111111-1111-1111-1111-111111111111';
  }

  const token = await user.getIdToken();
  const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

  console.log('[cleanupSidekickData] Cleaning up for workspace:', workspaceId);

  const response = await fetch(`${PYTHON_URL}/api/workspaces/${workspaceId}/cleanup-sidekick-data`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new Error(error.message || error.error?.message || 'Cleanup failed');
  }

  const result = await response.json();

  console.log('=== CLEANUP COMPLETE ===');
  console.log(`Needs deleted: ${result.needs_deleted}`);
  console.log(`Agent runs deleted: ${result.agent_runs_deleted}`);
  console.log(`Sidekick items deleted: ${result.sidekick_items_deleted}`);

  return result;
}

/**
 * Test Firestore connectivity by writing a test notification.
 * Call from browser console: await window.testFirestore()
 */
export async function testFirestore(): Promise<{
  success: boolean;
  message: string;
  emulator_host: string | null;
}> {
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');

  let workspaceId = localStorage.getItem(`herofy_workspace_id_${user.uid}`);
  if (!workspaceId) {
    workspaceId = '11111111-1111-1111-1111-111111111111';
  }

  const token = await user.getIdToken();
  const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

  console.log('[testFirestore] Testing for workspace:', workspaceId);

  const response = await fetch(`${PYTHON_URL}/api/workspaces/${workspaceId}/test-firestore`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  const result = await response.json();

  if (result.success) {
    console.log('✅ Firestore test PASSED');
    console.log(`   Emulator host: ${result.emulator_host || 'NOT SET'}`);
    console.log(`   ${result.message}`);
    console.log('   Check the Sidekick badge - it should show 999');
  } else {
    console.error('❌ Firestore test FAILED');
    console.error(`   ${result.message}`);
    console.error(`   Emulator host: ${result.emulator_host || 'NOT SET'}`);
  }

  return result;
}

/**
 * Manually refresh notification counts and push to Firestore.
 * Call from browser console: await window.refreshCounts()
 */
export async function refreshCounts(): Promise<{
  today_count: number;
  sidekick_questions: number;
}> {
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');

  let workspaceId = localStorage.getItem(`herofy_workspace_id_${user.uid}`);
  if (!workspaceId) {
    workspaceId = '11111111-1111-1111-1111-111111111111';
  }

  const token = await user.getIdToken();
  const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

  console.log('[refreshCounts] Refreshing for workspace:', workspaceId);

  const response = await fetch(`${PYTHON_URL}/api/workspaces/${workspaceId}/refresh-counts`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  const result = await response.json();

  console.log('=== COUNTS REFRESHED ===');
  console.log(`Today queue: ${result.today_count}`);
  console.log(`Sidekick questions: ${result.sidekick_questions}`);

  return result;
}

if (typeof window !== 'undefined') {
  (window as any).debugSidekickData = debugSidekickData;
  (window as any).findStuckNeeds = findStuckNeeds;
  (window as any).recoverStuckNeeds = recoverStuckNeeds;
  (window as any).cleanupSidekickData = cleanupSidekickData;
  (window as any).testFirestore = testFirestore;
  (window as any).refreshCounts = refreshCounts;
}

/**
 * Clean up stale/orphan agent runs that are stuck in waiting_for_input.
 *
 * Use this after a database wipe to clear runs where the linked customer
 * no longer exists (shows as "Unknown Customer").
 *
 * Can be called from browser console: await window.cleanupStaleAgentRuns()
 */
export async function cleanupStaleAgentRuns(): Promise<{
  cleaned: number;
  failed: string[];
}> {
  // Get workspace ID
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');

  let workspaceId = localStorage.getItem(`herofy_workspace_id_${user.uid}`);
  if (!workspaceId) {
    workspaceId = '11111111-1111-1111-1111-111111111111';
  }

  console.log('[cleanupStaleAgentRuns] Fetching waiting runs for workspace:', workspaceId);

  // Get all waiting runs
  const result = await getWaitingRuns({ workspaceId });
  const runs = result.data?.agentRuns || [];

  console.log('[cleanupStaleAgentRuns] Found', runs.length, 'waiting runs');

  // Find runs without a customer (orphans)
  const orphanRuns = runs.filter(run => !run.customer?.id);
  console.log('[cleanupStaleAgentRuns] Found', orphanRuns.length, 'orphan runs (no customer)');

  // Fail each orphan run
  const failed: string[] = [];
  let cleaned = 0;

  for (const run of orphanRuns) {
    try {
      await failAgentRun({
        id: run.id,
        errorMessage: 'Cleaned up: linked customer no longer exists',
        durationMs: 0,
      });
      cleaned++;
      console.log('[cleanupStaleAgentRuns] Cleaned run:', run.id);
    } catch (e) {
      console.error('[cleanupStaleAgentRuns] Failed to clean run:', run.id, e);
      failed.push(run.id);
    }
  }

  console.log('[cleanupStaleAgentRuns] Done. Cleaned:', cleaned, 'Failed:', failed.length);

  // Resync notifications after cleanup
  if (cleaned > 0) {
    try {
      await resyncNotifications(workspaceId);
    } catch (e) {
      console.warn('[cleanupStaleAgentRuns] Resync failed:', e);
    }
  }

  return { cleaned, failed };
}

/**
 * Clean up orphan sidekick needs - needs of type sidekick_question where
 * the linked agent run is no longer in waiting_for_input status.
 *
 * Use this after cleaning up agent runs to also remove their orphaned needs.
 *
 * Can be called from browser console: await window.cleanupOrphanSidekickNeeds()
 */
export async function cleanupOrphanSidekickNeeds(): Promise<{
  resolved: number;
  failed: string[];
}> {
  // Get workspace ID
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');

  let workspaceId = localStorage.getItem(`herofy_workspace_id_${user.uid}`);
  if (!workspaceId) {
    workspaceId = '11111111-1111-1111-1111-111111111111';
  }

  console.log('[cleanupOrphanSidekickNeeds] Fetching today queue for workspace:', workspaceId);

  // Get all needs in today queue
  const result = await getTodayQueue({ workspaceId });
  const needs = result.data?.needs || [];

  console.log('[cleanupOrphanSidekickNeeds] Found', needs.length, 'needs in today queue');

  // Find sidekick_question needs
  const sidekickNeeds = needs.filter(need => need.type === 'sidekick_question');
  console.log('[cleanupOrphanSidekickNeeds] Found', sidekickNeeds.length, 'sidekick_question needs');

  // Check each one's agent run status
  const orphanNeeds: typeof sidekickNeeds = [];

  for (const need of sidekickNeeds) {
    const agentRunId = (need as any).agentRun?.id;

    if (!agentRunId) {
      // No linked agent run - orphan
      console.log('[cleanupOrphanSidekickNeeds] Need has no agent run:', need.id);
      orphanNeeds.push(need);
      continue;
    }

    try {
      const runResult = await getAgentRun({ id: agentRunId });
      const run = runResult.data?.agentRun;

      if (!run) {
        console.log('[cleanupOrphanSidekickNeeds] Agent run not found:', agentRunId);
        orphanNeeds.push(need);
      } else if (run.status !== 'waiting_for_input') {
        console.log('[cleanupOrphanSidekickNeeds] Agent run not waiting:', agentRunId, 'status:', run.status);
        orphanNeeds.push(need);
      }
    } catch (e) {
      console.log('[cleanupOrphanSidekickNeeds] Error checking agent run:', agentRunId, e);
      orphanNeeds.push(need);
    }
  }

  console.log('[cleanupOrphanSidekickNeeds] Found', orphanNeeds.length, 'orphan needs to resolve');

  // Resolve each orphan need
  const failed: string[] = [];
  let resolved = 0;

  for (const need of orphanNeeds) {
    try {
      await resolveNeed({ id: need.id });
      resolved++;
      console.log('[cleanupOrphanSidekickNeeds] Resolved need:', need.id);
    } catch (e) {
      console.error('[cleanupOrphanSidekickNeeds] Failed to resolve need:', need.id, e);
      failed.push(need.id);
    }
  }

  console.log('[cleanupOrphanSidekickNeeds] Done. Resolved:', resolved, 'Failed:', failed.length);

  // Resync notifications after cleanup
  if (resolved > 0) {
    try {
      await resyncNotifications(workspaceId);
    } catch (e) {
      console.warn('[cleanupOrphanSidekickNeeds] Resync failed:', e);
    }
  }

  return { resolved, failed };
}

/**
 * Full cleanup - cleans up both orphan agent runs AND orphan needs.
 *
 * Can be called from browser console: await window.fullCleanup()
 */
export async function fullCleanup(): Promise<{
  agentRuns: { cleaned: number; failed: string[] };
  needs: { resolved: number; failed: string[] };
}> {
  console.log('[fullCleanup] Starting full cleanup...');

  const agentRuns = await cleanupStaleAgentRuns();
  const needs = await cleanupOrphanSidekickNeeds();

  console.log('[fullCleanup] Complete:', { agentRuns, needs });
  return { agentRuns, needs };
}

// Expose to window for easy console access
if (typeof window !== 'undefined') {
  (window as any).resyncNotifications = resyncNotifications;
  (window as any).cleanupStaleAgentRuns = cleanupStaleAgentRuns;
  (window as any).cleanupOrphanSidekickNeeds = cleanupOrphanSidekickNeeds;
  (window as any).fullCleanup = fullCleanup;
}

// ============================================================
// RENEWALS — pipeline list + adaptive workspace
// ============================================================

function transformRenewalProfile(p: any): import('./renewals').RenewalProfile {
  return {
    id: p.id,
    posture: p.posture,
    posture_reason: p.postureReason ?? null,
    narrative_lede: p.narrativeLede ?? null,
    target_arr_cents: p.targetArrCents != null ? Number(p.targetArrCents) : null,
    expansion_pipe_cents: p.expansionPipeCents != null ? Number(p.expansionPipeCents) : null,
    renewal_type: p.renewalType ?? null,
    auto_renew: p.autoRenew ?? null,
    term_note: p.termNote ?? null,
    last_price_change_note: p.lastPriceChangeNote ?? null,
    posture_set_by: p.postureSetBy ?? null,
    posture_derived_at: p.postureDerivedAt ?? null,
  };
}

function transformRenewalGoal(g: any): import('./renewals').RenewalGoal {
  return {
    id: g.id,
    text: g.text,
    is_primary: !!g.isPrimary,
    vectors: (g.progressVectors_on_goal || []).map((v: any) => ({
      id: v.id,
      category: v.category,
      description: v.description,
      current_state: v.currentState,
      progress: v.progress ?? null,
      baseline_progress: v.baselineProgress ?? null,
      target_progress: v.targetProgress ?? null,
      target_label: v.targetLabel ?? null,
      unlocks: v.unlocks ?? null,
      assessment_reason: v.assessmentReason ?? null,
    })),
  };
}

/**
 * Renewals pipeline list (Screen 1). Returns rows for every customer with a
 * renewal date, enriched with the renewal profile, goal-progress, and a
 * champion-departure flag.
 */
export function useRenewalsPipeline() {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetRenewalsPipeline(
    dataConnect,
    { workspaceId: workspaceId || '' },
    { enabled: !!workspaceId && !wsLoading }
  );

  const rows = useMemo<import('./renewals').RenewalPipelineRow[]>(() => {
    if (!query.data?.customers) return [];
    return query.data.customers
      .filter(c => c.daysToRenewal != null && c.daysToRenewal > 0)
      .map(c => {
        const profile = c.renewalProfiles_on_customer?.[0]
          ? transformRenewalProfile(c.renewalProfiles_on_customer[0])
          : null;
        const posture = profile?.posture ?? 'hold';
        const arr = c.arrCents != null ? Number(c.arrCents) : null;
        return {
          id: c.id,
          name: c.name,
          slug: c.slug,
          arr_cents: arr,
          days_to_renewal: c.daysToRenewal ?? null,
          lifecycle: c.lifecycle,
          renewal_readiness: c.renewalReadiness ?? null,
          value_realization_text: c.valueRealizationText ?? null,
          client_signed_date: c.clientSignedDate ?? null,
          profile,
          goals: (c.goals_on_customer || []).map(transformRenewalGoal),
          signals: (c.signals_on_customer || []).map((s: any) => ({
            kind: s.kind, state: s.state, sentence: s.sentence ?? null,
          })),
          champion_departed: (c.stakeholders_on_customer || []).some(
            (s: any) => s.isChampion && s.status === 'departed'
          ),
          posture,
          growth: deriveGrowth(arr, profile?.target_arr_cents ?? null, posture),
        };
      });
  }, [query.data]);

  return { ...query, rows, isLoading: query.isLoading || wsLoading };
}

/**
 * Renewal workspace detail (Screen 2) for one customer.
 */
export function useRenewalWorkspace(customerId: string | null) {
  const { workspaceId, loading: wsLoading } = useWorkspace();

  const query = useGetRenewalWorkspace(
    dataConnect,
    { customerId: customerId || '' },
    { enabled: !!customerId && !!workspaceId && !wsLoading }
  );

  const workspace = useMemo<import('./renewals').RenewalWorkspaceData | null>(() => {
    const c = query.data?.customer;
    if (!c) return null;
    const profileRaw = c.renewalProfiles_on_customer?.[0] ?? null;
    const profile = profileRaw ? transformRenewalProfile(profileRaw) : null;
    const posture = profile?.posture ?? 'hold';

    const plays: import('./renewals').RenewalPlay[] = (profileRaw?.renewalPlays_on_profile || []).map((p: any) => ({
      id: p.id,
      kind: p.kind,
      posture: p.posture,
      title: p.title,
      description: p.description,
      basis: p.basis ?? null,
      value_amount_cents: p.valueAmountCents != null ? Number(p.valueAmountCents) : null,
      value_label: p.valueLabel ?? null,
      is_primary: !!p.isPrimary,
      sort_order: p.sortOrder ?? 0,
    }));

    const risk_items: import('./renewals').RenewalRiskItem[] = (profileRaw?.renewalRiskItems_on_profile || []).map((r: any) => ({
      id: r.id,
      title: r.title,
      description: r.description,
      severity: r.severity,
      mitigation: r.mitigation ?? null,
      sort_order: r.sortOrder ?? 0,
    }));

    const stakeholders: import('./renewals').RenewalStakeholder[] = (c.stakeholders_on_customer || []).map((s: any) => ({
      id: s.id,
      name: s.name,
      role: s.role ?? null,
      status: s.status,
      is_champion: !!s.isChampion,
      sentiment_note: s.sentimentNote ?? null,
      last_interaction_at: s.lastInteractionAt ?? null,
      tone: stakeholderTone({ renewalHealth: s.renewalHealth ?? null, status: s.status, sentimentNote: s.sentimentNote ?? null }),
      initials: initialsOf(s.name),
    }));

    return {
      id: c.id,
      name: c.name,
      slug: c.slug,
      one_liner: c.oneLiner ?? null,
      tier: c.tier ?? null,
      arr_cents: c.arrCents != null ? Number(c.arrCents) : null,
      days_to_renewal: c.daysToRenewal ?? null,
      lifecycle: c.lifecycle,
      renewal_readiness: c.renewalReadiness ?? null,
      value_realization_text: c.valueRealizationText ?? null,
      client_signed_date: c.clientSignedDate ?? null,
      relationship_health: c.relationshipHealth ?? null,
      relationship_health_score: c.relationshipHealthScore ?? null,
      profile,
      posture,
      goals: (c.goals_on_customer || []).map(transformRenewalGoal),
      stakeholders,
      plays,
      risk_items,
      signals: (c.signals_on_customer || []).map((s: any) => ({
        id: s.id, kind: s.kind, state: s.state,
        sentence: s.sentence ?? null, evidence_text: s.evidenceText ?? null,
      })),
    };
  }, [query.data]);

  return { ...query, workspace, isLoading: query.isLoading || wsLoading };
}

/** Set just the renewal date (daysToRenewal) on a customer. */
export function useSetCustomerRenewalDate() {
  const mutation = useSetCustomerRenewalDateDC();
  return {
    ...mutation,
    setRenewalDays: (customerId: string, daysToRenewal: number) =>
      mutation.mutateAsync({ id: customerId, daysToRenewal }),
  };
}

