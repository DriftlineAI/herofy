/**
 * Herofy Types
 *
 * IMPORTANT: This file contains ONLY type definitions.
 *
 * For data operations, use:
 * - @/lib/dataconnect-hooks.ts for React hooks (useCustomers, useToday, etc.)
 * - Firebase SQL Connect mutations for write operations
 *
 * For agent/AI operations, use:
 * - dataconnect-hooks.ts (useSubmitAgentAnswers, useRequestDraft, etc.)
 * - These call the Python backend at VITE_PYTHON_URL
 *
 * The Express API server has been removed. All data flows through:
 * - Firebase SQL Connect (queries and mutations)
 * - Python FastAPI backend (agents, webhooks, AI)
 */

// ============================================================================
// Enums
// ============================================================================

export type CustomerLifecycle = 'prospect' | 'handoff' | 'onboarding' | 'active' | 'renewing' | 'at_risk' | 'churned';
export type NeedType = 'urgent_support' | 'going_dark' | 'stalled_milestone' | 'approaching_renewal' | 'open_commitment_overdue' | 'frustrated_signal' | 'champion_departed' | 'onboarding_behind' | 'renewal_at_risk' | 'new_handoff' | 'meeting_prep_ready' | 'positive_signal' | 'expansion_signal' | 'check_in_due' | 'escalation' | 'plan_approval_required' | 'draft_response_ready' | 'sidekick_question' | 'uncategorized';
export type ApprovalStatus = 'pending_approval' | 'approved' | 'rejected' | 'superseded';
export type HandoffStatus = 'draft' | 'confirmed' | 'needs_correction';
export type OwnerSide = 'us' | 'customer' | 'joint';
export type SignalKind = 'engagement' | 'sentiment' | 'commitments';
export type SignalState = 'ok' | 'warn' | 'risk';
export type MilestoneStatus = 'not_started' | 'in_progress' | 'blocked' | 'done' | 'skipped';
export type StakeholderStatus = 'active' | 'departed';
export type GoalStatus = 'active' | 'achieved' | 'dropped';

// Conversation/Thread types
export type MessageDirection = 'customer' | 'us' | 'internal';
export type InteractionChannel = 'email' | 'slack' | 'meeting' | 'in_app' | 'sms_screenshot' | 'note' | 'phone';
export type ThreadStatus = 'open' | 'resolved' | 'archived';
export type DraftSuggestedAction = 'reply' | 'schedule_call' | 'schedule_meeting';
export type MeetingSuggestionType = 'call' | 'meeting';
export type MeetingType = 'qbr' | 'renewal' | 'check_in' | 'onboarding' | 'kickoff' | 'support' | 'other';
export type MeetingStatus = 'scheduled' | 'completed' | 'cancelled';
export type MeetingSource = 'manual' | 'calendar_sync';

// Workflow status for threads/needs
export type WorkflowStatus =
  | 'needs_response'      // We need to reply
  | 'awaiting_customer'   // We replied, waiting on them
  | 'blocked'             // Something external blocking progress
  | 'snoozed'             // Temporarily hidden until a specific time
  | 'resolved';           // Done

export type ThreadType = 'customer' | 'sidekick' | 'internal';

// Agent types
export type AgentStatus = 'initialized' | 'running' | 'waiting_for_input' | 'resuming' | 'completed' | 'failed';
export type ConfidenceLevel = 'high' | 'medium' | 'low';
export type AutonomyMode = 'full_auto' | 'smart_auto' | 'supervised';

// Settings types
export type WorkspaceRole = 'owner' | 'csm' | 'viewer';
export type AutonomyLevel = 'full_auto' | 'smart_auto' | 'supervised';

// ============================================================================
// Core Entities
// ============================================================================

export type EnrichmentStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface LinkedPage {
  source: string;
  id: string;
  type: string;
  url: string;
  title: string;
  hasAccess: boolean;
}

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
  enrichment_status: EnrichmentStatus | null;
  external_source: string | null;
  external_id: string | null;
  raw_notes: string | null;
  linked_pages: LinkedPage[];
  client_signed_date?: string | null;
  relationship_health?: string | null;
  relationship_health_score?: number | null;
  relationship_health_updated_by?: string | null;
  relationship_health_updated_at?: string | null;
  relationship_health_reason?: string | null;
  // AI Classification (from setup)
  aiClassificationGroup?: string | null;
  aiClassificationConfidence?: number | null;
  aiClassificationReasoning?: string | null;
  aiClassificationWhatIKnow?: string | null;
  aiClassificationUncertainties?: string | null;
  aiClassificationAt?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Signal {
  id: string;
  customer_id: string;
  kind: SignalKind;
  state: SignalState;
  sentence: string | null;
  evidence_text: string | null;
  next_action: string | null;
}

