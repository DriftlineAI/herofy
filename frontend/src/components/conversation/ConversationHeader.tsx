import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronRight,
  ArrowLeft,
  Check,
  Clock,
  AlertTriangle,
  Pause,
  ChevronDown,
  RotateCcw,
  Loader2,
  X,
} from 'lucide-react';
import { RefCode, MissionStamp, Pulse } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import type { ThreadDetail, NeedType, CustomerLifecycle, WorkflowStatus } from '@/lib/api';

interface ConversationHeaderProps {
  thread: ThreadDetail;
  onUpdateStatus: (status: WorkflowStatus, blockedReason?: string, snoozedUntil?: string) => Promise<void>;
  isUpdatingStatus?: boolean;
}

function getNeedTypeLabel(type: NeedType | null): string {
  if (!type) return 'CONVERSATION';
  const labels: Record<NeedType, string> = {
    urgent_support: 'SUPPORT',
    going_dark: 'GOING DARK',
    stalled_milestone: 'STALLED',
    approaching_renewal: 'RENEWAL',
    open_commitment_overdue: 'OVERDUE',
    frustrated_signal: 'FRUSTRATED',
    champion_departed: 'CHAMPION LEFT',
    onboarding_behind: 'ONBOARDING',
    renewal_at_risk: 'RENEWAL RISK',
    new_handoff: 'HANDOFF',
    meeting_prep_ready: 'MEETING PREP',
    positive_signal: 'POSITIVE',
    expansion_signal: 'EXPANSION',
    check_in_due: 'CHECK-IN',
    escalation: 'ESCALATION',
    plan_approval_required: 'PLAN APPROVAL',
    draft_response_ready: 'DRAFT READY',
    sidekick_question: 'SIDEKICK HELP',
    uncategorized: 'CONVERSATION',
  };
  return labels[type] || 'CONVERSATION';
}

function getNeedTypeCategory(type: NeedType | null): 'support' | 'onboarding' | 'renewal' | 'general' {
  if (!type) return 'general';

  const supportTypes: NeedType[] = ['urgent_support', 'frustrated_signal', 'escalation', 'draft_response_ready'];
  const onboardingTypes: NeedType[] = ['onboarding_behind', 'stalled_milestone', 'new_handoff', 'plan_approval_required'];
  const renewalTypes: NeedType[] = ['approaching_renewal', 'renewal_at_risk', 'meeting_prep_ready', 'champion_departed'];

  if (supportTypes.includes(type)) return 'support';
  if (onboardingTypes.includes(type)) return 'onboarding';
  if (renewalTypes.includes(type)) return 'renewal';
  return 'general';
}

function getLifecycleLabel(lifecycle: CustomerLifecycle): string {
  const labels: Record<CustomerLifecycle, string> = {
    prospect: 'Prospect',
    handoff: 'Handoff',
    onboarding: 'Onboarding',
    active: 'Active',
    renewing: 'Renewing',
    at_risk: 'At Risk',
    churned: 'Churned',
  };
  return labels[lifecycle];
}

function formatARR(cents: number | null): string {
  if (!cents) return '';
  const dollars = cents / 100;
  if (dollars >= 1000) {
    return `$${(dollars / 1000).toFixed(0)}K`;
  }
  return `$${dollars.toFixed(0)}`;
}

function getWorkflowStatusConfig(status: WorkflowStatus | null | undefined) {
  const configs: Record<WorkflowStatus, { label: string; color: string; bgColor: string; icon: React.ReactNode }> = {
    needs_response: {
      label: 'Needs Response',
      color: 'text-rust-400',
      bgColor: 'bg-rust-900/30',
      icon: <Pulse active continuous />,
    },
    awaiting_customer: {
      label: 'Awaiting Customer',
      color: 'text-amber-400',
      bgColor: 'bg-amber-900/30',
      icon: <Clock className="w-3 h-3" />,
    },
    blocked: {
      label: 'Blocked',
      color: 'text-orange-400',
      bgColor: 'bg-orange-900/30',
      icon: <AlertTriangle className="w-3 h-3" />,
    },
    snoozed: {
      label: 'Snoozed',
      color: 'text-charcoal-400',
      bgColor: 'bg-charcoal-700',
      icon: <Pause className="w-3 h-3" />,
    },
    resolved: {
      label: 'Resolved',
      color: 'text-emerald-400',
      bgColor: 'bg-emerald-900/30',
      icon: <Check className="w-3 h-3" />,
    },
  };

  // Default to 'needs_response' if status is null/undefined
  return configs[status || 'needs_response'];
}

