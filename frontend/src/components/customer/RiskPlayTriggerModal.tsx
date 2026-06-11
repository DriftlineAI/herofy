import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, ShieldAlert, Loader2 } from 'lucide-react';
import { getAuth } from 'firebase/auth';

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

interface RiskPlayTriggerModalProps {
  isOpen: boolean;
  onClose: () => void;
  customerId: string;
  customerName: string;
  workspaceId: string | undefined;
  /** Called after the play is enqueued so the caller can poll/refetch. */
  onTriggered: () => void;
}

const NEED_TYPES: { value: string; label: string }[] = [
  { value: 'renewal_at_risk', label: 'Renewal at risk' },
  { value: 'going_dark', label: 'Gone dark' },
  { value: 'frustrated_signal', label: 'Frustrated' },
  { value: 'champion_departed', label: 'Champion left' },
];

/**
 * Manually spin up the Risk/Save play. The CSM describes what happened (e.g. learned
 * on a call that the customer is evaluating competitors); the backend seeds a risk
 * signal and runs the play, which adapts the workspace risk playbook into a concrete
 * save brief + steps. Result appears as the Risk/Save card once the worker finishes.
 */
export function RiskPlayTriggerModal({
  isOpen,
  onClose,
  customerId,
  customerName,
  workspaceId,
  onTriggered,
}: RiskPlayTriggerModalProps) {
  const [description, setDescription] = React.useState('');
  const [needType, setNeedType] = React.useState('renewal_at_risk');
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (isOpen) {
      setDescription('');
      setNeedType('renewal_at_risk');
      setError(null);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workspaceId || !description.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const token = await getAuth().currentUser?.getIdToken();
      const res = await fetch(`${PYTHON_URL}/agents/orchestrator/risk-play`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          workspace_id: workspaceId,
          customer_id: customerId,
          description: description.trim(),
          need_type: needType,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.status === 404) {
        throw new Error('The orchestrator is not enabled in this environment.');
      }
      if (!res.ok || body?.error) {
        throw new Error(body?.error?.message || `Request failed (${res.status})`);
      }
      onTriggered();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the save play.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-charcoal-900/80 backdrop-blur-sm z-50"
            onClick={onClose}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="fixed inset-x-4 top-[10%] md:inset-x-auto md:left-1/2 md:-translate-x-1/2 md:w-full md:max-w-lg z-50"
          >
            <div className="bg-surface border border-border">
              {/* Header */}
              <div className="flex items-center justify-between p-6 border-b border-border">
                <div className="flex items-center gap-3">
                  <ShieldAlert className="w-5 h-5 text-rust-500" />
                  <div>
                    <h2 className="font-display italic text-2xl text-fg-100">Spin up a save play</h2>
                    <p className="text-xs text-fg-400 mt-0.5">
                      Tell the agent what you learned. It adapts your risk playbook into a save plan for {customerName}.
                    </p>
                  </div>
                </div>
                <button onClick={onClose} className="text-fg-400 hover:text-fg-100 transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Form */}
              <form onSubmit={handleSubmit} className="p-6 space-y-5">
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-fg-400 mb-2">
                    What happened? *
                  </label>
                  <textarea
                    autoFocus
                    required
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="e.g. On our QBR the VP said budgets are being cut and they're evaluating two competitors. No firm renewal commitment."
                    rows={4}
                    className="w-full bg-surface-2 border border-border text-fg-100 px-4 py-3 placeholder:text-fg-500 focus:border-accent focus:outline-none resize-none text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-fg-400 mb-2">
                    Risk framing
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {NEED_TYPES.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setNeedType(opt.value)}
                        className={
                          'px-3 py-1.5 text-xs font-mono transition-colors border ' +
                          (needType === opt.value
                            ? 'bg-accent text-charcoal border-accent font-bold'
                            : 'bg-surface-2 text-fg-400 hover:text-fg-100 border-border')
                        }
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {error && <div className="text-xs text-rust-400">{error}</div>}

                <div className="flex justify-end gap-4 pt-2">
                  <button
                    type="button"
                    onClick={onClose}
                    className="text-xs font-mono uppercase tracking-widest border border-border text-fg-400 px-6 py-3 hover:border-fg-300 hover:text-fg-100 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submitting || !description.trim()}
                    className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    {submitting ? 'Starting…' : 'Run save play'}
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
