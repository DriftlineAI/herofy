import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, AlertCircle, Maximize2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { DecisionContext } from './DecisionContext';
import { useAgentRun, useSubmitAgentAnswers } from '@/lib/dataconnect-hooks';
import type { SidekickQueueItem } from '@/lib/dataconnect-hooks';
import type { AgentQuestion, QuestionType, QuestionOption, PersonOption } from '@/lib/api';
import {
  HITLPickOne,
  HITLPickMany,
  HITLPickPerson,
  HITLSlider,
  HITLFreeform,
  HITLYesNo,
} from './HITLComponents';
import { DateInput } from '@/components/ui/DateInput';

function getQuestionType(q: AgentQuestion): QuestionType {
  return q.question_type || 'freeform';
}

function getOptions(q: AgentQuestion): QuestionOption[] {
  return q.metadata?.options || [];
}

function getPeople(q: AgentQuestion): PersonOption[] {
  return q.metadata?.people || [];
}

function isAnswered(value: any): boolean {
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'number') return true;
  if (typeof value === 'string') return value.trim().length > 0;
  return false;
}

function formatArr(cents: number | null): string {
  if (!cents) return '';
  const d = cents / 100;
  if (d >= 1_000_000) return `$${(d / 1_000_000).toFixed(1)}M ARR`;
  if (d >= 1_000) return `$${Math.round(d / 1_000)}K ARR`;
  return `$${Math.round(d)} ARR`;
}

function FocusEmpty() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-8">
      <div className="w-14 h-14 border border-border flex items-center justify-center text-accent/40 mb-4">
        <span className="font-display text-2xl">SK</span>
      </div>
      <div className="font-display text-[22px] text-fg-300 mb-2">Queue clear</div>
      <p className="font-sans text-[13px] text-fg-400 leading-relaxed max-w-[280px]">
        Nothing needs you right now. Sidekick is running autonomously — watch the agents at right.
      </p>
    </div>
  );
}

function FocusLoading() {
  return (
    <div className="p-7 animate-pulse space-y-4">
      <div className="h-3 w-48 bg-border rounded" />
      <div className="h-10 w-full bg-border rounded" />
      <div className="h-5 w-3/4 bg-surface-2 rounded" />
      <div className="space-y-2 mt-6">
        <div className="h-14 bg-surface-2 rounded" />
        <div className="h-14 bg-surface-2 rounded" />
      </div>
    </div>
  );
}

interface FocusPaneProps {
  item: SidekickQueueItem | null;
  onAnswered?: () => void;
}