export interface CustomerWithSignals extends Customer {
  signals: Signal[];
}

export interface Stakeholder {
  id: string;
  customer_id: string;
  name: string;
  email: string | null;
  role: string | null;
  status: StakeholderStatus;
  sentiment_note: string | null;
}

export interface GoalObservation {
  id: string;
  text: string;
  confidence: ConfidenceLevel;
  source_type: string;
  observed_at: string;
  source_interaction: {
    id: string;
    sender_name: string | null;
    occurred_at: string;
  } | null;
}

export interface Goal {
  id: string;
  customer_id: string;
  text: string;
  status: GoalStatus;
  sort_order: number;
  source?: string;
  source_type?: string;
  source_date?: string;
  source_interaction_id?: string | null;
  source_thread_id?: string | null;
  observations?: GoalObservation[];
}

export interface Milestone {
  id: string;
  customer_id: string;
  title: string;
  owner_side: OwnerSide;
  target_date: string | null;
  status: MilestoneStatus;
  description: string | null;
  sort_order: number;
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
  snoozed_until: string | null;
  resolved_at: string | null;
  agent_reasoning: string;
  created_at: string;
}

export interface TodayQueueItem extends Need {
  customer_name: string;
  customer_lifecycle: CustomerLifecycle;
  customer_arr_cents: number | null;
  recommendation_primary: string | null;
  recommendation_secondary: string | null;
  recommendation_rationale: string | null;
  plan_id: string | null;
}

// ============================================================================
// Plan & Handoff
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
  status: ApprovalStatus;
  approved_by_user_id: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  human_edited: boolean;
  regeneration_count: number;
  generated_at: string;
  created_at: string;
}

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
  captured_at: string;
  body: string | null;
  sales_commitments: SalesCommitment[] | null;
  technical_context: TechnicalContext[] | null;
  reality_check_confidence: string | null;
  reality_check_risks: string | null;
  status: HandoffStatus;
  user_corrections: Record<string, unknown> | null;
  notion_deal_id: string | null;
  notion_deal_url: string | null;
  created_at: string;
}

export interface HandoffOpenQuestion {
  id: string;
  brief_id: string;
  text: string;
  resolved: boolean;
}

// ============================================================================
// Handbook
// ============================================================================

export interface HandbookDoc {
  id: string;
  workspace_id: string;
  slug: string;
  title: string;
  description: string | null;
  body: string;
  blast_radius: 'low' | 'medium' | 'high';
}

export interface HandbookVersion {
  id: string;
  doc_id: string;
  body: string;
  edited_by_user_id: string | null;
  edited_at: string;
}

// ============================================================================
// Conversations/Threads
// ============================================================================

export interface CustomerSummary {
  id: string;
  name: string;
  slug: string;
  lifecycle: CustomerLifecycle;
  arr_cents: number | null;
  tier: string | null;
}

export interface RelatedThread {
  id: string;
  subject: string | null;
  latest_message_at: string;
  status: ThreadStatus;
  message_count: number;
}

export interface Attachment {
  id: string;
  filename: string;
  url: string;
  mime_type: string;
  size_bytes: number;
}

export interface Mention {
  id: string;
  user_id: string;
  user_name: string;
  user_email: string;
}

export interface ThreadMessage {
  id: string;
  thread_id: string;
  direction: MessageDirection;
  channel: InteractionChannel;
  sender_name: string;
  sender_email: string | null;
  content: string;
  html_content: string | null;
  occurred_at: string;
  attachments: Attachment[];
  mentions: Mention[];
}

export interface DraftResponse {
  id: string;
  thread_id: string;
  content: string;
  suggested_action: DraftSuggestedAction;
  reasoning: string;
  generated_at: string;
}

export interface MeetingSuggestion {
  id: string;
  thread_id: string;
  suggested_type: MeetingSuggestionType;
  suggested_duration: number;
  reasoning: string;
  draft_internal_note: string;
}

export interface ThreadSidekick {
  summary: string;
  recommendations: string[];
}

export interface ThreadStats {
  first_contact_at: string;
  message_count: number;
  our_message_count: number;
  their_message_count: number;
  avg_response_time_minutes: number | null;
}

