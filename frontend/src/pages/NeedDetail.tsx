import { useState } from 'react';
import { useParams, Link, NavLink, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  Check,
  Clock,
  Mail,
  MessageSquare,
  Calendar,
  Zap,
  HelpCircle,
  FileText,
  AlertCircle,
  Target,
  Loader2,
} from 'lucide-react';
import { RefCode, Timestamp, Pulse, Sidekick } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { useNeed, useResolveNeed, useSnoozeNeed, useAgentRunForBlockingNeed, useCustomerThreads, useSidekickItems, useCustomerHandoffWithPlan, useCustomerPlans } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import { RightRail } from '@/components/sidekick';
import { NeedPlayLayout } from '@/components/conversation/NeedPlayLayout';
import type { NeedType } from '@/lib/api';

// Proactive-play need types (from the conversation reframe, screenshot 183157
// middle column): customer-facing needs that are surfaced *before* any thread
// exists. When such a need has no thread, it opens as a Play layout (brief +
// save-play steps) rather than the thread-reply view. Work-item needs
// (sidekick_question, plan_approval_required, meeting_prep_ready) are excluded.
const PLAY_NEED_TYPES = new Set<string>([
  'renewal_at_risk',
  'approaching_renewal',
  'stalled_milestone',
  'onboarding_behind',
  'champion_departed',
  'check_in_due',
  'expansion_signal',
  'positive_signal',
]);

// Map need types to display labels
const needTypeLabels: Record<NeedType, string> = {
  urgent_support: 'Urgent Support',
  going_dark: 'Going Dark',
  stalled_milestone: 'Stalled Milestone',
  approaching_renewal: 'Approaching Renewal',
  open_commitment_overdue: 'Overdue Commitment',
  frustrated_signal: 'Frustrated Signal',
  champion_departed: 'Champion Departed',
  onboarding_behind: 'Onboarding Behind',
  renewal_at_risk: 'Renewal at Risk',
  new_handoff: 'New Handoff',
  meeting_prep_ready: 'Meeting Prep Ready',
  positive_signal: 'Positive Signal',
  expansion_signal: 'Expansion Signal',
  check_in_due: 'Check-in Due',
  escalation: 'Escalation',
  plan_approval_required: 'Plan Approval Required',
  draft_response_ready: 'Draft Response Ready',
  sidekick_question: 'Sidekick Question',
  uncategorized: 'Uncategorized',
};

function formatTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return '1d ago';
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatARR(cents: number | null): string {
  if (!cents) return '';
  const amount = cents / 100;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return `$${amount}`;
}

function ChannelIcon({ channel }: { channel: string }) {
  switch (channel) {
    case 'slack':
      return <MessageSquare className="w-4 h-4" />;
    case 'email':
    default:
      return <Mail className="w-4 h-4" />;
  }
}

function LoadingSkeleton() {
  return (
    <div className="max-w-5xl mx-auto animate-pulse">
      <div className="h-6 w-32 bg-charcoal-700 rounded mb-8" />
      <div className="h-12 w-96 bg-charcoal-700 rounded mb-4" />
      <div className="h-6 w-64 bg-charcoal-800 rounded mb-8" />
      <div className="grid grid-cols-3 gap-8">
        <div className="col-span-2 space-y-6">
          <div className="h-32 bg-charcoal-800 rounded border border-charcoal-700" />
          <div className="h-48 bg-charcoal-800 rounded border border-charcoal-700" />
        </div>
        <div className="h-96 bg-charcoal-800 rounded border border-charcoal-700" />
      </div>
    </div>
  );
}

