import React, { useEffect, useRef, useState } from 'react';
import { useParams, NavLink, Link, useSearchParams, useNavigate } from 'react-router-dom';
import { RefCode, Timestamp, Pulse, Sidekick } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { PlanTimeline, PlanTimelineItem } from '@/components/ui/PlanTimeline';
import {
  useCustomer,
  useCustomerInteractions,
  useMeetings,
  useThreads,
  useCreateStakeholder,
  useUpdateStakeholder,
  useDeleteStakeholder,
  useCreateMilestone,
  useUpdateMilestone,
  useDeleteMilestone,
  useCreateGoal,
  useUpdateGoal,
  useDeleteGoal,
  useSyncNotionPage,
  useSidekickAlert,
  useSidekickItems,
  useUpdateCustomerHealth,
  useResolveNeed,
  useCreateHuddle,
  usePostHuddleMessage,
  useCustomerHandoffWithPlan,
  useCustomerPlans,
  usePlaybook,
  useCustomerTrends,
  useGoalsWithMilestones,
  useProgressVectorsForCustomer,
  useCustomerStrategy,
  useRiskBriefsForCustomer,
  useUpdateCustomer,
  useIntegrationStatus,
  useSearchNotionPages,
  useLinkPageToCustomer,
  type NotionPageResult,
} from '@/lib/dataconnect-hooks';
import { useWorkspaceNotifications, useRefreshOnFocus } from '@/lib/realtime-hooks';
import { useWorkspace } from '@/lib/workspace';
import { getAuth } from 'firebase/auth';
import type { LinkedPage } from '@/lib/api';
import type {
  Customer,
  Stakeholder,
  Goal,
  Signal,
  Need,
  Milestone,
  SignalState,
  MilestoneStatus,
  StakeholderStatus,
  GoalStatus,
  HandoffBrief,
  AIPlan,
  HandoffOpenQuestion,
  Meeting,
  CreateStakeholderInput,
  UpdateStakeholderInput,
  CreateMilestoneInput,
  UpdateMilestoneInput,
  CreateGoalInput,
  UpdateGoalInput,
  ThreadDetail,
  InteractionChannel,
} from '@/lib/api';
import {
  ChevronRight,
  ChevronDown,
  ChevronUp,
  User,
  Target,
  Flag,
  ShieldAlert,
  AlertTriangle,
  FileText,
  CheckCircle,
  Check,
  Clock,
  XCircle,
  Plus,
  Edit3,
  Trash2,
  Calendar,
  ArrowLeft,
  Zap,
  MessageSquare,
  Mail,
  Hash,
  Video,
  Search,
  Upload,
  Eye,
  ExternalLink,
  Filter,
  RefreshCw,
} from 'lucide-react';
import { StakeholderModal } from '@/components/customer/StakeholderModal';
import { MilestoneModal } from '@/components/customer/MilestoneModal';
import { PlaybookPickerModal } from '@/components/customer/PlaybookPickerModal';
import { RiskPlayTriggerModal } from '@/components/customer/RiskPlayTriggerModal';
import { HealthIndicator } from '@/components/customer/HealthIndicator';
import { TrendCard } from '@/components/ui/TrendCard';
import { HealthOverrideModal } from '@/components/customer/HealthOverrideModal';
import { SidekickAlert } from '@/components/sidekick';
import { OnboardingCard } from '@/components/customer/OnboardingCard';
import { RiskSavePlayCard } from '@/components/customer/RiskSavePlayCard';
import { motion, AnimatePresence } from 'motion/react';

// ============================================================================
// Type definitions for future AI-powered features
// ============================================================================

interface RelationshipSignal {
  type: 'engagement' | 'sentiment' | 'commitments';
  narrative: string;
  state: 'ok' | 'warn' | 'risk';
}

interface RecentInteraction {
  id: string;
  channel: InteractionChannel;
  summary: string;
  occurred_at: string;
  participants?: string[];
}

interface KeyMoment {
  id: string;
  date: string;
  summary: string;
}

interface ContractVersion {
  id: string;
  title: string;
  signed_at: string | null;
  uploaded_at: string;
  pages: number;
  forwarded_by?: string;
  status: 'viewing' | 'signed' | 'pending';
}

interface ContractFlag {
  id: string;
  title: string;
  description: string;
  severity: 'warning' | 'info';
}

interface ContractTerm {
  label: string;
  value: string;
  warning?: string;
}

// ============================================================================
// Utility Functions
// ============================================================================

function formatARR(cents: number | null): string {
  if (!cents) return '-';
  const amount = cents / 100;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return `$${amount}`;
}

function getSignalColor(state: SignalState): string {
  switch (state) {
    case 'ok': return 'bg-signal-ok';
    case 'warn': return 'bg-signal-warn';
    case 'risk': return 'bg-signal-bad';
    default: return 'bg-fg-400';
  }
}

function getSignalTextColor(state: SignalState): string {
  switch (state) {
    case 'ok': return 'text-signal-ok';
    case 'warn': return 'text-signal-warn';
    case 'risk': return 'text-signal-bad';
    default: return 'text-fg-400';
  }
}

function formatRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
}

function getChannelIcon(channel: InteractionChannel) {
  switch (channel) {
    case 'email': return Mail;
    case 'slack': return Hash;
    case 'meeting': return Video;
    default: return MessageSquare;
  }
}

function getChannelLabel(channel: InteractionChannel): string {
  switch (channel) {
    case 'email': return 'EMAIL';
    case 'slack': return 'SLACK';
    case 'meeting': return 'MEETING';
    case 'in_app': return 'IN-APP';
    default: return channel.toUpperCase();
  }
}

// ============================================================================
// Tab Components
// ============================================================================

type TabId = 'overview' | 'brief' | 'plans' | 'history' | 'contract' | 'contacts' | 'sidekick';

type PlanLens = 'north-star' | 'distance' | 'ledger' | 'memo';

interface TabProps {
  id: TabId;
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}

function Tab({ id, label, count, active, onClick }: TabProps) {
  const isSidekick = id === 'sidekick';
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-1 py-3 text-sm font-medium font-mono uppercase tracking-wider border-b-2 transition-colors',
        active
          ? 'border-accent text-fg-100'
          : isSidekick
            ? 'border-transparent text-accent hover:text-accent hover:border-accent/40'
            : 'border-transparent text-fg-400 hover:text-fg-200 hover:border-border'
      )}
    >
      {label}
      {count !== undefined && (
        <span className={cn(
          'ml-1.5',
          active
            ? 'text-fg-300'
            : isSidekick
              ? 'text-accent'
              : 'text-fg-400'
        )}>
          · {count}
        </span>
      )}
    </button>
  );
}

// ============================================================================
// Brief Tab Component (for Handoff/Onboarding customers)
// ============================================================================

interface BriefTabProps {
  customerId: string;
}