export function FocusPane({ item, onAnswered }: FocusPaneProps) {
  const navigate = useNavigate();
  const { data, isLoading } = useAgentRun(item?.run_id || '');
  const submitMutation = useSubmitAgentAnswers();

  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [submitted, setSubmitted] = useState(false);

  const run = data?.run;
  const questions = run?.questions || [];

  // Reset when item changes
  useEffect(() => {
    setAnswers({});
    setSubmitted(false);
  }, [item?.id]);

  // Initialize all question answers
  useEffect(() => {
    if (questions.length === 0) return;
    setAnswers(prev => {
      const next = { ...prev };
      let changed = false;
      questions.forEach(q => {
        if (next[q.id] !== undefined) return;
        const type = getQuestionType(q);
        if (type === 'pick_many') next[q.id] = [];
        else if (type === 'slider') next[q.id] = q.metadata?.default || 7;
        else if (type === 'date' && q.metadata?.default_date) next[q.id] = q.metadata.default_date;
        else next[q.id] = '';
        changed = true;
      });
      return changed ? next : prev;
    });
  }, [questions.map(q => q.id).join(',')]);

  if (!item) return <FocusEmpty />;
  if (isLoading) return <FocusLoading />;

  if (submitted) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-8">
        <div className="w-12 h-12 bg-signal-ok/20 flex items-center justify-center mx-auto mb-4">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-signal-ok">
            <path d="M20 6L9 17l-5-5" />
          </svg>
        </div>
        <div className="font-display text-[22px] text-fg-100 mb-2">Answer submitted</div>
        <p className="font-sans text-[13px] text-fg-400">Agent is resuming for {item.customer_name}.</p>
      </div>
    );
  }

  const handleSubmit = async () => {
    if (!item.run_id) return;
    const stringAnswers: Record<string, string> = {};
    Object.entries(answers).forEach(([id, value]) => {
      if (Array.isArray(value)) stringAnswers[id] = value.join(', ');
      else if (typeof value === 'number') stringAnswers[id] = value.toString();
      else stringAnswers[id] = String(value ?? '');
    });
    try {
      await submitMutation.mutateAsync({ runId: item.run_id, data: { answers: stringAnswers } });
      setSubmitted(true);
      onAnswered?.();
    } catch {
      // error shown below
    }
  };

  const handleDecide = () => {
    if (!item.run_id) return;
    const newAnswers: Record<string, string> = {};
    questions.forEach(q => { newAnswers[q.id] = '__DECIDE__'; });
    submitMutation.mutateAsync({ runId: item.run_id, data: { answers: newAnswers } })
      .then(() => { setSubmitted(true); onAnswered?.(); })
      .catch(() => {});
  };

  const answeredCount = questions.filter(q => isAnswered(answers[q.id])).length;
  const allAnswered = questions.length > 0 && answeredCount === questions.length;

  const arrLabel = formatArr(item.customer_arr_cents);
  const agentLabel = item.agent_type.replace(/_/g, '-');
  const whyText = item.context;
  const unblocks = run?.current_step?.replace(/_/g, ' ') || agentLabel;

  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-8 py-6 space-y-5">
      {/* Breadcrumb + expand button */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center flex-wrap gap-3 font-mono text-[10.5px] uppercase tracking-[0.18em]">
          <span className="text-accent font-bold">{item.customer_name}</span>
          {arrLabel && (
            <>
              <span className="text-border-strong">//</span>
              <span className="text-fg-400">{arrLabel}</span>
            </>
          )}
          <span className="text-border-strong">//</span>
          <span className="text-fg-400">{agentLabel}</span>
        </div>
        {item.run_id && (
          <button
            onClick={() => navigate(`/app/sidekick/${item.run_id}`)}
            title="Open full console"
            className="flex-shrink-0 p-1.5 text-fg-400 hover:text-fg-100 hover:bg-surface-2 border border-transparent hover:border-border transition-all rounded-sm"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Questions — all rendered inline */}
      {questions.length > 0 ? (
        <div className="space-y-8">
          {questions.map((q, index) => {
            const type = getQuestionType(q);
            const metadata = q.metadata || {};
            const num = String(index + 1).padStart(2, '0');
            const done = isAnswered(answers[q.id]);

            return (
              <div key={q.id} className={cn('space-y-3', index > 0 && 'pt-6 border-t border-border/50')}>
                {/* Question number + text */}
                <div className="flex items-start gap-3">
                  <span className={cn(
                    'font-mono text-[11px] tracking-[0.06em] flex-shrink-0 pt-0.5',
                    done ? 'text-signal-ok' : 'text-accent'
                  )}>
                    {done ? (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 6L9 17l-5-5" />
                      </svg>
                    ) : num}
                  </span>
                  <h2 className="font-display text-[28px] leading-none text-fg-100">
                    {q.text}
                  </h2>
                </div>

                {q.context && <DecisionContext context={q.context} className="pl-6" />}

                {/* Answer affordance */}
                <div className="max-w-[540px] pl-6">
                  {type === 'pick_one' && (
                    <HITLPickOne
                      options={getOptions(q)}
                      value={answers[q.id] || ''}
                      onChange={v => setAnswers(prev => ({ ...prev, [q.id]: v }))}
                      decideLabel={metadata.decide_label}
                    />
                  )}
                  {type === 'pick_many' && (
                    <HITLPickMany
                      options={getOptions(q)}
                      value={answers[q.id] || []}
                      onChange={v => setAnswers(prev => ({ ...prev, [q.id]: v }))}
                    />
                  )}
                  {type === 'pick_person' && (
                    <HITLPickPerson
                      people={getPeople(q)}
                      value={answers[q.id] || ''}
                      onChange={v => setAnswers(prev => ({ ...prev, [q.id]: v }))}
                    />
                  )}
                  {type === 'slider' && (
                    <HITLSlider
                      min={metadata.min || 3}
                      max={metadata.max || 21}
                      value={answers[q.id] ?? (metadata.default || 7)}
                      onChange={v => setAnswers(prev => ({ ...prev, [q.id]: v }))}
                      labelLow={metadata.label_low || 'Low'}
                      labelHigh={metadata.label_high || 'High'}
                      format={metadata.format_template
                        ? (v) => metadata.format_template!.replace('{value}', String(v)).replace('{s}', v === 1 ? '' : 's')
                        : undefined}
                    />
                  )}
                  {type === 'freeform' && (
                    <HITLFreeform
                      placeholder={q.placeholder || 'Type your answer…'}
                      value={answers[q.id] || ''}
                      onChange={v => setAnswers(prev => ({ ...prev, [q.id]: v }))}
                    />
                  )}
                  {type === 'yes_no' && (
                    <HITLYesNo
                      value={answers[q.id] || ''}
                      onChange={v => setAnswers(prev => ({ ...prev, [q.id]: v }))}
                      yesLabel={metadata.yes_label}
                      noLabel={metadata.no_label}
                      allowDecide={metadata.allow_decide}
                    />
                  )}
                  {type === 'date' && (
                    <DateInput
                      value={answers[q.id] || ''}
                      onChange={v => setAnswers(prev => ({ ...prev, [q.id]: v }))}
                      minDate={metadata.min_date}
                      maxDate={metadata.max_date}
                      placeholder={q.placeholder}
                    />
                  )}
                  {!['pick_one','pick_many','pick_person','slider','freeform','yes_no','date'].includes(type) && (
                    <HITLFreeform
                      placeholder={q.placeholder || 'Type your answer…'}
                      value={answers[q.id] || ''}
                      onChange={v => setAnswers(prev => ({ ...prev, [q.id]: v }))}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="font-sans text-[13px] text-fg-400 italic">No questions loaded.</p>
      )}

      {/* Secondary actions */}
      <div className="flex flex-wrap gap-2 pt-2">
        {[
          { label: 'Sidekick, you decide', onClick: handleDecide },
          { label: 'Need more info', onClick: () => {} },
          { label: 'Snooze 1d', onClick: () => {} },
          { label: 'Dismiss', onClick: () => {} },
        ].map(({ label, onClick }) => (
          <button
            key={label}
            onClick={onClick}
            className="inline-flex items-center font-mono text-[10.5px] uppercase tracking-[0.18em] px-4 py-2 border border-border text-fg-300 hover:text-fg-100 hover:border-border-strong transition-all duration-150 rounded-sm"
          >
            {label}
          </button>
        ))}
      </div>

      {/* Why this matters */}
      {whyText && (
        <div className="p-4 bg-surface/55 border-l-2 border-accent/60">
          <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-accent mb-2">Why this matters</div>
          <p className="font-sans text-[13.5px] leading-relaxed text-fg-300">{whyText}</p>
          {unblocks && (
            <div className="mt-3 pt-3 border-t border-dashed border-border font-mono text-[10px] tracking-[0.06em] text-fg-400 flex items-center gap-2">
              <span className="text-accent">↳</span>
              Answering resumes{' '}
              <strong className="text-accent-hover font-normal">{unblocks}</strong>
            </div>
          )}
        </div>
      )}

      {/* Progress + submit */}
      {questions.length > 0 && (
        <div className="space-y-3 pt-2">
          {questions.length > 1 && (
            <div className="flex items-center gap-3 font-mono text-[10px] tracking-[0.08em] text-fg-400">
              <strong className="text-fg-100">{answeredCount}</strong> of {questions.length} answered
              <div className="flex gap-1">
                {questions.map((_, i) => (
                  <span key={i} className={cn('w-6 h-0.5', i < answeredCount ? 'bg-accent' : 'bg-border')} />
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              onClick={handleSubmit}
              disabled={!allAnswered || submitMutation.isPending}
              className={cn(
                'inline-flex items-center gap-2 px-5 py-2.5 font-mono text-[10.5px] uppercase tracking-[0.18em] font-bold transition-all rounded-sm',
                allAnswered
                  ? 'bg-accent text-page hover:bg-accent-hover border border-accent'
                  : 'bg-surface-2 text-fg-400 cursor-not-allowed border border-border'
              )}
            >
              {submitMutation.isPending
                ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /><span>Submitting…</span></>
                : 'Submit & resume agent →'
              }
            </button>
            <span className="font-mono text-[10px] text-fg-400 tracking-[0.1em]">or press ⏎</span>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex justify-between items-center pt-3 border-t border-border font-mono text-[9.5px] uppercase tracking-[0.1em] text-fg-400">
        <span>{item.refcode} · from <span className="text-accent">{agentLabel}</span></span>
        <span className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-border-strong" />
          First-wins · nobody else viewing
        </span>
      </div>

      {/* Error */}
      {submitMutation.isError && (
        <div className="flex items-center gap-2 p-3 bg-signal-bad/10 border border-signal-bad/30 text-signal-bad text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {(submitMutation.error as Error)?.message || 'Submission failed'}
        </div>
      )}
    </div>
  );
}
