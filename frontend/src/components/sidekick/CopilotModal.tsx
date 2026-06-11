import React, { useEffect, useRef, useState } from 'react';
import { X, Send, Zap, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { isDemoHost } from '@/lib/demo';
import { useAuth } from '@/lib/auth';
import { useWorkspace } from '@/lib/workspace';
import { useSidekickAskingItems, useToday, runDemoSweep } from '@/lib/dataconnect-hooks';
import { SkSigil, SidekickWorking } from './SidekickAtoms';

/**
 * Copilot Modal - Command palette / chat interface.
 *
 * Two modes:
 * - **Normal**: a stubbed chat surface (backend `copilot/ask` not yet wired).
 * - **Demo** (`isDemoHost()`): a scripted guide that walks a self-serve judge through
 *   the "going-dark save" arc — orient → run the morning sweep → watch the Risk/Save
 *   play work → the HITL decision keystone → convert. No new surface; the floating
 *   Sidekick chat IS the guide. See the "Demo Arc" plan.
 *
 * Opens via CopilotFab, Cmd+K / Ctrl+K, or (in demo) auto-opens from AppLayout.
 */

export interface CopilotMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

interface CopilotModalProps {
  isOpen: boolean;
  onClose: () => void;
  className?: string;
}

// ---- Demo guide state machine ---------------------------------------------
// Advances on real backend signals (sweep completion + the surfaced HITL need),
// never on timers. See useSidekickAskingItems / runDemoSweep.
// welcome → orient (run sweep) → working → findings (review on the customer record) →
// decide (approve the draft yourself or hand it to Sidekick) → wrap (next steps).
type DemoStep = 'welcome' | 'orient' | 'working' | 'findings' | 'decide' | 'wrap';
const STEP_ORDER: DemoStep[] = ['welcome', 'orient', 'working', 'findings', 'decide', 'wrap'];

// Need types the Risk/Save play surfaces — used to pick the hero catch out of the Today queue.
const RISK_NEED_TYPES = new Set<string>([
  'going_dark', 'renewal_at_risk', 'frustrated_signal', 'champion_departed',
  'onboarding_behind', 'open_commitment_overdue', 'approaching_renewal', 'escalation',
]);

// Per-tab, ephemeral hint for where the visitor left off (NOT a source of truth —
// the pending sidekick_question in the DB is). Lets a refresh after answering land
// on the convert beat instead of restarting. sessionStorage, not Firebase. Scoped to
// the workspace so a brand-new demo account in the same tab starts fresh rather than
// inheriting the prior account's beat.
const TOUR_STEP_KEY = 'herofy_demo_tour_step';
function readStoredStep(workspaceId: string | null): DemoStep | null {
  if (!workspaceId) return null;
  try {
    const raw = sessionStorage.getItem(TOUR_STEP_KEY);
    if (!raw) return null;
    const { ws, step } = JSON.parse(raw) as { ws?: string; step?: string };
    if (ws !== workspaceId || !step || !(STEP_ORDER as string[]).includes(step)) return null;
    return step as DemoStep;
  } catch {
    return null;
  }
}
function writeStoredStep(workspaceId: string | null, step: DemoStep): void {
  if (!workspaceId) return;
  try {
    sessionStorage.setItem(TOUR_STEP_KEY, JSON.stringify({ ws: workspaceId, step }));
  } catch {
    /* storage unavailable — resume just won't persist, no harm */
  }
}

const PRIMARY_BTN =
  'inline-flex items-center justify-center px-3 py-2 bg-rust-500 hover:bg-rust-400 ' +
  'text-charcoal-900 text-xs font-mono uppercase tracking-widest transition-colors ' +
  'disabled:opacity-50 disabled:cursor-not-allowed';

const GuideBubble: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="flex gap-3 justify-start">
    <div className="w-7 h-7 rounded-full bg-rust-500/20 flex items-center justify-center shrink-0 mt-0.5">
      <SkSigil size={11} />
    </div>
    <div className="flex-1 min-w-0 rounded-lg bg-charcoal-800 text-cream-200 border border-charcoal-700 px-4 py-3.5 space-y-3.5">
      {children}
    </div>
  </div>
);

