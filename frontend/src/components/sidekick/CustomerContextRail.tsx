import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, ExternalLink, MessageSquare, Check, Clock, AlertCircle, Zap, Building, DollarSign, Calendar } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import type { Customer, Need } from '@/lib/api';

/**
 * CustomerContextRail - Right Rail Component
 *
 * Slides in from the right when a need is selected in Today Queue.
 * Shows customer context + clusters ALL AI items for that customer.
 *
 * Features:
 * - Customer profile summary (tier, ARR, lifecycle, progress)
 * - All Sidekick questions for that customer (answered + unanswered)
 * - Related agent runs (plan approval, drafts, etc.)
 * - Quick actions (View Customer, Open in Sidekick, Chat)
 *
 * Per SIDEKICK_UX_FINAL.md Section 3: "Right Rail: Customer Context + Clustered AI Items"
 */

interface AIItem {
  id: string;
  type: 'sidekick_question' | 'plan_approval' | 'draft_ready' | 'agent_run';
  title: string;
  status: 'pending' | 'answered' | 'completed';
  timestamp: Date;
  is_current?: boolean;
}

interface CustomerContextRailProps {
  customer: Customer;
  aiItems: AIItem[];
  relatedNeeds: Need[];
  isOpen: boolean;
  onClose: () => void;
  onOpenSidekick?: () => void;
  onStartChat?: () => void;
}

function formatARR(cents: number | null): string {
  if (!cents) return '$0';
  const amount = cents / 100;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return `$${amount}`;
}

function timeAgo(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  return `${days}d ago`;
}

function LifecycleBar({ lifecycle, progress }: { lifecycle: string; progress?: number }) {
  const colors = {
    prospect: 'bg-charcoal-600',
    onboarding: 'bg-blue-500',
    active: 'bg-emerald-500',
    renewing: 'bg-amber-500',
    'at-risk': 'bg-red-500',
    churned: 'bg-charcoal-700',
  };

  const color = colors[lifecycle as keyof typeof colors] || 'bg-charcoal-600';

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-charcoal-400 uppercase tracking-widest font-mono">
          {lifecycle.replace('-', ' ')}
        </span>
        {progress !== undefined && (
          <span className="text-cream-300 font-mono font-bold">
            {progress}%
          </span>
        )}
      </div>
      {progress !== undefined && (
        <div className="h-1 bg-charcoal-800 rounded-full overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 1, ease: 'easeOut' }}
            className={cn('h-full', color)}
          />
        </div>
      )}
    </div>
  );
}

function AIItemCard({ item, onAction }: { item: AIItem; onAction?: () => void }) {
  const icons = {
    sidekick_question: <Zap className="w-3 h-3 fill-rust-500" />,
    plan_approval: <Check className="w-3 h-3" />,
    draft_ready: <MessageSquare className="w-3 h-3" />,
    agent_run: <Clock className="w-3 h-3" />,
  };

  const statusColors = {
    pending: 'border-rust-500/50 bg-rust-900/10',
    answered: 'border-emerald-500/30 bg-emerald-900/5',
    completed: 'border-charcoal-700 bg-charcoal-800/30',
  };

  const statusIcons = {
    pending: <AlertCircle className="w-3 h-3 text-rust-500" />,
    answered: <Check className="w-3 h-3 text-emerald-500" />,
    completed: <Check className="w-3 h-3 text-charcoal-500" />,
  };

  return (
    <div className={cn(
      'border-l-2 pl-3 py-2 transition-colors',
      statusColors[item.status],
      item.is_current && 'border-rust-500 bg-rust-900/20'
    )}>
      <div className="flex items-start gap-2">
        <div className={cn(
          'mt-0.5 p-1 rounded',
          item.status === 'pending' ? 'bg-rust-500/20' : 'bg-charcoal-700'
        )}>
          {icons[item.type]}
        </div>
        <div className="flex-1 min-w-0">
          <p className={cn(
            'text-sm leading-relaxed',
            item.status === 'completed' ? 'text-charcoal-400' : 'text-cream-200'
          )}>
            {item.title}
          </p>
          <div className="flex items-center gap-2 mt-1">
            <div className="flex items-center gap-1">
              {statusIcons[item.status]}
              <span className="text-xs text-charcoal-500 font-mono">
                {item.status === 'pending' ? 'Needs answer' : timeAgo(item.timestamp)}
              </span>
            </div>
            {item.is_current && (
              <span className="text-xs text-rust-400 font-mono font-bold">
                ← You are here
              </span>
            )}
          </div>
        </div>
      </div>
      {item.status === 'pending' && onAction && (
        <button
          onClick={onAction}
          className="mt-2 text-xs font-mono uppercase tracking-widest text-rust-400 hover:text-rust-300 transition-colors"
        >
          Answer Now →
        </button>
      )}
    </div>
  );
}

