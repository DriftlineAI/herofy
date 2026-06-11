import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { AlertCircle, Check, Loader2, ChevronRight, MessageSquare } from 'lucide-react';
import { useAgentRun, useSubmitAgentAnswers, useSkipAgentQuestions } from '@/lib/dataconnect-hooks';
import { useRefreshOnFocus } from '@/lib/realtime-hooks';
import { cn } from '@/lib/utils';
import { DecisionContext } from '@/components/sidekick/DecisionContext';
import type { AgentQuestion, QuestionType, QuestionOption, PersonOption } from '@/lib/api';
import {
  HITLQuestion,
  HITLPickOne,
  HITLPickMany,
  HITLPickPerson,
  HITLSlider,
  HITLFreeform,
  HITLYesNo,
} from '@/components/sidekick/HITLComponents';
import { DateInput } from '@/components/ui/DateInput';
import { BriefingRail } from '@/components/sidekick/BriefingRail';

function timeAgo(dateString: string): string {
  const date = new Date(dateString);
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  if (mins < 60) return `${mins}m`;
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function getQuestionType(q: AgentQuestion): QuestionType {
  return q.question_type || 'freeform';
}

function getOptions(q: AgentQuestion): QuestionOption[] {
  return q.metadata?.options || [];
}

function getPeople(q: AgentQuestion): PersonOption[] {
  return q.metadata?.people || [];
}

function LoadingSkeleton() {
  return (
    <div className="flex h-full">
      <div className="w-[320px] border-r border-border bg-surface/45 animate-pulse" />
      <div className="flex-1 p-14 animate-pulse space-y-6">
        <div className="h-12 w-3/4 bg-border rounded" />
        <div className="h-5 w-1/2 bg-surface-2 rounded" />
        {[1, 2, 3].map(i => <div key={i} className="h-32 bg-surface-2 rounded" />)}
      </div>
    </div>
  );
}

function SuccessState({ customerName }: { customerName?: string }) {
  const navigate = useNavigate();
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex flex-col items-center justify-center h-full text-center px-8"
    >
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
        className="w-20 h-20 bg-signal-ok/20 flex items-center justify-center mx-auto mb-6"
      >
        <Check className="w-10 h-10 text-signal-ok" />
      </motion.div>
      <h2 className="font-display text-[36px] text-fg-100 mb-3">Answers submitted</h2>
      <p className="font-sans text-[17px] text-fg-300 mb-2">
        Sidekick is resuming for <em className="text-accent">{customerName || 'this customer'}</em>.
      </p>
      <p className="font-sans text-[13px] text-fg-400 mb-8">
        You'll be notified when the plan is ready for review.
      </p>
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/app/sidekick')}
          className="inline-flex items-center gap-2 bg-surface-2 hover:bg-border text-fg-200 px-5 py-2.5 font-mono text-xs uppercase tracking-widest transition-colors"
        >
          ← Sidekick
        </button>
        <button
          onClick={() => navigate('/app/today', { state: { refetch: true } })}
          className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-page px-5 py-2.5 font-mono text-xs uppercase tracking-widest font-bold transition-colors"
        >
          Back to Today
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </motion.div>
  );
}

