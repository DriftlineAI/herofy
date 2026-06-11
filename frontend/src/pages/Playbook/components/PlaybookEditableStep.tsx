import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { MandateBadge } from './MandateBadge';
import { VariableChip } from './VariableChip';
import { ScopeToggle } from './ScopeToggle';
import type { PlanStepData } from './PlanStep';

interface EditableStepProps {
  step: PlanStepData;
  customerName?: string;
  playbookSlug?: string;
  affectedCustomers?: number;
  onSave: (data: {
    title: string;
    detail: string;
    scope: 'customer' | 'playbook';
  }) => void;
  onCancel: () => void;
  onRewrite?: () => void;
  className?: string;
}

/**
 * PlaybookEditableStep - Inline step editor (Artboard 7)
 * The crucial question: does your edit apply only to this customer, or back to the playbook itself?
 */
export function PlaybookEditableStep({
  step,
  customerName = 'this customer',
  playbookSlug = 'PB-ENT-ONB',
  affectedCustomers = 0,
  onSave,
  onCancel,
  onRewrite,
  className
}: EditableStepProps) {
  const [title, setTitle] = useState(step.title);
  const [detail, setDetail] = useState(step.detail || '');
  const [scope, setScope] = useState<'customer' | 'playbook'>('customer');

  const handleSave = () => {
    onSave({ title, detail, scope });
  };

  return (
    <div className={cn('pb-step is-editing', className)}>
      {/* Step number */}
      <div className="pb-step__n">{step.stepNumber}</div>

      <div className="pb-step__content">
        {/* Inline title input */}
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="pb-step-edit__title"
          placeholder="Step title..."
        />

        {/* Inline detail textarea */}
        <textarea
          value={detail}
          onChange={(e) => setDetail(e.target.value)}
          className="pb-step-edit__detail"
          placeholder="Add details..."
          rows={3}
        />

        {/* Mandate badge (if applicable) */}
        {step.mandate && (
          <div className="mt-3">
            <MandateBadge locked={step.mandateLocked} />
          </div>
        )}

        {/* Variables pane */}
        <div className="pb-step-vars">
          <span className="pb-step-vars__label">VARIABLES</span>
          <div className="pb-step-vars__chips">
            <VariableChip
              variable="customer.champion"
              value={null}
              pending
            />
            <button className="pb-step-vars__add">+ Add variable</button>
          </div>
        </div>

        {/* Scope toggle - THE CENTERPIECE */}
        <ScopeToggle
          value={scope}
          onChange={setScope}
          customerName={customerName}
          playbookSlug={playbookSlug}
          affectedCustomers={affectedCustomers}
        />

        {/* Footer actions */}
        <div className="pb-step-actions">
          {/* Left: provenance link */}
          <div className="pb-step-actions__left">
            <span className="text-xs font-mono text-app-fg-400">
              Provenance ·{' '}
              <span className="text-rust-500">"{step.title.slice(0, 30)}..."</span>
              {step.provenanceLink && (
                <a
                  href={step.provenanceLink}
                  className="text-rust-500 hover:text-rust-400 ml-1"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  view in playbook ↗
                </a>
              )}
            </span>
          </div>

          {/* Right: action buttons */}
          <div className="pb-step-actions__right">
            <button
              onClick={onCancel}
              className="px-4 py-2 text-sm font-mono uppercase tracking-wider text-app-fg-300 hover:text-app-fg-100"
            >
              Cancel
            </button>
            {onRewrite && (
              <button
                onClick={onRewrite}
                className="px-4 py-2 text-sm font-mono uppercase tracking-wider text-rust-500 hover:text-rust-400"
              >
                Sidekick, rewrite this
              </button>
            )}
            <button
              onClick={handleSave}
              className="px-6 py-2 text-sm font-mono uppercase tracking-wider bg-rust-500 text-cream-50 hover:bg-rust-400 rounded-sm"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
