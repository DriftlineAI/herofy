import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, BookOpen, ChevronRight, Loader2 } from 'lucide-react';
import { getAuth } from 'firebase/auth';
import { cn } from '@/lib/utils';
import { usePlaybooks } from '@/lib/dataconnect-hooks';

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

interface PlaybookPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  customerId: string;
  workspaceId: string | undefined;
  /** Called after a plan is created so the caller can refetch. */
  onCreated: () => void;
}

/**
 * Apply one of the workspace's playbook templates as a customer's plan.
 * Calls the backend (POST .../plans/from-playbook), which deterministically
 * creates a Goal + its Milestones from the playbook — no AI, instant.
 */
export function PlaybookPickerModal({
  isOpen,
  onClose,
  customerId,
  workspaceId,
  onCreated,
}: PlaybookPickerModalProps) {
  const { data, isLoading } = usePlaybooks();
  const [submittingId, setSubmittingId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const playbooks = data?.playbooks || [];

  const handlePick = async (playbookId: string) => {
    if (!workspaceId || submittingId) return;
    setSubmittingId(playbookId);
    setError(null);
    try {
      const token = await getAuth().currentUser?.getIdToken();
      const res = await fetch(
        `${PYTHON_URL}/api/workspaces/${workspaceId}/customers/${customerId}/plans/from-playbook`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ playbook_id: playbookId }),
        }
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok || body?.success === false) {
        throw new Error(body?.message || `Request failed (${res.status})`);
      }
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the plan.');
    } finally {
      setSubmittingId(null);
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
            className="fixed inset-x-4 top-[8%] md:inset-x-auto md:left-1/2 md:-translate-x-1/2 md:w-full md:max-w-lg z-50"
          >
            <div className="bg-surface border border-border max-h-[80vh] flex flex-col">
              {/* Header */}
              <div className="flex items-center justify-between p-6 border-b border-border">
                <div className="flex items-center gap-3">
                  <BookOpen className="w-5 h-5 text-accent" />
                  <div>
                    <h2 className="font-display italic text-2xl text-fg-100">Start from a playbook</h2>
                    <p className="text-xs text-fg-400 mt-0.5">
                      Pick a template to build this customer's plan. You can edit every step afterward.
                    </p>
                  </div>
                </div>
                <button onClick={onClose} className="text-fg-400 hover:text-fg-100 transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* List */}
              <div className="p-4 overflow-y-auto">
                {isLoading ? (
                  <div className="text-center py-10 text-fg-400 text-sm">Loading playbooks…</div>
                ) : playbooks.length === 0 ? (
                  <div className="text-center py-10 text-fg-400 text-sm">
                    No playbooks in this workspace yet. Create one in Settings → Playbooks.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {playbooks.map((pb) => {
                      const busy = submittingId === pb.id;
                      return (
                        <button
                          key={pb.id}
                          onClick={() => handlePick(pb.id)}
                          disabled={!!submittingId}
                          className={cn(
                            'w-full text-left p-4 border border-border bg-surface-2 transition-colors group flex items-center justify-between gap-4',
                            'hover:border-accent disabled:opacity-60 disabled:cursor-not-allowed'
                          )}
                        >
                          <div className="min-w-0">
                            <div className="font-mono text-[9.5px] tracking-[0.25em] uppercase text-fg-400 font-bold mb-1">
                              {(pb.scenario || 'plan').toUpperCase()} · {pb.milestones.length} STEPS
                            </div>
                            <div className="font-display italic text-lg text-fg-100 leading-tight group-hover:text-accent transition-colors">
                              {pb.name}
                            </div>
                            {pb.fit_note && (
                              <div className="text-xs text-fg-400 mt-1 line-clamp-2">{pb.fit_note}</div>
                            )}
                          </div>
                          {busy ? (
                            <Loader2 className="w-4 h-4 text-accent animate-spin shrink-0" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-fg-400 group-hover:text-accent group-hover:translate-x-0.5 transition-all shrink-0" />
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
                {error && <div className="mt-3 text-xs text-rust-400 px-1">{error}</div>}
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