// Sidekick Questions Section
function SidekickQuestionsSection({ need }: { need: NonNullable<ReturnType<typeof useNeed>['data']>['need'] }) {
  const agentRun = need.agent_run;

  // Fallback: search for agent runs that are blocking this need
  const { data: fallbackData, isLoading: fallbackLoading } = useAgentRunForBlockingNeed(
    agentRun ? null : need.id // Only query if no agent_run directly on the need
  );

  // Get questions from either source
  let questions: Array<{ id: string; text: string; context?: string }> = [];
  let agentRunId: string | null = null;

  if (agentRun?.clarifying_questions) {
    // Primary: use questions from the need's linked agent run
    try {
      const parsed = JSON.parse(agentRun.clarifying_questions);
      questions = parsed.map((q: { question: string; context?: string; field?: string }, index: number) => ({
        id: q.field || `q${index}`,
        text: q.question,
        context: q.context,
      }));
      agentRunId = agentRun.id;
    } catch (e) {
      console.warn('Failed to parse clarifying questions:', e);
    }
  } else if (fallbackData) {
    // Fallback: use questions from agent run blocking this need
    questions = fallbackData.questions;
    agentRunId = fallbackData.agent_run_id;
  }

  // Show loading state while checking for fallback
  if (!agentRun && fallbackLoading) {
    return (
      <div className="bg-charcoal-800 border border-charcoal-700 p-6 flex items-center justify-center gap-3">
        <Loader2 className="w-4 h-4 animate-spin text-charcoal-400" />
        <p className="text-charcoal-400">Looking for pending questions...</p>
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <div className="bg-charcoal-800 border border-charcoal-700 p-6 text-center">
        <p className="text-charcoal-400">No questions pending</p>
      </div>
    );
  }

  return (
    <div className="border-2 border-rust-500/50 bg-gradient-to-br from-charcoal-800 to-charcoal-900 p-6">
      <div className="flex items-center gap-3 mb-6">
        <Zap className="w-5 h-5 text-rust-500 fill-rust-500" />
        <h3 className="text-sm font-mono uppercase tracking-widest text-rust-400">
          Sidekick Questions ({questions.length})
        </h3>
        {!agentRun && fallbackData && (
          <span className="text-xs font-mono text-charcoal-500">(from blocking agent)</span>
        )}
      </div>

      <div className="space-y-4 mb-6">
        {questions.map((q, index) => (
          <div
            key={q.id}
            className="flex items-start gap-3 bg-charcoal-900/50 border border-charcoal-700 p-4"
          >
            <div className="flex items-center justify-center w-6 h-6 rounded-full bg-rust-500/20 text-rust-400 text-sm font-bold shrink-0">
              {index + 1}
            </div>
            <div className="flex-1">
              <p className="text-cream-200 leading-relaxed">{q.text}</p>
              {q.context && (
                <p className="text-charcoal-400 text-sm mt-2 italic">{q.context}</p>
              )}
            </div>
          </div>
        ))}
      </div>

      <NavLink
        to={agentRunId ? `/app/sidekick/${agentRunId}` : '#'}
        className={cn(
          "inline-flex items-center gap-2 px-6 py-3 font-mono text-xs uppercase tracking-widest font-bold transition-colors",
          agentRunId
            ? "bg-rust-500 hover:bg-rust-400 text-charcoal-900"
            : "bg-charcoal-700 text-charcoal-400 cursor-not-allowed"
        )}
      >
        <HelpCircle className="w-4 h-4" />
        <span>Answer Questions</span>
      </NavLink>
    </div>
  );
}