function BriefTab({ customerId }: BriefTabProps) {
  const { data, isLoading } = useCustomerHandoffWithPlan(customerId);

  // Also fetch plans directly (in case plan isn't linked to brief)
  const { data: customerPlansData, isLoading: plansLoading } = useCustomerPlans(customerId);

  if (isLoading || plansLoading) {
    return (
      <div className="text-fg-400 text-center py-12">
        Loading handoff brief...
      </div>
    );
  }

  if (!data || !data.brief) {
    return (
      <div className="border border-border p-8 text-center">
        <div className="text-fg-400 mb-2">No handoff brief found</div>
        <p className="text-sm text-fg-400">
          A handoff brief will be created when the Handoff Agent processes this customer.
        </p>
      </div>
    );
  }

  const { brief, open_questions } = data;
  // Use plan from brief if available, otherwise fall back to direct customer plan
  const plan = data.plan || customerPlansData?.plans?.[0];
  const capturedDate = brief.created_at
    ? new Date(brief.created_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : 'Unknown';

  return (
    <div className="space-y-8">
      {/* Handoff Brief Section */}
      <div className="border border-border p-6">
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-fg-400 mb-1">
              HANDOFF BRIEF · Captured {capturedDate}
            </div>
            <div className={cn(
              'text-xs font-mono uppercase tracking-wider px-2 py-0.5 inline-block',
              brief.status === 'confirmed'
                ? 'text-signal-ok bg-signal-ok/10'
                : brief.status === 'draft'
                ? 'text-signal-warn bg-amber-400/10'
                : 'text-accent bg-rust-400/10'
            )}>
              {brief.status === 'confirmed' ? 'Confirmed' : brief.status === 'draft' ? 'Draft' : 'Needs Correction'}
            </div>
          </div>
          {brief.notion_deal_url && (
            <a
              href={brief.notion_deal_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-fg-400 hover:text-fg-200 flex items-center gap-1"
            >
              View in Notion
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>

        {/* Body (markdown) - primary content from agent */}
        {brief.body && (
          <div className="mb-6 prose prose-invert prose-sm max-w-none">
            <div className="whitespace-pre-wrap text-fg-200 text-sm leading-relaxed">
              {brief.body}
            </div>
          </div>
        )}

        {/* Sales Commitments (legacy structured field) */}
        {!brief.body && brief.sales_commitments && brief.sales_commitments.length > 0 && (
          <div className="mb-6">
            <h4 className="text-[10px] font-mono uppercase tracking-widest text-fg-400 mb-3">
              SALES COMMITMENTS
            </h4>
            <ul className="space-y-2">
              {brief.sales_commitments.map((commitment: { text?: string; commitment?: string }, i: number) => (
                <li key={i} className="flex items-start gap-2 text-fg-200">
                  <span className="text-fg-400 mt-0.5">•</span>
                  <span>{commitment.text || commitment.commitment || JSON.stringify(commitment)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Technical Context (legacy structured field) */}
        {!brief.body && brief.technical_context && brief.technical_context.length > 0 && (
          <div className="mb-6">
            <h4 className="text-[10px] font-mono uppercase tracking-widest text-fg-400 mb-3">
              TECHNICAL CONTEXT
            </h4>
            <ul className="space-y-2">
              {brief.technical_context.map((context: { text?: string; requirement?: string }, i: number) => (
                <li key={i} className="flex items-start gap-2 text-fg-200">
                  <span className="text-fg-400 mt-0.5">•</span>
                  <span>{context.text || context.requirement || JSON.stringify(context)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Reality Check */}
        {(brief.reality_check_confidence || brief.reality_check_risks) && (
          <div className="mb-6 border-t border-border pt-6">
            <h4 className="text-[10px] font-mono uppercase tracking-widest text-fg-400 mb-3">
              REALITY CHECK
            </h4>
            {brief.reality_check_confidence && (
              <div className="flex items-center gap-2 mb-2">
                <span className="text-fg-400 text-sm">Confidence:</span>
                <span className={cn(
                  'text-sm font-medium',
                  brief.reality_check_confidence === 'high' && 'text-signal-ok',
                  brief.reality_check_confidence === 'medium' && 'text-signal-warn',
                  brief.reality_check_confidence === 'low' && 'text-accent'
                )}>
                  {brief.reality_check_confidence.charAt(0).toUpperCase() + brief.reality_check_confidence.slice(1)}
                </span>
              </div>
            )}
            {brief.reality_check_risks && (
              <p className="text-fg-300 text-sm">{brief.reality_check_risks}</p>
            )}
          </div>
        )}

        {/* Open Questions */}
        {open_questions && open_questions.length > 0 && (
          <div className="border-t border-border pt-6">
            <h4 className="text-[10px] font-mono uppercase tracking-widest text-fg-400 mb-3">
              OPEN QUESTIONS
            </h4>
            <ul className="space-y-2">
              {open_questions.map((q) => (
                <li key={q.id} className="flex items-start gap-2">
                  <span className={cn(
                    'mt-0.5',
                    q.resolved ? 'text-signal-ok' : 'text-signal-warn'
                  )}>
                    {q.resolved ? <CheckCircle className="w-4 h-4" /> : <Clock className="w-4 h-4" />}
                  </span>
                  <span className={cn(
                    q.resolved ? 'text-fg-400 line-through' : 'text-fg-200'
                  )}>
                    {q.text}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* AI Plan Section */}
      {plan && (
        <div className="border border-border p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-fg-400 mb-1">
                AI PLAN · {plan.status === 'pending_approval' ? 'Pending Approval' : plan.status === 'approved' ? 'Approved' : plan.status}
              </div>
              <div className="text-fg-100 font-medium">{plan.archetype_name}</div>
              <div className="text-fg-400 text-sm">
                {plan.milestone_count} milestones · {plan.duration_label}
              </div>
            </div>
            <div className={cn(
              'text-xs font-mono uppercase tracking-wider px-2 py-0.5',
              plan.status === 'approved'
                ? 'text-signal-ok bg-signal-ok/10'
                : plan.status === 'pending_approval'
                ? 'text-signal-warn bg-amber-400/10'
                : 'text-fg-400 bg-border'
            )}>
              {plan.status === 'approved' ? 'Approved' : plan.status === 'pending_approval' ? 'Awaiting Review' : plan.status}
            </div>
          </div>

          {plan.headline && (
            <p className="text-fg-200 mb-4">{plan.headline}</p>
          )}

          {plan.status === 'pending_approval' && (
            <Link
              to={`/app/plans/${plan.id}`}
              className="inline-flex items-center gap-2 bg-accent text-page px-4 py-2 text-sm font-medium hover:bg-accent-hover transition-colors"
            >
              Review & Approve Plan
              <ChevronRight className="w-4 h-4" />
            </Link>
          )}

          {plan.status === 'approved' && plan.approved_at && (
            <div className="text-sm text-fg-400">
              Approved {new Date(plan.approved_at).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
              })}
              {plan.approved_by && ` by ${plan.approved_by}`}
            </div>
          )}
        </div>
      )}

      {/* No Plan Yet */}
      {!plan && (
        <div className="border border-border p-8 text-center">
          <div className="text-fg-400 mb-2">No AI plan generated yet</div>
          <p className="text-sm text-fg-400">
            An AI-generated onboarding plan will appear here once the Handoff Agent completes processing.
          </p>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Overview Tab Components
// ============================================================================

function WhatTheyCareAbout({
  goals,
  customerId,
  onCreateGoal,
  onUpdateGoal,
  onDeleteGoal,
  isCreating,
  isUpdating,
}: {
  goals: Goal[];
  customerId: string;
  onCreateGoal: (data: CreateGoalInput) => void;
  onUpdateGoal: (goalId: string, data: UpdateGoalInput) => void;
  onDeleteGoal: (goalId: string) => void;
  isCreating: boolean;
  isUpdating: boolean;
}) {
  const [isAdding, setIsAdding] = React.useState(false);
  const [newGoalText, setNewGoalText] = React.useState('');
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editText, setEditText] = React.useState('');
  const inputRef = React.useRef<HTMLInputElement>(null);
  const editInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (isAdding && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isAdding]);

  React.useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
    }
  }, [editingId]);

  const handleAdd = () => {
    if (newGoalText.trim()) {
      onCreateGoal({ text: newGoalText.trim(), status: 'active' });
      setNewGoalText('');
      setIsAdding(false);
    }
  };

  const handleStartEdit = (goal: Goal) => {
    setEditingId(goal.id);
    setEditText(goal.text);
  };

  const handleSaveEdit = () => {
    if (editingId && editText.trim()) {
      onUpdateGoal(editingId, { text: editText.trim() });
      setEditingId(null);
      setEditText('');
    }
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent, action: 'add' | 'edit') => {
    if (e.key === 'Enter') {
      e.preventDefault();
      action === 'add' ? handleAdd() : handleSaveEdit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      action === 'add' ? setIsAdding(false) : handleCancelEdit();
    }
  };

  // Helper to format goal source attribution
  const formatGoalSource = (goal: Goal) => {
    if (!goal.source_type || !goal.source) return 'Added to customer goals';

    const sourceTypeMap: Record<string, string> = {
      'handoff_brief': 'Handoff',
      'enrichment': 'Enrichment',
      'manual': 'Manual',
      'interaction': 'Conversation',
    };

    const sourceLabel = sourceTypeMap[goal.source_type] || goal.source_type;
    const date = goal.source_date ? new Date(goal.source_date).toLocaleDateString() : '';

    return `${sourceLabel}${date ? ` · ${date}` : ''}`;
  };

  const activeGoals = goals.filter(g => g.status === 'active');

  return (
    <div className="mb-8 grid grid-cols-1 lg:grid-cols-2 gap-8">
      {/* Left column: What they care about */}
      <div>
        <SectionLabel
          label="WHAT THEY CARE ABOUT"
          action={
            <button
              onClick={() => setIsAdding(true)}
              className="text-[11px] font-mono uppercase tracking-[0.2em] text-fg-400 hover:text-fg-200 flex items-center gap-1 transition-colors"
            >
              <Plus className="w-3 h-3" />
              Add
            </button>
          }
        />

        <ul className="space-y-4">
          {activeGoals.map((goal) => (
            <li key={goal.id} className="group">
              {editingId === goal.id ? (
                <div className="flex items-center gap-2">
                  <input
                    ref={editInputRef}
                    type="text"
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => handleKeyDown(e, 'edit')}
                    onBlur={handleSaveEdit}
                    className="flex-1 bg-surface-2 border border-border px-2 py-1 text-fg-200 text-base focus:outline-none focus:border-accent"
                    disabled={isUpdating}
                  />
                </div>
              ) : (
                <>
                  <div className="flex items-start gap-2">
                    <p className="flex-1 text-fg-200 text-base leading-relaxed">{goal.text}</p>
                    <div className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1 shrink-0">
                      <button
                        onClick={() => handleStartEdit(goal)}
                        className="p-1 text-fg-400 hover:text-fg-200 transition-colors"
                        title="Edit"
                      >
                        <Edit3 className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => onDeleteGoal(goal.id)}
                        className="p-1 text-fg-400 hover:text-accent transition-colors"
                        title="Remove"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                  {/* Goal source attribution */}
                  <p className="text-xs text-fg-400 italic mt-1">
                    {formatGoalSource(goal)}
                  </p>
                </>
              )}
            </li>
          ))}

          {/* Add new goal inline */}
          {isAdding && (
            <li>
              <div className="flex items-center gap-2">
                <input
                  ref={inputRef}
                  type="text"
                  value={newGoalText}
                  onChange={(e) => setNewGoalText(e.target.value)}
                  onKeyDown={(e) => handleKeyDown(e, 'add')}
                  placeholder="What does this customer care about?"
                  className="flex-1 bg-surface-2 border border-border px-2 py-1 text-fg-200 text-base placeholder:text-fg-400 focus:outline-none focus:border-accent"
                  disabled={isCreating}
                />
                <button
                  onClick={handleAdd}
                  disabled={!newGoalText.trim() || isCreating}
                  className="text-xs font-mono text-accent hover:text-accent disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Save
                </button>
                <button
                  onClick={() => {
                    setIsAdding(false);
                    setNewGoalText('');
                  }}
                  className="text-xs font-mono text-fg-400 hover:text-fg-200"
                >
                  Cancel
                </button>
              </div>
            </li>
          )}

          {/* Empty state */}
          {activeGoals.length === 0 && !isAdding && (
            <li className="text-fg-400 text-sm italic">
              No goals recorded yet.{' '}
              <button
                onClick={() => setIsAdding(true)}
                className="text-accent hover:text-accent not-italic"
              >
                Add one
              </button>
            </li>
          )}
        </ul>
      </div>

      {/* Right column: Sidekick Observed */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <Zap className="w-3 h-3 text-fg-400" />
          <h3 className="text-xs font-mono uppercase tracking-widest text-fg-400">
            SIDEKICK // OBSERVED
          </h3>
        </div>
        {activeGoals.length > 0 ? (
          <div className="space-y-6">
            {activeGoals.map((goal) => {
              const observations = goal.observations?.slice(0, 3) || [];

              if (observations.length === 0) {
                return (
                  <div key={`obs-${goal.id}`} className="text-sm text-fg-400 italic">
                    Tracking progress on this goal. Waiting for Sidekick to surface relevant observations.
                  </div>
                );
              }

              return (
                <div key={`obs-${goal.id}`} className="space-y-3">
                  {observations.map((obs) => (
                    <div
                      key={obs.id}
                      className="border-l-2 border-accent pl-3 py-1"
                    >
                      <p className="text-sm text-fg-300 leading-relaxed mb-1">
                        {obs.text}
                      </p>
                      <div className="flex items-center gap-2 text-xs text-fg-400">
                        <span>
                          {new Date(obs.observed_at).toLocaleDateString()}
                        </span>
                        {obs.source_interaction?.sender_name && (
                          <>
                            <span>·</span>
                            <span>{obs.source_interaction.sender_name}</span>
                          </>
                        )}
                        {obs.confidence && obs.confidence !== 'high' && (
                          <>
                            <span>·</span>
                            <span className="italic">{obs.confidence} confidence</span>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-fg-400 italic">
            Add goals to see Sidekick's observations
          </p>
        )}
      </div>
    </div>
  );
}

function RelationshipSignalsSection({ signals }: { signals: RelationshipSignal[] }) {
  if (signals.length === 0) return null;

  return (
    <div className="mb-8">
      <h3 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-2">
        RELATIONSHIP SIGNALS
      </h3>
      <p className="text-xs text-fg-400 italic mb-4">
        Three sentences, written by the system, edited by no one. Not a score.
      </p>
      <div className="space-y-4">
        {signals.map((signal) => (
          <div key={signal.type} className="flex items-start gap-3">
            <div className={cn('w-2 h-2 rounded-full mt-2 shrink-0', getSignalColor(signal.state))} />
            <div>
              <span className={cn('text-[10px] font-mono uppercase tracking-widest block mb-1', getSignalTextColor(signal.state))}>
                {signal.type}
              </span>
              <p className="text-fg-200">{signal.narrative}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Right-rail panel: open Sidekick items (questions/working) for this customer.
function SidekickRail({ items }: { items: SidekickItem[] }) {
  const openItems = (items || []).filter((i) => !i.resolvedAt);
  if (openItems.length === 0) return null;

  return (
    <div className="border border-border bg-surface p-4">
      <div className="flex items-center gap-2 mb-3">
        <Zap className="w-3 h-3 fill-rust-500 text-accent" />
        <h3 className="text-[10px] font-mono uppercase tracking-[0.2em] text-accent">
          SIDEKICK · OPEN
        </h3>
        <span className="text-[10px] font-mono text-fg-400">· {openItems.length}</span>
      </div>

      <div className="space-y-3">
        {openItems.map((item) => {
          const working = item.type === 'working';
          return (
            <div key={item.id} className={cn('border-l-2 pl-3', working ? 'border-border' : 'border-accent')}>
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-fg-400">
                  {working ? 'Working' : 'Asking'}
                </span>
                {item.timestampLabel && (
                  <span className="text-[9px] font-mono text-fg-400">· {item.timestampLabel}</span>
                )}
                {item.isBlocking && (
                  <span className="text-[9px] font-mono uppercase tracking-[0.2em] text-signal-bad">Blocking</span>
                )}
              </div>
              <p className="text-sm text-fg-200 leading-snug">
                {item.question || item.text || item.task || 'Sidekick is working…'}
              </p>
            </div>
          );
        })}
      </div>

      <NavLink
        to="/app/sidekick"
        className="mt-4 inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-[0.2em] text-accent hover:text-accent-hover transition-colors"
      >
        Open Sidekick →
      </NavLink>
    </div>
  );
}

// Pending Plan Card - shows when there's a plan awaiting approval
// Simple type for pending plan display - works with both handoff plans and direct customer plans
interface PendingPlanInfo {
  id: string;
  archetype_name?: string | null;
  milestone_count?: number | null;
  duration_label?: string | null;
  headline?: string | null;
  status: string;
}

function PendingPlanCard({ plan }: { plan: PendingPlanInfo | null | undefined }) {
  if (!plan || plan.status === 'approved') return null;

  return (
    <Link
      to={`/app/plans/${plan.id}`}
      className="block border-2 border-rust-500/50 bg-gradient-to-br from-charcoal-800 to-charcoal-900 p-6 mb-8 hover:border-rust-500 transition-colors group"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <FileText className="w-5 h-5 text-rust-500" />
          <span className="text-xs font-mono uppercase tracking-widest text-rust-400 font-bold">
            Plan Awaiting Approval
          </span>
        </div>
        <span className="text-xs font-mono uppercase tracking-wider px-2 py-0.5 text-signal-warn bg-amber-400/10">
          Pending Review
        </span>
      </div>

      <div className="flex items-baseline justify-between mb-2">
        <h3 className="font-serif text-xl text-fg-100 group-hover:text-rust-400 transition-colors">
          {plan.archetype_name || 'AI-Generated Onboarding Plan'}
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-sm text-fg-400">{plan.milestone_count} milestones</span>
          <span className="text-fg-400">·</span>
          <span className="text-sm text-fg-400">{plan.duration_label}</span>
        </div>
      </div>

      {plan.headline && (
        <p className="text-fg-300 text-sm mb-4 italic">"{plan.headline}"</p>
      )}

      <div className="flex items-center gap-2 text-rust-500 text-sm font-medium">
        <span>Review & Approve Plan</span>
        <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
      </div>
    </Link>
  );
}

// Section label with the brass hairline treatment (— LABEL · N ————————) used across the
// customer overview. Reusable: pass a label, optional count, optional right-aligned action.
function SectionLabel({ label, count, action }: { label: string; count?: number; action?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <span className="h-px w-6 bg-brass shrink-0" aria-hidden />
      <span className="text-[11px] font-mono uppercase tracking-[0.2em] text-brass whitespace-nowrap">
        {label}
        {count != null && <span className="text-fg-400"> · {count}</span>}
      </span>
      <span className="flex-1 border-t border-rule" aria-hidden />
      {action && <span className="shrink-0">{action}</span>}
    </div>
  );
}

// Need types that read as "urgent" — they get the terracotta alarm treatment in row lists.
const RISK_NEED_TYPES = new Set([
  'renewal_at_risk', 'renewal_risk', 'champion_departed', 'frustrated_signal',
  'escalation', 'urgent_support', 'going_dark', 'open_commitment_overdue',
]);

// Shared row-card chrome used across the overview lists and the Sidekick/History/Contacts tabs:
// a left edge accent, a circular left icon, a flexible body, and optional trailing content.
type RowEdge = 'risk' | 'brass' | 'ok' | 'muted';

const ROW_EDGE: Record<RowEdge, { edge: string; icon: string; accentText: string }> = {
  risk:  { edge: 'edge-risk',  icon: 'border-signal-risk text-signal-risk', accentText: 'text-signal-risk' },
  brass: { edge: 'edge-brass', icon: 'border-brass text-brass',             accentText: 'text-brass' },
  ok:    { edge: 'edge-ok',    icon: 'border-signal-ok text-signal-ok',     accentText: 'text-signal-ok' },
  muted: { edge: '',           icon: 'border-border text-fg-400',           accentText: 'text-fg-400' },
};

function RowCard({
  edge = 'brass',
  icon,
  to,
  trailing,
  align = 'start',
  className,
  children,
}: {
  edge?: RowEdge;
  icon: React.ReactNode;
  to?: string;
  trailing?: React.ReactNode;
  align?: 'start' | 'center';
  className?: string;
  children: React.ReactNode;
}) {
  const e = ROW_EDGE[edge];
  const inner = (
    <>
      <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-[11px]', e.icon)}>
        {icon}
      </span>
      <div className="flex-1 min-w-0">{children}</div>
      {trailing && <span className="shrink-0">{trailing}</span>}
    </>
  );
  const base = cn(
    'group flex gap-4 p-4 border border-border',
    align === 'center' ? 'items-center' : 'items-start',
    e.edge,
    className
  );
  return to ? (
    <NavLink to={to} className={cn(base, 'transition-colors hover:border-border-strong')}>
      {inner}
    </NavLink>
  ) : (
    <div className={base}>{inner}</div>
  );
}

// A row in the overview's bottom lists (needs + meetings share this shape):
// left edge accent, a circular icon, headline + meta, and a trailing arrow.
function OverviewRow({
  to, edge, icon, headline, type, meta,
}: {
  to: string;
  edge: 'risk' | 'brass';
  icon: React.ReactNode;
  headline: string;
  type: string;
  meta?: string;
}) {
  const accent = ROW_EDGE[edge].accentText;
  return (
    <RowCard
      to={to}
      edge={edge}
      icon={icon}
      align="center"
      trailing={
        <span className={cn('text-lg transition-transform group-hover:translate-x-0.5', accent)} aria-hidden>
          →
        </span>
      }
    >
      <p className="text-fg-100 group-hover:text-fg-200 transition-colors truncate">{headline}</p>
      <div className="mt-1 flex items-center gap-2">
        <span className={cn('text-[10px] font-mono uppercase tracking-[0.2em]', accent)}>{type}</span>
        {meta && <span className="text-[10px] font-mono text-fg-400">· {meta}</span>}
      </div>
    </RowCard>
  );
}

function OpenNeedsSection({ needs }: { needs: Need[] }) {
  if (needs.length === 0) return null;

  return (
    <div className="mb-8">
      <SectionLabel label="OPEN NEEDS" count={needs.length} />
      <div className="space-y-3">
        {needs.map((need) => {
          const risk = RISK_NEED_TYPES.has(need.type);
          return (
            <OverviewRow
              key={need.id}
              to={need.thread_id ? `/app/conversations/${need.thread_id}` : `/app/needs/${need.id}`}
              edge={risk ? 'risk' : 'brass'}
              icon={risk ? '▲' : '•'}
              headline={need.headline}
              type={need.type.replace(/_/g, ' ')}
              meta={formatRelativeTime(need.created_at) || undefined}
            />
          );
        })}
      </div>
    </div>
  );
}

function ActiveConversationsSection({
  threads,
  customerId
}: {
  threads: ThreadDetail[];
  customerId: string;
}) {
  const customerThreads = threads.filter(
    t => t.customer_id === customerId && t.status === 'open'
  ).slice(0, 3);

  if (customerThreads.length === 0) return null;

  return (
    <div className="mb-8">
      <SectionLabel label="ACTIVE CONVERSATIONS" count={customerThreads.length} />
      <div className="space-y-3">
        {customerThreads.map((thread) => {
          const Icon = getChannelIcon(thread.channel);
          const meta = [
            thread.stats?.message_count ? `${thread.stats.message_count} messages` : null,
            formatRelativeTime(thread.latest_message_at) || null,
          ].filter(Boolean).join(' · ');
          return (
            <OverviewRow
              key={thread.id}
              to={`/app/conversations/${thread.id}`}
              edge="brass"
              icon={<Icon className="w-3.5 h-3.5" />}
              headline={thread.subject}
              type={thread.thread_type === 'sidekick' ? 'SIDEKICK' : getChannelLabel(thread.channel)}
              meta={meta || undefined}
            />
          );
        })}
      </div>
      <NavLink
        to={`/app/conversations?customer=${customerId}`}
        className="text-sm text-accent hover:text-accent transition-colors mt-3 inline-block"
      >
        View all conversations →
      </NavLink>
    </div>
  );
}

function UpcomingMeetingsSection({
  meetings,
  customerId
}: {
  meetings: Meeting[];
  customerId: string;
}) {
  const customerMeetings = meetings
    .filter(m => m.customer_id === customerId && m.status === 'scheduled')
    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
    .slice(0, 3);

  if (customerMeetings.length === 0) return null;

  return (
    <div className="mb-8">
      <SectionLabel label="UPCOMING MEETINGS" count={customerMeetings.length} />
      <div className="space-y-3">
        {customerMeetings.map((meeting) => {
          const date = new Date(meeting.scheduled_at);
          const valid = !Number.isNaN(date.getTime());
          const dayName = valid ? date.toLocaleDateString('en-US', { weekday: 'long' }) : '';
          const time = valid
            ? date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
            : '';
          const attendees = meeting.attendees_theirs?.map((a) => a.name).join(', ');

          return (
            <OverviewRow
              key={meeting.id}
              to={`/app/meetings/${meeting.id}?mode=prep`}
              edge="brass"
              icon={<Calendar className="w-3.5 h-3.5" />}
              headline={valid ? `${dayName} · ${time}` : 'Scheduled'}
              type={(meeting.type || 'meeting').replace(/_/g, ' ')}
              meta={attendees || 'TBD'}
            />
          );
        })}
      </div>
    </div>
  );
}

function RecentInteractionsSection({ interactions }: { interactions: RecentInteraction[] }) {
  if (interactions.length === 0) return null;

  return (
    <div className="mb-8">
      <SectionLabel label="RECENT INTERACTIONS" />
      <div className="space-y-3">
        {interactions.map((interaction) => {
          const Icon = getChannelIcon(interaction.channel);
          const date = new Date(interaction.occurred_at);
          const isToday = date.toDateString() === new Date().toDateString();
          const isYesterday = date.toDateString() === new Date(Date.now() - 86400000).toDateString();

          let dateLabel: string;
          if (isToday) {
            dateLabel = 'Today, ' + date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
          } else if (isYesterday) {
            dateLabel = 'Yesterday, ' + date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
          } else {
            dateLabel = date.toLocaleDateString('en-US', { weekday: 'long' });
          }

          return (
            <div key={interaction.id} className="flex items-start gap-4">
              <span className="text-[10px] font-mono uppercase text-fg-400 w-16 shrink-0 pt-0.5">
                {getChannelLabel(interaction.channel)}
              </span>
              <p className="flex-1 text-fg-200">{interaction.summary}</p>
              <span className="text-xs text-fg-400 shrink-0">{dateLabel}</span>
            </div>
          );
        })}
      </div>
      <button className="text-sm text-accent hover:text-accent transition-colors mt-4">
        View full conversation history →
      </button>
    </div>
  );
}

// ============================================================================
// History Tab Components
// ============================================================================

interface HistoryFilters {
  channels: ('email' | 'slack' | 'meeting' | 'note')[];
  search: string;
  timeRange: 'all' | 'week' | 'month' | 'quarter';
  sortOrder: 'newest' | 'oldest';
  groupBy: 'chronological' | 'thread';
}

function HistoryTab({
  customerId,
  threads,
  daysToRenewal,
}: {
  customerId: string;
  threads: ThreadDetail[];
  daysToRenewal: number | null;
}) {
  const [filters, setFilters] = React.useState<HistoryFilters>({
    channels: [],
    search: '',
    timeRange: 'all',
    sortOrder: 'newest',
    groupBy: 'chronological',
  });

  // Fetch customer interactions
  const { data: interactionsData } = useCustomerInteractions(customerId);

  // Transform interactions to RecentInteraction format
  const historyInteractions: RecentInteraction[] = React.useMemo(() => {
    if (!interactionsData?.interactions) return [];

    return interactionsData.interactions.map((interaction: any) => ({
      id: interaction.id,
      channel: interaction.channel,
      summary: interaction.summaryAi || interaction.subject || interaction.bodyEncrypted?.substring(0, 100) || 'No content',
      occurred_at: interaction.occurredAt,
      participants: interaction.senderName ? [interaction.senderName] : undefined,
    }));
  }, [interactionsData]);

  // Use real data - no mocks
  const keyMoments: KeyMoment[] = []; // Would come from AI-detected key moments

  // Group interactions by date
  const groupedByDate = React.useMemo(() => {
    const groups: Record<string, RecentInteraction[]> = {};
    historyInteractions.forEach((interaction) => {
      const date = formatDate(interaction.occurred_at);
      if (!groups[date]) groups[date] = [];
      groups[date].push(interaction);
    });
    return groups;
  }, [historyInteractions]);

  const toggleChannel = (channel: 'email' | 'slack' | 'meeting' | 'note') => {
    setFilters(prev => ({
      ...prev,
      channels: prev.channels.includes(channel)
        ? prev.channels.filter(c => c !== channel)
        : [...prev.channels, channel],
    }));
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
      {/* Main content */}
      <div className="lg:col-span-8">
        {historyInteractions.length === 0 ? (
          <p className="text-fg-300 font-serif italic mb-6">
            No interaction history yet. As conversations happen, they'll appear here.
          </p>
        ) : (
          <p className="text-fg-300 font-serif italic mb-6">
            {historyInteractions.length} interactions across multiple channels.
          </p>
        )}

        {/* Search */}
        <div className="relative mb-4">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-fg-400" />
          <input
            type="text"
            placeholder="Search conversations, decisions, commitments..."
            value={filters.search}
            onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value }))}
            className="w-full pl-11 pr-4 py-3 bg-surface border border-border text-fg-200 placeholder:text-fg-400 focus:outline-none focus:border-border"
          />
        </div>

        {/* Filter chips */}
        <div className="flex flex-wrap items-center gap-2 mb-4">
          {(['email', 'slack', 'meeting', 'note'] as const).map((channel) => (
            <button
              key={channel}
              onClick={() => toggleChannel(channel)}
              className={cn(
                'px-3 py-1.5 text-xs font-mono uppercase border transition-colors',
                filters.channels.includes(channel)
                  ? 'border-cream-200 text-fg-200 bg-surface-2'
                  : 'border-border text-fg-400 hover:border-border'
              )}
            >
              {channel === 'note' ? 'Internal note' : channel.charAt(0).toUpperCase() + channel.slice(1)}
            </button>
          ))}

          <div className="h-4 w-px bg-border mx-2" />

          <select
            className="px-3 py-1.5 text-xs font-mono bg-surface-2 border border-border text-fg-300 focus:outline-none"
            defaultValue="all"
            disabled
          >
            <option value="all">All people</option>
          </select>

          <select
            className="px-3 py-1.5 text-xs font-mono bg-surface-2 border border-border text-fg-300 focus:outline-none"
            defaultValue="all"
            disabled
          >
            <option value="all">All need tags</option>
          </select>

          <select
            className="px-3 py-1.5 text-xs font-mono bg-surface-2 border border-border text-fg-300 focus:outline-none"
            value={filters.timeRange}
            onChange={(e) => setFilters(prev => ({ ...prev, timeRange: e.target.value as HistoryFilters['timeRange'] }))}
          >
            <option value="all">All time</option>
            <option value="week">This week</option>
            <option value="month">This month</option>
            <option value="quarter">This quarter</option>
          </select>

          <select
            className="px-3 py-1.5 text-xs font-mono bg-surface-2 border border-border text-fg-300 focus:outline-none"
            value={filters.sortOrder}
            onChange={(e) => setFilters(prev => ({ ...prev, sortOrder: e.target.value as HistoryFilters['sortOrder'] }))}
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
        </div>

        {/* View toggle */}
        <div className="flex justify-end mb-6">
          <div className="flex border border-border">
            <button
              onClick={() => setFilters(prev => ({ ...prev, groupBy: 'chronological' }))}
              className={cn(
                'px-3 py-1.5 text-xs font-mono transition-colors',
                filters.groupBy === 'chronological'
                  ? 'bg-border text-fg-200'
                  : 'text-fg-400 hover:text-fg-300'
              )}
            >
              Chronological
            </button>
            <button
              onClick={() => setFilters(prev => ({ ...prev, groupBy: 'thread' }))}
              className={cn(
                'px-3 py-1.5 text-xs font-mono transition-colors',
                filters.groupBy === 'thread'
                  ? 'bg-border text-fg-200'
                  : 'text-fg-400 hover:text-fg-300'
              )}
            >
              Grouped by thread
            </button>
          </div>
        </div>

        {/* Timeline */}
        <div className="space-y-8">
          {Object.keys(groupedByDate).length === 0 ? (
            <div className="text-center py-12 text-fg-400">
              <p className="text-lg font-serif mb-2">No interaction history yet</p>
              <p className="text-sm">As conversations happen, they'll appear here in chronological order.</p>
            </div>
          ) : (
            (Object.entries(groupedByDate) as [string, RecentInteraction[]][]).map(([date, interactions]) => (
              <div key={date}>
                <h4 className="text-lg font-serif text-fg-100 mb-4">
                  {date}
                  <span className="text-sm text-fg-400 ml-2">· {interactions.length} interaction{interactions.length > 1 ? 's' : ''}</span>
                </h4>
                <div className="space-y-3">
                  {interactions.map((interaction) => {
                    const Icon = getChannelIcon(interaction.channel);
                    const time = new Date(interaction.occurred_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });

                    return (
                      <RowCard key={interaction.id} edge="brass" icon={<Icon className="w-3.5 h-3.5" />}>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-brass">
                            {getChannelLabel(interaction.channel)}
                          </span>
                          {interaction.channel === 'meeting' && (
                            <span className="text-xs text-fg-400">Weekly check-in</span>
                          )}
                          <span className="text-[10px] font-mono text-fg-400 ml-auto">
                            {date.split(',')[0]} · {time}
                          </span>
                        </div>
                        <p className="text-fg-200">{interaction.summary}</p>
                        {interaction.participants && (
                          <p className="text-xs text-fg-400 mt-1">
                            {interaction.participants.join(' · ')}
                          </p>
                        )}
                        <button className="text-sm text-accent hover:text-accent transition-colors mt-2">
                          Expand
                        </button>
                      </RowCard>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Sidebar */}
      <div className="lg:col-span-4 space-y-8">
        {/* Key Moments */}
        {keyMoments.length > 0 && (
          <div className="hud-pane p-6">
            <h3 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4">
              KEY MOMENTS
            </h3>
            <div className="space-y-4">
              {keyMoments.map((moment) => (
                <div key={moment.id}>
                  <span className="text-[10px] font-mono text-fg-400 block mb-0.5">
                    {moment.date}
                  </span>
                  <p className="text-sm text-fg-200">{moment.summary}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Renewal countdown */}
        {daysToRenewal !== null && (
          <div className="hud-pane p-6">
            <h3 className="text-xs font-mono uppercase tracking-widest text-accent mb-2">
              RENEWAL IN
            </h3>
            <span className="text-2xl font-mono text-fg-100">{daysToRenewal} days</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Contract Review Tab Components
// ============================================================================

function ContractReviewTab({ customerId }: { customerId: string }) {
  const [activeVersion, setActiveVersion] = React.useState<string>('');
  const [activeSubTab, setActiveSubTab] = React.useState<'terms' | 'diff'>('terms');

  // Use real data - no mocks
  const versions: ContractVersion[] = []; // Would come from uploaded contracts
  const flags: ContractFlag[] = []; // Would come from AI contract analysis
  const terms: ContractTerm[] = []; // Would come from AI contract extraction
  const currentVersion = versions.find(v => v.id === activeVersion);

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <h3 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-2">
          CONTRACT REVIEW
        </h3>
        <p className="text-lg font-serif text-fg-200">
          Give the AI your contract for context.
        </p>
        <p className="text-sm text-fg-400 mt-2">
          Herofy isn't where Northwind Analytics signs. Drop in the signed PDF (or whatever your legal team produces) and the AI will extract the terms that matter, surface anything risky, and keep a redline-style diff between versions so you walk into renewals knowing what actually changed.
        </p>
      </div>

      {/* Upload + Versions grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* Upload area */}
        <div className="border-2 border-dashed border-border p-8 flex flex-col items-center justify-center text-center hover:border-border transition-colors cursor-pointer">
          <Upload className="w-8 h-8 text-fg-400 mb-3" />
          <p className="text-fg-300 mb-1">Drop a signed contract here</p>
          <p className="text-xs text-fg-400">PDF or DOCX. The AI extracts terms, flags risks, and diffs against prior versions.</p>
          <button className="text-xs text-accent hover:text-accent mt-4 uppercase tracking-widest">
            OR CLICK TO UPLOAD
          </button>
        </div>

        {/* Versions list */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-mono uppercase tracking-widest text-fg-400">
              ON FILE
            </span>
            <span className="text-[10px] font-mono text-fg-400/50">· {versions.length} VERSIONS</span>
          </div>
          {versions.length === 0 ? (
            <div className="border border-border p-6 text-center text-fg-400">
              <p className="text-sm">No contracts uploaded yet</p>
            </div>
          ) : (
            <div className="space-y-2">
              {versions.map((version) => (
                <button
                  key={version.id}
                  onClick={() => setActiveVersion(version.id)}
                  className={cn(
                    'w-full text-left p-3 border transition-colors',
                    activeVersion === version.id
                      ? 'border-accent bg-accent/10/10'
                      : 'border-border hover:border-border'
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-fg-400" />
                        <span className="text-fg-200">{version.title}</span>
                      </div>
                      <p className="text-xs text-fg-400 mt-1 ml-6">
                        {version.signed_at ? `Signed ${version.signed_at}` : `Proposed ${version.uploaded_at}`} · {version.pages} pages
                        {version.forwarded_by && ` · Forwarded by ${version.forwarded_by}`}
                      </p>
                    </div>
                    {version.status === 'viewing' && (
                      <span className="text-[10px] font-mono uppercase bg-accent text-page px-2 py-0.5">
                        VIEWING
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Sidekick flags - only shown if there are versions and flags */}
      {versions.length > 0 && flags.length > 0 && (
        <div className="mb-8">
          <h4 className="text-xs font-mono uppercase tracking-widest text-accent mb-4 flex items-center gap-2">
            <Zap className="w-3 h-3 fill-rust-500" />
            SIDEKICK IS FLAGGING
          </h4>
          <div className="space-y-3">
            {flags.map((flag) => (
              <div key={flag.id} className="border border-border p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-4 h-4 text-signal-warn shrink-0 mt-0.5" />
                  <div>
                    <h5 className="text-signal-warn font-medium mb-1">{flag.title}</h5>
                    <p className="text-sm text-fg-300">{flag.description}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Extracted terms - only show if there are versions */}
      {versions.length > 0 && (
        <div>
          <div className="flex items-center gap-4 border-b border-border mb-6">
            <button
              onClick={() => setActiveSubTab('terms')}
              className={cn(
                'pb-3 text-sm font-medium border-b-2 -mb-px transition-colors',
                activeSubTab === 'terms'
                  ? 'border-cream-200 text-fg-200'
                  : 'border-transparent text-fg-400 hover:text-fg-300'
              )}
            >
              Extracted terms
            </button>
            <button
              onClick={() => setActiveSubTab('diff')}
              className={cn(
                'pb-3 text-sm font-medium border-b-2 -mb-px transition-colors',
                activeSubTab === 'diff'
                  ? 'border-cream-200 text-fg-200'
                  : 'border-transparent text-fg-400 hover:text-fg-300'
              )}
            >
              Version diff
            </button>
          </div>

          {activeSubTab === 'terms' && (
            <div>
              {currentVersion && terms.length > 0 ? (
                <>
                  <div className="mb-4">
                    <span className="text-[10px] font-mono uppercase tracking-widest text-fg-400">
                      {currentVersion.title.toUpperCase()}
                    </span>
                    <p className="text-fg-300 font-serif italic mt-1">
                      Customer-proposed renewal with shorter notice window, expanded data residency, and a new termination clause. Two items worth raising before counter-signing.
                    </p>
                  </div>

                  <div className="border border-border divide-y divide-charcoal-700">
                    {terms.map((term, i) => (
                      <div key={i} className="grid grid-cols-3 gap-4 p-4">
                        <span className="text-[10px] font-mono uppercase tracking-widest text-fg-400">
                          {term.label}
                        </span>
                        <div className="col-span-2">
                          <span className="text-fg-200">{term.value}</span>
                          {term.warning && (
                            <p className="text-sm text-signal-warn mt-1 flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3" />
                              {term.warning}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="text-center py-12 text-fg-400">
                  <p>No terms extracted yet.</p>
                  <p className="text-xs mt-2">Once a contract is uploaded, AI will extract key terms automatically.</p>
                </div>
              )}
            </div>
          )}

          {activeSubTab === 'diff' && (
            <div className="text-center py-12 text-fg-400">
              <p>Version diff view coming soon.</p>
              <p className="text-xs mt-2">This will show redline-style differences between contract versions.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Sidekick Tab Components
// ============================================================================

interface SidekickItem {
  id: string;
  type: string;
  text?: string;
  question?: string;
  why?: string;
  isBlocking?: boolean;
  task?: string;
  step?: string;
  stepNum?: number;
  totalSteps?: number;
  resolution?: string;
  resolvedByUser?: {
    id: string;
    displayName?: string;
  };
  resolvedAt?: string;
  timestampLabel?: string;
}

function SidekickTab({ sidekickItems }: { sidekickItems: SidekickItem[] }) {
  if (!sidekickItems || sidekickItems.length === 0) {
    return (
      <div className="text-center py-12 text-fg-400">
        <Zap className="w-8 h-8 mx-auto mb-3 text-fg-400/50" />
        <p className="text-lg font-serif mb-2">No Sidekick activity yet</p>
        <p className="text-sm">When agents have questions about this customer, they'll appear here.</p>
      </div>
    );
  }

  // Separate open and resolved items
  const openItems = sidekickItems.filter(item => !item.resolvedAt);
  const resolvedItems = sidekickItems.filter(item => item.resolvedAt);

  return (
    <div>
      {/* Open Items */}
      {openItems.length > 0 && (
        <div className="mb-8">
          <SectionLabel label="NEEDS YOUR INPUT" count={openItems.length} />

          <div className="space-y-3">
            {openItems.map((item) => (
              <div key={item.id}>
                {item.type === 'asking' && (
                  <RowCard edge={item.isBlocking ? 'risk' : 'brass'} icon={<Zap className="w-3.5 h-3.5" />}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={cn('text-[10px] font-mono uppercase tracking-[0.2em]', item.isBlocking ? 'text-signal-risk' : 'text-brass')}>
                        Sidekick · Asking
                      </span>
                      {item.isBlocking && (
                        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-signal-risk">· Blocking</span>
                      )}
                      {item.timestampLabel && (
                        <span className="text-[10px] font-mono text-fg-400">· {item.timestampLabel}</span>
                      )}
                    </div>
                    {item.question && <p className="text-fg-100 font-medium mb-1">{item.question}</p>}
                    {item.text && <p className="text-fg-300 text-sm mb-2">{item.text}</p>}
                    {item.why && (
                      <div className="mt-2 pt-2 border-t border-border">
                        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-fg-400 block mb-1">
                          Why this matters
                        </span>
                        <p className="text-sm text-fg-300">{item.why}</p>
                      </div>
                    )}
                    <NavLink
                      to="/app/sidekick"
                      className="mt-3 inline-flex items-center gap-1 text-[11px] font-mono uppercase tracking-[0.2em] text-accent hover:text-accent-hover transition-colors"
                    >
                      Answer in Sidekick →
                    </NavLink>
                  </RowCard>
                )}

                {item.type === 'working' && item.task && (
                  <RowCard edge="brass" icon={<span className="w-2 h-2 bg-brass rounded-full animate-pulse" />}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-brass">Sidekick · Working</span>
                    </div>
                    <p className="text-fg-200">{item.task}</p>
                    {item.step && (
                      <div className="flex items-center gap-2 text-sm text-fg-400 mt-1">
                        {item.stepNum && item.totalSteps && (
                          <span className="text-brass">{item.stepNum}/{item.totalSteps}</span>
                        )}
                        <span>·</span>
                        <span>{item.step}</span>
                      </div>
                    )}
                  </RowCard>
                )}

                {item.type === 'tip' && item.text && (
                  <RowCard edge="brass" icon={<Zap className="w-3.5 h-3.5" />}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-brass">Sidekick · Tip</span>
                    </div>
                    <p className="text-fg-300">{item.text}</p>
                  </RowCard>
                )}

                {item.type === 'observed' && item.text && (
                  <RowCard edge="muted" icon={<Eye className="w-3.5 h-3.5" />}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-fg-400">Sidekick · Observed</span>
                      {item.timestampLabel && (
                        <span className="text-[10px] font-mono text-fg-400">· {item.timestampLabel}</span>
                      )}
                    </div>
                    <p className="text-fg-300">{item.text}</p>
                  </RowCard>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Resolved Items */}
      {resolvedItems.length > 0 && (
        <div>
          <SectionLabel label="RESOLVED" count={resolvedItems.length} />

          <div className="space-y-3">
            {resolvedItems.map((item) => (
              <RowCard key={item.id} edge="ok" icon={<CheckCircle className="w-3.5 h-3.5" />} className="opacity-70">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-signal-ok">Sidekick · Resolved</span>
                </div>
                {item.question && <p className="text-fg-400 text-sm mb-1">{item.question}</p>}
                {item.resolution && <p className="text-fg-300 mb-1">{item.resolution}</p>}
                <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.2em] text-fg-400">
                  {item.resolvedByUser?.displayName && (
                    <>
                      <span>{item.resolvedByUser.displayName}</span>
                      <span>·</span>
                    </>
                  )}
                  {item.resolvedAt && <span>{formatRelativeTime(item.resolvedAt)}</span>}
                </div>
              </RowCard>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Plans Tab - Goal-Centric Architecture
// ============================================================================

interface PlansTabProps {
  customerId: string;
  customerName: string;
  pendingPlan?: PendingPlanInfo | null;
}

function PlansTab({ customerId, customerName, pendingPlan }: PlansTabProps) {
  const [selectedPlanId, setSelectedPlanId] = React.useState<string | null>(null);
  const [activeLens, setActiveLens] = React.useState<PlanLens>('north-star');
  const [showPlaybookPicker, setShowPlaybookPicker] = React.useState(false);
  const [showAddStep, setShowAddStep] = React.useState(false);
  const { workspaceId } = useWorkspace();
  const createMilestone = useCreateMilestone();

  // Fetch goals with milestones
  const { data: goalsData, isLoading: goalsLoading, refetch: refetchGoals } = useGoalsWithMilestones(customerId);
  // Fetch progress vectors
  const { data: vectorsData, isLoading: vectorsLoading } = useProgressVectorsForCustomer(customerId);
  // Fetch customer strategy
  const { data: strategyData, isLoading: strategyLoading } = useCustomerStrategy(customerId);

  const isLoading = goalsLoading || vectorsLoading || strategyLoading;

  // Get plans (goals) list
  const plans = goalsData?.goals || [];

  // Select primary plan by default
  React.useEffect(() => {
    if (!selectedPlanId && plans.length > 0) {
      const primaryPlan = plans.find(p => p.isPrimary) || plans[0];
      setSelectedPlanId(primaryPlan.id);
    }
  }, [plans, selectedPlanId]);

  const selectedPlan = plans.find(p => p.id === selectedPlanId);
  const selectedVectors = vectorsData?.vectors?.filter(v => v.goal?.id === selectedPlanId) || [];

  // Rendered in every branch that can open it (empty state + populated state).
  const playbookPickerModal = (
    <PlaybookPickerModal
      isOpen={showPlaybookPicker}
      onClose={() => setShowPlaybookPicker(false)}
      customerId={customerId}
      workspaceId={workspaceId}
      onCreated={() => { setSelectedPlanId(null); refetchGoals(); }}
    />
  );

  // Add a step to the selected plan — links the new milestone to that plan's Goal.
  const addStepModal = (
    <MilestoneModal
      isOpen={showAddStep}
      onClose={() => setShowAddStep(false)}
      isSubmitting={createMilestone.isPending}
      onSubmit={(data) => {
        if (!selectedPlanId) return;
        createMilestone.mutate(
          { customerId, goalId: selectedPlanId, data: data as CreateMilestoneInput },
          { onSuccess: () => { setShowAddStep(false); refetchGoals(); } }
        );
      }}
    />
  );

  if (isLoading) {
    return (
      <div className="text-fg-400 text-center py-12">
        Loading plans...
      </div>
    );
  }

  // Check if there's a plan awaiting approval
  const hasPendingApproval = pendingPlan && pendingPlan.status !== 'approved';

  if (plans.length === 0) {
    // If no goals but there's a pending plan, show approval prompt
    if (hasPendingApproval) {
      return (
        <div className="text-center py-12">
          <Link
            to={`/app/plans/${pendingPlan.id}`}
            className="inline-block border-2 border-accent/50 bg-accent/5 p-8 hover:border-accent transition-colors group max-w-lg"
          >
            <div className="flex items-center justify-center gap-3 mb-4">
              <div className="w-3 h-3 rounded-full bg-accent animate-pulse" />
              <span className="text-[11px] font-mono uppercase tracking-[0.3em] text-accent font-bold">
                Plan Awaiting Your Approval
              </span>
            </div>
            <h3 className="font-display italic text-2xl text-fg-100 mb-2 group-hover:text-accent transition-colors">
              {pendingPlan.archetype_name || 'AI-Generated Onboarding Plan'}
            </h3>
            <p className="text-fg-300 text-sm mb-4">
              {pendingPlan.milestone_count} milestones · {pendingPlan.duration_label}
            </p>
            {pendingPlan.headline && (
              <p className="text-fg-400 text-sm italic mb-6">"{pendingPlan.headline}"</p>
            )}
            <div className="inline-flex items-center gap-2 bg-accent text-charcoal px-5 py-2.5 font-mono text-[11px] font-bold uppercase tracking-[0.2em] group-hover:bg-accent-hover transition-colors">
              Review & Approve
              <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </div>
          </Link>
        </div>
      );
    }

    return (
      <div className="text-center py-12">
        <Target className="w-8 h-8 mx-auto mb-3 text-fg-400/50" />
        <p className="text-lg font-serif mb-2">No plans yet</p>
        <p className="text-fg-400 text-sm mb-5">Start from one of your playbooks, or let an AI plan generate from a handoff.</p>
        <button
          onClick={() => setShowPlaybookPicker(true)}
          className="inline-flex items-center gap-2 bg-accent text-charcoal px-5 py-2.5 font-mono text-[11px] font-bold uppercase tracking-[0.2em] hover:bg-accent-hover transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          Start from a playbook
        </button>
        {playbookPickerModal}
      </div>
    );
  }

  const lenses: { id: PlanLens; label: string; num: string }[] = [
    { id: 'north-star', label: 'North Star', num: '01' },
    { id: 'distance', label: 'Distance', num: '02' },
    { id: 'ledger', label: 'Ledger', num: '03' },
    { id: 'memo', label: 'Memo', num: '04' },
  ];

  return (
    <div>
      {playbookPickerModal}
      {addStepModal}
      {/* Pending Approval Banner */}
      {hasPendingApproval && (
        <Link
          to={`/app/plans/${pendingPlan.id}`}
          className="flex items-center justify-between gap-4 px-5 py-4 mb-4 border-2 border-accent/50 bg-accent/5 hover:border-accent transition-colors group"
        >
          <div className="flex items-center gap-4">
            <div className="w-2.5 h-2.5 rounded-full bg-accent animate-pulse" />
            <div>
              <span className="text-[10px] font-mono uppercase tracking-[0.28em] text-accent font-bold">
                Action Required
              </span>
              <span className="block font-display italic text-lg text-fg-100 group-hover:text-accent transition-colors">
                {pendingPlan.archetype_name || 'AI-Generated Plan'} awaiting your approval
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 bg-accent text-charcoal px-4 py-2 font-mono text-[10px] font-bold uppercase tracking-[0.2em] group-hover:bg-accent-hover transition-colors">
            Review & Approve
            <ChevronRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </Link>
      )}

      {/* Plan Picker */}
      <div className="flex items-stretch bg-surface border border-border mb-0">
        <div className="px-6 py-4 border-r border-rule font-mono text-[10.5px] tracking-[0.28em] uppercase text-fg-400 font-bold flex items-center">
          PLANS · {plans.length}
        </div>
        <div className="flex flex-1">
          {plans.map(plan => (
            <button
              key={plan.id}
              onClick={() => setSelectedPlanId(plan.id)}
              className={cn(
                "flex-1 px-5 py-3 border-r border-rule text-left transition-colors relative",
                selectedPlanId === plan.id ? "bg-accent/10" : "hover:bg-surface-2"
              )}
            >
              {selectedPlanId === plan.id && (
                <div className="absolute inset-x-0 top-0 h-0.5 bg-accent" />
              )}
              <div className="font-mono text-[9.5px] tracking-[0.25em] uppercase text-fg-400 font-bold mb-1">
                {plan.isPrimary ? '★ ONBOARDING PLAN' : 'SOLUTION PLAN'} · {plan.status?.toUpperCase()}
              </div>
              <div className="font-display italic text-[1.1rem] text-fg-100 leading-tight line-clamp-2">
                {plan.text}
              </div>
              <div className="font-mono text-[9.5px] tracking-[0.18em] uppercase text-fg-300 mt-1 flex items-center gap-1.5">
                <span className={cn("w-1.5 h-1.5 rounded-full", plan.status === 'active' ? "bg-accent" : "bg-fg-400")} />
                {plan.milestones?.length || 0} MILESTONES
              </div>
            </button>
          ))}
        </div>
        <button
          onClick={() => setShowPlaybookPicker(true)}
          className="px-6 py-4 border-l border-rule font-mono text-[10.5px] font-bold tracking-[0.22em] uppercase text-fg-400 hover:text-accent flex items-center gap-2"
        >
          <Plus className="w-3.5 h-3.5" />
          NEW PLAN
        </button>
      </div>

      {/* Lens Switcher */}
      <div className="grid grid-cols-[auto_1fr_auto] gap-5 items-center px-6 py-4 bg-surface border border-border border-t-0">
        <div className="font-mono text-[10.5px] tracking-[0.28em] uppercase text-fg-400 font-bold">
          LENS
        </div>
        <div className="flex border border-border">
          {lenses.map(lens => (
            <button
              key={lens.id}
              onClick={() => setActiveLens(lens.id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2.5 font-mono text-[10.5px] font-bold tracking-[0.22em] uppercase border-r border-border last:border-r-0 transition-colors",
                activeLens === lens.id
                  ? "bg-accent text-charcoal"
                  : "text-fg-400 hover:text-fg-200"
              )}
            >
              <span className={cn(
                "font-display italic text-[0.95rem] tracking-normal",
                activeLens === lens.id ? "text-charcoal" : "text-accent"
              )}>
                {lens.num}
              </span>
              {lens.label}
            </button>
          ))}
        </div>
        {selectedPlanId ? (
          <button
            onClick={() => setShowAddStep(true)}
            className="flex items-center gap-2 px-4 py-2.5 border border-border font-mono text-[10.5px] font-bold tracking-[0.22em] uppercase text-fg-400 hover:text-accent hover:border-accent transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            ADD STEP
          </button>
        ) : (
          <div className="font-mono text-[9.5px] tracking-[0.2em] uppercase text-fg-400">
            SAME PLAN · <em className="font-display italic text-accent text-[1.05rem] tracking-normal">4 ways to look at it</em>
          </div>
        )}
      </div>

      {/* Lens Content */}
      <div className="bg-surface border border-border border-t-0 p-8">
        {activeLens === 'north-star' && selectedPlan && (
          <NorthStarLens plan={selectedPlan} vectors={selectedVectors} customerName={customerName} />
        )}
        {activeLens === 'distance' && selectedPlan && (
          <DistanceLens plan={selectedPlan} />
        )}
        {activeLens === 'ledger' && selectedPlan && (
          <LedgerLens plan={selectedPlan} />
        )}
        {activeLens === 'memo' && (
          <MemoLens strategy={strategyData?.strategy} customerName={customerName} plan={selectedPlan} />
        )}
      </div>
    </div>
  );
}

// North Star Lens - The goal and vectors of progress
function NorthStarLens({
  plan,
  vectors,
  customerName,
}: {
  plan: NonNullable<ReturnType<typeof useGoalsWithMilestones>['data']>['goals'][0];
  vectors: NonNullable<ReturnType<typeof useProgressVectorsForCustomer>['data']>['vectors'];
  customerName: string;
}) {
  return (
    <div>
      {/* The Goal */}
      <div className="flex items-center gap-3.5 mb-4">
        <div className="w-7 h-px bg-accent" />
        <span className="font-mono text-[10.5px] font-bold tracking-[0.32em] uppercase text-accent">
          THE GOAL · WHY THEY HIRED US
        </span>
      </div>
      <blockquote className="font-display italic text-[2.3rem] leading-tight text-fg-100 mb-4 max-w-[32ch]">
        "{plan.text}"
      </blockquote>
      <div className="font-mono text-[10px] tracking-[0.22em] uppercase text-fg-400 mb-10">
        SOURCE · {plan.source?.toUpperCase() || 'DISCOVERY'} · {plan.sourceDate ? new Date(plan.sourceDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase() : 'UNKNOWN'}
      </div>

      {/* Vectors of Progress */}
      {vectors.length > 0 && (
        <>
          <div className="flex items-center gap-3.5 mb-5">
            <div className="w-12 h-px bg-accent" />
            <span className="font-mono text-[10.5px] font-bold tracking-[0.3em] uppercase text-accent">
              VECTORS OF PROGRESS
            </span>
            <div className="flex-1 h-px bg-rule" />
            <span className="font-mono text-[10.5px] tracking-[0.2em] uppercase text-fg-400">
              {vectors.length} · WHAT EACH UNLOCKS
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {vectors.map((vector, i) => (
              <div key={vector.id} className="bg-surface-2 border border-border p-6">
                <div className="flex items-baseline gap-3 mb-2">
                  <span className="font-display italic text-[1.4rem] text-accent">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <h3 className="font-display text-[1.3rem] text-fg-100">
                    {vector.category.replace(/_/g, ' ')}
                  </h3>
                </div>
                <p className="font-display italic text-[1rem] text-fg-300 mb-4">
                  <span className="text-fg-400">unlocks </span>
                  <span className="text-accent">{vector.unlocks || 'progress toward goal'}</span>
                </p>

                {/* Progress bar */}
                <div className="flex justify-between text-[9.5px] font-mono tracking-[0.18em] uppercase text-fg-400 mb-2">
                  <span>{Math.round((vector.progress || 0) * 100)}% TOWARD UNLOCK</span>
                  <span>TARGET · {vector.targetLabel || '100%'}</span>
                </div>
                <div className="h-1 bg-charcoal relative overflow-hidden">
                  <div
                    className="absolute inset-y-0 left-0 bg-accent"
                    style={{ width: `${(vector.progress || 0) * 100}%` }}
                  />
                  {vector.targetProgress && (
                    <div
                      className="absolute top-[-3px] bottom-[-3px] w-px bg-cream/50"
                      style={{ left: `${vector.targetProgress * 100}%` }}
                    />
                  )}
                </div>

                {/* State indicator */}
                <div className="mt-3 flex items-center gap-2">
                  <span className={cn(
                    "w-2 h-2 rounded-full",
                    vector.currentState === 'ok' ? "bg-signal-ok" :
                    vector.currentState === 'warn' ? "bg-signal-warn" : "bg-signal-bad"
                  )} />
                  <span className="font-mono text-[9px] tracking-[0.2em] uppercase text-fg-400">
                    {vector.currentState?.toUpperCase() || 'UNKNOWN'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Milestones linked to this goal */}
      {plan.milestones && plan.milestones.length > 0 && (
        <>
          <div className="flex items-center gap-3.5 mt-10 mb-5">
            <div className="w-12 h-px bg-accent" />
            <span className="font-mono text-[10.5px] font-bold tracking-[0.3em] uppercase text-accent">
              WAYPOINTS
            </span>
            <div className="flex-1 h-px bg-rule" />
            <span className="font-mono text-[10.5px] tracking-[0.2em] uppercase text-fg-400">
              {plan.milestones.length} MILESTONES
            </span>
          </div>

          <PlanTimeline gap={0}>
            {plan.milestones.map((milestone, i) => (
              <PlanTimelineItem key={milestone.id} status={milestone.status} dotTop={22}>
              <div
                className={cn(
                  "grid grid-cols-[60px_1fr_180px] gap-4 py-4 px-5 bg-surface border border-border items-start",
                  i !== 0 && "border-t-0",
                  milestone.status === 'done' && "opacity-60"
                )}
              >
                <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-fg-300 pt-1">
                  <span className="block font-display italic text-[1.5rem] text-accent leading-none mb-1">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  {milestone.targetDate ? new Date(milestone.targetDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '-'}
                </div>
                <div>
                  <h4 className={cn(
                    "font-display text-[1.2rem] text-fg-100 mb-1",
                    milestone.status === 'done' && "line-through text-fg-400"
                  )}>
                    {milestone.title}
                  </h4>
                  {milestone.description && (
                    <p className="text-[0.86rem] text-fg-300 leading-relaxed">
                      {milestone.description}
                    </p>
                  )}
                  {milestone.goalRationale && (
                    <p className="text-[0.82rem] text-fg-400 mt-1 italic">
                      <span className="text-accent">{milestone.goalRationale}</span>
                    </p>
                  )}
                </div>
                <div className="text-right">
                  <span className={cn(
                    "inline-block font-mono text-[9px] tracking-[0.22em] uppercase px-2 py-1 border",
                    milestone.status === 'done' ? "border-signal-ok text-signal-ok" :
                    milestone.status === 'in_progress' ? "border-accent text-accent" :
                    milestone.status === 'blocked' ? "border-signal-bad text-signal-bad" :
                    "border-border text-fg-400"
                  )}>
                    {milestone.status?.replace(/_/g, ' ').toUpperCase() || 'NOT STARTED'}
                  </span>
                  {milestone.ownerSide && (
                    <div className="font-mono text-[9px] tracking-[0.18em] uppercase text-fg-400 mt-2">
                      {milestone.ownerSide === 'us' ? 'OUR MOVE' : 'THEIR MOVE'}
                    </div>
                  )}
                </div>
              </div>
              </PlanTimelineItem>
            ))}
          </PlanTimeline>
        </>
      )}
    </div>
  );
}

// Distance Lens - Focus on timeline and distance to value
function DistanceLens({
  plan,
}: {
  plan: NonNullable<ReturnType<typeof useGoalsWithMilestones>['data']>['goals'][0];
}) {
  const milestones = plan.milestones || [];
  const completedCount = milestones.filter(m => m.status === 'done' || m.status === 'skipped').length;
  const progress = milestones.length > 0 ? completedCount / milestones.length : 0;

  return (
    <div>
      <div className="flex items-center gap-3.5 mb-4">
        <div className="w-7 h-px bg-accent" />
        <span className="font-mono text-[10.5px] font-bold tracking-[0.32em] uppercase text-accent">
          DISTANCE TO VALUE
        </span>
      </div>

      {/* Progress Summary */}
      <div className="grid grid-cols-4 gap-0 border border-border mb-8">
        <div className="p-5 border-r border-rule">
          <div className="font-mono text-[9.5px] tracking-[0.25em] uppercase text-fg-400 mb-2">MILESTONES</div>
          <div className="font-display text-[2.4rem] text-fg-100">{completedCount}<span className="text-fg-400">/{milestones.length}</span></div>
        </div>
        <div className="p-5 border-r border-rule">
          <div className="font-mono text-[9.5px] tracking-[0.25em] uppercase text-fg-400 mb-2">PROGRESS</div>
          <div className="font-display text-[2.4rem] text-accent italic">{Math.round(progress * 100)}%</div>
        </div>
        <div className="p-5 border-r border-rule">
          <div className="font-mono text-[9.5px] tracking-[0.25em] uppercase text-fg-400 mb-2">STATUS</div>
          <div className="font-display text-[2.4rem] text-fg-100">{plan.status}</div>
        </div>
        <div className="p-5">
          <div className="font-mono text-[9.5px] tracking-[0.25em] uppercase text-fg-400 mb-2">VALUE MOMENT</div>
          <div className="font-display text-[2.4rem] text-accent italic">TBD</div>
        </div>
      </div>

      {/* Timeline View */}
      <div className="flex items-center gap-3.5 mb-5">
        <div className="w-12 h-px bg-accent" />
        <span className="font-mono text-[10.5px] font-bold tracking-[0.3em] uppercase text-accent">
          TIMELINE
        </span>
        <div className="flex-1 h-px bg-rule" />
      </div>

      <PlanTimeline gap={12}>
        {milestones.map((milestone, i) => {
          const isDone = milestone.status === 'done' || milestone.status === 'skipped';
          const isCurrent = milestone.status === 'in_progress';

          return (
            <PlanTimelineItem key={milestone.id} status={milestone.status} dotTop={15}>
            <div
              className={cn(
                "flex items-center gap-4 py-3 px-4 bg-surface border-l-[3px] transition-colors",
                isDone ? "border-l-signal-ok bg-signal-ok/5" :
                isCurrent ? "border-l-accent bg-accent/5" :
                milestone.status === 'blocked' ? "border-l-signal-bad bg-signal-bad/5" :
                "border-l-border"
              )}
            >
              <div className="font-display italic text-[1.1rem] text-accent w-8">
                {String(i + 1).padStart(2, '0')}
              </div>
              <div className="flex-1">
                <span className={cn("text-[0.95rem]", isDone ? "text-fg-400 line-through" : "text-fg-100")}>
                  {milestone.title}
                </span>
              </div>
              <div className="font-mono text-[9px] tracking-[0.2em] uppercase text-fg-400">
                {milestone.targetDate ? new Date(milestone.targetDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '-'}
              </div>
              <div className={cn(
                "w-4 h-4 border-2 rounded-sm",
                isDone ? "bg-signal-ok border-signal-ok" :
                isCurrent ? "border-accent" :
                "border-fg-400/30"
              )}>
                {isDone && <Check className="w-full h-full text-charcoal" />}
              </div>
            </div>
            </PlanTimelineItem>
          );
        })}
      </PlanTimeline>
    </div>
  );
}

// Ledger Lens - Commitments and stakes
function LedgerLens({
  plan,
}: {
  plan: NonNullable<ReturnType<typeof useGoalsWithMilestones>['data']>['goals'][0];
}) {
  // For now, show milestones as "commitments" - in production this would be from the Commitment table
  const milestones = plan.milestones || [];
  const ourCommitments = milestones.filter(m => m.ownerSide === 'us');
  const theirCommitments = milestones.filter(m => m.ownerSide === 'customer');

  return (
    <div>
      <div className="flex items-center gap-3.5 mb-4">
        <div className="w-12 h-px bg-accent" />
        <span className="font-mono text-[10.5px] font-bold tracking-[0.3em] uppercase text-accent">
          THE LEDGER
        </span>
        <div className="flex-1 h-px bg-rule" />
        <span className="font-mono text-[10px] tracking-[0.2em] uppercase text-fg-400">
          PROMISES MADE · PROMISES KEPT
        </span>
      </div>

      <div className="grid grid-cols-3 gap-0 border border-border mb-8">
        {/* We Promised */}
        <div className="border-r border-border">
          <div className="px-6 py-4 border-b border-border bg-surface-2">
            <div className="font-mono text-[10px] font-bold tracking-[0.3em] uppercase text-accent mb-1">
              WE PROMISED
            </div>
            <div className="font-display italic text-[1.35rem] text-fg-100">
              {ourCommitments.length} items
            </div>
            <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-fg-400 mt-1">
              {ourCommitments.filter(m => m.status === 'done').length} DELIVERED
            </div>
          </div>
          <div>
            {ourCommitments.slice(0, 5).map(m => (
              <div key={m.id} className="px-6 py-4 border-b border-rule last:border-b-0">
                <div className="flex items-baseline justify-between gap-2 mb-2">
                  <span className="font-display text-[1.06rem] text-fg-100">{m.title}</span>
                  <span className="font-mono text-[9.5px] tracking-[0.18em] uppercase text-accent font-bold whitespace-nowrap">
                    {m.targetDate ? new Date(m.targetDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '-'}
                  </span>
                </div>
                {m.description && (
                  <p className="text-[0.85rem] text-fg-300 leading-relaxed">{m.description}</p>
                )}
              </div>
            ))}
            {ourCommitments.length === 0 && (
              <div className="px-6 py-8 text-center text-fg-400 text-sm">No commitments yet</div>
            )}
          </div>
        </div>

        {/* They Promised */}
        <div className="border-r border-border">
          <div className="px-6 py-4 border-b border-border bg-surface-2">
            <div className="font-mono text-[10px] font-bold tracking-[0.3em] uppercase text-accent mb-1">
              THEY PROMISED
            </div>
            <div className="font-display italic text-[1.35rem] text-fg-100">
              {theirCommitments.length} items
            </div>
            <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-fg-400 mt-1">
              {theirCommitments.filter(m => m.status === 'done').length} DELIVERED
            </div>
          </div>
          <div>
            {theirCommitments.slice(0, 5).map(m => (
              <div key={m.id} className="px-6 py-4 border-b border-rule last:border-b-0">
                <div className="flex items-baseline justify-between gap-2 mb-2">
                  <span className="font-display text-[1.06rem] text-fg-100">{m.title}</span>
                  <span className="font-mono text-[9.5px] tracking-[0.18em] uppercase text-accent font-bold whitespace-nowrap">
                    {m.targetDate ? new Date(m.targetDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '-'}
                  </span>
                </div>
                {m.description && (
                  <p className="text-[0.85rem] text-fg-300 leading-relaxed">{m.description}</p>
                )}
              </div>
            ))}
            {theirCommitments.length === 0 && (
              <div className="px-6 py-8 text-center text-fg-400 text-sm">No commitments yet</div>
            )}
          </div>
        </div>

        {/* At Stake */}
        <div>
          <div className="px-6 py-4 border-b border-border bg-accent/10">
            <div className="font-mono text-[10px] font-bold tracking-[0.3em] uppercase text-signal-bad mb-1">
              AT STAKE
            </div>
            <div className="font-display italic text-[1.35rem] text-fg-100">
              Relationship
            </div>
            <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-fg-400 mt-1">
              IF WE MISS
            </div>
          </div>
          <div className="px-6 py-6">
            <p className="font-display italic text-fg-200 leading-relaxed">
              Failing to deliver on our commitments risks <em className="text-signal-bad">losing their trust</em> and potentially the renewal.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// Memo Lens - Strategy document
function MemoLens({
  strategy,
  customerName,
  plan,
}: {
  strategy?: {
    id: string;
    body: string;
    lastUpdatedBy: string | null;
    createdAt: string;
    updatedAt: string;
  };
  customerName: string;
  plan?: NonNullable<ReturnType<typeof useGoalsWithMilestones>['data']>['goals'][0];
}) {
  return (
    <div className="bg-cream text-charcoal p-12 min-h-[600px] relative">
      <div className="absolute inset-x-0 top-0 h-1 bg-accent" />

      {/* Memo Header */}
      <div className="flex justify-between items-end pb-4 border-b border-charcoal/20 mb-8">
        <div className="font-mono text-[10px] tracking-[0.3em] uppercase text-charcoal/60 leading-relaxed">
          <strong className="text-charcoal font-bold block">CUSTOMER SUCCESS STRATEGY</strong>
          {customerName}
        </div>
        <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-charcoal/60 text-right leading-relaxed">
          REF · <span className="text-accent font-bold">{plan?.id?.slice(0, 8).toUpperCase()}</span>
          <br />
          {strategy?.updatedAt ? new Date(strategy.updatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).toUpperCase() : 'DRAFT'}
        </div>
      </div>

      {/* Title */}
      <h1 className="font-display text-[3rem] leading-none tracking-tight text-charcoal mb-4 max-w-[22ch]">
        {plan?.text ? (
          <>Get them to <em className="italic text-accent">{plan.text.toLowerCase()}</em></>
        ) : (
          <>Customer Strategy <em className="italic text-accent">Memo</em></>
        )}
      </h1>

      {strategy?.body ? (
        <div
          className="font-serif text-[1.12rem] leading-relaxed text-charcoal/80 max-w-[64ch] whitespace-pre-wrap"
          dangerouslySetInnerHTML={{ __html: strategy.body }}
        />
      ) : (
        <div className="text-center py-12">
          <p className="font-display italic text-charcoal/60 text-lg mb-4">
            No strategy memo written yet.
          </p>
          <p className="text-charcoal/50 text-sm">
            The strategy memo captures the high-level approach for this customer's success.
          </p>
        </div>
      )}

      {/* Footer */}
      <div className="mt-12 pt-6 border-t border-charcoal/20 flex justify-between items-end">
        <div className="font-display italic text-charcoal">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent mr-2 align-middle" />
          Generated by Sidekick
        </div>
        <div className="font-mono text-[10px] tracking-[0.2em] uppercase text-charcoal/50">
          HEROFY · CUSTOMER SUCCESS
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Contacts Tab Components
// ============================================================================

function ContactsTab({
  stakeholders,
  onEdit,
  onDelete,
  onAdd,
}: {
  stakeholders: Stakeholder[];
  onEdit: (stakeholder: Stakeholder) => void;
  onDelete: (stakeholder: Stakeholder) => void;
  onAdd: () => void;
}) {
  const getRelationshipReading = (stakeholder: Stakeholder): string => {
    if (stakeholder.sentiment_note) return stakeholder.sentiment_note;
    if (stakeholder.status === 'departed') return 'No longer at company';
    return 'Neutral';
  };

  const getLastInteraction = (stakeholder: Stakeholder): { when: string; channel: string } => {
    // Would come from interaction history in production
    return { when: 'Unknown', channel: '' };
  };

  return (
    <div>
      <SectionLabel
        label="CONTACTS"
        count={stakeholders.length}
        action={
          <button
            onClick={onAdd}
            className="text-[11px] font-mono uppercase tracking-[0.2em] text-fg-400 hover:text-fg-200 flex items-center gap-1 transition-colors"
          >
            <Plus className="w-3 h-3" />
            Add
          </button>
        }
      />
      <p className="text-fg-300 font-serif italic mb-6">
        Everyone we've heard from at this company, with how recently we've been in touch and how the relationship is reading.
      </p>

      {stakeholders.length === 0 ? (
        <div className="border border-border p-8 text-center text-fg-400">
          No contacts added yet.
        </div>
      ) : (
        <div className="space-y-3">
          {stakeholders.map((stakeholder) => {
            const lastInteraction = getLastInteraction(stakeholder);
            const relationshipReading = getRelationshipReading(stakeholder);
            const isDeparted = stakeholder.status === 'departed';

            return (
              <RowCard
                key={stakeholder.id}
                edge={isDeparted ? 'muted' : 'brass'}
                align="center"
                icon={<User className="w-3.5 h-3.5" />}
                className={cn(isDeparted && 'opacity-60')}
                trailing={
                  <span className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => { e.preventDefault(); onEdit(stakeholder); }}
                      className="p-1.5 text-fg-400 hover:text-fg-200 transition-colors"
                    >
                      <Edit3 className="w-3 h-3" />
                    </button>
                    <button
                      onClick={(e) => { e.preventDefault(); onDelete(stakeholder); }}
                      className="p-1.5 text-fg-400 hover:text-accent transition-colors"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </span>
                }
              >
                <div className="flex items-baseline gap-2">
                  <span className={cn('font-medium', isDeparted ? 'text-fg-400 line-through' : 'text-fg-100')}>
                    {stakeholder.name}
                  </span>
                  {stakeholder.role && <span className="text-xs text-fg-400">{stakeholder.role}</span>}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span className={cn(
                    'text-sm font-serif italic',
                    isDeparted
                      ? 'text-fg-400'
                      : relationshipReading.toLowerCase().includes('frustrated')
                        ? 'text-signal-risk'
                        : relationshipReading.toLowerCase().includes('quiet')
                          ? 'text-signal-warn'
                          : 'text-fg-300'
                  )}>
                    {relationshipReading}
                  </span>
                  {lastInteraction.when && lastInteraction.when !== 'Unknown' && (
                    <span className="text-[10px] font-mono text-fg-400">
                      · {lastInteraction.when}{lastInteraction.channel ? ` · ${lastInteraction.channel}` : ''}
                    </span>
                  )}
                </div>
              </RowCard>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Loading Skeleton
// ============================================================================

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-8">
      <div className="flex items-start gap-4">
        <div className="h-6 w-24 bg-border rounded" />
        <div className="h-12 w-64 bg-border rounded" />
      </div>
      <div className="flex gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-10 w-24 bg-border rounded" />
        ))}
      </div>
      <div className="h-64 bg-surface-2 rounded" />
    </div>
  );
}

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

interface ColdStartDataPanelProps {
  customerId: string;
  workspaceId: string | undefined;
  isOnboarding: boolean;
  onDataAdded: () => void;
}

function ColdStartDataPanel({
  customerId,
  workspaceId,
  isOnboarding,
  onDataAdded,
}: ColdStartDataPanelProps) {
  const [notes, setNotes] = useState('');
  const [isSavingNotes, setIsSavingNotes] = useState(false);
  const [notionSearchQuery, setNotionSearchQuery] = useState('');
  const [notionSearchResults, setNotionSearchResults] = useState<NotionPageResult[]>([]);
  const [showNotionDropdown, setShowNotionDropdown] = useState(false);
  const [linkingPage, setLinkingPage] = useState(false);

  const updateCustomer = useUpdateCustomer();
  const { data: notionStatus } = useIntegrationStatus('notion');
  const { searchPages, isLoading: isSearching } = useSearchNotionPages();
  const { linkPage } = useLinkPageToCustomer();

  const triggerAgent = async () => {
    if (!isOnboarding || !workspaceId) return;
    try {
      const token = await getAuth().currentUser?.getIdToken();
      fetch(`${PYTHON_URL}/agents/handoff-auto/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          workspace_id: workspaceId,
          customer_id: customerId,
          trigger_type: 'cold_start_data_added',
        }),
      }).catch(() => {});
    } catch { /* token failure */ }
  };

  const handleSaveNotes = async () => {
    if (!notes.trim()) return;
    setIsSavingNotes(true);
    try {
      await updateCustomer.mutateAsync({ customerId, data: { raw_notes: notes } });
      await triggerAgent();
      onDataAdded();
    } catch { /* refetch will reflect state */ } finally {
      setIsSavingNotes(false);
    }
  };

  useEffect(() => {
    if (!notionStatus?.connected) return;
    const timer = setTimeout(async () => {
      if (!notionSearchQuery.trim()) {
        setNotionSearchResults([]);
        setShowNotionDropdown(false);
        return;
      }
      try {
        const result = await searchPages(notionSearchQuery);
        setNotionSearchResults(result.pages);
        setShowNotionDropdown(true);
      } catch {
        setNotionSearchResults([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [notionSearchQuery, notionStatus?.connected, searchPages]);

  const handleLinkPage = async (page: NotionPageResult) => {
    setLinkingPage(true);
    setNotionSearchQuery('');
    setNotionSearchResults([]);
    setShowNotionDropdown(false);
    try {
      await linkPage(customerId, {
        source: 'notion',
        page_id: page.id,
        page_type: 'handoff',
        url: page.url,
        title: page.title,
      });
      await triggerAgent();
      onDataAdded();
    } catch { /* silently fail */ } finally {
      setLinkingPage(false);
    }
  };

  return (
    <div className="hud-pane border-l-2 border-l-charcoal-600 p-6 mb-6">
      <h3 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-1">
        No data yet
      </h3>
      <p className="text-sm text-fg-300 mb-5">
        Give Herofy something to read and it will generate an onboarding plan, surface risks, and populate Today Queue.
      </p>

      <div className="space-y-5">
        <div>
          <label className="block text-xs font-mono uppercase tracking-widest text-fg-400 mb-2">
            Add notes or context
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Paste sales notes, CRM export, Slack history, or anything you know about this customer..."
            rows={4}
            className="w-full bg-surface-2 border border-border text-fg-200 px-4 py-3 placeholder:text-fg-400 focus:border-border-strong focus:outline-none resize-none text-sm"
          />
          <div className="flex justify-end mt-2">
            <button
              type="button"
              onClick={handleSaveNotes}
              disabled={!notes.trim() || isSavingNotes}
              className="text-xs font-mono uppercase tracking-widest bg-accent text-page px-4 py-2 hover:bg-accent-hover transition-colors font-bold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isSavingNotes ? 'Saving...' : 'Save & generate plan'}
            </button>
          </div>
        </div>

        {notionStatus?.connected ? (
          <div>
            <label className="block text-xs font-mono uppercase tracking-widest text-fg-400 mb-2">
              Or link a Notion page
            </label>
            <div className="relative">
              <input
                type="text"
                value={notionSearchQuery}
                onChange={(e) => setNotionSearchQuery(e.target.value)}
                onFocus={() => notionSearchResults.length > 0 && setShowNotionDropdown(true)}
                placeholder={linkingPage ? 'Linking...' : 'Search Notion pages...'}
                disabled={linkingPage}
                className="w-full bg-surface-2 border border-border text-fg-200 px-4 py-2.5 placeholder:text-fg-400 focus:border-border-strong focus:outline-none text-sm disabled:opacity-50"
              />
              {isSearching && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-fg-400">
                  Searching…
                </span>
              )}
              {showNotionDropdown && notionSearchResults.length > 0 && (
                <div className="absolute z-10 w-full border border-border bg-surface-2 mt-0.5 max-h-48 overflow-y-auto">
                  {notionSearchResults.map((page) => (
                    <button
                      key={page.id}
                      type="button"
                      onClick={() => handleLinkPage(page)}
                      className="w-full text-left px-4 py-2.5 text-sm text-fg-200 hover:bg-border transition-colors"
                    >
                      {page.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 pt-1">
            <span className="text-xs text-fg-400">No integrations connected.</span>
            <a
              href="/app/onboarding"
              className="text-xs font-mono uppercase tracking-widest border border-border text-fg-300 px-4 py-2 hover:border-border-strong hover:text-fg-100 transition-colors"
            >
              Connect integrations
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function CustomerDetail() {
  const { customerId } = useParams<{ customerId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get('tab') as TabId) || 'overview';

  const { data, isLoading, error, refetch } = useCustomer(customerId || '');
  const { data: meetingsData } = useMeetings();
  const { data: threadsData } = useThreads();

  // Fetch playbook info for onboarding progress
  const { data: playbookData } = usePlaybook(data?.customer?.adapted_from_playbook_id);

  // Fetch sidekick alert for this customer
  const { data: sidekickAlertData, refetch: refetchSidekickAlert } = useSidekickAlert(customerId);

  // Fetch sidekick items for this customer
  const { data: sidekickItemsData, refetch: refetchSidekickItems } = useSidekickItems(customerId);

  // Fetch customer trends (sentiment + engagement)
  const { data: trendsData, isLoading: trendsLoading } = useCustomerTrends(customerId);

  // Fetch handoff with plan data for plan approval card
  const { data: handoffPlanData } = useCustomerHandoffWithPlan(customerId);

  // Also fetch plans directly (in case they're not linked to a brief)
  const { data: customerPlansData } = useCustomerPlans(customerId);

  // Fetch the orchestrator's Risk/Save play output (RiskBrief + steps)
  const { data: riskData, refetch: refetchRisk } = useRiskBriefsForCustomer(customerId);
  const [showRiskPlay, setShowRiskPlay] = useState(false);
  const navigate = useNavigate();

  // Real-time notifications subscription
  const { workspaceId } = useWorkspace();
  const notifications = useWorkspaceNotifications(workspaceId);
  const prevSidekickCountRef = useRef<number | undefined>(undefined);
  const prevUpdatedAtRef = useRef<number | undefined>(undefined);

  // Refetch main customer data on mount and page focus
  useRefreshOnFocus(refetch);
  // The Risk/Save play is written by an agent run that may fire AFTER this record was first
  // cached (open the customer → run the sweep → come back). DataConnect reads PREFER_CACHE, so
  // the cached-empty play would persist until a hard reload — force a server refetch on mount +
  // focus, same as the main query.
  useRefreshOnFocus(refetchRisk);

  // Auto-refetch ALL data when notifications change
  useEffect(() => {
    // Check sidekick_questions for sidekick-specific refetch
    const currentSidekickCount = notifications?.sidekick_questions;
    if (prevSidekickCountRef.current !== undefined && currentSidekickCount !== prevSidekickCountRef.current) {
      console.log('[CustomerDetail] Sidekick count changed, refetching sidekick data...');
      refetchSidekickAlert();
      refetchSidekickItems();
    }
    prevSidekickCountRef.current = currentSidekickCount;

    // Check updated_at for general data changes (agent activity, etc.)
    const updatedAt = notifications?.updated_at instanceof Date
      ? notifications.updated_at.getTime()
      : (notifications?.updated_at as any)?.toMillis?.();

    if (updatedAt && prevUpdatedAtRef.current !== undefined && prevUpdatedAtRef.current !== updatedAt) {
      console.log('[CustomerDetail] Workspace updated, refetching customer data...');
      // Small delay to allow database propagation
      setTimeout(() => { refetch(); refetchRisk(); }, 300);
    }
    prevUpdatedAtRef.current = updatedAt;
  }, [notifications?.sidekick_questions, notifications?.updated_at, refetchSidekickAlert, refetchSidekickItems, refetch, refetchRisk]);

  // Transform alert data to match component expectations
  const sidekickAlert = sidekickAlertData ? {
    has_questions: sidekickAlertData.has_questions,
    items: sidekickAlertData.items.map(item => ({
      question: item.question || null,
      headline: item.text,
      context: item.context || null,
    })),
    // Get first agent_run_id for navigation (blocking items first)
    first_agent_run_id: sidekickAlertData.items.find(item => item.agent_run_id)?.agent_run_id,
  } : null;

  // Notion sync for manual refresh
  const { sync: syncNotion, isPending: isSyncing } = useSyncNotionPage();
  const [syncMessage, setSyncMessage] = React.useState<string | null>(null);

  // Stakeholder CRUD
  const createStakeholder = useCreateStakeholder();
  const updateStakeholder = useUpdateStakeholder();
  const deleteStakeholder = useDeleteStakeholder();

  // Milestone CRUD
  const createMilestone = useCreateMilestone();
  const updateMilestone = useUpdateMilestone();
  const deleteMilestone = useDeleteMilestone();

  // Goal CRUD
  const createGoal = useCreateGoal();
  const updateGoal = useUpdateGoal();
  const deleteGoal = useDeleteGoal();

  // Health update
  const updateCustomerHealth = useUpdateCustomerHealth();
  // Risk save-play card actions (escalation huddle / mark stable)
  const resolveNeed = useResolveNeed();
  const createHuddle = useCreateHuddle();
  const postHuddleMessage = usePostHuddleMessage();

  // Modal states
  const [stakeholderModal, setStakeholderModal] = React.useState<{
    isOpen: boolean;
    stakeholder: Stakeholder | null;
  }>({ isOpen: false, stakeholder: null });

  const [milestoneModal, setMilestoneModal] = React.useState<{
    isOpen: boolean;
    milestone: Milestone | null;
  }>({ isOpen: false, milestone: null });

  const [healthModal, setHealthModal] = React.useState(false);

  const setActiveTab = (tab: TabId) => {
    setSearchParams({ tab });
  };

  // Stakeholder handlers
  const handleStakeholderSubmit = (data: CreateStakeholderInput | UpdateStakeholderInput) => {
    if (stakeholderModal.stakeholder) {
      updateStakeholder.mutate(
        {
          stakeholderId: stakeholderModal.stakeholder.id,
          customerId: customerId!,
          data: data as UpdateStakeholderInput,
        },
        {
          onSuccess: () => {
            setStakeholderModal({ isOpen: false, stakeholder: null });
            refetch();
          },
        }
      );
    } else {
      createStakeholder.mutate(
        {
          customerId: customerId!,
          data: data as CreateStakeholderInput,
        },
        {
          onSuccess: () => {
            setStakeholderModal({ isOpen: false, stakeholder: null });
            refetch();
          },
        }
      );
    }
  };

  const handleStakeholderDelete = (stakeholder: Stakeholder) => {
    if (confirm(`Remove ${stakeholder.name} from contacts?`)) {
      deleteStakeholder.mutate({
        stakeholderId: stakeholder.id,
        customerId: customerId!,
      }, {
        onSuccess: () => refetch(),
      });
    }
  };

  // Handle Notion sync
  const handleNotionSync = async () => {
    // Try to get Notion page ID from URL prompt (for demo)
    // In production, this would come from customer.notion_page_id or handoff_brief.notion_deal_id
    const notionPageId = window.prompt(
      'Enter Notion page ID to sync:\n\n(In production, this would be linked automatically from the handoff)',
      ''
    );

    if (!notionPageId) {
      return; // User cancelled
    }

    try {
      const result = await syncNotion(notionPageId);
      setSyncMessage(`Synced: ${result.updated_fields.join(', ') || 'No changes'}`);
      // Refetch customer data to show updates
      refetch();
      setTimeout(() => setSyncMessage(null), 5000);
    } catch (err) {
      setSyncMessage('Sync failed - check Notion connection');
      setTimeout(() => setSyncMessage(null), 3000);
    }
  };

  // Milestone handlers
  const handleMilestoneSubmit = (data: CreateMilestoneInput | UpdateMilestoneInput) => {
    if (milestoneModal.milestone) {
      updateMilestone.mutate(
        {
          milestoneId: milestoneModal.milestone.id,
          customerId: customerId!,
          data: data as UpdateMilestoneInput,
        },
        {
          onSuccess: () => setMilestoneModal({ isOpen: false, milestone: null }),
        }
      );
    } else {
      createMilestone.mutate(
        {
          customerId: customerId!,
          data: data as CreateMilestoneInput,
        },
        {
          onSuccess: () => setMilestoneModal({ isOpen: false, milestone: null }),
        }
      );
    }
  };

  // Health override handler
  const handleHealthOverrideSubmit = (data: {
    relationshipHealth: string;
    relationshipHealthScore: number;
    relationshipHealthReason: string;
  }) => {
    updateCustomerHealth.mutate({
      customerId: customerId!,
      ...data,
    });
    setHealthModal(false);
  };

  if (!customerId) {
    return (
      <div className="max-w-5xl mx-auto">
        <div className="hud-pane p-8 text-center">
          <p className="text-fg-300">No customer selected.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto">
        <div className="hud-pane p-8 border-l-4 border-l-rust-500">
          <div className="text-[10px] uppercase tracking-[0.3em] text-accent font-bold mb-4">
            Connection Error
          </div>
          <p className="text-fg-200 mb-4">{(error as Error).message}</p>
          <button
            onClick={() => refetch()}
            className="text-xs font-mono uppercase tracking-widest border border-accent text-accent px-4 py-2 hover:bg-accent hover:text-page transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto">
        <LoadingSkeleton />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-5xl mx-auto">
        <div className="hud-pane p-8 text-center">
          <p className="text-fg-300">Customer not found.</p>
        </div>
      </div>
    );
  }

  const {
    customer,
    stakeholders,
    goals,
    signals: signalsRaw,
    open_needs,
    milestones,
  } = data;
  // Cast: generated SignalKind enum → api.ts string union (pre-existing mismatch)
  const signals = signalsRaw as any as import('@/lib/api').Signal[];

  // The save play's outreach thread (linked to the risk Need) — target for the card's
  // escalation/deep-link actions, and the source of the Need id for "Mark stable". The Need can be
  // any risk type (going_dark, renewal_at_risk, …) depending on what tripped the sweep.
  const RISK_THREAD_NEED_TYPES = new Set([
    'going_dark', 'renewal_at_risk', 'frustrated_signal', 'champion_departed',
    'onboarding_behind', 'approaching_renewal', 'open_commitment_overdue',
  ]);
  const riskThread = threadsData?.threads?.find(
    (th) => th.customer_id === customerId && !!th.need_type && RISK_THREAD_NEED_TYPES.has(th.need_type)
  );

  // Escalation Brief: open a huddle on the play's conversation, post the brief as a Sidekick
  // message, and land the CSM in it to @mention whoever should own the escalation.
  const handleEscalation = async () => {
    if (!riskThread || !workspaceId || !customerId) {
      navigate('/app/conversations');
      return;
    }
    const brief = riskData?.briefs?.[0];
    try {
      const res = await createHuddle.mutateAsync({
        workspaceId, customerId, threadId: riskThread.id, title: `Escalation — ${customer.name}`,
      });
      const huddleId = (res as { huddle_insert?: { id?: string } })?.huddle_insert?.id;
      if (huddleId && brief) {
        const stepLines = (brief.steps || []).map((s, i) => `${i + 1}. ${s.label}`).join('\n');
        const body = [
          `Escalation summary — ${customer.name}`,
          brief.whatChanged,
          brief.evidenceText ? `Evidence: ${brief.evidenceText}` : '',
          stepLines ? `Save play:\n${stepLines}` : '',
          'Pulling in the right owner — @mention whoever should take this.',
        ].filter(Boolean).join('\n\n');
        await postHuddleMessage.mutateAsync({ huddleId, body, authorKind: 'agent' });
      }
    } catch (e) {
      console.warn('Escalation huddle failed:', e);
    }
    navigate(`/app/conversations/${riskThread.id}`);
  };

  // Mark stable: the risk is handled/false-alarm → resolve the Need + lift health out of at-risk.
  const handleMarkStable = () => {
    try {
      updateCustomerHealth.mutate({
        customerId: customerId!,
        relationshipHealth: 'stable',
        relationshipHealthScore: Math.max(customer.relationship_health_score ?? 0, 62),
        relationshipHealthReason: 'CSM marked stable after reviewing the save play.',
      });
      const needId = riskThread?.need?.id;
      if (needId) resolveNeed.mutate(needId);
    } catch (e) {
      console.warn('Mark stable failed:', e);
    }
    refetchRisk();
    refetch();
  };

  const isAtRisk = customer.lifecycle === 'at_risk';
  const isOnboardingCustomer =
    customer.lifecycle === 'handoff' || customer.lifecycle === 'onboarding';
  const showColdStartPanel =
    isOnboardingCustomer &&
    !handoffPlanData?.brief &&
    !handoffPlanData?.plan &&
    !(customerPlansData?.plans?.length) &&
    !customer.raw_notes?.trim() &&
    (customer.linked_pages?.length ?? 0) === 0;
  // Only use real data from API - no mocks
  const relationshipSignals: RelationshipSignal[] = []; // Would come from AI in production
  const recentInteractions: RecentInteraction[] = []; // Would come from threads/interactions
  const threads = threadsData?.threads || [];
  const meetings = meetingsData?.meetings || [];

  return (
    <div>
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <NavLink
            to="/app/customers"
            className="inline-flex items-center gap-1 text-xs font-mono text-fg-400 hover:text-fg-200 transition-colors"
          >
            <ArrowLeft className="w-3 h-3" />
            All customers
          </NavLink>

          {/* Sync button */}
          <button
            onClick={handleNotionSync}
            disabled={isSyncing}
            className={cn(
              'inline-flex items-center gap-1.5 text-xs font-mono uppercase tracking-widest transition-colors',
              isSyncing
                ? 'text-fg-400 cursor-not-allowed'
                : 'text-fg-400 hover:text-fg-200'
            )}
            title="Refresh from Notion"
          >
            <RefreshCw className={cn('w-3 h-3', isSyncing && 'animate-spin')} />
            {isSyncing ? 'Syncing...' : 'Sync'}
          </button>
        </div>

        {/* Sync message toast */}
        {syncMessage && (
          <div className="mb-4 px-3 py-2 bg-surface-2 border border-border text-xs text-fg-300">
            {syncMessage}
          </div>
        )}

        <div className="flex items-start gap-4 mb-4">
          <div className="w-12 h-12 bg-border flex items-center justify-center text-fg-400 font-mono text-sm shrink-0">
            {customer.name.substring(0, 2).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <h1 className={cn(
              'font-serif text-4xl sm:text-5xl mb-1 tracking-tight',
              isAtRisk ? 'text-accent' : 'text-fg-100'
            )}>
              {customer.name}
            </h1>
            {customer.one_liner && (
              <p className="text-fg-300 font-serif italic">{customer.one_liner}</p>
            )}
          </div>
          {/* Health Panel - Right Side. On the overview tab the read lives in the right rail,
              so only show it in the hero on other tabs to avoid duplication. */}
          {activeTab !== 'overview' && (
            <div className="shrink-0 hidden sm:block">
              <HealthIndicator
                health={customer.relationship_health}
                score={customer.relationship_health_score}
                reason={customer.relationship_health_reason}
                updatedBy={customer.relationship_health_updated_by}
                updatedAt={customer.relationship_health_updated_at}
                onClick={() => setHealthModal(true)}
                variant="full"
                signals={signals}
              />
            </div>
          )}
        </div>
        {/* Mobile Health Indicator */}
        {activeTab !== 'overview' && (
          <div className="sm:hidden mb-4">
            <HealthIndicator
              health={customer.relationship_health}
              score={customer.relationship_health_score}
              reason={customer.relationship_health_reason}
              updatedBy={customer.relationship_health_updated_by}
              onClick={() => setHealthModal(true)}
              variant="compact"
              signals={signals}
            />
          </div>
        )}

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-2 text-sm text-fg-400 mb-6">
          {customer.tier && (
            <>
              <span>Tier {customer.tier === 'Enterprise' ? '1' : customer.tier === 'Growth' ? '2' : '3'} · {customer.tier}</span>
              <span className="text-fg-400/50">·</span>
            </>
          )}
          <span className="text-fg-200">{formatARR(customer.arr_cents)} ARR</span>
          <span className="text-fg-400/50">·</span>
          <span className={isAtRisk ? 'text-accent underline' : ''}>
            {customer.lifecycle.replace('_', ' ')}
          </span>
          {customer.days_to_renewal !== null && (
            <>
              <span className="text-fg-400/50">·</span>
              <span>Renews in {customer.days_to_renewal} days</span>
            </>
          )}
        </div>

        {/* Sidekick Alert Banner - Above tabs */}
        {sidekickAlert && sidekickAlert.has_questions && sidekickAlert.items.length > 0 && (
          <div className="mb-6 border-l-4 border-accent bg-surface p-6">
            <div className="flex items-start justify-between gap-8">
              <div className="flex-1">
                <h3 className="text-xs font-mono uppercase tracking-widest text-accent mb-3">
                  Sidekick has {sidekickAlert.items.length} question{sidekickAlert.items.length !== 1 ? 's' : ''} about {customer.name}
                </h3>
                <ul className="space-y-2">
                  {sidekickAlert.items.map((item, idx) => (
                    <li key={idx} className="text-sm text-fg-200">
                      <span className="text-accent mr-2">•</span>
                      {item.question || item.headline}
                      {item.context && (
                        <span className="text-fg-400"> — {item.context}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
              <button
                onClick={() => {
                  // Navigate to sidekick page which shows all pending questions
                  // The needs-based Sidekick page will show the questions for this customer
                  window.location.href = '/app/sidekick';
                }}
                className="shrink-0 px-4 py-2 text-xs font-mono uppercase tracking-wider text-accent hover:text-accent-hover border border-accent/40 hover:border-accent transition-colors flex items-center gap-2"
              >
                Answer in Sidekick
                <span>→</span>
              </button>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-6 border-b border-border">
          <Tab
            id="overview"
            label="Overview"
            active={activeTab === 'overview'}
            onClick={() => setActiveTab('overview')}
          />
          {/* Brief tab - only show for handoff or onboarding customers */}
          {(customer.lifecycle === 'handoff' || customer.lifecycle === 'onboarding') && (
            <Tab
              id="brief"
              label="Brief"
              active={activeTab === 'brief'}
              onClick={() => setActiveTab('brief')}
            />
          )}
          <Tab
            id="plans"
            label="Plans"
            active={activeTab === 'plans'}
            onClick={() => setActiveTab('plans')}
          />
          <Tab
            id="history"
            label="History"
            active={activeTab === 'history'}
            onClick={() => setActiveTab('history')}
          />
          <Tab
            id="contract"
            label="Contract Review"
            active={activeTab === 'contract'}
            onClick={() => setActiveTab('contract')}
          />
          <Tab
            id="contacts"
            label="Contacts"
            count={stakeholders.length}
            active={activeTab === 'contacts'}
            onClick={() => setActiveTab('contacts')}
          />
          <Tab
            id="sidekick"
            label="Sidekick"
            count={sidekickItemsData?.items?.length || 0}
            active={activeTab === 'sidekick'}
            onClick={() => setActiveTab('sidekick')}
          />
        </div>
      </header>

      {/* Onboarding Card - Show if customer has an active onboarding plan */}
      {customer.lifecycle === 'onboarding' && milestones.length > 0 && (() => {
        // Compute real onboarding progress from milestones
        // MilestoneStatus: not_started, in_progress, blocked, done, skipped
        const completedMilestones = milestones.filter(m => m.status === 'done' || m.status === 'skipped');
        const completedSteps = completedMilestones.length;
        const totalSteps = milestones.length;

        // Get day progress from customer or compute a reasonable default
        const daysCurrent = customer.onboarding_day_current || 1;
        const daysTotal = customer.onboarding_day_total || 90;

        // Find first incomplete milestone for "next mandate"
        const nextMilestone = milestones.find(m => m.status !== 'done' && m.status !== 'skipped');
        const nextMandate = nextMilestone?.title;
        const nextMandateDate = nextMilestone?.target_date
          ? new Date(nextMilestone.target_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
          : undefined;

        // Determine status based on progress
        // If behind schedule (less than expected progress), mark at_risk or behind
        const expectedProgress = (daysCurrent / daysTotal) * totalSteps;
        const actualProgress = completedSteps;
        const progressRatio = actualProgress / Math.max(expectedProgress, 1);

        let status: 'on_track' | 'at_risk' | 'behind' = 'on_track';
        if (progressRatio < 0.5) {
          status = 'behind';
        } else if (progressRatio < 0.8) {
          status = 'at_risk';
        }

        // Check if any milestone is blocked
        const hasBlockedMilestone = milestones.some(m => m.status === 'blocked');
        if (hasBlockedMilestone) {
          status = 'at_risk';
        }

        // Get playbook info
        const playbookName = playbookData?.name || 'Onboarding';
        const playbookSlug = playbookData?.archetype?.toUpperCase() || 'ONB';
        const playbookTitle = `${playbookName} · ${daysTotal}-day`;

        return (
          <OnboardingCard
            customerId={customer.id}
            customerName={customer.name}
            playbookSlug={`PB-${playbookSlug}`}
            playbookTitle={playbookTitle}
            daysCurrent={daysCurrent}
            daysTotal={daysTotal}
            completedSteps={completedSteps}
            totalSteps={totalSteps}
            nextMandate={nextMandate}
            nextMandateDate={nextMandateDate}
            status={status}
            className="mb-8"
          />
        );
      })()}

      {/* Tab Content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.15 }}
        >
          {activeTab === 'overview' && (
            <div className="lg:grid lg:grid-cols-3 lg:gap-8 lg:items-start">
              {/* ---- MAIN COLUMN ---- */}
              <div className="lg:col-span-2 min-w-0">
                {showColdStartPanel && (
                  <ColdStartDataPanel
                    customerId={customerId!}
                    workspaceId={workspaceId}
                    isOnboarding={isOnboardingCustomer}
                    onDataAdded={() => refetch()}
                  />
                )}

                {/* Risk/Save Play Card - orchestrator's renewal-risk save play (highest priority) */}
                {riskData?.briefs?.length ? (
                  <RiskSavePlayCard
                    briefs={riskData.briefs}
                    daysToRenewal={customer.days_to_renewal}
                    healthLabel={customer.relationship_health}
                    healthScore={customer.relationship_health_score}
                    arrCents={customer.arr_cents}
                    lifecycle={customer.lifecycle}
                    stakeholders={stakeholders}
                    signals={signals}
                    // Deep-link to the save play's conversation (Sidekick's "why I opened this"
                    // note + the drafted email). Escalation opens a huddle there; Mark stable
                    // resolves the Need + lifts health.
                    onStartPlay={() => navigate(riskThread ? `/app/conversations/${riskThread.id}` : '/app/conversations')}
                    onEscalation={handleEscalation}
                    onMarkStable={handleMarkStable}
                    onStepChanged={refetchRisk}
                  />
                ) : (
                  <button
                    onClick={() => setShowRiskPlay(true)}
                    className="w-full mb-6 flex items-center justify-between gap-3 px-5 py-3 border border-dashed border-border text-fg-400 hover:border-rust-500 hover:text-fg-200 transition-colors group"
                  >
                    <span className="flex items-center gap-2.5">
                      <ShieldAlert className="w-4 h-4 text-rust-500" />
                      <span className="font-mono text-[10.5px] tracking-[0.18em] uppercase font-bold">
                        Heard something concerning? Spin up a save play
                      </span>
                    </span>
                    <ChevronRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                  </button>
                )}

                <RiskPlayTriggerModal
                  isOpen={showRiskPlay}
                  onClose={() => setShowRiskPlay(false)}
                  customerId={customerId!}
                  customerName={customer.name}
                  workspaceId={workspaceId}
                  onTriggered={() => {
                    // The worker runs the play async (background drain); give it a beat,
                    // then refetch so the new save brief surfaces without a manual reload.
                    setTimeout(() => refetchRisk(), 8000);
                  }}
                />

                {/* Pending Plan Card - shows prominently when plan awaits approval */}
                {/* Check both handoff-linked plans and direct customer plans */}
                {(handoffPlanData?.plan || customerPlansData?.pending_plan) && (
                  <PendingPlanCard plan={handoffPlanData?.plan || customerPlansData?.pending_plan} />
                )}

                {/* What They Care About */}
                <WhatTheyCareAbout
                  goals={goals}
                  customerId={customerId}
                  onCreateGoal={(data) => createGoal.mutate({ customerId: customerId!, data }, { onSuccess: () => refetch() })}
                  onUpdateGoal={(goalId, data) => updateGoal.mutate({ goalId, customerId: customerId!, data }, { onSuccess: () => refetch() })}
                  onDeleteGoal={(goalId) => {
                    if (confirm('Remove this goal?')) {
                      deleteGoal.mutate({ goalId, customerId: customerId! }, { onSuccess: () => refetch() });
                    }
                  }}
                  isCreating={createGoal.isPending}
                  isUpdating={updateGoal.isPending}
                />

                {/* Relationship Signals */}
                <RelationshipSignalsSection signals={relationshipSignals} />

                {/* Open Needs */}
                <OpenNeedsSection needs={open_needs as any} />

                {/* Active Conversations */}
                <ActiveConversationsSection threads={threads as any} customerId={customerId} />

                {/* Upcoming Meetings */}
                <UpcomingMeetingsSection meetings={meetings as any} customerId={customerId} />

                {/* Recent Interactions */}
                <RecentInteractionsSection interactions={recentInteractions} />
              </div>

              {/* ---- RIGHT RAIL ---- */}
              <aside className="lg:col-span-1 mt-8 lg:mt-0 space-y-6 lg:sticky lg:top-6">
                {/* Sidekick's Read - relationship health verdict */}
                <HealthIndicator
                  health={customer.relationship_health}
                  score={customer.relationship_health_score}
                  reason={customer.relationship_health_reason}
                  updatedBy={customer.relationship_health_updated_by}
                  updatedAt={customer.relationship_health_updated_at}
                  onClick={() => setHealthModal(true)}
                  variant="full"
                  signals={signals}
                  className="w-full edge-brass"
                />

                {/* Trends - Sentiment & Engagement */}
                {(trendsData || trendsLoading) && (
                  <div className="border border-border bg-surface p-4">
                    <h3 className="text-[10px] font-mono uppercase tracking-[0.2em] text-fg-400 mb-3">
                      TRENDS · 30 DAYS
                    </h3>
                    {trendsLoading ? (
                      <div className="text-fg-400 text-sm italic">Loading trends...</div>
                    ) : (
                      <TrendCard
                        sentiment={trendsData?.sentiment}
                        engagement={trendsData?.engagement}
                        showSparkline={true}
                      />
                    )}
                  </div>
                )}

                {/* Sidekick open items */}
                <SidekickRail items={sidekickItemsData?.items || []} />
              </aside>
            </div>
          )}

          {activeTab === 'brief' && (
            <BriefTab customerId={customerId || ''} />
          )}

          {activeTab === 'plans' && (
            <PlansTab
              customerId={customerId || ''}
              customerName={customer.name}
              pendingPlan={handoffPlanData?.plan || customerPlansData?.pending_plan}
            />
          )}

          {activeTab === 'history' && (
            <HistoryTab
              customerId={customerId}
              threads={threads as any}
              daysToRenewal={customer.days_to_renewal}
            />
          )}

          {activeTab === 'contract' && (
            <ContractReviewTab customerId={customerId} />
          )}

          {activeTab === 'contacts' && (
            <ContactsTab
              stakeholders={stakeholders}
              onEdit={(s) => setStakeholderModal({ isOpen: true, stakeholder: s })}
              onDelete={handleStakeholderDelete}
              onAdd={() => setStakeholderModal({ isOpen: true, stakeholder: null })}
            />
          )}

          {activeTab === 'sidekick' && (
            <SidekickTab sidekickItems={sidekickItemsData?.items || []} />
          )}
        </motion.div>
      </AnimatePresence>

      {/* Modals */}
      <StakeholderModal
        isOpen={stakeholderModal.isOpen}
        onClose={() => setStakeholderModal({ isOpen: false, stakeholder: null })}
        onSubmit={handleStakeholderSubmit}
        isSubmitting={createStakeholder.isPending || updateStakeholder.isPending}
        stakeholder={stakeholderModal.stakeholder}
      />

      <MilestoneModal
        isOpen={milestoneModal.isOpen}
        onClose={() => setMilestoneModal({ isOpen: false, milestone: null })}
        onSubmit={handleMilestoneSubmit}
        isSubmitting={createMilestone.isPending || updateMilestone.isPending}
        milestone={milestoneModal.milestone}
      />

      <HealthOverrideModal
        isOpen={healthModal}
        currentHealth={customer?.relationship_health}
        currentScore={customer?.relationship_health_score}
        currentReason={customer?.relationship_health_reason}
        onClose={() => setHealthModal(false)}
        onSubmit={handleHealthOverrideSubmit}
        isSubmitting={updateCustomerHealth.isPending}
      />
    </div>
  );
}