export function CustomerContextRail({
  customer,
  aiItems,
  relatedNeeds,
  isOpen,
  onClose,
  onOpenSidekick,
  onStartChat,
}: CustomerContextRailProps) {
  const pendingItems = aiItems.filter(item => item.status === 'pending');
  const completedItems = aiItems.filter(item => item.status !== 'pending');

  // Calculate onboarding progress if applicable
  const onboardingProgress = customer.lifecycle === 'onboarding' ? 35 : undefined;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ x: '100%', opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: '100%', opacity: 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          className="fixed right-0 top-0 bottom-0 w-full sm:w-[400px] bg-charcoal-900 border-l-2 border-charcoal-700 shadow-2xl z-40 flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="bg-gradient-to-r from-charcoal-800 to-charcoal-900 border-b border-charcoal-700 p-4 flex items-center justify-between">
            <h2 className="text-cream-100 font-mono text-sm uppercase tracking-widest font-bold">
              Customer Context
            </h2>
            <button
              onClick={onClose}
              className="text-charcoal-400 hover:text-cream-200 transition-colors p-1"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto">
            {/* Customer Profile Summary */}
            <div className="p-6 border-b border-charcoal-700/50">
              <h3 className="font-serif text-2xl text-cream-100 mb-4">
                {customer.name}
              </h3>

              <div className="space-y-4">
                {/* Key Stats */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-charcoal-500 uppercase tracking-widest font-mono mb-1">
                      Tier
                    </div>
                    <div className="text-cream-200 font-medium">
                      {customer.tier || 'Standard'}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-charcoal-500 uppercase tracking-widest font-mono mb-1">
                      ARR
                    </div>
                    <div className="text-cream-200 font-medium">
                      {formatARR(customer.arr_cents)}
                    </div>
                  </div>
                </div>

                {/* Lifecycle Progress */}
                <LifecycleBar lifecycle={customer.lifecycle} progress={onboardingProgress} />

                {/* One-liner */}
                {customer.one_liner && (
                  <p className="text-sm text-cream-300 italic border-l-2 border-charcoal-700 pl-3">
                    "{customer.one_liner}"
                  </p>
                )}
              </div>
            </div>

            {/* All Sidekick Items (Clustered) */}
            {aiItems.length > 0 && (
              <div className="p-6 border-b border-charcoal-700/50">
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-xs text-charcoal-400 uppercase tracking-widest font-mono font-bold">
                    All Sidekick Items
                  </h4>
                  {pendingItems.length > 0 && (
                    <span className="bg-rust-500/20 text-rust-400 px-2 py-0.5 text-xs font-mono font-bold rounded">
                      {pendingItems.length} pending
                    </span>
                  )}
                </div>

                <div className="space-y-3">
                  {pendingItems.map(item => (
                    <AIItemCard
                      key={item.id}
                      item={item}
                      onAction={onOpenSidekick}
                    />
                  ))}

                  {completedItems.length > 0 && (
                    <>
                      <div className="text-xs text-charcoal-600 uppercase tracking-widest font-mono mt-6 mb-3">
                        History
                      </div>
                      {completedItems.slice(0, 3).map(item => (
                        <AIItemCard key={item.id} item={item} />
                      ))}
                      {completedItems.length > 3 && (
                        <p className="text-xs text-charcoal-600 italic pl-9">
                          +{completedItems.length - 3} more completed
                        </p>
                      )}
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Related Customer Needs */}
            {relatedNeeds.length > 0 && (
              <div className="p-6 border-b border-charcoal-700/50">
                <h4 className="text-xs text-charcoal-400 uppercase tracking-widest font-mono font-bold mb-4">
                  Customer Needs
                </h4>
                <div className="space-y-2">
                  {relatedNeeds.slice(0, 3).map(need => (
                    <NavLink
                      key={need.id}
                      to={`/app/needs/${need.id}`}
                      className="block p-3 bg-charcoal-800/50 border border-charcoal-700 hover:border-rust-500/50 transition-colors"
                    >
                      <div className="flex items-center gap-2 text-sm text-cream-200">
                        <AlertCircle className="w-3 h-3 text-rust-500 shrink-0" />
                        <span className="line-clamp-1">{need.headline}</span>
                      </div>
                    </NavLink>
                  ))}
                </div>
              </div>
            )}

            {/* Quick Actions */}
            <div className="p-6">
              <h4 className="text-xs text-charcoal-400 uppercase tracking-widest font-mono font-bold mb-4">
                Quick Actions
              </h4>
              <div className="space-y-2">
                <NavLink
                  to={`/app/customers/${customer.id}`}
                  className="flex items-center gap-3 p-3 bg-charcoal-800 hover:bg-charcoal-700 border border-charcoal-700 hover:border-rust-500/50 transition-all group"
                >
                  <Building className="w-4 h-4 text-charcoal-400 group-hover:text-rust-400" />
                  <span className="text-sm text-cream-200 group-hover:text-cream-100">
                    View Customer Profile
                  </span>
                  <ExternalLink className="w-3 h-3 text-charcoal-600 ml-auto" />
                </NavLink>

                {pendingItems.length > 0 && onOpenSidekick && (
                  <button
                    onClick={onOpenSidekick}
                    className="w-full flex items-center gap-3 p-3 bg-rust-500/10 hover:bg-rust-500/20 border border-rust-500/30 hover:border-rust-500/50 transition-all group"
                  >
                    <Zap className="w-4 h-4 text-rust-400 fill-rust-400" />
                    <span className="text-sm text-rust-300 group-hover:text-rust-200">
                      Open in Sidekick
                    </span>
                  </button>
                )}

                {onStartChat && (
                  <button
                    onClick={onStartChat}
                    className="w-full flex items-center gap-3 p-3 bg-charcoal-800 hover:bg-charcoal-700 border border-charcoal-700 hover:border-rust-500/50 transition-all group"
                  >
                    <MessageSquare className="w-4 h-4 text-charcoal-400 group-hover:text-rust-400" />
                    <span className="text-sm text-cream-200 group-hover:text-cream-100">
                      Chat about {customer.name}
                    </span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default CustomerContextRail;