// Plan Approval Section
function PlanApprovalSection({ need }: { need: NonNullable<ReturnType<typeof useNeed>['data']>['need'] }) {
  // Primary: try to get plan from agent_run
  const agentRunPlan = need.agent_run?.plan;

  // Fallback 1: fetch plan via customer handoff brief
  const customerId = need.customer?.id || null;
  const { data: handoffData, isLoading: handoffLoading } = useCustomerHandoffWithPlan(
    agentRunPlan ? null : customerId // Only query if no plan from agent_run
  );

  // Fallback 2: fetch plans directly from customer (in case no brief exists)
  const { data: customerPlansData, isLoading: plansLoading } = useCustomerPlans(
    agentRunPlan || handoffData?.plan ? null : customerId // Only if no plan found yet
  );

  // Use whichever plan is available (agent_run -> handoff -> direct)
  const plan = agentRunPlan || handoffData?.plan || customerPlansData?.pending_plan;
  const isLoading = !agentRunPlan && (handoffLoading || (!handoffData?.plan && plansLoading));

  return (
    <div className="bg-charcoal-800 border border-charcoal-700 p-6">
      <div className="flex items-center gap-3 mb-4">
        <FileText className="w-5 h-5 text-rust-500" />
        <h3 className="text-sm font-mono uppercase tracking-widest text-charcoal-400">
          Plan Approval Required
        </h3>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-3">
          <Loader2 className="w-4 h-4 animate-spin text-charcoal-400" />
          <p className="text-charcoal-400 italic">Loading plan...</p>
        </div>
      ) : plan ? (
        <>
          <p className="text-cream-300 mb-2">
            An AI-generated onboarding plan is ready for your review.
          </p>
          {plan.headline && (
            <p className="text-sm text-charcoal-400 mb-6 italic">
              "{plan.headline}"
            </p>
          )}
          <NavLink
            to={`/app/plans/${plan.id}`}
            className="inline-flex items-center gap-2 bg-rust-500 hover:bg-rust-400 text-charcoal-900 px-6 py-3 font-mono text-xs uppercase tracking-widest font-bold transition-colors"
          >
            <FileText className="w-4 h-4" />
            <span>Review Plan</span>
          </NavLink>
        </>
      ) : (
        <p className="text-charcoal-400 italic">
          No plan found. The agent may still be working on generating one.
        </p>
      )}
    </div>
  );
}

