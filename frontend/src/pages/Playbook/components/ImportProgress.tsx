import React from 'react';
import { cn } from '@/lib/utils';
import { Check } from 'lucide-react';
import { Pulse } from '@/components/ui/huds';

export type ProgressStepState = 'done' | 'current' | 'pending';

export interface ProgressStep {
  label: string;
  state: ProgressStepState;
}

interface ImportProgressProps {
  filename: string;
  currentStep: number;
  totalSteps: number;
  steps: ProgressStep[];
  className?: string;
}

/**
 * ImportProgress - 6-step progress tracker with status indicators
 * Used in PlaybookImport (Artboard 5)
 */
export function ImportProgress({
  filename,
  currentStep,
  totalSteps,
  steps,
  className
}: ImportProgressProps) {
  return (
    <div className={cn('pb-import__progress', className)}>
      {/* Header */}
      <div className="pb-import__progress-head">
        <Pulse />
        <span className="pb-import__progress-label">
          SIDEKICK · READING "{filename}"
        </span>
        <span className="pb-import__progress-count">
          {currentStep} / {totalSteps} STEPS
        </span>
      </div>

      {/* Steps */}
      <div className="pb-import__progress-steps">
        {steps.map((step, i) => (
          <div
            key={i}
            className={cn(
              'pb-import__progress-step',
              step.state === 'done' && 'is-done',
              step.state === 'current' && 'is-current'
            )}
          >
            <div className="pb-import__progress-step-status">
              {step.state === 'done' ? (
                <Check className="w-3.5 h-3.5 text-signal-ok" />
              ) : step.state === 'current' ? (
                <div className="pb-import__progress-step-pulse" />
              ) : (
                <div className="pb-import__progress-step-box" />
              )}
            </div>
            <div className="pb-import__progress-step-label">
              {step.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
