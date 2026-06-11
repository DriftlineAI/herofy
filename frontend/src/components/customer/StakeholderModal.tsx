import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Stakeholder, StakeholderStatus, CreateStakeholderInput, UpdateStakeholderInput } from '@/lib/api';

interface StakeholderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateStakeholderInput | UpdateStakeholderInput) => void;
  isSubmitting?: boolean;
  stakeholder?: Stakeholder | null; // If provided, we're editing
}

const STATUS_OPTIONS: { value: StakeholderStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'departed', label: 'Departed' },
];

export function StakeholderModal({
  isOpen,
  onClose,
  onSubmit,
  isSubmitting = false,
  stakeholder,
}: StakeholderModalProps) {
  const isEditing = !!stakeholder;

  const [formData, setFormData] = React.useState({
    name: '',
    email: '',
    role: '',
    status: 'active' as StakeholderStatus,
    sentiment_note: '',
  });

  // Reset form when modal opens or stakeholder changes
  React.useEffect(() => {
    if (isOpen) {
      if (stakeholder) {
        setFormData({
          name: stakeholder.name,
          email: stakeholder.email || '',
          role: stakeholder.role || '',
          status: stakeholder.status,
          sentiment_note: stakeholder.sentiment_note || '',
        });
      } else {
        setFormData({
          name: '',
          email: '',
          role: '',
          status: 'active',
          sentiment_note: '',
        });
      }
    }
  }, [isOpen, stakeholder]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const data: CreateStakeholderInput | UpdateStakeholderInput = {
      name: formData.name,
      email: formData.email || undefined,
      role: formData.role || undefined,
      status: formData.status,
      sentiment_note: formData.sentiment_note || undefined,
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
                  <User className="w-5 h-5 text-rust-500" />
                  <h2 className="font-serif text-2xl text-cream-100">
                    {isEditing ? 'Edit Stakeholder' : 'Add Stakeholder'}
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
                {/* Name */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.name}
                    onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g., Sarah Chen"
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                  />
                </div>

                {/* Email */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Email
                  </label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData((prev) => ({ ...prev, email: e.target.value }))}
                    placeholder="e.g., sarah@acme.com"
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                  />
                </div>

                {/* Role */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Role
                  </label>
                  <input
                    type="text"
                    value={formData.role}
                    onChange={(e) => setFormData((prev) => ({ ...prev, role: e.target.value }))}
                    placeholder="e.g., Technical Lead"
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                  />
                </div>

                {/* Status */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Status
                  </label>
                  <div className="flex gap-2">
                    {STATUS_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setFormData((prev) => ({ ...prev, status: option.value }))}
                        className={cn(
                          "flex-1 px-4 py-2 text-sm font-mono transition-colors",
                          formData.status === option.value
                            ? option.value === 'departed'
                              ? "bg-charcoal-600 text-charcoal-300"
                              : "bg-rust-500 text-charcoal-900"
                            : "bg-charcoal-800 text-charcoal-400 hover:text-cream-200 border border-charcoal-700"
                        )}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Sentiment Note */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Sentiment Note
                  </label>
                  <textarea
                    value={formData.sentiment_note}
                    onChange={(e) => setFormData((prev) => ({ ...prev, sentiment_note: e.target.value }))}
                    placeholder="e.g., Generally positive, but frustrated with recent delays"
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
                    disabled={isSubmitting || !formData.name}
                    className="text-xs font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSubmitting ? 'Saving...' : isEditing ? 'Save Changes' : 'Add Stakeholder'}
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
