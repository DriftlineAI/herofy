import React from 'react';
import { cn } from '@/lib/utils';
import { MandateBadge } from './MandateBadge';

export type StepMode = 'view' | 'edit' | 'preview';
export type StepState = 'pending' | 'current' | 'done';

export interface PlanStepData {
  stepNumber: number;
  title: string;
  detail?: string;
  mandate?: boolean;
  mandateLocked?: boolean;
  provenance?: string; // e.g., "from · mandate · week 2"
  provenanceLink?: string;
}

interface PlanStepProps {
  mode: StepMode;
  state: StepState;
  step: PlanStepData;
  onEdit?: () => void;
  onClick?: () => void;
  className?: string;
}

/**
 * PlanStep - The highest-leverage component, used in artboards 4, 6, and 7
 * Three modes: view (static card), edit (inline editing), preview (right pane in editor)
 * Three states: pending, current (rust accent), done (emerald accent)
 */
export function PlanStep({
  mode,
  state,
  step,
  onEdit,
  onClick,
  className
}: PlanStepProps) {
  const handleClick = () => {
    if (mode === 'view' && onEdit) {
      onEdit();
    } else if (onClick) {
      onClick();
    }
  };

  return (
    <div
      className={cn(
        'pb-step',
        state === 'done' && 'is-done',
        state === 'current' && 'is-current',
        mode === 'edit' && 'is-editing',
        (mode === 'view' && onEdit) && 'cursor-pointer',
        className
      )}
      onClick={handleClick}
    >
      {/* Step number - absolutely positioned at left */}
      <div className="pb-step__n">{step.stepNumber}</div>

      {/* Content */}
      <div className="pb-step__content">
        <div className="pb-step__head">
          <div className="pb-step__title">
            {step.title}
            {step.mandate && (
              <MandateBadge
                locked={step.mandateLocked}
                className="ml-2 inline-block"
              />
            )}
          </div>
        </div>

        {step.detail && (
          <div className="pb-step__detail">{step.detail}</div>
        )}

        {/* Provenance line - traceability back to playbook */}
        {step.provenance && (
          <div className="pb-step__src">
            <div className="pb-step__src-dot" />
            {step.provenanceLink ? (
              <a
                href={step.provenanceLink}
                className="pb-step__src-link"
                onClick={(e) => e.stopPropagation()}
              >
                {step.provenance}
              </a>
            ) : (
              <span>{step.provenance}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
