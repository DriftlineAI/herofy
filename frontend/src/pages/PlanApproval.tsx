import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, NavLink } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { RefCode, Timestamp, Pulse, Sidekick } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { usePlan, useApprovePlan, useRejectPlan, useRegeneratePlan, useUpdatePlan, useUpdateHandoff, useCustomerHandoffWithPlan } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import type { AIPlan, HandoffBrief, Customer, PlanMilestone, SalesCommitment, TechnicalContext } from '@/lib/api';
import {
  ChevronRight,
  Check,
  X,
  RefreshCw,
  Edit3,
  Plus,
  Trash2,
  GripVertical,
  AlertTriangle,
  Sparkles,
  Clock,
  User,
  Building
} from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

interface EditableMilestone extends PlanMilestone {
  id: string; // Temporary ID for UI
}

// ============================================================================
// Loading State
// ============================================================================

function LoadingSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-pulse">
      <div className="hud-border p-8">
        <div className="h-6 w-32 bg-charcoal-700 rounded mb-8" />
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 bg-charcoal-800 rounded" />
          ))}
        </div>
      </div>
      <div className="hud-border p-8">
        <div className="h-6 w-32 bg-charcoal-700 rounded mb-8" />
        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-16 bg-charcoal-800 rounded" />
          ))}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Handoff Brief Editor (Left Pane)
// ============================================================================

// TODO: Re-add structured fields editor (sales_commitments, technical_context, reality_check)
// For now, we just show the markdown body for simplicity
function HandoffBriefEditor({
  brief,
  onUpdate,
  isUpdating
}: {
  brief: HandoffBrief;
  onUpdate: (data: Partial<HandoffBrief>) => void;
  isUpdating: boolean;
}) {
  const [body, setBody] = useState(brief.body || '');
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setHasChanges(body !== (brief.body || ''));
  }, [body, brief.body]);

  const handleSave = () => {
    onUpdate({ body });
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-4">
          Handoff Brief
        </h3>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Sales handoff details, commitments, technical context..."
          className="w-full h-96 bg-charcoal-900 border border-charcoal-700 p-4 text-cream-200 text-sm leading-relaxed placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none resize-none"
        />
      </div>

      {/* Save Button */}
      {hasChanges && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="sticky bottom-0 bg-gradient-to-t from-charcoal-900 pt-4"
        >
          <button
            onClick={handleSave}
            disabled={isUpdating}
            className="w-full text-xs font-mono uppercase tracking-widest bg-charcoal-700 text-cream-200 px-4 py-3 hover:bg-charcoal-600 transition-colors disabled:opacity-50"
          >
            {isUpdating ? 'Saving...' : 'Save Handoff Changes'}
          </button>
        </motion.div>
      )}
    </div>
  );
}

// ============================================================================
// Plan Editor (Right Pane)
// ============================================================================