export interface ThreadDetail {
  id: string;
  need_id: string;
  customer_id: string;
  customer_name: string;
  customer: CustomerSummary;
  need: Need | null;
  need_type: NeedType | null;
  thread_type: ThreadType;
  status: ThreadStatus;
  workflow_status: WorkflowStatus;
  blocked_reason: string | null;
  snoozed_until: string | null;
  channel: InteractionChannel;
  subject: string | null;
  latest_message_at: string;
  stats: ThreadStats;
  related_threads: RelatedThread[];
  current_draft: DraftResponse | null;
  sidekick: ThreadSidekick | null;
  stakeholders: Stakeholder[];
  signals: Signal[];
  milestones: Milestone[];
  upcoming_meetings: UpcomingMeeting[];
  derailment_risks: string[];
  agent_run_id?: string | null;
}

export interface UpcomingMeeting {
  id: string;
  title: string;
  scheduled_at: string;
  duration_minutes: number;
  meeting_type: string;
}

// ============================================================================
// Meetings
// ============================================================================

export interface MeetingAttendee {
  name: string;
  email: string;
  role?: string;
}

export interface Meeting {
  id: string;
  workspace_id: string;
  customer_id: string;
  customer_name: string;
  need_id: string | null;
  need: Need | null;
  title: string;
  type: MeetingType;
  scheduled_at: string;
  duration_minutes: number;
  source: MeetingSource;
  external_event_id: string | null;
  attendees_ours: MeetingAttendee[];
  attendees_theirs: MeetingAttendee[];
  status: MeetingStatus;
  brief: MeetingBrief | null;
  context?: MeetingContext;
}

export interface MeetingBrief {
  id: string;
  meeting_id: string;
  // AI-generated content (from DataConnect MeetingBrief table)
  progress_narrative: string | null;
  progress_facts: Record<string, unknown>[] | null;
  friction: string | null;
  talking_points: MeetingTalkingPoint[] | null;
  value_delivered: string | null;
  risk_to_renewal: string | null;
  expansion_signals: string | null;
  pricing_context: string | null;
  followup_email: MeetingFollowupEmail | null;
  generated_at: string | null;
}

// Backend writes talking_points as list[str] (plain strings).
// The frontend parses each string as the full talking point text.
export type MeetingTalkingPoint = string;

export interface MeetingFollowupEmail {
  subject: string;
  to?: string[]; // populated by backend when known; absent when LLM-drafted
  body: string;
}

export interface MeetingStakeholder {
  id: string;
  name: string;
  email: string;
  role: string;
  status: string;
  sentiment_note: string | null;
}

export interface MeetingContextSignal {
  kind: string;
  state: string;
  sentence: string;
}

export interface MeetingContextMilestone {
  id: string;
  title: string;
  status: string;
  target_date: string | null;
  goal_rationale: string | null;
  goal: { id: string; text: string; is_primary: boolean } | null;
}

export interface MeetingContextCommitment {
  id: string;
  side: string;
  text: string;
  due_label: string | null;
  stake: string | null;
  stake_holder: { id: string; name: string } | null;
}

export interface MeetingContext {
  stakeholders: MeetingStakeholder[];
  signals: MeetingContextSignal[];
  milestones: MeetingContextMilestone[];
  commitments: MeetingContextCommitment[];
  arr_cents: number | null;
  one_liner: string | null;
}

// ============================================================================
// Agent/Sidekick
// ============================================================================

/**
 * Structured question types for HITL (Human-in-the-Loop) UI.
 * These types tell the frontend how to render each question.
 */
export type QuestionType = 'pick_one' | 'pick_many' | 'pick_person' | 'slider' | 'freeform' | 'date' | 'yes_no';

export interface QuestionOption {
  label: string;
  value: string;
  default?: boolean;
  description?: string;
}

export interface PersonOption {
  stakeholder_id?: string;
  name: string;
  role: string;
  avatar_seed: string;
  signal?: 'ok' | 'warn' | 'neutral' | 'risk';
  signal_label?: string;
  last_contact?: string;
  email?: string;
}

