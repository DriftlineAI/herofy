import { useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  ChevronDown,
  ChevronUp,
  Check,
  Clock,
  Mail,
  MessageSquare,
  Zap,
  HelpCircle,
  FileText,
  AlertCircle,
} from 'lucide-react';
import { RefCode, Timestamp, Pulse } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import type { ConversationNeed } from '@/lib/dataconnect-hooks';
import type { NeedType } from '@/lib/api';

export interface ConversationsNeedCardProps {
  need: ConversationNeed;
  onResolve?: () => void;
  onSnooze?: () => void;
  key?: string;
}

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

function ChannelIcon({ channel }: { channel: string }) {
  switch (channel) {
    case 'slack':
      return <MessageSquare className="w-3 h-3" />;
    case 'email':
    default:
      return <Mail className="w-3 h-3" />;
  }
}

// Format ARR for display
function formatARR(cents: number | null): string {
  if (!cents) return '';
  const amount = cents / 100;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return `$${amount}`;
}

// Sidekick variant for sidekick_question type needs
function SidekickNeedCardVariant({ need, onSnooze }: { need: ConversationNeed; onSnooze?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const questionCount = need.agent_questions?.length || 0;

  return (
    <div className="hud-pane hud-pane--asks group">
      {/* Header Strip */}
      <div className="hud-pane__header hud-pane__header--asks">
        <Zap className="w-3.5 h-3.5 fill-current" />
        <span className="hud-pane__label">SIDEKICK NEEDS HELP</span>
        <span className="grow" />
        <span className="hud-pane__ref">{need.id.slice(0, 7).toUpperCase()} · {questionCount} QUESTION{questionCount !== 1 ? 'S' : ''}</span>
      </div>

      {/* Body */}
      <div className="hud-pane__body">
        {/* Customer + headline */}
        <Link to={`/app/needs/${need.id}`} className="block hover:opacity-80 transition-opacity mb-4">
          <div className="hud-pane__title-row mb-1">
            <h3 className="hud-pane__customer">{need.customer_name}</h3>
            {need.customer_arr_cents && (
              <span className="hud-pane__arr">{formatARR(need.customer_arr_cents)} ARR</span>
            )}
          </div>
          <p className="text-fg-200 leading-relaxed">{need.headline}</p>
        </Link>

        {/* Context Box */}
        {need.agent_reasoning && (
          <div className="border-l-2 border-accent pl-4 py-2 mb-4 bg-accent-bg/30">
            <div className="text-[10px] font-mono uppercase tracking-widest text-accent mb-1 flex items-center gap-1">
              <AlertCircle className="w-2.5 h-2.5" />
              <span>Why I'm asking</span>
            </div>
            <p className="text-fg-300 text-sm leading-relaxed">
              {need.agent_reasoning}
            </p>
          </div>
        )}

        {/* Questions Preview */}
        <div className="space-y-3 mb-4">
          {need.agent_questions?.slice(0, expanded ? undefined : 1).map((q, index) => (
            <div
              key={q.id}
              className="flex items-start gap-3 bg-surface-2 border border-border p-3"
            >
              <div className="flex items-center justify-center w-5 h-5 bg-accent/20 text-accent text-xs font-bold shrink-0 mt-0.5">
                {index + 1}
              </div>
              <div className="flex-1">
                <p className="text-fg-200 text-sm leading-relaxed">{q.text}</p>
                {q.context && (
                  <p className="text-fg-400 text-xs mt-1 italic">{q.context}</p>
                )}
              </div>
            </div>
          ))}

          {questionCount > 1 && !expanded && (
            <div className="text-xs text-fg-400 pl-8">+{questionCount - 1} more questions</div>
          )}
        </div>

        {/* Expand/Collapse */}
        {questionCount > 1 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-2 text-xs font-mono text-fg-400 hover:text-fg-100 transition-colors mb-4"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            <span className="uppercase tracking-widest">
              {expanded ? 'Show less' : `Show all ${questionCount} questions`}
            </span>
          </button>
        )}
      </div>

      {/* CTA */}
      <NavLink
        to={`/app/needs/${need.id}`}
        className="hud-pane__cta"
      >
        <span>Answer questions →</span>
        <span className="hud-pane__cta-badge">{questionCount} OPEN</span>
      </NavLink>
    </div>
  );
}

