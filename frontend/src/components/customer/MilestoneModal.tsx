import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, Flag } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Milestone, MilestoneStatus, OwnerSide, CreateMilestoneInput, UpdateMilestoneInput } from '@/lib/api';

interface MilestoneModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateMilestoneInput | UpdateMilestoneInput) => void;
  isSubmitting?: boolean;
  milestone?: Milestone | null; // If provided, we're editing
}

const STATUS_OPTIONS: { value: MilestoneStatus; label: string; color: string }[] = [
  { value: 'not_started', label: 'Not Started', color: 'bg-charcoal-600 text-charcoal-300' },
  { value: 'in_progress', label: 'In Progress', color: 'bg-amber-500 text-charcoal-900' },
  { value: 'blocked', label: 'Blocked', color: 'bg-rust-500 text-charcoal-900' },
  { value: 'done', label: 'Done', color: 'bg-emerald-500 text-charcoal-900' },
  { value: 'skipped', label: 'Skipped', color: 'bg-charcoal-700 text-charcoal-400' },
];

const OWNER_OPTIONS: { value: OwnerSide; label: string }[] = [
  { value: 'us', label: 'Us' },
  { value: 'customer', label: 'Customer' },
  { value: 'joint', label: 'Joint' },
];

export function MilestoneModal({
  isOpen,
  onClose,
  onSubmit,
  isSubmitting = false,
  milestone,
}: MilestoneModalProps) {
  const isEditing = !!milestone;

  const [formData, setFormData] = React.useState({
    title: '',
    owner_side: 'joint' as OwnerSide,
    target_date: '',
    status: 'not_started' as MilestoneStatus,
    description: '',
  });

  // Reset form when modal opens or milestone changes
  React.useEffect(() => {
    if (isOpen) {
      if (milestone) {
        setFormData({
          title: milestone.title,
          owner_side: milestone.owner_side,
          target_date: milestone.target_date ? milestone.target_date.split('T')[0] : '',
          status: milestone.status,
          description: milestone.description || '',
        });
      } else {
        // Default to 7 days from now for new milestones
        const nextWeek = new Date();
        nextWeek.setDate(nextWeek.getDate() + 7);

        setFormData({
          title: '',
          owner_side: 'joint',
          target_date: nextWeek.toISOString().split('T')[0],
          status: 'not_started',
          description: '',
        });
      }
    }
  }, [isOpen, milestone]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const data: CreateMilestoneInput | UpdateMilestoneInput = {
      title: formData.title,
      owner_side: formData.owner_side,
      target_date: formData.target_date || undefined,
      status: formData.status,
      description: formData.description || undefined,
    };

    onSubmit(data);
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-charcoal-900/80 backdrop-blur-sm z-50"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="fixed inset-x-4 top-[10%] md:inset-x-auto md:left-1/2 md:-translate-x-1/2 md:w-full md:max-w-md z-50"
          >
            <div className="bg-charcoal-900 border border-charcoal-700">
              {/* Header */}
              <div className="flex items-center justify-between p-6 border-b border-charcoal-700">
                <div className="flex items-center gap-3">
                  <Flag className="w-5 h-5 text-rust-500" />
                  <h2 className="font-serif text-2xl text-cream-100">
                    {isEditing ? 'Edit Milestone' : 'Add Milestone'}
                  </h2>
                </div>
                <button
                  onClick={onClose}
                  className="text-charcoal-400 hover:text-cream-200 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Form */}
              <form onSubmit={handleSubmit} className="p-6 space-y-5">
                {/* Title */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Title *
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.title}
                    onChange={(e) => setFormData((prev) => ({ ...prev, title: e.target.value }))}
                    placeholder="e.g., API Integration Complete"
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                  />
                </div>

                {/* Owner */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Owner
                  </label>
                  <div className="flex gap-2">
                    {OWNER_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setFormData((prev) => ({ ...prev, owner_side: option.value }))}
                        className={cn(
                          "flex-1 px-4 py-2 text-sm font-mono transition-colors",
                          formData.owner_side === option.value
                            ? option.value === 'us'
                              ? "bg-rust-500 text-charcoal-900"
                              : "bg-cream-300 text-charcoal-900"
                            : "bg-charcoal-800 text-charcoal-400 hover:text-cream-200 border border-charcoal-700"
                        )}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Target Date */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Target Date
                  </label>
                  <input
                    type="date"
                    value={formData.target_date}
                    onChange={(e) => setFormData((prev) => ({ ...prev, target_date: e.target.value }))}
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 focus:border-rust-500 focus:outline-none"
                  />
                </div>

                {/* Status (only show when editing) */}
                {isEditing && (
                  <div>
                    <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                      Status
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {STATUS_OPTIONS.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          onClick={() => setFormData((prev) => ({ ...prev, status: option.value }))}
                          className={cn(
                            "px-3 py-1.5 text-xs font-mono transition-colors",
                            formData.status === option.value
                              ? option.color
                              : "bg-charcoal-800 text-charcoal-400 hover:text-cream-200 border border-charcoal-700"
                          )}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Description */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Description
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData((prev) => ({ ...prev, description: e.target.value }))}
                    placeholder="Optional details about this milestone..."
                    rows={2}
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none resize-none"
                  />
                </div>

                {/* Actions */}
                <div className="flex justify-end gap-4 pt-4">
                  <button
                    type="button"
                    onClick={onClose}
                    className="text-xs font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting || !formData.title}
                    className="text-xs font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSubmitting ? 'Saving...' : isEditing ? 'Save Changes' : 'Add Milestone'}
                  </button>
                </div>
              </form>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
