import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, Calendar, Clock, Users, LinkIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useCustomers } from '@/lib/dataconnect-hooks';
import type { MeetingType, MeetingAttendee, Need, CreateMeetingInput } from '@/lib/api';

interface MeetingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateMeetingInput) => void;
  isSubmitting?: boolean;
  preselectedCustomerId?: string;
  preselectedNeedId?: string;
}

const MEETING_TYPES: { value: MeetingType; label: string }[] = [
  { value: 'check_in', label: 'Check-in' },
  { value: 'qbr', label: 'Quarterly Business Review' },
  { value: 'renewal', label: 'Renewal Discussion' },
  { value: 'onboarding', label: 'Onboarding' },
  { value: 'kickoff', label: 'Kickoff Call' },
  { value: 'support', label: 'Support Call' },
  { value: 'other', label: 'Other' },
];

const DURATION_OPTIONS = [15, 30, 45, 60, 90, 120];

export function MeetingModal({
  isOpen,
  onClose,
  onSubmit,
  isSubmitting = false,
  preselectedCustomerId,
  preselectedNeedId,
}: MeetingModalProps) {
  const { data: customersData } = useCustomers();
  const [formData, setFormData] = React.useState({
    customer_id: preselectedCustomerId || '',
    need_id: preselectedNeedId || '',
    title: '',
    type: 'check_in' as MeetingType,
    scheduled_at: '',
    scheduled_time: '',
    duration_minutes: 30,
    attendees_theirs: [] as MeetingAttendee[],
    attendees_ours: [] as MeetingAttendee[],
  });

  const [newAttendee, setNewAttendee] = React.useState({ name: '', email: '', role: '' });

  // Reset form when modal opens
  React.useEffect(() => {
    if (isOpen) {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      tomorrow.setHours(10, 0, 0, 0);

      setFormData({
        customer_id: preselectedCustomerId || '',
        need_id: preselectedNeedId || '',
        title: '',
        type: 'check_in',
        scheduled_at: tomorrow.toISOString().split('T')[0],
        scheduled_time: '10:00',
        duration_minutes: 30,
        attendees_theirs: [],
        attendees_ours: [],
      });
    }
  }, [isOpen, preselectedCustomerId, preselectedNeedId]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Combine date and time
    const scheduledDateTime = new Date(`${formData.scheduled_at}T${formData.scheduled_time}`);

    onSubmit({
      customer_id: formData.customer_id,
      need_id: formData.need_id || null,
      title: formData.title,
      type: formData.type,
      scheduled_at: scheduledDateTime.toISOString(),
      duration_minutes: formData.duration_minutes,
      attendees_theirs: formData.attendees_theirs,
      attendees_ours: formData.attendees_ours,
    });
  };

  const addAttendee = (isOurs: boolean) => {
    if (!newAttendee.name || !newAttendee.email) return;

    const attendee: MeetingAttendee = {
      name: newAttendee.name,
      email: newAttendee.email,
      role: newAttendee.role || undefined,
    };

    if (isOurs) {
      setFormData((prev) => ({
        ...prev,
        attendees_ours: [...prev.attendees_ours, attendee],
      }));
    } else {
      setFormData((prev) => ({
        ...prev,
        attendees_theirs: [...prev.attendees_theirs, attendee],
      }));
    }

    setNewAttendee({ name: '', email: '', role: '' });
  };

  const removeAttendee = (index: number, isOurs: boolean) => {
    if (isOurs) {
      setFormData((prev) => ({
        ...prev,
        attendees_ours: prev.attendees_ours.filter((_, i) => i !== index),
      }));
    } else {
      setFormData((prev) => ({
        ...prev,
        attendees_theirs: prev.attendees_theirs.filter((_, i) => i !== index),
      }));
    }
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
            className="fixed inset-x-4 top-[5%] bottom-[5%] md:inset-x-auto md:left-1/2 md:-translate-x-1/2 md:w-full md:max-w-2xl z-50 overflow-hidden"
          >
            <div className="h-full bg-charcoal-900 border border-charcoal-700 flex flex-col">
              {/* Header */}
              <div className="flex items-center justify-between p-6 border-b border-charcoal-700">
                <div className="flex items-center gap-3">
                  <Calendar className="w-5 h-5 text-rust-500" />
                  <h2 className="font-serif text-2xl text-cream-100">Schedule Meeting</h2>
                </div>
                <button
                  onClick={onClose}
                  className="text-charcoal-400 hover:text-cream-200 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Form */}
              <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* Customer Selection */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Customer *
                  </label>
                  <select
                    required
                    value={formData.customer_id}
                    onChange={(e) => setFormData((prev) => ({ ...prev, customer_id: e.target.value }))}
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 focus:border-rust-500 focus:outline-none"
                  >
                    <option value="">Select a customer...</option>
                    {customersData?.customers.map((customer) => (
                      <option key={customer.id} value={customer.id}>
                        {customer.name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Title */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Meeting Title *
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.title}
                    onChange={(e) => setFormData((prev) => ({ ...prev, title: e.target.value }))}
                    placeholder="e.g., Q3 Business Review"
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                  />
                </div>

                {/* Type */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Meeting Type
                  </label>
                  <select
                    value={formData.type}
                    onChange={(e) => setFormData((prev) => ({ ...prev, type: e.target.value as MeetingType }))}
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 focus:border-rust-500 focus:outline-none"
                  >
                    {MEETING_TYPES.map((type) => (
                      <option key={type.value} value={type.value}>
                        {type.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Date and Time */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                      Date *
                    </label>
                    <input
                      type="date"
                      required
                      value={formData.scheduled_at}
                      onChange={(e) => setFormData((prev) => ({ ...prev, scheduled_at: e.target.value }))}
                      className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 focus:border-rust-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                      Time *
                    </label>
                    <input
                      type="time"
                      required
                      value={formData.scheduled_time}
                      onChange={(e) => setFormData((prev) => ({ ...prev, scheduled_time: e.target.value }))}
                      className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 focus:border-rust-500 focus:outline-none"
                    />
                  </div>
                </div>

                {/* Duration */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Duration
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {DURATION_OPTIONS.map((duration) => (
                      <button
                        key={duration}
                        type="button"
                        onClick={() => setFormData((prev) => ({ ...prev, duration_minutes: duration }))}
                        className={cn(
                          "px-4 py-2 text-sm font-mono transition-colors",
                          formData.duration_minutes === duration
                            ? "bg-rust-500 text-charcoal-900"
                            : "bg-charcoal-800 text-charcoal-400 hover:text-cream-200 border border-charcoal-700"
                        )}
                      >
                        {duration}m
                      </button>
                    ))}
                  </div>
                </div>

                {/* Attendees */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    External Attendees
                  </label>
                  <div className="space-y-2">
                    {formData.attendees_theirs.map((attendee, i) => (
                      <div key={i} className="flex items-center gap-2 bg-charcoal-800 px-3 py-2">
                        <span className="text-cream-200">{attendee.name}</span>
                        <span className="text-charcoal-500 text-sm">{attendee.email}</span>
                        {attendee.role && (
                          <span className="text-charcoal-400 text-xs">({attendee.role})</span>
                        )}
                        <button
                          type="button"
                          onClick={() => removeAttendee(i, false)}
                          className="ml-auto text-charcoal-500 hover:text-rust-500"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="Name"
                        value={newAttendee.name}
                        onChange={(e) => setNewAttendee((prev) => ({ ...prev, name: e.target.value }))}
                        className="flex-1 bg-charcoal-800 border border-charcoal-700 text-cream-200 px-3 py-2 text-sm placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                      />
                      <input
                        type="email"
                        placeholder="Email"
                        value={newAttendee.email}
                        onChange={(e) => setNewAttendee((prev) => ({ ...prev, email: e.target.value }))}
                        className="flex-1 bg-charcoal-800 border border-charcoal-700 text-cream-200 px-3 py-2 text-sm placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => addAttendee(false)}
                        className="px-3 py-2 bg-charcoal-700 text-charcoal-300 hover:text-cream-200 text-sm"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                </div>
              </form>

              {/* Footer */}
              <div className="flex justify-end gap-4 p-6 border-t border-charcoal-700">
                <button
                  type="button"
                  onClick={onClose}
                  className="text-xs font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  form="meeting-form"
                  onClick={handleSubmit}
                  disabled={isSubmitting || !formData.customer_id || !formData.title}
                  className="text-xs font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSubmitting ? 'Scheduling...' : 'Schedule Meeting'}
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