export interface AgentQuestion {
  id: string;
  text: string;
  context?: string;
  field?: string; // What data field this relates to
  question_type?: QuestionType; // Backend provides this
  required?: boolean;
  placeholder?: string;
  metadata?: {
    // For pick_one/pick_many
    options?: QuestionOption[];
    allow_decide?: boolean;
    allow_other?: boolean;
    decide_label?: string;
    min_selections?: number;
    max_selections?: number;

    // For pick_person
    people?: PersonOption[];
    allow_manual?: boolean;
    multi_select?: boolean;

    // For slider
    min?: number;
    max?: number;
    default?: number;
    step?: number;
    label_low?: string;
    label_high?: string;
    format_template?: string;

    // For freeform
    multiline?: boolean;
    max_length?: number;

    // For date
    min_date?: string;
    max_date?: string;
    default_date?: string;

    // For yes_no
    yes_label?: string;
    no_label?: string;
  };
}

export interface AgentQuestionAnswer {
  question_id: string;
  answer: string;
}

export interface AgentRun {
  id: string;
  workspace_id: string;
  agent_name: string;
  trigger_source: string;
  status: AgentStatus;
  current_step: string | null;
  confidence_level: ConfidenceLevel | null;
  paused_at_step: string | null;
  paused_at: string | null;
  questions: AgentQuestion[] | null;
  customer_id: string | null;
  customer_name: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface SidekickNeed extends TodayQueueItem {
  agent_run_id: string | null;
  agent_questions: AgentQuestion[] | null;
  agent_context: string | null;
}

// ============================================================================
// Settings
// ============================================================================

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  avatar_seed: string | null;
  notification_preferences: NotificationPreferences | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationPreferences {
  email: boolean;
  in_app: boolean;
}

export interface WorkspaceMembership {
  workspace_id: string;
  user_id: string;
  role: WorkspaceRole;
  joined_at: string;
  workspace_name: string;
  workspace_slug: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  autonomy_level: AutonomyLevel;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceMember {
  workspace_id: string;
  user_id: string;
  role: WorkspaceRole;
  joined_at: string;
  email: string;
  display_name: string | null;
}

export interface TeamMember {
  id: string;
  name: string;
  email: string;
  avatar_url?: string;
}

// ============================================================================
// Response Types
// ============================================================================

export interface DashboardStats {
  escalations: number;
  active_onboardings: number;
  renewals_30_days: number;
  total_arr_cents: number;
  pending_approvals: number;
}

export interface TodayResponse {
  items: TodayQueueItem[];
  count: number;
  active_count: number;
}

export interface CustomersResponse {
  customers: CustomerWithSignals[];
  lifecycle_counts: Record<string, number>;
  total: number;
}

export interface CustomerDetailResponse {
  customer: Customer;
  stakeholders: Stakeholder[];
  goals: Goal[];
  signals: Signal[];
  open_needs: Need[];
  milestones: Milestone[];
  handoff_brief: HandoffBrief | null;
  ai_plan: AIPlan | null;
  handoff_open_questions: HandoffOpenQuestion[];
}

export interface PlanDetailResponse {
  plan: AIPlan;
  brief: HandoffBrief | null;
  customer: Customer | null;
}

export interface HandoffsResponse {
  briefs: HandoffBrief[];
  count: number;
}

export interface HandoffDetailResponse {
  brief: HandoffBrief;
  plan: AIPlan | null;
  open_questions: HandoffOpenQuestion[];
}

export interface HandbookResponse {
  docs: HandbookDoc[];
  count: number;
}

export interface HandbookDocResponse {
  doc: HandbookDoc;
  versions: HandbookVersion[];
}

export interface MeetingsResponse {
  meetings: Meeting[];
  count: number;
}

export interface MeetingDetailResponse {
  meeting: Meeting;
}

export interface ThreadDetailResponse {
  thread: ThreadDetail;
}

export interface ThreadListResponse {
  threads: ThreadDetail[];
  count: number;
}

export interface ThreadMessagesResponse {
  messages: ThreadMessage[];
  count: number;
}

export interface AgentRunDetailResponse {
  run: AgentRun;
  need: SidekickNeed | null;
  customer_name: string | null;
}

export interface CurrentUserResponse {
  user: User;
  memberships: WorkspaceMembership[];
}

export interface WorkspaceSettingsResponse {
  workspace: Workspace;
  members: WorkspaceMember[];
  user_role: WorkspaceRole;
}

// ============================================================================
// Input Types (for mutations)
// ============================================================================

export interface UpdateCustomerInput {
  name?: string;
  one_liner?: string;
  tier?: string;
  arr_cents?: number;
  lifecycle?: CustomerLifecycle;
}

export interface CreateCustomerInput {
  name: string;
  slug?: string;
  one_liner?: string;
  tier?: string;
  arr_cents?: number;
  lifecycle?: CustomerLifecycle;
  raw_notes?: string;
  linked_pages?: LinkedPage[];
}

export interface CreateStakeholderInput {
  name: string;
  email?: string;
  role?: string;
  status?: StakeholderStatus;
  sentiment_note?: string;
}

export interface UpdateStakeholderInput {
  name?: string;
  email?: string;
  role?: string;
  status?: StakeholderStatus;
  sentiment_note?: string;
}

export interface CreateMilestoneInput {
  title: string;
  owner_side: OwnerSide;
  target_date?: string;
  status?: MilestoneStatus;
  description?: string;
}

export interface UpdateMilestoneInput {
  title?: string;
  owner_side?: OwnerSide;
  target_date?: string;
  status?: MilestoneStatus;
  description?: string;
}

export interface CreateGoalInput {
  text: string;
  status?: GoalStatus;
}

export interface UpdateGoalInput {
  text?: string;
  status?: GoalStatus;
}

export interface CreateMeetingInput {
  customer_id: string;
  need_id?: string | null;
  title: string;
  type: MeetingType;
  scheduled_at: string;
  duration_minutes: number;
  attendees_ours?: MeetingAttendee[];
  attendees_theirs?: MeetingAttendee[];
}

export interface UpdateMeetingInput {
  title?: string;
  type?: MeetingType;
  scheduled_at?: string;
  duration_minutes?: number;
  need_id?: string | null;
  attendees_ours?: MeetingAttendee[];
  attendees_theirs?: MeetingAttendee[];
  status?: MeetingStatus;
  prep_notes?: string;
  live_notes?: string;
  followup_notes?: string;
}

export interface ApprovePlanInput {
  milestones?: PlanMilestone[];
}

export interface UpdateHandoffInput {
  sales_commitments?: SalesCommitment[];
  technical_context?: TechnicalContext[];
  reality_check_confidence?: string;
  reality_check_risks?: string;
}

export interface UpdateHandbookInput {
  body?: string;
  title?: string;
  description?: string;
}

export interface SendMessageInput {
  content: string;
  is_internal: boolean;
  channel?: InteractionChannel;
  mentions?: string[];
}

export interface RequestDraftInput {
  vibe_input?: string;
}

export interface UpdateWorkflowStatusInput {
  workflow_status: WorkflowStatus;
  blocked_reason?: string;
  snoozed_until?: string;
}

export interface SubmitAnswersInput {
  answers: AgentQuestionAnswer[];
}

export interface UpdateUserInput {
  display_name?: string;
  avatar_seed?: string;
  notification_preferences?: NotificationPreferences;
}

export interface UpdateWorkspaceSettingsInput {
  name?: string;
  autonomy_level?: AutonomyLevel;
}

// ============================================================================
// Misc Types
// ============================================================================

export interface CustomerIntelTransmission {
  id: string;
  channel: 'email' | 'slack' | 'meeting' | 'phone' | 'notion';
  direction: 'customer' | 'us' | 'internal';
  sender: string | null;
  occurred_at: string;
  subject: string | null;
  summary: string | null;
}

export interface CustomerIntelResponse {
  customer_name: string;
  engagement: {
    level: 'Strong' | 'Moderate' | 'Weak' | 'Unknown';
    activity_bars: number[];
    description: string | null;
    evidence: string | null;
  };
  transmissions: CustomerIntelTransmission[];
  sentiment: {
    state: 'positive' | 'neutral' | 'negative';
    quote: string | null;
    summary: string | null;
  } | null;
}

// ============================================================================
// Integrations
// ============================================================================

export type IntegrationType = 'gmail' | 'slack' | 'notion' | 'notion_mcp';
export type IntegrationStatus = 'active' | 'error' | 'revoked' | 'not_connected';

export interface Integration {
  integration_type: IntegrationType;
  status: IntegrationStatus;
  connected: boolean;
  last_sync_at: string | null;
  last_error: string | null;
  config: Record<string, unknown> | null;
}

export interface IntegrationsListResponse {
  integrations: Integration[];
}

export interface OAuthStartResponse {
  authorization_url: string;
  state: string;
}

// Error class for API errors
export class APIError extends Error {
  constructor(
    public statusCode: number,
    message: string,
    public code?: string
  ) {
    super(message);
    this.name = 'APIError';
  }
}