// Regular NeedCard for non-sidekick needs
function RegularNeedCard({ need, onResolve, onSnooze, urgent }: {
  need: ConversationNeed;
  onResolve?: () => void;
  onSnooze?: () => void;
  urgent?: boolean;
}) {
  const [threadsExpanded, setThreadsExpanded] = useState(true); // Default expanded for conversations
  const threadCount = need.threads.length;
  const needLabel = needTypeLabels[need.type as NeedType] || 'ATTENTION';
  const isPlanApproval = need.type === 'plan_approval_required';

  // Find the most recent thread
  const latestThread = need.threads[0];
  const snippet = latestThread?.latest_interaction?.summary_ai || need.lede || '';

  return (
    <div className="hud-pane group">
      {/* Header Strip */}
      <div className="hud-pane__header">
        {urgent && <span className="hud-pane__pulse" />}
        <span className="hud-pane__label">
          {need.id.slice(0, 7).toUpperCase()} · {needLabel}
          {threadCount > 0 && <span className="text-fg-400 ml-2">· {threadCount} THREAD{threadCount !== 1 ? 'S' : ''}</span>}
        </span>
        <span className="grow" />
        <span className="hud-pane__ref">{formatTime(need.updated_at)}</span>

        {/* Quick actions */}
        <div className="flex items-center gap-1 ml-3 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={onSnooze}
            className="p-1 text-fg-400 hover:text-fg-100 transition-colors"
            title="Snooze for 24h"
          >
            <Clock className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onResolve}
            className="p-1 text-fg-400 hover:text-signal-ok transition-colors"
            title="Mark resolved"
          >
            <Check className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="hud-pane__body">
        {/* Header with customer name and plan approval button */}
        <div className="flex items-start justify-between gap-4 mb-3">
          <Link
            to={`/app/needs/${need.id}`}
            className="hover:opacity-80 transition-opacity"
          >
            <div className="hud-pane__title-row mb-1">
              <h3 className="hud-pane__customer">{need.customer_name}</h3>
              {need.customer_arr_cents && (
                <span className="hud-pane__arr">{formatARR(need.customer_arr_cents)} ARR</span>
              )}
            </div>
          </Link>

          {isPlanApproval && (
            <NavLink
              to={`/app/needs/${need.id}`}
              className="text-[10px] font-mono uppercase tracking-widest bg-accent text-page px-3 py-1.5 hover:bg-accent-hover transition-colors font-bold shrink-0"
            >
              <FileText className="w-3 h-3 inline mr-1.5" />
              Review Plan
            </NavLink>
          )}
        </div>

        {/* Need headline clickable */}
        <Link
          to={`/app/needs/${need.id}`}
          className="block hover:opacity-80 transition-opacity"
        >
          <p className="text-fg-200 leading-relaxed mb-2">{need.headline}</p>

          {snippet && (
            <p className="text-sm text-fg-400 italic line-clamp-2">"{snippet}"</p>
          )}
        </Link>

        {/* Threads section (collapsible) */}
        {threadCount > 0 && (
          <div className="border-t border-rule mt-4 pt-3">
            <button
              onClick={() => setThreadsExpanded(!threadsExpanded)}
              className="flex items-center gap-2 text-[11px] font-mono text-fg-400 hover:text-fg-100 transition-colors w-full uppercase tracking-widest"
            >
              {threadsExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              <span>
                {threadsExpanded ? 'Hide threads' : `View ${threadCount} thread${threadCount !== 1 ? 's' : ''}`}
              </span>
            </button>

            <AnimatePresence>
              {threadsExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="mt-3 space-y-2">
                    {need.threads.map(thread => (
                      <Link
                        key={thread.id}
                        to={`/app/conversations/${thread.id}`}
                        className="flex items-center gap-3 p-3 bg-surface-2 hover:bg-border/50 transition-colors text-sm border border-transparent hover:border-border"
                      >
                        <ChannelIcon channel={thread.channel} />
                        <span className="text-fg-200 flex-1 truncate">
                          {thread.subject || 'No subject'}
                        </span>
                        <span className={cn(
                          'text-[9px] font-mono uppercase px-1.5 py-0.5',
                          thread.status === 'resolved'
                            ? 'bg-signal-ok/20 text-signal-ok'
                            : 'bg-surface-2 text-fg-400 border border-border'
                        )}>
                          {thread.status}
                        </span>
                        <span className="text-[10px] font-mono text-fg-400">{formatTime(thread.updated_at)}</span>
                      </Link>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}

export function ConversationsNeedCard({ need, onResolve, onSnooze }: ConversationsNeedCardProps) {
  // Special rendering for sidekick_question type
  if (need.type === 'sidekick_question') {
    return <SidekickNeedCardVariant need={need} onSnooze={onSnooze} />;
  }

  // Check if this is an urgent need type
  const isUrgent = ['urgent_support', 'escalation', 'frustrated_signal'].includes(need.type);

  return (
    <RegularNeedCard
      need={need}
      onResolve={onResolve}
      onSnooze={onSnooze}
      urgent={isUrgent}
    />
  );
}

export default ConversationsNeedCard;