function formatSnoozeUntil(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffHours < 1) return 'less than an hour';
  if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''}`;
  if (diffDays < 7) return `${diffDays} day${diffDays !== 1 ? 's' : ''}`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Snooze duration options
const SNOOZE_OPTIONS = [
  { label: '1 hour', value: () => new Date(Date.now() + 1 * 60 * 60 * 1000).toISOString() },
  { label: '4 hours', value: () => new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString() },
  { label: 'Tomorrow', value: () => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(9, 0, 0, 0);
    return tomorrow.toISOString();
  }},
  { label: 'Next week', value: () => {
    const nextWeek = new Date();
    nextWeek.setDate(nextWeek.getDate() + 7);
    nextWeek.setHours(9, 0, 0, 0);
    return nextWeek.toISOString();
  }},
];

export function ConversationHeader({ thread, onUpdateStatus, isUpdatingStatus = false }: ConversationHeaderProps) {
  const [showStatusMenu, setShowStatusMenu] = useState(false);
  const [showSnoozeMenu, setShowSnoozeMenu] = useState(false);
  const [showBlockedInput, setShowBlockedInput] = useState(false);
  const [blockedReason, setBlockedReason] = useState('');

  const category = getNeedTypeCategory(thread.need_type);
  const needLabel = getNeedTypeLabel(thread.need_type);
  const statusConfig = getWorkflowStatusConfig(thread.workflow_status);

  const badgeColors = {
    support: 'border-rust-500 text-rust-400',
    onboarding: 'border-amber-500 text-amber-400',
    renewal: 'border-emerald-500 text-emerald-400',
    general: 'border-charcoal-600 text-cream-300',
  };

  const handleResolve = async () => {
    await onUpdateStatus('resolved');
    setShowStatusMenu(false);
  };

  const handleSnooze = async (until: string) => {
    await onUpdateStatus('snoozed', undefined, until);
    setShowSnoozeMenu(false);
    setShowStatusMenu(false);
  };

  const handleMarkBlocked = async () => {
    if (blockedReason.trim()) {
      await onUpdateStatus('blocked', blockedReason);
      setBlockedReason('');
      setShowBlockedInput(false);
      setShowStatusMenu(false);
    }
  };

  const handleReopen = async () => {
    await onUpdateStatus('needs_response');
    setShowStatusMenu(false);
  };

  const handleSetNeedsResponse = async () => {
    await onUpdateStatus('needs_response');
    setShowStatusMenu(false);
  };

  const handleSetAwaitingCustomer = async () => {
    await onUpdateStatus('awaiting_customer');
    setShowStatusMenu(false);
  };

  return (
    <header className="sticky top-0 z-10 bg-charcoal-900 border-b border-charcoal-700 px-6 py-4">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 mb-3 text-sm">
        <Link
          to="/app/conversations"
          className="text-cream-400 hover:text-cream-200 transition-colors flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="font-mono text-xs uppercase tracking-wider">Conversations</span>
        </Link>
        <ChevronRight className="w-4 h-4 text-charcoal-600" />
        <Link
          to={`/app/customers/${thread.customer_id}`}
          className="text-cream-400 hover:text-cream-200 transition-colors font-serif"
        >
          {thread.customer_name}
        </Link>
        <ChevronRight className="w-4 h-4 text-charcoal-600" />
        <RefCode>{thread.id.slice(0, 8).toUpperCase()}</RefCode>
      </div>

      {/* Main Header Row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Customer Name + Badges */}
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="font-serif text-2xl sm:text-3xl text-cream-100 truncate">
              {thread.customer_name}
            </h1>

            <div className="flex items-center gap-2">
              {/* Need Type Badge */}
              <MissionStamp
                type={needLabel}
                className={cn(badgeColors[category])}
              />

              {/* Workflow Status Badge */}
              <div
                className={cn(
                  "flex items-center gap-1.5 px-2 py-1 rounded",
                  statusConfig.bgColor
                )}
              >
                {statusConfig.icon}
                <span className={cn("font-mono text-[10px] uppercase tracking-wider", statusConfig.color)}>
                  {statusConfig.label}
                </span>
              </div>
            </div>
          </div>

          {/* Subject Line */}
          {thread.subject && (
            <p className="text-fg-200 mt-1 text-sm truncate">
              {thread.subject}
            </p>
          )}

          {/* Blocked Reason or Snoozed Until */}
          {thread.workflow_status === 'blocked' && thread.blocked_reason && (
            <p className="text-xs text-orange-400 mt-1 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              Blocked: {thread.blocked_reason}
            </p>
          )}
          {thread.workflow_status === 'snoozed' && thread.snoozed_until && (
            <p className="text-xs text-charcoal-400 mt-1 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              Snoozed for {formatSnoozeUntil(thread.snoozed_until)}
            </p>
          )}

          {/* Meta Info */}
          <div className="flex items-center gap-4 mt-2 text-xs font-mono text-charcoal-400">
            <span className={cn(
              "px-1.5 py-0.5 rounded",
              thread.customer.lifecycle === 'at_risk' && "bg-rust-900/30 text-rust-400",
              thread.customer.lifecycle === 'onboarding' && "bg-amber-900/30 text-amber-400",
              thread.customer.lifecycle === 'active' && "bg-emerald-900/30 text-emerald-400",
              !['at_risk', 'onboarding', 'active'].includes(thread.customer.lifecycle) && "bg-charcoal-800 text-cream-400"
            )}>
              {getLifecycleLabel(thread.customer.lifecycle)}
            </span>
            {thread.customer.arr_cents && (
              <span className="text-cream-300">
                {formatARR(thread.customer.arr_cents)} ARR
              </span>
            )}
            <span className="text-charcoal-500">•</span>
            <span>
              {thread.stats.message_count} messages ({thread.stats.our_message_count} us, {thread.stats.their_message_count} them)
            </span>
          </div>
        </div>

        {/* Status Actions */}
        <div className="relative flex-shrink-0">
          <button
            onClick={() => setShowStatusMenu(!showStatusMenu)}
            disabled={isUpdatingStatus}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded border transition-colors",
              "border-charcoal-600 hover:border-charcoal-500 bg-charcoal-800 hover:bg-charcoal-700",
              "text-sm text-cream-300",
              isUpdatingStatus && "opacity-50 cursor-not-allowed"
            )}
          >
            {isUpdatingStatus ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <span>Actions</span>
                <ChevronDown className="w-4 h-4" />
              </>
            )}
          </button>

          {/* Status Menu Dropdown */}
          <AnimatePresence>
            {showStatusMenu && (
              <>
                {/* Backdrop */}
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => {
                    setShowStatusMenu(false);
                    setShowSnoozeMenu(false);
                    setShowBlockedInput(false);
                  }}
                />

                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="absolute right-0 top-full mt-2 w-56 bg-charcoal-800 border border-charcoal-700 rounded-lg shadow-xl z-20 overflow-hidden"
                >
                  {/* Blocked Input */}
                  {showBlockedInput ? (
                    <div className="p-3">
                      <label className="text-xs text-charcoal-400 font-mono uppercase tracking-wider mb-2 block">
                        What's blocking this?
                      </label>
                      <input
                        type="text"
                        value={blockedReason}
                        onChange={(e) => setBlockedReason(e.target.value)}
                        placeholder="e.g., Waiting on engineering"
                        className="w-full bg-charcoal-900 border border-charcoal-700 rounded px-3 py-2 text-sm text-cream-200 placeholder:text-charcoal-500 focus:outline-none focus:border-rust-500/50"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleMarkBlocked();
                          if (e.key === 'Escape') setShowBlockedInput(false);
                        }}
                      />
                      <div className="flex items-center gap-2 mt-2">
                        <button
                          onClick={handleMarkBlocked}
                          disabled={!blockedReason.trim()}
                          className="flex-1 px-3 py-1.5 bg-orange-600 hover:bg-orange-500 text-white text-xs font-medium rounded transition-colors disabled:opacity-50"
                        >
                          Mark Blocked
                        </button>
                        <button
                          onClick={() => setShowBlockedInput(false)}
                          className="px-3 py-1.5 text-charcoal-400 hover:text-cream-300 text-xs transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : showSnoozeMenu ? (
                    <div className="py-1">
                      <div className="px-3 py-2 text-xs text-charcoal-400 font-mono uppercase tracking-wider border-b border-charcoal-700">
                        Snooze until
                      </div>
                      {SNOOZE_OPTIONS.map((option) => (
                        <button
                          key={option.label}
                          onClick={() => handleSnooze(option.value())}
                          className="w-full text-left px-4 py-2 text-sm text-cream-300 hover:bg-charcoal-700 transition-colors"
                        >
                          {option.label}
                        </button>
                      ))}
                      <button
                        onClick={() => setShowSnoozeMenu(false)}
                        className="w-full text-left px-4 py-2 text-sm text-charcoal-400 hover:text-cream-300 hover:bg-charcoal-700 transition-colors border-t border-charcoal-700"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <div className="py-1">
                      {thread.workflow_status !== 'resolved' ? (
                        <>
                          <button
                            onClick={handleResolve}
                            className="w-full text-left px-4 py-2 text-sm text-cream-300 hover:bg-charcoal-700 transition-colors flex items-center gap-2"
                          >
                            <Check className="w-4 h-4 text-emerald-400" />
                            <span>Mark Resolved</span>
                          </button>
                          <button
                            onClick={() => setShowSnoozeMenu(true)}
                            className="w-full text-left px-4 py-2 text-sm text-cream-300 hover:bg-charcoal-700 transition-colors flex items-center gap-2"
                          >
                            <Pause className="w-4 h-4 text-charcoal-400" />
                            <span>Snooze</span>
                            <ChevronRight className="w-4 h-4 ml-auto text-charcoal-500" />
                          </button>
                          <button
                            onClick={() => setShowBlockedInput(true)}
                            className="w-full text-left px-4 py-2 text-sm text-cream-300 hover:bg-charcoal-700 transition-colors flex items-center gap-2"
                          >
                            <AlertTriangle className="w-4 h-4 text-orange-400" />
                            <span>Mark Blocked</span>
                          </button>

                          {/* Manual Status Override Section */}
                          <div className="border-t border-charcoal-700 mt-1 pt-1">
                            <div className="px-4 py-1.5 text-[10px] font-mono text-charcoal-500 uppercase tracking-wider">
                              Change Status
                            </div>
                            {thread.workflow_status !== 'needs_response' && (
                              <button
                                onClick={handleSetNeedsResponse}
                                className="w-full text-left px-4 py-2 text-sm text-cream-300 hover:bg-charcoal-700 transition-colors flex items-center gap-2"
                              >
                                <Pulse active continuous className="scale-75" />
                                <span>Needs Response</span>
                              </button>
                            )}
                            {thread.workflow_status !== 'awaiting_customer' && (
                              <button
                                onClick={handleSetAwaitingCustomer}
                                className="w-full text-left px-4 py-2 text-sm text-cream-300 hover:bg-charcoal-700 transition-colors flex items-center gap-2"
                              >
                                <Clock className="w-4 h-4 text-amber-400" />
                                <span>Awaiting Customer</span>
                              </button>
                            )}
                          </div>
                        </>
                      ) : (
                        <button
                          onClick={handleReopen}
                          className="w-full text-left px-4 py-2 text-sm text-cream-300 hover:bg-charcoal-700 transition-colors flex items-center gap-2"
                        >
                          <RotateCcw className="w-4 h-4 text-rust-400" />
                          <span>Reopen</span>
                        </button>
                      )}
                    </div>
                  )}
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>
      </div>
    </header>
  );
}

export { getNeedTypeCategory };
