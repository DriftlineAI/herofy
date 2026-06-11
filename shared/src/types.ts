// Herofy Shared Types
// TypeScript interfaces matching the PostgreSQL schema

import { z } from 'zod';
import type {
  WorkspaceRole,
  CustomerLifecycle,
  RenewalReadiness,
  StakeholderStatus,
  GoalStatus,
  InteractionChannel,
  InteractionDirection,
  ThreadStatus,
  ThreadCategory,
  MeetingSource,
  MilestoneStatus,
  OwnerSide,
  CommitmentStatus,
  CommitmentSide,
  SignalKind,
  SignalState,
  RiskLevel,
  BlastRadius,
  ApprovalStatus,
  HandoffStatus,
  DraftResponseStatus,
  NeedType,
} from './constants';

// ============================================================================
// CORE TENANCY
// ============================================================================

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  created_at: Date;
  updated_at: Date;
}

export interface User {
  id: string; // Matches Firebase Auth UID
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface WorkspaceMember {
  workspace_id: string;
  user_id: string;
  role: WorkspaceRole;
  joined_at: Date;
}

// ============================================================================
// CUSTOMERS
// ============================================================================

export interface Customer {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  one_liner: string | null;
  tier: string | null;
  arr_cents: number | null;
  lifecycle: CustomerLifecycle;
  days_to_renewal: number | null;
  onboarding_day_current: number | null;
  onboarding_day_total: number | null;
  renewal_readiness: RenewalReadiness | null;
  value_realization_text: string | null;
  adapted_from_playbook_id: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface Stakeholder {
  id: string;
  workspace_id: string;
  customer_id: string;
  name: string;
  email: string | null;
  role: string | null;
  status: StakeholderStatus;
  sentiment_note: string | null;
  last_interaction_at: Date | null;
  created_at: Date;
  updated_at: Date;
}

export interface Goal {
  id: string;
  workspace_id: string;
  customer_id: string;
  text: string;
  status: GoalStatus;
  sort_order: number;
  created_at: Date;
  updated_at: Date;
}

// ============================================================================
// INTERACTIONS
// ============================================================================

export interface Thread {
  id: string;
  workspace_id: string;
  customer_id: string;
  subject: string | null;
  status: ThreadStatus;
  channel: InteractionChannel | null;
  assigned_user_id: string | null;
  category: ThreadCategory;
  ai_category_suggestion: ThreadCategory | null;
  origin_detail: string | null;
  archived_at: Date | null;
  resolved_at: Date | null;
  created_at: Date;
  updated_at: Date;
}

export interface ExternalRef {
  system: string;
  thread_id?: string;
  message_id?: string;
}

export interface Interaction {
  id: string;
  workspace_id: string;
  customer_id: string;
  thread_id: string | null;
  channel: InteractionChannel;
  origin_kind: string | null;
  direction: InteractionDirection;
  sender_name: string | null;
  sender_user_id: string | null;
  occurred_at: Date;
  subject: string | null;
  body_encrypted: string | null;
  summary_ai: string | null;
  external_ref: ExternalRef | null;
  body_stored_at: string | null;
  created_at: Date;
  updated_at: Date;
}

// ============================================================================
// MEETINGS
// ============================================================================

export interface Meeting {
  id: string;
  workspace_id: string;
  customer_id: string;
  title: string;
  type: string | null;
  scheduled_at: Date;
  duration_minutes: number | null;
  source: MeetingSource;
  external_event_id: string | null;
  attendees_ours: Record<string, unknown>[] | null;
  attendees_theirs: Record<string, unknown>[] | null;
  created_at: Date;
  updated_at: Date;
}

export interface MeetingBrief {
  id: string;
  workspace_id: string;
  meeting_id: string;
  progress_narrative: string | null;
  progress_facts: Record<string, unknown>[] | null;
  friction: string | null;
  talking_points: string[] | null;
  value_delivered: string | null;
  risk_to_renewal: string | null;
  expansion_signals: string | null;
  pricing_context: string | null;
  followup_email: Record<string, unknown> | null;
  generated_at: Date;
  model: string;
  prompt_version: string;
  inputs_hash: string;
  handbook_version_id: string;
  created_at: Date;
  updated_at: Date;
}

// ============================================================================
// COMMITMENTS & MILESTONES
// ============================================================================

export interface Milestone {
  id: string;
  workspace_id: string;
  customer_id: string;
  title: string;
  owner_label: string | null;
  owner_side: OwnerSide;
  target_date: Date | null;
  status: MilestoneStatus;
  description: string | null;
  blocked_reason: string | null;
  sort_order: number;
  adapted_from_playbook_id: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface Commitment {
  id: string;
  workspace_id: string;
  customer_id: string;
  side: CommitmentSide;
  text: string;
  due_label: string | null;
  status: CommitmentStatus;
  source_interaction_id: string | null;
  source_meeting_id: string | null;
  created_at: Date;
  updated_at: Date;
}

// ============================================================================
// SIGNALS & NEEDS
// ============================================================================

export interface Signal {
  id: string;
  workspace_id: string;
  customer_id: string;
  kind: SignalKind;
  state: SignalState;
  sentence: string | null;
  evidence_text: string | null;
  next_action: string | null;
  superseded_at: Date | null;
  generated_at: Date;
  model: string;
  prompt_version: string;
  inputs_hash: string;
  handbook_version_id: string;
  created_at: Date;
  updated_at: Date;
}

export interface NeedSource {
  channel?: string;
  from?: string;
  quote?: string;
}

export interface Need {
  id: string;
  workspace_id: string;
  customer_id: string;
  type: NeedType;
  headline: string;
  lede: string | null;
  priority_rank: number;
  thread_id: string | null;
  milestone_id: string | null;
  meeting_id: string | null;
  focus_section: string | null;
  snoozed_until: Date | null;
  resolved_at: Date | null;
  source: NeedSource | null;
  agent_reasoning: string; // REQUIRED
  handbook_version_id: string;
  created_at: Date;
  updated_at: Date;
}

export interface NeedRecommendation {
  id: string;
  need_id: string;
  rationale: string | null;
  primary_action: string | null;
  secondary_action: string | null;
  confidence_text: string | null;
  model: string;
  prompt_version: string;
  generated_at: Date;
  handbook_version_id: string;
  created_at: Date;
}

export interface NeedEvidence {
  id: string;
  need_id: string;
  interaction_id: string | null;
  meeting_id: string | null;
  commitment_id: string | null;
  created_at: Date;
}

// ============================================================================
// RISK MANAGEMENT
// ============================================================================

export interface RiskBrief {
  id: string;
  workspace_id: string;
  customer_id: string;
  what_changed: string | null;
  evidence_text: string | null;
  play: string | null;
  generated_at: Date;
  model: string;
  prompt_version: string;
  inputs_hash: string;
  handbook_version_id: string;
  created_at: Date;
  updated_at: Date;
}

export interface RiskPlayStep {
  id: string;
  brief_id: string;
  label: string;
  rationale: string | null;
  done: boolean;
  sort_order: number;
  created_at: Date;
}

export interface RenewalRisk {
  id: string;
  workspace_id: string;
  customer_id: string;
  risk_level: RiskLevel;
  summary: string | null;
  evidence_ids: string[] | null;
  generated_at: Date;
  handbook_version_id: string;
  created_at: Date;
  updated_at: Date;
}

// ============================================================================
// HANDOFFS (HITL)
// ============================================================================

export interface SalesCommitment {
  item: string;
  details?: string;
}

export interface TechnicalContext {
  item: string;
  details?: string;
}

export interface HandoffBrief {
  id: string;
  workspace_id: string;
  customer_id: string | null;
  captured_at: Date;
  day_current: number | null;
  day_total: number | null;
  sales_commitments: SalesCommitment[] | null;
  technical_context: TechnicalContext[] | null;
  reality_check_confidence: string | null;
  reality_check_risks: string | null;
  // HITL fields
  status: HandoffStatus;
  user_corrections: Record<string, unknown> | null;
  confirmed_by_user_id: string | null;
  confirmed_at: Date | null;
  // External reference
  notion_deal_id: string | null;
  notion_deal_url: string | null;
  // AI metadata
  handbook_version_id: string;
  model: string | null;
  prompt_version: string | null;
  created_at: Date;
  updated_at: Date;
}

export interface HandoffOpenQuestion {
  id: string;
  brief_id: string;
  text: string;
  resolved: boolean;
  created_at: Date;
}

// ============================================================================
// AI PLANS (HITL)
// ============================================================================

export interface PlanMilestone {
  title: string;
  owner_side: OwnerSide;
  target_days: number;
  description: string | null;
}

export interface AIPlan {
  id: string;
  workspace_id: string;
  customer_id: string | null;
  brief_id: string | null;
  archetype_name: string | null;
  milestone_count: number | null;
  duration_label: string | null;
  rationale: string | null;
  headline: string | null;
  milestones: PlanMilestone[] | null;
  // HITL approval workflow
  status: ApprovalStatus;
  approved_by_user_id: string | null;
  approved_at: Date | null;
  rejection_reason: string | null;
  regenerated_from_plan_id: string | null;
  human_edited: boolean;
  regeneration_count: number;
  // AI metadata
  generated_at: Date;
  model: string;
  prompt_version: string;
  inputs_hash: string;
  handbook_version_id: string;
  created_at: Date;
  updated_at: Date;
}

// ============================================================================
// DRAFT RESPONSES (HITL)
// ============================================================================

export interface DraftResponse {
  id: string;
  workspace_id: string;
  customer_id: string;
  thread_id: string | null;
  subject: string | null;
  body: string;
  // HITL approval workflow
  status: DraftResponseStatus;
  edited_body: string | null;
  approved_by_user_id: string | null;
  approved_at: Date | null;
  sent_at: Date | null;
  auto_send_after: Date | null;
  // Link to surfaced need
  surfaced_in_need_id: string | null;
  // AI metadata
  generated_at: Date;
  model: string;
  prompt_version: string;
  handbook_version_id: string;
  created_at: Date;
  updated_at: Date;
}

// ============================================================================
// CAPTURED ITEMS
// ============================================================================

export interface CapturedItem {
  id: string;
  workspace_id: string;
  customer_id: string;
  meeting_id: string | null;
  tag: string;
  text: string;
  due_label: string | null;
  published: boolean;
  captured_by_user_id: string | null;
  created_at: Date;
  updated_at: Date;
}

// ============================================================================
// HANDBOOK
// ============================================================================

export interface HandbookDoc {
  id: string;
  workspace_id: string;
  slug: string;
  title: string;
  description: string | null;
  body: string;
  blast_radius: BlastRadius;
  created_at: Date;
  updated_at: Date;
}

export interface HandbookVersion {
  id: string;
  doc_id: string;
  body: string;
  edited_by_user_id: string | null;
  edited_at: Date;
  created_at: Date;
}

// ============================================================================
// PLAYBOOKS
// ============================================================================

export interface Playbook {
  id: string;
  workspace_id: string;
  name: string;
  archetype: string | null;
  fit_note: string | null;
  drawn_from_count: number;
  created_at: Date;
  updated_at: Date;
}

export interface PlaybookMilestone {
  id: string;
  playbook_id: string;
  title: string;
  owner_side: OwnerSide;
  duration_days: number | null;
  description: string | null;
  sort_order: number;
  created_at: Date;
}

// ============================================================================
// AGENT STATE
// ============================================================================

export interface AgentState {
  id: string;
  workspace_id: string;
  key: string;
  value: string | null;
  updated_at: Date;
}

// ============================================================================
// VIEW TYPES (Today Queue)
// ============================================================================

export interface TodayQueueItem {
  id: string;
  workspace_id: string;
  customer_id: string;
  type: NeedType;
  headline: string;
  lede: string | null;
  priority_rank: number;
  thread_id: string | null;
  milestone_id: string | null;
  meeting_id: string | null;
  focus_section: string | null;
  snoozed_until: Date | null;
  agent_reasoning: string;
  created_at: Date;
  // Joined fields
  customer_name: string;
  customer_lifecycle: CustomerLifecycle;
  customer_arr_cents: number | null;
  recommendation_primary: string | null;
  recommendation_secondary: string | null;
  recommendation_rationale: string | null;
}

export interface RenewalsViewItem extends Customer {
  renewal_band: '0-30' | '31-60' | '61-90' | '90+';
  current_signals: { kind: SignalKind; state: SignalState; sentence: string }[] | null;
}

// ============================================================================
// API REQUEST/RESPONSE TYPES
// ============================================================================

export interface CreateCustomerInput {
  name: string;
  slug?: string;
  one_liner?: string;
  tier?: string;
  arr_cents?: number;
  lifecycle?: CustomerLifecycle;
}

export interface UpdateCustomerInput {
  name?: string;
  one_liner?: string;
  tier?: string;
  arr_cents?: number;
  lifecycle?: CustomerLifecycle;
  days_to_renewal?: number;
  onboarding_day_current?: number;
  onboarding_day_total?: number;
  renewal_readiness?: RenewalReadiness;
  value_realization_text?: string;
}

export interface ApproveAIPlanInput {
  milestones?: PlanMilestone[]; // If user edited milestones
}

export interface RejectAIPlanInput {
  rejection_reason: string;
}

export interface UpdateHandoffBriefInput {
  sales_commitments?: SalesCommitment[];
  technical_context?: TechnicalContext[];
  reality_check_confidence?: string;
  reality_check_risks?: string;
  user_corrections?: Record<string, unknown>;
}

export interface SnoozeNeedInput {
  snoozed_until: Date;
}

// ============================================================================
// ZOD SCHEMAS (for runtime validation)
// ============================================================================

export const CreateCustomerInputSchema = z.object({
  name: z.string().min(1),
  slug: z.string().optional(),
  one_liner: z.string().optional(),
  tier: z.string().optional(),
  arr_cents: z.number().int().positive().optional(),
  lifecycle: z.string().optional(),
});

export const ApproveAIPlanInputSchema = z.object({
  milestones: z.array(z.object({
    title: z.string(),
    owner_side: z.enum(['us', 'customer', 'joint']),
    target_days: z.number().int(),
    description: z.string().nullable(),
  })).optional(),
});

export const RejectAIPlanInputSchema = z.object({
  rejection_reason: z.string().min(1, 'Rejection reason is required'),
});

export const UpdateHandoffBriefInputSchema = z.object({
  sales_commitments: z.array(z.object({
    item: z.string(),
    details: z.string().optional(),
  })).optional(),
  technical_context: z.array(z.object({
    item: z.string(),
    details: z.string().optional(),
  })).optional(),
  reality_check_confidence: z.string().optional(),
  reality_check_risks: z.string().optional(),
  user_corrections: z.record(z.unknown()).optional(),
});

export const SnoozeNeedInputSchema = z.object({
  snoozed_until: z.coerce.date(),
});