// Milestone Section
function MilestoneSection({ milestone }: {
  milestone: NonNullable<NonNullable<ReturnType<typeof useNeed>['data']>['need']['milestone']>
}) {
  return (
    <div className="bg-charcoal-800 border border-charcoal-700 p-6">
      <div className="flex items-center gap-3 mb-4">
        <Target className="w-5 h-5 text-amber-500" />
        <h3 className="text-sm font-mono uppercase tracking-widest text-charcoal-400">
          Related Milestone
        </h3>
      </div>

      <div className="flex items-start justify-between">
        <div>
          <h4 className="text-lg text-cream-100 font-serif">{milestone.title}</h4>
          {milestone.description && (
            <p className="text-sm text-charcoal-400 mt-1">{milestone.description}</p>
          )}
          {milestone.blocked_reason && (
            <div className="mt-3 flex items-center gap-2 text-amber-400 text-sm">
              <AlertCircle className="w-4 h-4" />
              <span>{milestone.blocked_reason}</span>
            </div>
          )}
        </div>
        <div className="text-right">
          <span className={cn(
            'text-xs font-mono uppercase px-2 py-1',
            milestone.status === 'done' ? 'bg-emerald-900/30 text-emerald-400' :
            milestone.status === 'blocked' ? 'bg-amber-900/30 text-amber-400' :
            milestone.status === 'in_progress' ? 'bg-blue-900/30 text-blue-400' :
            'bg-charcoal-700 text-charcoal-400'
          )}>
            {milestone.status.replace('_', ' ')}
          </span>
          {milestone.target_date && (
            <p className="text-xs text-charcoal-500 mt-2">
              Target: {new Date(milestone.target_date).toLocaleDateString()}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// Meeting Section
function MeetingSection({ meeting }: {
  meeting: NonNullable<NonNullable<ReturnType<typeof useNeed>['data']>['need']['meeting']>
}) {
  const scheduledDate = new Date(meeting.scheduled_at);
  const isPast = scheduledDate < new Date();

  return (
    <div className="bg-charcoal-800 border border-charcoal-700 p-6">
      <div className="flex items-center gap-3 mb-4">
        <Calendar className="w-5 h-5 text-blue-500" />
        <h3 className="text-sm font-mono uppercase tracking-widest text-charcoal-400">
          {isPast ? 'Related Meeting' : 'Upcoming Meeting'}
        </h3>
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-lg text-cream-100 font-serif">{meeting.title}</h4>
          <p className="text-sm text-charcoal-400 mt-1">
            {scheduledDate.toLocaleDateString('en-US', {
              weekday: 'short',
              month: 'short',
              day: 'numeric',
              hour: 'numeric',
              minute: '2-digit',
            })}
            {meeting.duration_minutes && ` · ${meeting.duration_minutes}min`}
          </p>
        </div>

        <NavLink
          to={`/app/meetings/${meeting.id}`}
          className="text-xs font-mono uppercase tracking-widest text-charcoal-400 hover:text-cream-200 border border-charcoal-600 px-3 py-1.5 transition-colors"
        >
          View Brief
        </NavLink>
      </div>
    </div>
  );
}

// Threads Section - with fallback to customer threads when none directly linked
function ThreadsSection({ threads, customerId }: {
  threads: NonNullable<ReturnType<typeof useNeed>['data']>['need']['threads'];
  customerId: string | null;
}) {
  const [expanded, setExpanded] = useState(true);

  // Fallback: fetch customer's recent threads if no directly linked threads
  const shouldUseFallback = threads.length === 0 && !!customerId;
  const { data: customerThreadsData, isLoading: fallbackLoading } = useCustomerThreads(
    shouldUseFallback ? customerId : null
  );

  // Use directly linked threads, or fallback to customer threads
  const displayThreads = threads.length > 0 ? threads : (customerThreadsData?.threads || []);
  const isFallback = threads.length === 0 && displayThreads.length > 0;

  // Show loading state while checking fallback
  if (shouldUseFallback && fallbackLoading) {
    return (
      <div className="bg-charcoal-800 border border-charcoal-700 p-6 flex items-center justify-center gap-3">
        <Loader2 className="w-4 h-4 animate-spin text-charcoal-400" />
        <p className="text-charcoal-400">Looking for related threads...</p>
      </div>
    );
  }

  if (displayThreads.length === 0) {
    return (
      <div className="bg-charcoal-800 border border-charcoal-700 p-6 text-center">
        <p className="text-charcoal-400">No threads for this need</p>
      </div>
    );
  }

  return (
    <div className="bg-charcoal-800 border border-charcoal-700">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-charcoal-700/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <MessageSquare className="w-5 h-5 text-charcoal-400" />
          <h3 className="text-sm font-mono uppercase tracking-widest text-charcoal-400">
            {isFallback ? "Customer's Recent Threads" : 'Threads'} ({displayThreads.length})
          </h3>
          {isFallback && (
            <span className="text-[10px] font-mono text-amber-500 uppercase">Fallback</span>
          )}
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-charcoal-400" /> : <ChevronDown className="w-4 h-4 text-charcoal-400" />}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            className="overflow-hidden"
          >
            <div className="border-t border-charcoal-700">
              {displayThreads.map((thread, index) => (
                <Link
                  key={thread.id}
                  to={`/app/conversations/${thread.id}`}
                  className={cn(
                    'flex items-center gap-4 p-4 hover:bg-charcoal-700/50 transition-colors',
                    index !== displayThreads.length - 1 && 'border-b border-charcoal-700/50'
                  )}
                >
                  <ChannelIcon channel={thread.channel} />
                  <div className="flex-1 min-w-0">
                    <p className="text-cream-200 truncate">{thread.subject || 'No subject'}</p>
                    <p className="text-xs text-charcoal-500 mt-0.5 capitalize">{thread.thread_type} · {thread.channel}</p>
                  </div>
                  <span className={cn(
                    'text-[9px] font-mono uppercase px-1.5 py-0.5',
                    thread.status === 'resolved'
                      ? 'bg-emerald-900/30 text-emerald-400'
                      : 'bg-charcoal-700 text-charcoal-400'
                  )}>
                    {thread.status}
                  </span>
                  <Timestamp time={formatTime(thread.updated_at)} className="text-[10px]" />
                </Link>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function NeedDetail() {
  const { needId } = useParams<{ needId: string }>();
  const navigate = useNavigate();
  const { data, isLoading, error, refetch } = useNeed(needId || '');
  const resolveNeed = useResolveNeed();
  const snoozeNeed = useSnoozeNeed();

  // Refetch on mount and page focus to prevent stale data
  useRefreshOnFocus(refetch);

  const [reasoningExpanded, setReasoningExpanded] = useState(false);

  // Get customer ID for sidekick items (need to call hook before conditionals)
  const customerId = data?.need?.customer?.id || null;

  // Fetch sidekick items for the customer
  const { data: sidekickData } = useSidekickItems(customerId);

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

  if (isLoading) {
    return <LoadingSkeleton />;
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto text-center py-16">
        <p className="text-rust-400">Failed to load need</p>
        <p className="text-charcoal-400 text-sm mt-2">{(error as Error).message}</p>
        <button
          onClick={() => navigate(-1)}
          className="mt-4 text-xs font-mono uppercase tracking-widest border border-charcoal-600 px-4 py-2 text-charcoal-400 hover:text-cream-200 transition-colors"
        >
          Go Back
        </button>
      </div>
    );
  }

  if (!data?.need) {
    return (
      <div className="max-w-5xl mx-auto text-center py-16">
        <p className="text-charcoal-400">Need not found</p>
        <button
          onClick={() => navigate(-1)}
          className="mt-4 text-xs font-mono uppercase tracking-widest border border-charcoal-600 px-4 py-2 text-charcoal-400 hover:text-cream-200 transition-colors"
        >
          Go Back
        </button>
      </div>
    );
  }

  const { need } = data;
  const needLabel = needTypeLabels[need.type as NeedType] || 'Need';
  const isSidekickQuestion = need.type === 'sidekick_question';
  const isPlanApproval = need.type === 'plan_approval_required';
  const isUrgent = ['urgent_support', 'escalation', 'frustrated_signal'].includes(need.type);

  const handleResolve = () => {
    resolveNeed.mutate(need.id);
    navigate('/app/conversations');
  };

  const handleSnooze = () => {
    const snoozedUntil = new Date();
    snoozedUntil.setHours(snoozedUntil.getHours() + 24);
    snoozeNeed.mutate({ needId: need.id, snoozedUntil });
  };

  // Route the need-open view by what the need IS, not by whether a thread exists.
  // A threadless proactive-play need (no thread AND a play-class type) opens as the
  // Play layout (brief + save-play steps). Thread-backed needs keep the existing
  // threaded-conversation handling below, unchanged.
  const hasThread = !!need.thread_id || need.threads.length > 0;
  const isThreadlessPlay = !hasThread && PLAY_NEED_TYPES.has(need.type);

  if (isThreadlessPlay) {
    return <NeedPlayLayout need={need} onResolve={handleResolve} onSnooze={handleSnooze} />;
  }

  return (
    <div className="max-w-5xl mx-auto">
      {/* Breadcrumb */}
      <Link
        to="/app/conversations"
        className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-charcoal-400 hover:text-cream-200 transition-colors mb-8"
      >
        <ChevronLeft className="w-4 h-4" />
        <span>Back to Conversations</span>
      </Link>

      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center gap-4 mb-4">
          <Pulse active={!need.snoozed_until} />
          <div className="flex items-center gap-3 font-mono text-[10px] tracking-widest text-charcoal-500 uppercase">
            <RefCode className={cn(isUrgent ? 'text-rust-500' : 'text-rust-500/50', 'font-bold')}>
              {need.id.slice(0, 8).toUpperCase()}
            </RefCode>
            <span>//</span>
            <span className={cn(isUrgent ? 'text-rust-400' : 'text-charcoal-400')}>{needLabel}</span>
            <span>//</span>
            <Timestamp time={formatTime(need.updated_at)} />
          </div>

          {/* Actions */}
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={handleSnooze}
              className="p-2 text-charcoal-400 hover:text-cream-200 hover:bg-charcoal-800 rounded transition-colors"
              title="Snooze for 24h"
            >
              <Clock className="w-5 h-5" />
            </button>
            <button
              onClick={handleResolve}
              className="p-2 text-charcoal-400 hover:text-emerald-500 hover:bg-charcoal-800 rounded transition-colors"
              title="Mark resolved"
            >
              <Check className="w-5 h-5" />
            </button>
          </div>
        </div>

        <h1 className="text-3xl font-serif text-cream-100 mb-2">{need.headline}</h1>
        {need.lede && (
          <p className="text-lg text-cream-300 italic">{need.lede}</p>
        )}
      </header>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column - Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Type-specific sections */}
          {isSidekickQuestion && <SidekickQuestionsSection need={need} />}
          {isPlanApproval && <PlanApprovalSection need={need} />}

          {/* Milestone if exists */}
          {need.milestone && <MilestoneSection milestone={need.milestone} />}

          {/* Meeting if exists */}
          {need.meeting && <MeetingSection meeting={need.meeting} />}

          {/* Threads */}
          <ThreadsSection threads={need.threads} customerId={need.customer?.id || null} />

          {/* Agent Reasoning */}
          {need.agent_reasoning && (
            <div className="bg-charcoal-800 border border-charcoal-700">
              <button
                onClick={() => setReasoningExpanded(!reasoningExpanded)}
                className="w-full flex items-center justify-between p-4 hover:bg-charcoal-700/50 transition-colors"
              >
                <span className="text-xs font-mono uppercase tracking-widest text-charcoal-400">
                  Why did this surface?
                </span>
                {reasoningExpanded ? <ChevronUp className="w-4 h-4 text-charcoal-400" /> : <ChevronDown className="w-4 h-4 text-charcoal-400" />}
              </button>

              <AnimatePresence>
                {reasoningExpanded && (
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: 'auto' }}
                    exit={{ height: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-4 border-t border-charcoal-700">
                      <p className="text-cream-300 text-sm leading-relaxed pt-4">
                        {need.agent_reasoning}
                      </p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Recommendations */}
          {need.recommendations.length > 0 && (
            <div className="bg-charcoal-800 border border-charcoal-700 p-6">
              <h3 className="text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-4">
                Recommendations
              </h3>
              <div className="space-y-4">
                {need.recommendations.map((rec, index) => (
                  <div key={index}>
                    <Sidekick>
                      {rec.primary_action}
                      {rec.secondary_action && (
                        <span className="block mt-2 text-cream-400 text-xs">
                          Alternative: {rec.secondary_action}
                        </span>
                      )}
                      {rec.rationale && (
                        <span className="block mt-2 text-charcoal-400 text-xs italic">
                          {rec.rationale}
                        </span>
                      )}
                    </Sidekick>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Column - Sidebar with Full Customer Context */}
        <div className="sticky top-12 self-start">
          {customerId && railData && (
            <RightRail
              key={railData.customer.id}
              customer={railData.customer}
              items={railData.items}
              openItemsCount={railData.openItemsCount}
              resolvedItemsCount={railData.resolvedItemsCount}
              onOpenCustomer={() => navigate(`/app/customers/${customerId}`)}
              onOpenSidekick={() => {
                const askingItem = railData.items.find(i => i.type === 'asking');
                if (askingItem) {
                  navigate(`/app/sidekick/${askingItem.id}`);
                }
              }}
            />
          )}
          {customerId && !railData && (
            <div className="bg-surface border border-border p-6">
              <div className="animate-pulse space-y-4">
                <div className="h-6 bg-border rounded w-3/4" />
                <div className="h-4 bg-surface-2 rounded w-1/2" />
                <div className="h-20 bg-surface-2 rounded mt-6" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