const DemoGuide: React.FC<{
  onClose: () => void;
  messagesEndRef: React.RefObject<HTMLDivElement>;
}> = ({ onClose, messagesEndRef }) => {
  const navigate = useNavigate();
  const { workspaceId } = useWorkspace();
  const { items: askingItems, isLoading: askingLoading, refetch: refetchAsking } =
    useSidekickAskingItems();
  // The sweep surfaces the save as a going-dark/risk Need in the Today queue (the asking
  // SidekickItem — the HITL question — may not exist yet at the findings beat). The freshest
  // risk Need IS the catch; we route "Review the findings" to its customer.
  const { data: today, isLoading: todayLoading, refetch: refetchToday } = useToday();

  // Resume synchronously from the per-tab session hint (survives refresh, cleared on
  // tab close). Never resume into the transient 'working' spinner — its in-flight
  // request is gone — fall back to 'orient' where the visitor can re-run the sweep.
  const [step, setStep] = useState<DemoStep>(() => {
    const s = readStoredStep(workspaceId);
    return s === 'working' ? 'orient' : (s ?? 'welcome');
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upgradedRef = useRef(false);

  // True once the guide has reached (or passed) the given beat — lets earlier beats
  // stay visible as a growing transcript while only the current one shows its action.
  const at = (s: DemoStep) => STEP_ORDER.indexOf(step) >= STEP_ORDER.indexOf(s);

  // The keystone HITL pause surfaces as its own sidekick_question Need (approve/counter/hold),
  // carrying the agent run. This is the un-seedable "the sweep ran and a save is waiting" signal:
  // seeded fixtures contain risk Needs but never a run-backed sidekick_question, so this is what
  // distinguishes a real post-sweep state from a freshly provisioned workspace.
  const pendingDecision = React.useMemo(
    () => (today?.items ?? []).find((n) => n.type === 'sidekick_question' && n.agent_run_id),
    [today?.items],
  );

  // The hero catch: the freshest risk Need the sweep surfaced — drives "Review the findings" to
  // the right customer record. Prefer the pending decision's customer (exact) when present.
  const heroNeed = React.useMemo(() => {
    const items = (today?.items ?? []).filter((n) => RISK_NEED_TYPES.has(n.type));
    if (items.length === 0) return undefined;
    return [...items].sort((a, b) => (a.created_at < b.created_at ? 1 : -1))[0];
  }, [today?.items]);

  const decisionRunId = pendingDecision?.agent_run_id ?? heroNeed?.agent_run_id ?? undefined;

  const pending = askingItems[0];
  const heroCustomerId = pendingDecision?.customer_id || pending?.customer_id || heroNeed?.customer_id;
  const pendingName = pendingDecision?.customer_name || pending?.customer_name || heroNeed?.customer_name;

  // Backend truth reconciles the session hint once the queries settle (runs once). A pending
  // run-backed sidekick_question means the sweep already ran and the save is waiting on the human
  // → make sure we're at least at 'findings'. Gating on the decision (not any risk Need) keeps a
  // freshly provisioned workspace — which is seeded with risk Needs — starting at 'welcome'. Never
  // auto-advances toward 'wrap'; the guide buttons own forward progress, so a refresh mid-flow
  // resumes where the visitor left off.
  useEffect(() => {
    if (upgradedRef.current || askingLoading || todayLoading) return;
    upgradedRef.current = true;
    if (pendingDecision && STEP_ORDER.indexOf(step) < STEP_ORDER.indexOf('findings')) {
      setStep('findings');
    }
  }, [askingLoading, todayLoading, pendingDecision, step]);

  // Persist the current beat for this tab on every change (unconditional — initial
  // step already came from storage, so this never clobbers the resume value).
  useEffect(() => {
    writeStoredStep(workspaceId, step);
  }, [workspaceId, step]);

  const handleRunSweep = async () => {
    if (!workspaceId || busy) return;
    setError(null);
    setBusy(true);
    setStep('working');
    try {
      await runDemoSweep(workspaceId);
      await Promise.all([refetchAsking(), refetchToday()]);
      setStep('findings');
    } catch (e) {
      setError((e as Error).message || 'The sweep failed — try again.');
      setStep('orient');
    } finally {
      setBusy(false);
    }
  };

  // Where the Need itself takes you — the customer's record, with the save play laid out.
  const handleReviewFindings = () => {
    navigate(heroCustomerId ? `/app/customers/${heroCustomerId}` : '/app');
    setStep('decide');
  };

  // Hand the send to Sidekick — the HITL decision screen (approve / counter / hold), which lives
  // on the paused run at /app/sidekick/:runId. Fall back to the asking item / sidekick list.
  const handleCheckSidekick = () => {
    const item = askingItems[0];
    const target = decisionRunId
      ? `/app/sidekick/${decisionRunId}`
      : item?.need_id
        ? `/app/needs/${item.need_id}`
        : '/app/sidekick';
    navigate(target);
    setStep('wrap');
  };

  const handleExploreDesk = () => {
    onClose();
    navigate('/app');
  };

  return (
    <div className="flex-1 overflow-y-auto px-5 py-6 space-y-5">
      {/* Beat 0 — Welcome / mission framing */}
      <GuideBubble>
        <p className="text-sm leading-relaxed">
          Welcome to the Herofy demo. I'm Sidekick — your guide for this mission. I'll walk you
          through a few quick steps so you can see how Herofy helps you be a hero for your
          customers, every single day.
        </p>
        {step === 'welcome' && (
          <button onClick={() => setStep('orient')} className={PRIMARY_BTN}>
            Start the tour →
          </button>
        )}
      </GuideBubble>

      {/* Beat 1 — Orient: the scenario */}
      {at('orient') && (
        <GuideBubble>
          <p className="text-sm leading-relaxed">
            First, a scenario every CS team knows: an account going dark. You're 90 days into running
            a 13-customer book — and one of them has gone quiet without realizing it. Let me find it.
          </p>
          {step === 'orient' && (
            <button onClick={handleRunSweep} disabled={busy || !workspaceId} className={PRIMARY_BTN}>
              Run the morning sweep
            </button>
          )}
          {error && <p className="text-xs text-signal-bad">{error}</p>}
        </GuideBubble>
      )}

      {/* Beat 2/3 — Catch + watch it work */}
      {step === 'working' && (
        <GuideBubble>
          <p className="text-sm leading-relaxed">
            Sweeping the book and working the save — researching the account, shaping a plan, and
            drafting the outreach…
          </p>
          <SidekickWorking
            task="Re-engaging the account that went dark"
            step="research → strategy → draft"
            stepNum={2}
            total={4}
          />
        </GuideBubble>
      )}

      {/* Beat 4 — Findings: where the Need itself takes you (the customer's save play) */}
      {at('findings') && (
        <GuideBubble>
          <p className="text-sm leading-relaxed">
            Found it{pendingName ? ` — ${pendingName}` : ''}. Silent for weeks. I ran the deep dive
            and built a save play. One thing to know: a save play adapts to what went wrong — going
            dark gets a re-engagement; an escalation or a stalled onboarding would look different.
            Take a look at what I found.
          </p>
          {step === 'findings' && (
            <button onClick={handleReviewFindings} className={PRIMARY_BTN}>
              Review the findings →
            </button>
          )}
        </GuideBubble>
      )}

      {/* Beat 5 — Decide: approve it yourself, or hand the send to Sidekick */}
      {at('decide') && (
        <GuideBubble>
          <p className="text-sm leading-relaxed">
            I also drafted the re-engagement email. You can approve &amp; send it yourself from the
            conversation — or hand it to me and I'll send it the moment you approve.
          </p>
          {step === 'decide' && (
            <button onClick={handleCheckSidekick} className={PRIMARY_BTN}>
              Check with Sidekick →
            </button>
          )}
        </GuideBubble>
      )}

      {/* Beat 6 — Wrap: what's next (don't dead-end) */}
      {step === 'wrap' && (
        <GuideBubble>
          <p className="text-sm leading-relaxed">
            That's one save, start to finish — caught, worked, and out the door on your call. The
            thread's now awaiting their reply; from here you'd work the rest of your Today queue, or
            connect your own Gmail &amp; Notion to run your whole book like this.
          </p>
          <button onClick={handleExploreDesk} className={PRIMARY_BTN}>
            Explore the desk →
          </button>
        </GuideBubble>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
};

export const CopilotModal: React.FC<CopilotModalProps> = ({
  isOpen,
  onClose,
  className
}) => {
  // The guided tour is for anonymous demo visitors only. A real logged-in account —
  // even locally with VITE_DEMO_ENABLED — gets the normal Copilot chat (the guided
  // flow for live accounts is a separate, non-anon experience).
  const { isAnonymous } = useAuth();
  const demo = isDemoHost() && isAnonymous;
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Focus input when modal opens (chat mode only)
  useEffect(() => {
    if (isOpen && !demo && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen, demo]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: CopilotMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // TODO: Call backend API
    // const response = await fetch('/api/workspaces/:id/copilot/ask', {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify({ message: userMessage.content }),
    // });
    // const data = await response.json();

    // Mock response for now
    setTimeout(() => {
      const assistantMessage: CopilotMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'This is where Sidekick\'s response will appear. The backend needs to implement: POST /api/workspaces/:id/copilot/ask',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMessage]);
      setIsLoading(false);
    }, 800);
  };

  const handleSuggestionClick = (suggestion: string) => {
    setInput(suggestion);
    inputRef.current?.focus();
  };

  const suggestions = [
    'What needs my attention right now?',
    'Summarize activity for Acme Corp',
    'Draft a follow-up for the onboarding call',
    'Show me customers at risk',
  ];

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Drawer - no backdrop, just the panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className={cn(
              'fixed top-0 right-0 w-full max-w-md h-full z-50',
              'bg-charcoal-900 border-l border-charcoal-700 shadow-2xl',
              'flex flex-col',
              className
            )}
          >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-charcoal-700">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 bg-rust-500 text-charcoal-900 px-2 py-1">
                <SkSigil size={12} />
                <span className="font-mono text-xs uppercase tracking-widest font-bold">
                  Sidekick
                </span>
              </div>
              <span className="text-xs text-charcoal-500 font-mono">
                {demo ? 'Your guided tour' : 'Ask me anything'}
              </span>
            </div>
            <button
              onClick={onClose}
              className="text-charcoal-400 hover:text-cream-200 transition-colors"
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {demo ? (
            <>
              <DemoGuide onClose={onClose} messagesEndRef={messagesEndRef} />
              <div className="border-t border-charcoal-700 p-4">
                <p className="text-xs text-charcoal-500 font-mono">
                  Sidekick is guiding this demo · <kbd className="px-1 py-0.5 bg-charcoal-800 border border-charcoal-700 text-charcoal-400">Esc</kbd> to dismiss
                </p>
              </div>
            </>
          ) : (
          <>
          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
            {messages.length === 0 ? (
              <div className="flex flex-col h-full text-left py-8">
                <div className="w-12 h-12 rounded-full bg-rust-500/10 flex items-center justify-center mb-4">
                  <Zap className="w-6 h-6 text-rust-500" />
                </div>
                <h3 className="font-serif text-lg text-cream-100 mb-2">
                  How can I help?
                </h3>
                <p className="text-charcoal-400 text-sm mb-6">
                  Ask me about your customers, draft responses, or get quick insights.
                </p>

                {/* Suggestions */}
                <div className="space-y-2">
                  <div className="text-xs font-mono uppercase tracking-widest text-charcoal-500 mb-3">
                    Try asking...
                  </div>
                  {suggestions.map((suggestion, i) => (
                    <button
                      key={i}
                      onClick={() => handleSuggestionClick(suggestion)}
                      className="w-full text-left px-3 py-2.5 border border-charcoal-700 hover:border-rust-500 bg-charcoal-800/50 hover:bg-charcoal-800 transition-all text-xs text-cream-300 hover:text-cream-100"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={cn(
                      'flex gap-2',
                      message.role === 'user' ? 'justify-end' : 'justify-start'
                    )}
                  >
                    {message.role === 'assistant' && (
                      <div className="w-6 h-6 rounded-full bg-rust-500/20 flex items-center justify-center shrink-0 mt-1">
                        <SkSigil size={10} />
                      </div>
                    )}
                    <div
                      className={cn(
                        'flex-1 px-3 py-2',
                        message.role === 'user'
                          ? 'bg-rust-500 text-charcoal-900'
                          : 'bg-charcoal-800 text-cream-200 border border-charcoal-700'
                      )}
                    >
                      <p className="text-sm leading-relaxed whitespace-pre-wrap">
                        {message.content}
                      </p>
                    </div>
                  </div>
                ))}
                {isLoading && (
                  <div className="flex gap-2 justify-start">
                    <div className="w-6 h-6 rounded-full bg-rust-500/20 flex items-center justify-center shrink-0 mt-1">
                      <SkSigil size={10} />
                    </div>
                    <div className="bg-charcoal-800 border border-charcoal-700 px-3 py-2">
                      <Loader2 className="w-4 h-4 text-rust-500 animate-spin" />
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Input Area */}
          <form onSubmit={handleSubmit} className="border-t border-charcoal-700 p-4">
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask Sidekick..."
                className="flex-1 bg-charcoal-800 border border-charcoal-700 px-3 py-2 text-cream-200 placeholder:text-charcoal-500 focus:outline-none focus:border-rust-500 transition-colors text-sm"
                disabled={isLoading}
              />
              <button
                type="submit"
                disabled={!input.trim() || isLoading}
                className={cn(
                  'px-3 py-2 transition-all flex items-center justify-center',
                  input.trim() && !isLoading
                    ? 'bg-rust-500 hover:bg-rust-400 text-charcoal-900'
                    : 'bg-charcoal-700 text-charcoal-500 cursor-not-allowed'
                )}
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>
            <p className="text-xs text-charcoal-500 mt-2 font-mono">
              <kbd className="px-1 py-0.5 bg-charcoal-800 border border-charcoal-700 text-charcoal-400">Esc</kbd> to close · <kbd className="px-1 py-0.5 bg-charcoal-800 border border-charcoal-700 text-charcoal-400">⌘K</kbd> to toggle
            </p>
          </form>
          </>
          )}
        </motion.div>
      </>
      )}
    </AnimatePresence>
  );
};

export default CopilotModal;