function PlanEditor({
  plan,
  onUpdate,
  isUpdating
}: {
  plan: AIPlan;
  onUpdate: (milestones: PlanMilestone[]) => void;
  isUpdating: boolean;
}) {
  const [milestones, setMilestones] = useState<EditableMilestone[]>(() =>
    (plan.milestones || []).map((m, i) => ({ ...m, id: `milestone-${i}` }))
  );
  const [hasChanges, setHasChanges] = useState(false);

  // Track changes
  useEffect(() => {
    const original = JSON.stringify(plan.milestones || []);
    const current = JSON.stringify(milestones.map(({ id, ...m }) => m));
    setHasChanges(original !== current);
  }, [milestones, plan.milestones]);

  const addMilestone = () => {
    setMilestones([
      ...milestones,
      {
        id: `milestone-${Date.now()}`,
        title: '',
        owner_side: 'us',
        target_days: (milestones.length + 1) * 7,
        description: null,
      },
    ]);
  };

  const updateMilestone = (id: string, field: keyof EditableMilestone, value: any) => {
    setMilestones(
      milestones.map((m) => (m.id === id ? { ...m, [field]: value } : m))
    );
  };

  const removeMilestone = (id: string) => {
    setMilestones(milestones.filter((m) => m.id !== id));
  };

  const handleSave = () => {
    onUpdate(milestones.map(({ id, ...m }) => m));
  };

  return (
    <div className="space-y-6">
      {/* Plan Header */}
      <div className="border-b border-charcoal-700 pb-4">
        {plan.archetype_name && (
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="w-4 h-4 text-rust-500" />
            <span className="text-xs font-mono uppercase tracking-widest text-rust-500">
              {plan.archetype_name}
            </span>
          </div>
        )}
        {plan.headline && (
          <p className="text-cream-300 font-serif italic">{plan.headline}</p>
        )}
        {plan.rationale && (
          <p className="text-sm text-charcoal-400 mt-2">{plan.rationale}</p>
        )}
      </div>

      {/* Duration Info */}
      <div className="flex items-center gap-6 text-sm">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-charcoal-400" />
          <span className="text-cream-300">{plan.duration_label || 'Custom duration'}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-charcoal-400">{milestones.length} milestones</span>
        </div>
        {plan.human_edited && (
          <div className="flex items-center gap-1 text-amber-500">
            <Edit3 className="w-3 h-3" />
            <span className="text-xs">Edited</span>
          </div>
        )}
      </div>

      {/* Milestones */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-mono uppercase tracking-widest text-charcoal-400">
            Milestones
          </h3>
          <button
            onClick={addMilestone}
            className="text-xs font-mono uppercase tracking-widest text-rust-500 hover:text-rust-400 flex items-center gap-1"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>

        <div className="space-y-3">
          {milestones.map((milestone, index) => (
            <div
              key={milestone.id}
              className="group border border-charcoal-700 bg-charcoal-900/50 p-4"
            >
              <div className="flex items-start gap-3">
                <div className="flex items-center gap-2 text-charcoal-500 mt-1">
                  <GripVertical className="w-4 h-4 cursor-grab" />
                  <span className="text-xs font-mono">{index + 1}</span>
                </div>

                <div className="flex-1 space-y-3">
                  <input
                    type="text"
                    value={milestone.title}
                    onChange={(e) => updateMilestone(milestone.id, 'title', e.target.value)}
                    placeholder="Milestone title..."
                    className="w-full bg-transparent border-b border-charcoal-700 pb-1 text-cream-200 font-medium placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                  />

                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-charcoal-400">Owner:</label>
                      <select
                        value={milestone.owner_side}
                        onChange={(e) => updateMilestone(milestone.id, 'owner_side', e.target.value)}
                        className="bg-charcoal-800 border border-charcoal-700 text-cream-200 text-sm px-2 py-1 focus:border-rust-500 focus:outline-none"
                      >
                        <option value="us">Us</option>
                        <option value="customer">Customer</option>
                        <option value="joint">Joint</option>
                      </select>
                    </div>

                    <div className="flex items-center gap-2">
                      <label className="text-xs text-charcoal-400">Day:</label>
                      <input
                        type="number"
                        value={milestone.target_days}
                        onChange={(e) => updateMilestone(milestone.id, 'target_days', parseInt(e.target.value) || 0)}
                        className="w-16 bg-charcoal-800 border border-charcoal-700 text-cream-200 text-sm px-2 py-1 focus:border-rust-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <textarea
                    value={milestone.description || ''}
                    onChange={(e) => updateMilestone(milestone.id, 'description', e.target.value || null)}
                    placeholder="Description (optional)..."
                    className="w-full h-16 bg-charcoal-800 border border-charcoal-700 p-2 text-cream-400 text-sm placeholder:text-charcoal-600 focus:border-rust-500 focus:outline-none resize-none"
                  />
                </div>

                <button
                  onClick={() => removeMilestone(milestone.id)}
                  className="opacity-0 group-hover:opacity-100 text-charcoal-500 hover:text-rust-500 transition-opacity"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Save Button */}
      {hasChanges && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="sticky bottom-0 bg-gradient-to-t from-charcoal-900 pt-4"
        >
          <button
            onClick={handleSave}
            disabled={isUpdating}
            className="w-full text-xs font-mono uppercase tracking-widest bg-charcoal-700 text-cream-200 px-4 py-3 hover:bg-charcoal-600 transition-colors disabled:opacity-50"
          >
            {isUpdating ? 'Saving...' : 'Save Plan Changes'}
          </button>
        </motion.div>
      )}
    </div>
  );
}

// ============================================================================
// Rejection Modal
// ============================================================================

function RejectionModal({
  isOpen,
  onClose,
  onReject,
  isRejecting
}: {
  isOpen: boolean;
  onClose: () => void;
  onReject: (reason: string) => void;
  isRejecting: boolean;
}) {
  const [reason, setReason] = useState('');

  const handleSubmit = () => {
    if (reason.trim()) {
      onReject(reason);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-charcoal-950/80 flex items-center justify-center z-50 p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-charcoal-900 border border-rust-500 p-8 max-w-lg w-full"
      >
        <h2 className="text-xl font-serif text-cream-100 mb-2">Reject This Plan</h2>
        <p className="text-cream-400 text-sm mb-6">
          Please provide a reason. This feedback will be used to improve future plan generation.
        </p>

        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="What's wrong with this plan?"
          className="w-full h-32 bg-charcoal-800 border border-charcoal-700 p-4 text-cream-200 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none resize-none mb-6"
          autoFocus
        />

        <div className="flex gap-4">
          <button
            onClick={handleSubmit}
            disabled={!reason.trim() || isRejecting}
            className="flex-1 text-xs font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-4 py-3 hover:bg-rust-400 transition-colors disabled:opacity-50 font-bold"
          >
            {isRejecting ? 'Rejecting...' : 'Reject Plan'}
          </button>
          <button
            onClick={onClose}
            className="text-xs font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-4 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors"
          >
            Cancel
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function PlanApproval() {
  const { planId } = useParams<{ planId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, error, refetch } = usePlan(planId || '');
  const approvePlan = useApprovePlan();
  const rejectPlan = useRejectPlan();
  const regeneratePlan = useRegeneratePlan();
  const updatePlan = useUpdatePlan();
  const updateHandoff = useUpdateHandoff();

  // Refetch on mount and page focus to prevent stale data
  useRefreshOnFocus(refetch);

  // Fallback: fetch brief from customer if plan doesn't have one linked
  const customerId = data?.customer?.id || null;
  const needsBriefFallback = data && !data.brief && customerId;
  const { data: customerHandoffData, isLoading: handoffLoading } = useCustomerHandoffWithPlan(
    needsBriefFallback ? customerId : null
  );

  const [showRejectModal, setShowRejectModal] = useState(false);
  const [editedMilestones, setEditedMilestones] = useState<PlanMilestone[] | null>(null);

  if (!planId) {
    return (
      <div className="max-w-6xl mx-auto">
        <div className="hud-border p-8 text-center">
          <p className="text-cream-400">No plan selected.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto">
        <div className="hud-border p-8 border-l-4 border-l-rust-500">
          <div className="text-[10px] uppercase tracking-[0.3em] text-rust-500 font-bold mb-4">
            Error Loading Plan
          </div>
          <p className="text-cream-200 mb-4">{(error as Error).message}</p>
          <button
            onClick={() => refetch()}
            className="text-xs font-mono uppercase tracking-widest border border-rust-500 text-rust-500 px-4 py-2 hover:bg-rust-500 hover:text-charcoal-900 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (isLoading || (needsBriefFallback && handoffLoading)) {
    return (
      <div className="max-w-6xl mx-auto">
        <LoadingSkeleton />
      </div>
    );
  }

  if (!data || !data.plan) {
    return (
      <div className="max-w-6xl mx-auto">
        <div className="hud-border p-8 text-center">
          <p className="text-cream-400">Plan not found.</p>
        </div>
      </div>
    );
  }

  const { plan, customer } = data;
  // Use brief from plan if available, otherwise fall back to customer's handoff brief
  const brief = data.brief || (customerHandoffData?.brief ? {
    id: customerHandoffData.brief.id,
    workspace_id: '',
    customer_id: customerId,
    captured_at: '',
    body: customerHandoffData.brief.body,  // Markdown content from agent
    sales_commitments: customerHandoffData.brief.sales_commitments || [],
    technical_context: customerHandoffData.brief.technical_context || [],
    day_current: customerHandoffData.brief.day_current,
    day_total: customerHandoffData.brief.day_total,
    reality_check_confidence: customerHandoffData.brief.reality_check_confidence,
    reality_check_risks: customerHandoffData.brief.reality_check_risks,
    status: customerHandoffData.brief.status as 'draft' | 'confirmed' | 'needs_correction',
    user_corrections: null,
    notion_deal_id: customerHandoffData.brief.notion_deal_id,
    notion_deal_url: customerHandoffData.brief.notion_deal_url,
    created_at: customerHandoffData.brief.created_at || '',
  } : null);
  const isPending = plan.status === 'pending_approval';

  // Action handlers
  const handleApprove = () => {
    approvePlan.mutate(
      { planId, milestones: editedMilestones || undefined },
      {
        onSuccess: () => {
          navigate(customer ? `/app/customers/${customer.id}` : '/app');
        },
      }
    );
  };

  const handleReject = (reason: string) => {
    rejectPlan.mutate(
      { planId, rejectionReason: reason },
      {
        onSuccess: () => {
          setShowRejectModal(false);
          navigate('/app');
        },
      }
    );
  };

  const handleRegenerate = () => {
    regeneratePlan.mutate(planId, {
      onSuccess: () => {
        // The plan has been marked as superseded
        // A new plan will be generated asynchronously
        navigate('/app');
      },
    });
  };

  const handleUpdatePlan = (milestones: PlanMilestone[]) => {
    setEditedMilestones(milestones);
    updatePlan.mutate({ planId, milestones });
  };

  const handleUpdateHandoff = (data: Partial<HandoffBrief>) => {
    if (brief) {
      updateHandoff.mutate({
        briefId: brief.id,
        data: data as any,
      });
    }
  };

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center gap-2 text-xs font-mono text-charcoal-400 mb-4">
          <NavLink to="/app" className="hover:text-cream-200 transition-colors">
            Today
          </NavLink>
          <ChevronRight className="w-3 h-3" />
          {customer && (
            <>
              <NavLink
                to={`/app/customers/${customer.id}`}
                className="hover:text-cream-200 transition-colors"
              >
                {customer.name}
              </NavLink>
              <ChevronRight className="w-3 h-3" />
            </>
          )}
          <span className="text-cream-200">Plan Review</span>
        </div>

        <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b border-charcoal-700 pb-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              {isPending && <Pulse active />}
              <RefCode>{planId.slice(0, 8).toUpperCase()}</RefCode>
              <span className={cn(
                "text-xs font-mono uppercase tracking-widest px-2 py-0.5 border",
                isPending
                  ? "border-rust-500 text-rust-500"
                  : plan.status === 'approved'
                  ? "border-emerald-500 text-emerald-500"
                  : "border-charcoal-500 text-charcoal-500"
              )}>
                {plan.status.replace('_', ' ')}
              </span>
              {plan.regeneration_count > 0 && (
                <span className="text-xs text-charcoal-400">
                  v{plan.regeneration_count + 1}
                </span>
              )}
            </div>
            <h1 className="font-serif text-3xl text-cream-100">
              {customer?.name || 'Plan'} Onboarding Plan
            </h1>
          </div>

          {/* Action Buttons */}
          {isPending && (
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => setShowRejectModal(true)}
                disabled={rejectPlan.isPending}
                className="text-xs font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-4 py-2 hover:border-rust-500 hover:text-rust-500 transition-colors flex items-center gap-2"
              >
                <X className="w-4 h-4" />
                Reject
              </button>
              <button
                onClick={handleRegenerate}
                disabled={regeneratePlan.isPending}
                className="text-xs font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-4 py-2 hover:border-cream-400 hover:text-cream-200 transition-colors flex items-center gap-2"
              >
                <RefreshCw className={cn("w-4 h-4", regeneratePlan.isPending && "animate-spin")} />
                Regenerate
              </button>
              <button
                onClick={handleApprove}
                disabled={approvePlan.isPending}
                className="text-xs font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-2 hover:bg-rust-400 transition-colors flex items-center gap-2 font-bold"
              >
                <Check className="w-4 h-4" />
                {approvePlan.isPending ? 'Approving...' : 'Approve Plan'}
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Dual Pane Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left Pane: Handoff Brief */}
        <div className="hud-border p-6 lg:p-8">
          <div className="flex items-center gap-3 mb-6 pb-4 border-b border-charcoal-700">
            <Building className="w-5 h-5 text-charcoal-400" />
            <h2 className="text-sm font-mono uppercase tracking-widest text-cream-200">
              Handoff Brief
            </h2>
            {brief?.status === 'needs_correction' && (
              <span className="text-xs font-mono uppercase tracking-widest text-amber-500 border border-amber-500 px-2 py-0.5">
                Needs Correction
              </span>
            )}
          </div>

          {brief ? (
            <HandoffBriefEditor
              brief={brief}
              onUpdate={handleUpdateHandoff}
              isUpdating={updateHandoff.isPending}
            />
          ) : (
            <div className="text-center py-12">
              <AlertTriangle className="w-8 h-8 text-charcoal-500 mx-auto mb-4" />
              <p className="text-charcoal-400">No handoff brief associated with this plan.</p>
            </div>
          )}
        </div>

        {/* Right Pane: Generated Plan */}
        <div className="hud-border p-6 lg:p-8 border-l-2 border-l-rust-500/30">
          <div className="flex items-center gap-3 mb-6 pb-4 border-b border-charcoal-700">
            <Sparkles className="w-5 h-5 text-rust-500" />
            <h2 className="text-sm font-mono uppercase tracking-widest text-cream-200">
              Generated Plan
            </h2>
            {plan.human_edited && (
              <span className="text-xs font-mono uppercase tracking-widest text-amber-500 flex items-center gap-1">
                <Edit3 className="w-3 h-3" />
                Edited
              </span>
            )}
          </div>

          <PlanEditor
            plan={plan}
            onUpdate={handleUpdatePlan}
            isUpdating={updatePlan.isPending}
          />
        </div>
      </div>

      {/* Rejection Modal */}
      <RejectionModal
        isOpen={showRejectModal}
        onClose={() => setShowRejectModal(false)}
        onReject={handleReject}
        isRejecting={rejectPlan.isPending}
      />
    </div>
  );
}
