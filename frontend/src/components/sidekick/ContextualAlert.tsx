import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, Zap, AlertCircle, CheckCircle, Info, ChevronRight } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

/**
 * ContextualAlert - AI Native Alert Banners
 *
 * Non-intrusive alert banners that appear on relevant pages to surface AI items.
 * Shows on customer detail pages when there are pending sidekick questions,
 * plan approvals, or other AI items requiring attention.
 *
 * Features:
 * - Non-intrusive banner design
 * - Context-relevant messaging
 * - Action-oriented buttons
 * - Dismissible
 * - Shows item counts
 *
 * Per SIDEKICK_UX_FINAL.md Section 5: "Contextual Awareness (Customer Detail Page)"
 */

export type AlertSeverity = 'info' | 'warning' | 'success' | 'error';

export interface ContextualAlertItem {
  id: string;
  text: string;
  blocksProgress?: boolean;
}

interface ContextualAlertProps {
  severity?: AlertSeverity;
  title: string;
  items?: ContextualAlertItem[];
  customerName?: string;
  actionLabel?: string;
  actionLink?: string;
  onAction?: () => void;
  dismissible?: boolean;
  onDismiss?: () => void;
  className?: string;
}

const severityConfig = {
  info: {
    icon: Info,
    iconBg: 'bg-blue-500/20',
    iconColor: 'text-blue-400',
    borderColor: 'border-blue-500/30',
    bgColor: 'bg-blue-900/10',
    textColor: 'text-blue-300',
  },
  warning: {
    icon: AlertCircle,
    iconBg: 'bg-rust-500/20',
    iconColor: 'text-rust-400',
    borderColor: 'border-rust-500/30',
    bgColor: 'bg-rust-900/10',
    textColor: 'text-rust-300',
  },
  success: {
    icon: CheckCircle,
    iconBg: 'bg-emerald-500/20',
    iconColor: 'text-emerald-400',
    borderColor: 'border-emerald-500/30',
    bgColor: 'bg-emerald-900/10',
    textColor: 'text-emerald-300',
  },
  error: {
    icon: AlertCircle,
    iconBg: 'bg-red-500/20',
    iconColor: 'text-red-400',
    borderColor: 'border-red-500/30',
    bgColor: 'bg-red-900/10',
    textColor: 'text-red-300',
  },
};