export default function SidekickQuestion() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, error, refetch } = useAgentRun(runId || '');
  const submitMutation = useSubmitAgentAnswers();
  const skipMutation = useSkipAgentQuestions();

  useRefreshOnFocus(refetch);

  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [isSubmitted, setIsSubmitted] = useState(false);

  const run = data?.run;
  const customerName = data?.customer_name || run?.customer_name || '';
  const questions = run?.questions || [];

  // Initialize answers
  useEffect(() => {
    if (questions.length === 0) return;
    const initial: Record<string, any> = {};
    questions.forEach(q => {
      if (answers[q.id] !== undefined) return;
      const type = getQuestionType(q);
      if (type === 'pick_many') initial[q.id] = [];
      else if (type === 'slider') initial[q.id] = q.metadata?.default || 7;
      else if (type === 'date' && q.metadata?.default_date) initial[q.id] = q.metadata.default_date;
      else initial[q.id] = '';
    });
    if (Object.keys(initial).length > 0) setAnswers(prev => ({ ...prev, ...initial }));
  }, [questions]);

  const isAnswered = (id: string, val: any): boolean => {
    if (Array.isArray(val)) return val.length > 0;
    if (typeof val === 'number') return true;
    if (typeof val === 'string') return val.trim().length > 0;
    return false;
  };

  const answeredCount = questions.filter(q => isAnswered(q.id, answers[q.id])).length;
  const allAnswered = answeredCount === questions.length && questions.length > 0;

  const handleSubmit = async () => {
    if (!runId) return;
    const stringAnswers: Record<string, string> = {};
    Object.entries(answers).forEach(([id, value]) => {
      if (Array.isArray(value)) stringAnswers[id] = value.join(', ');
      else if (typeof value === 'number') stringAnswers[id] = value.toString();
      else stringAnswers[id] = String(value ?? '');
    });
    try {
      await submitMutation.mutateAsync({ runId, data: { answers: stringAnswers } });
      setIsSubmitted(true);
    } catch {
      // error shown inline
    }
  };

  const handleDecideRest = () => {
    const newAnswers = { ...answers };
    questions.forEach(q => {
      if (!isAnswered(q.id, answers[q.id])) newAnswers[q.id] = '__DECIDE__';
    });
    setAnswers(newAnswers);
  };

  const handleSaveDraft = async () => {
    if (!runId) return;
    try {
      await skipMutation.mutateAsync(runId);
      navigate('/app/today', { state: { refetch: true } });
    } catch {
      // error shown inline
    }
  };

  if (isLoading) return <LoadingSkeleton />;

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center py-16">
        <AlertCircle className="w-12 h-12 text-signal-bad mx-auto mb-4" />
        <h2 className="font-display text-[24px] text-fg-100 mb-2">Failed to load</h2>
        <p className="font-sans text-[13px] text-fg-400 mb-4">{(error as Error).message}</p>
        <button onClick={() => refetch()} className="px-4 py-2 bg-surface-2 hover:bg-border text-fg-200 font-mono text-xs uppercase tracking-widest transition-colors">
          Try Again
        </button>
      </div>
    );
  }

  if (isSubmitted) return <SuccessState customerName={customerName} />;

  if (!run || questions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center py-16">
        <MessageSquare className="w-12 h-12 text-fg-400 mx-auto mb-4" />
        <h2 className="font-display text-[24px] text-fg-100 mb-2">No questions found</h2>
        <p className="font-sans text-[13px] text-fg-400 mb-4">
          {run ? `Agent run status: ${run.status}` : 'Agent run not found'}
        </p>
        <button onClick={() => navigate('/app/sidekick')} className="px-4 py-2 bg-accent hover:bg-accent-hover text-page font-mono text-xs uppercase tracking-widest transition-colors">
          ← Sidekick
        </button>
      </div>
    );
  }

  const agentLabel = run.agent_name?.replace(/_/g, '-') || 'sidekick';
  const pausedAgo = run.paused_at ? timeAgo(run.paused_at) : null;

  return (
    <div className="flex flex-col h-[calc(100dvh-17.5rem)] min-h-0">
      {/* Console bar */}
      <div className="flex-shrink-0 flex items-center gap-4 px-8 py-3.5 border-b border-border bg-surface/70">
        <Link
          to="/app/sidekick"
          className="font-mono text-[10px] uppercase tracking-[0.16em] text-fg-200 hover:text-accent border border-border hover:border-accent px-3 py-1.5 transition-all inline-flex items-center gap-2 rounded-sm"
        >
          ← Sidekick
        </Link>
        <span className="font-mono text-[10px] tracking-[0.1em] text-fg-400">
          <strong className="text-accent font-normal">{run.id.slice(0, 12).toUpperCase()}</strong>
          {' · '}{agentLabel}
          {' · '}{customerName}
        </span>
        {pausedAgo && (
          <div className="ml-auto inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-signal-warn border border-signal-warn/28 bg-signal-warn/6 px-3 py-1.5 rounded-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-signal-warn flex-shrink-0" />
            Agent paused · {pausedAgo}
          </div>
        )}
      </div>

      {/* Two-column body */}
      <div className="flex-1 min-h-0 grid" style={{ gridTemplateColumns: '320px minmax(0,1fr)' }}>

        {/* Left — Briefing rail */}
        <BriefingRail
          agentName={run.agent_name || 'sidekick'}
          customerName={customerName || ''}
          refcode={run.id.slice(0, 12).toUpperCase()}
          batchRationale={run.current_step?.replace(/_/g, ' ') || ''}
          answeredCount={answeredCount}
          totalCount={questions.length}
          onSubmit={handleSubmit}
          onDecideRest={handleDecideRest}
          onSaveDraft={handleSaveDraft}
          isSubmitting={submitMutation.isPending}
          canSubmit={allAnswered}
        />

        {/* Right — Question stack */}
        <div className="overflow-y-auto px-14 py-9">
          {/* Intro header */}
          <div className="mb-10">
            <h1 className="font-display text-[44px] leading-none text-fg-100 mb-3 max-w-[700px]">
              A few things before I can finish the{' '}
              <em className="font-sans italic text-accent not-uppercase">{customerName}</em>{' '}
              {run.agent_name?.includes('onboarding') ? 'onboarding plan' : 'next steps'}.
            </h1>
            <p className="font-sans italic font-medium text-[17px] text-fg-300 max-w-[600px]">
              I'd rather batch this than ping you {questions.length} times.
              Answer what you can — leave the rest, or tell me to decide.
            </p>
          </div>

          {/* Question stack */}
          <div className="flex flex-col divide-y divide-border/40">
            {questions.map((question, index) => {
              const type = getQuestionType(question);
              const num = String(index + 1).padStart(2, '0');
              const metadata = question.metadata || {};
              const answered = isAnswered(question.id, answers[question.id]);

              return (
                <motion.div
                  key={question.id}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.08 }}
                  className="grid py-8 first:pt-2"
                  style={{ gridTemplateColumns: '64px minmax(0,1fr)', gap: '8px' }}
                >
                  {/* Number gutter */}
                  <div className="font-mono text-[13px] text-accent tracking-[0.06em] pt-1.5">
                    {num}
                    {answered && (
                      <span className="block mt-1.5 text-signal-ok">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 6L9 17l-5-5" />
                        </svg>
                      </span>
                    )}
                  </div>

                  {/* Question content */}
                  <div>
                    <h3 className="font-display text-[28px] leading-none text-fg-100 mb-2.5">
                      {question.text}
                    </h3>
                    {question.context && <DecisionContext context={question.context} className="mb-5" />}

                    <div className="max-w-[560px]">
                      {type === 'pick_one' && (
                        <HITLPickOne
                          options={getOptions(question)}
                          value={answers[question.id] || ''}
                          onChange={v => setAnswers(prev => ({ ...prev, [question.id]: v }))}
                          decideLabel={metadata.decide_label}
                        />
                      )}
                      {type === 'pick_many' && (
                        <HITLPickMany
                          options={getOptions(question)}
                          value={answers[question.id] || []}
                          onChange={v => setAnswers(prev => ({ ...prev, [question.id]: v }))}
                        />
                      )}
                      {type === 'pick_person' && (
                        <HITLPickPerson
                          people={getPeople(question)}
                          value={answers[question.id] || ''}
                          onChange={v => setAnswers(prev => ({ ...prev, [question.id]: v }))}
                        />
                      )}
                      {type === 'slider' && (
                        <HITLSlider
                          min={metadata.min || 3}
                          max={metadata.max || 21}
                          value={answers[question.id] ?? (metadata.default || 7)}
                          onChange={v => setAnswers(prev => ({ ...prev, [question.id]: v }))}
                          labelLow={metadata.label_low || 'Low'}
                          labelHigh={metadata.label_high || 'High'}
                          format={metadata.format_template
                            ? (v) => metadata.format_template!.replace('{value}', String(v)).replace('{s}', v === 1 ? '' : 's')
                            : undefined}
                        />
                      )}
                      {type === 'freeform' && (
                        <HITLFreeform
                          placeholder={question.placeholder || 'Type your answer…'}
                          value={answers[question.id] || ''}
                          onChange={v => setAnswers(prev => ({ ...prev, [question.id]: v }))}
                        />
                      )}
                      {type === 'yes_no' && (
                        <HITLYesNo
                          value={answers[question.id] || ''}
                          onChange={v => setAnswers(prev => ({ ...prev, [question.id]: v }))}
                          yesLabel={metadata.yes_label}
                          noLabel={metadata.no_label}
                          allowDecide={metadata.allow_decide}
                        />
                      )}
                      {type === 'date' && (
                        <DateInput
                          value={answers[question.id] || ''}
                          onChange={v => setAnswers(prev => ({ ...prev, [question.id]: v }))}
                          minDate={metadata.min_date}
                          maxDate={metadata.max_date}
                          placeholder={question.placeholder}
                        />
                      )}
                      {!['pick_one','pick_many','pick_person','slider','freeform','yes_no','date'].includes(type) && (
                        <HITLFreeform
                          placeholder={question.placeholder || 'Type your answer…'}
                          value={answers[question.id] || ''}
                          onChange={v => setAnswers(prev => ({ ...prev, [question.id]: v }))}
                        />
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>

          {/* Footer echo */}
          <div className="flex items-center gap-4 mt-10 pt-6 border-t border-border">
            <div className="flex gap-1">
              {questions.map((_, i) => (
                <span key={i} className={cn('w-10 h-0.5', i < answeredCount ? 'bg-accent' : 'bg-border')} />
              ))}
            </div>
            <span className="font-mono text-[11px] tracking-[0.1em] text-fg-400">
              <strong className="text-fg-100">{answeredCount}</strong> of {questions.length} answered
            </span>
            <button
              onClick={handleSubmit}
              disabled={!allAnswered || submitMutation.isPending}
              className={cn(
                'ml-auto inline-flex items-center gap-2 px-5 py-2.5 font-mono text-[10.5px] uppercase tracking-[0.18em] font-bold transition-all rounded-sm',
                allAnswered ? 'bg-accent text-page hover:bg-accent-hover' : 'bg-surface-2 text-fg-400 cursor-not-allowed border border-border'
              )}
            >
              {submitMutation.isPending
                ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Sending…</span></>
                : 'Send · resume agent →'
              }
            </button>
          </div>

          {/* Errors */}
          <AnimatePresence>
            {(submitMutation.isError || skipMutation.isError) && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                className="mt-4 p-4 bg-signal-bad/10 border border-signal-bad/30 flex items-center gap-3"
              >
                <AlertCircle className="w-5 h-5 text-signal-bad shrink-0" />
                <p className="text-signal-bad text-sm">
                  {((submitMutation.error || skipMutation.error) as Error)?.message || 'An error occurred'}
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
