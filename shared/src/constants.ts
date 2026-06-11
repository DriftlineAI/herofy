// Herofy Shared Constants
// These match the PostgreSQL enum types in the schema

export const WorkspaceRole = {
  OWNER: 'owner',
  CSM: 'csm',
  VIEWER: 'viewer',
} as const;
export type WorkspaceRole = typeof WorkspaceRole[keyof typeof WorkspaceRole];

export const CustomerLifecycle = {
  PROSPECT: 'prospect',
  HANDOFF: 'handoff',
  ONBOARDING: 'onboarding',
  ACTIVE: 'active',
  RENEWING: 'renewing',
  AT_RISK: 'at_risk',
  CHURNED: 'churned',
} as const;
export type CustomerLifecycle = typeof CustomerLifecycle[keyof typeof CustomerLifecycle];

export const RenewalReadiness = {
  NOT_STARTED: 'not_started',
  TRACKING: 'tracking',
  READY: 'ready',
  AT_RISK: 'at_risk',
} as const;
export type RenewalReadiness = typeof RenewalReadiness[keyof typeof RenewalReadiness];

export const StakeholderStatus = {
  ACTIVE: 'active',
  DEPARTED: 'departed',
} as const;
export type StakeholderStatus = typeof StakeholderStatus[keyof typeof StakeholderStatus];

export const GoalStatus = {
  ACTIVE: 'active',
  ACHIEVED: 'achieved',
  DROPPED: 'dropped',
} as const;
export type GoalStatus = typeof GoalStatus[keyof typeof GoalStatus];

export const InteractionChannel = {
  EMAIL: 'email',
  SLACK: 'slack',
  MEETING: 'meeting',
  IN_APP: 'in_app',
  SMS_SCREENSHOT: 'sms_screenshot',
  NOTE: 'note',
} as const;
export type InteractionChannel = typeof InteractionChannel[keyof typeof InteractionChannel];

export const InteractionDirection = {
  US: 'us',
  CUSTOMER: 'customer',
  INTERNAL: 'internal',
} as const;
export type InteractionDirection = typeof InteractionDirection[keyof typeof InteractionDirection];

export const ThreadStatus = {
  OPEN: 'open',
  RESOLVED: 'resolved',
  ARCHIVED: 'archived',
} as const;
export type ThreadStatus = typeof ThreadStatus[keyof typeof ThreadStatus];

export const ThreadCategory = {
  SUPPORT: 'support',
  ONBOARDING: 'onboarding',
  SUCCESS: 'success',
  UNCATEGORIZED: 'uncategorized',
} as const;
export type ThreadCategory = typeof ThreadCategory[keyof typeof ThreadCategory];

export const MeetingSource = {
  MANUAL: 'manual',
  GOOGLE_CALENDAR: 'google_calendar',
  MCP_SYNC: 'mcp_sync',
} as const;
export type MeetingSource = typeof MeetingSource[keyof typeof MeetingSource];

export const MilestoneStatus = {
  NOT_STARTED: 'not_started',
  IN_PROGRESS: 'in_progress',
  BLOCKED: 'blocked',
  DONE: 'done',
  SKIPPED: 'skipped',
} as const;
export type MilestoneStatus = typeof MilestoneStatus[keyof typeof MilestoneStatus];

export const OwnerSide = {
  US: 'us',
  CUSTOMER: 'customer',
  JOINT: 'joint',
} as const;
export type OwnerSide = typeof OwnerSide[keyof typeof OwnerSide];

export const CommitmentStatus = {
  IN_PROGRESS: 'in_progress',
  DONE: 'done',
  OVERDUE: 'overdue',
} as const;
export type CommitmentStatus = typeof CommitmentStatus[keyof typeof CommitmentStatus];

export const CommitmentSide = {
  US: 'us',
  THEM: 'them',
} as const;
export type CommitmentSide = typeof CommitmentSide[keyof typeof CommitmentSide];

export const SignalKind = {
  ENGAGEMENT: 'engagement',
  SENTIMENT: 'sentiment',
  COMMITMENTS: 'commitments',
} as const;
export type SignalKind = typeof SignalKind[keyof typeof SignalKind];

export const SignalState = {
  OK: 'ok',
  WARN: 'warn',
  RISK: 'risk',
} as const;
export type SignalState = typeof SignalState[keyof typeof SignalState];

export const RiskLevel = {
  LOW: 'low',
  MEDIUM: 'medium',
  HIGH: 'high',
} as const;
export type RiskLevel = typeof RiskLevel[keyof typeof RiskLevel];

export const BlastRadius = {
  LOW: 'low',
  MEDIUM: 'medium',
  HIGH: 'high',
} as const;
export type BlastRadius = typeof BlastRadius[keyof typeof BlastRadius];

// HITL-specific enums
export const ApprovalStatus = {
  PENDING_APPROVAL: 'pending_approval',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  SUPERSEDED: 'superseded',
} as const;
export type ApprovalStatus = typeof ApprovalStatus[keyof typeof ApprovalStatus];

export const HandoffStatus = {
  DRAFT: 'draft',
  CONFIRMED: 'confirmed',
  NEEDS_CORRECTION: 'needs_correction',
} as const;
export type HandoffStatus = typeof HandoffStatus[keyof typeof HandoffStatus];

export const DraftResponseStatus = {
  PENDING_REVIEW: 'pending_review',
  APPROVED: 'approved',
  SENT: 'sent',
  DISCARDED: 'discarded',
  EDITED: 'edited',
} as const;
export type DraftResponseStatus = typeof DraftResponseStatus[keyof typeof DraftResponseStatus];

// Need types - comprehensive list
export const NeedType = {
  URGENT_SUPPORT: 'urgent_support',
  GOING_DARK: 'going_dark',
  STALLED_MILESTONE: 'stalled_milestone',
  APPROACHING_RENEWAL: 'approaching_renewal',
  OPEN_COMMITMENT_OVERDUE: 'open_commitment_overdue',
  FRUSTRATED_SIGNAL: 'frustrated_signal',
  CHAMPION_DEPARTED: 'champion_departed',
  ONBOARDING_BEHIND: 'onboarding_behind',
  RENEWAL_AT_RISK: 'renewal_at_risk',
  NEW_HANDOFF: 'new_handoff',
  MEETING_PREP_READY: 'meeting_prep_ready',
  POSITIVE_SIGNAL: 'positive_signal',
  EXPANSION_SIGNAL: 'expansion_signal',
  CHECK_IN_DUE: 'check_in_due',
  ESCALATION: 'escalation',
  PLAN_APPROVAL_REQUIRED: 'plan_approval_required',
  DRAFT_RESPONSE_READY: 'draft_response_ready',
  UNCATEGORIZED: 'uncategorized',
} as const;
export type NeedType = typeof NeedType[keyof typeof NeedType];