export function ContextualAlert({
  severity = 'info',
  title,
  items = [],
  customerName,
  actionLabel = 'View Details',
  actionLink,
  onAction,
  dismissible = true,
  onDismiss,
  className,
}: ContextualAlertProps) {
  const [isDismissed, setIsDismissed] = useState(false);

  const config = severityConfig[severity];
  const Icon = config.icon;

  const handleDismiss = () => {
    setIsDismissed(true);
    onDismiss?.();
  };

  if (isDismissed) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn(
        'border-l-4 p-4 flex items-start gap-4',
        config.borderColor,
        config.bgColor,
        className
      )}
    >
      {/* Icon */}
      <div className={cn('p-2 rounded shrink-0', config.iconBg)}>
        <Icon className={cn('w-5 h-5', config.iconColor)} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Title */}
        <h3 className={cn('text-sm font-medium mb-1', config.textColor)}>
          {title}
        </h3>

        {/* Items List */}
        {items.length > 0 && (
          <ul className="space-y-1 mb-3">
            {items.map(item => (
              <li key={item.id} className="flex items-start gap-2 text-sm text-cream-300">
                <span className={cn(
                  'shrink-0 mt-1.5',
                  item.blocksProgress ? 'text-rust-500' : 'text-charcoal-500'
                )}>
                  •
                </span>
                <span className="leading-relaxed">
                  {item.text}
                  {item.blocksProgress && (
                    <span className="ml-2 text-xs text-rust-400 font-mono uppercase tracking-widest">
                      (blocks progress)
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}

        {/* Action Button */}
        {(actionLink || onAction) && (
          <div className="mt-3">
            {actionLink ? (
              <NavLink
                to={actionLink}
                className={cn(
                  'inline-flex items-center gap-2 px-4 py-2 rounded',
                  'font-mono text-xs uppercase tracking-widest font-bold',
                  'transition-colors',
                  severity === 'warning'
                    ? 'bg-rust-500 hover:bg-rust-400 text-charcoal-900'
                    : 'bg-charcoal-800 hover:bg-charcoal-700 text-cream-200 border border-charcoal-700'
                )}
              >
                <span>{actionLabel}</span>
                <ChevronRight className="w-3 h-3" />
              </NavLink>
            ) : (
              <button
                onClick={onAction}
                className={cn(
                  'inline-flex items-center gap-2 px-4 py-2 rounded',
                  'font-mono text-xs uppercase tracking-widest font-bold',
                  'transition-colors',
                  severity === 'warning'
                    ? 'bg-rust-500 hover:bg-rust-400 text-charcoal-900'
                    : 'bg-charcoal-800 hover:bg-charcoal-700 text-cream-200 border border-charcoal-700'
                )}
              >
                <span>{actionLabel}</span>
                <ChevronRight className="w-3 h-3" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* Dismiss Button */}
      {dismissible && (
        <button
          onClick={handleDismiss}
          className="text-charcoal-500 hover:text-cream-200 transition-colors shrink-0"
          aria-label="Dismiss alert"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </motion.div>
  );
}

/**
 * SidekickQuestionsAlert - Specialized alert for Sidekick questions
 */
interface SidekickQuestionsAlertProps {
  customerName: string;
  questionCount: number;
  questions: Array<{
    id: string;
    text: string;
    blocksProgress?: boolean;
  }>;
  onAnswerClick?: () => void;
  onDismiss?: () => void;
}

export function SidekickQuestionsAlert({
  customerName,
  questionCount,
  questions,
  onAnswerClick,
  onDismiss,
}: SidekickQuestionsAlertProps) {
  return (
    <ContextualAlert
      severity="warning"
      title={`🤖 Sidekick has ${questionCount} question${questionCount > 1 ? 's' : ''} about ${customerName}`}
      items={questions}
      actionLabel="Answer in Sidekick →"
      actionLink="/app/sidekick"
      onAction={onAnswerClick}
      dismissible
      onDismiss={onDismiss}
    />
  );
}

/**
 * UnverifiedContactsAlert - Alert for unverified stakeholders
 */
interface UnverifiedContactsAlertProps {
  count: number;
  onReviewClick?: () => void;
  onDismiss?: () => void;
}

export function UnverifiedContactsAlert({
  count,
  onReviewClick,
  onDismiss,
}: UnverifiedContactsAlertProps) {
  return (
    <ContextualAlert
      severity="info"
      title={`⚠️ ${count} Unverified Contact${count > 1 ? 's' : ''}`}
      items={[
        {
          id: '1',
          text: 'Sidekick auto-created these contacts from emails. Please verify roles and mark champions.',
        },
      ]}
      actionLabel="Review in Sidekick →"
      onAction={onReviewClick}
      dismissible
      onDismiss={onDismiss}
    />
  );
}

/**
 * PlanApprovalAlert - Alert for pending plan approval
 */
interface PlanApprovalAlertProps {
  customerName: string;
  planId: string;
  onReviewClick?: () => void;
  onDismiss?: () => void;
}

export function PlanApprovalAlert({
  customerName,
  planId,
  onReviewClick,
  onDismiss,
}: PlanApprovalAlertProps) {
  return (
    <ContextualAlert
      severity="warning"
      title={`Onboarding plan for ${customerName} is ready for review`}
      items={[
        {
          id: '1',
          text: 'Sidekick has generated an onboarding plan based on the handoff notes. Please review and approve.',
          blocksProgress: true,
        },
      ]}
      actionLabel="Review Plan →"
      actionLink={`/app/plans/${planId}`}
      onAction={onReviewClick}
      dismissible
      onDismiss={onDismiss}
    />
  );
}

/**
 * DraftReadyAlert - Alert for AI-generated draft responses
 */
interface DraftReadyAlertProps {
  customerName: string;
  threadId: string;
  subject: string;
  onReviewClick?: () => void;
  onDismiss?: () => void;
}

export function DraftReadyAlert({
  customerName,
  threadId,
  subject,
  onReviewClick,
  onDismiss,
}: DraftReadyAlertProps) {
  return (
    <ContextualAlert
      severity="success"
      title={`Draft response ready for ${customerName}`}
      items={[
        {
          id: '1',
          text: `Re: "${subject}" - Sidekick has drafted a response for your review.`,
        },
      ]}
      actionLabel="Review Draft →"
      actionLink={`/app/conversations/${threadId}`}
      onAction={onReviewClick}
      dismissible
      onDismiss={onDismiss}
    />
  );
}

export default ContextualAlert;
