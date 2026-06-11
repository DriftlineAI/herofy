import React from 'react';
import { cn } from '@/lib/utils';

type PlaybookScenario = 'onboarding' | 'renewal' | 'risk';

interface PlaybookTypeChipProps {
  type: PlaybookScenario;
  strict?: boolean;
  className?: string;
}

const SCENARIO_STYLES: Record<PlaybookScenario, string> = {
  onboarding: 'pb-type-chip--onboarding',
  renewal: 'pb-type-chip--renewal',
  risk: 'pb-type-chip--action',
};

/**
 * PlaybookTypeChip - Small bordered mono tag for playbook scenario
 * Emerald for onboarding, amber for renewal, rust for risk
 */
export function PlaybookTypeChip({ type, strict, className }: PlaybookTypeChipProps) {
  return (
    <span
      className={cn(
        'pb-type-chip',
        SCENARIO_STYLES[type] || 'pb-type-chip--action',
        className
      )}
    >
      {type.toUpperCase()}
      {strict !== undefined && (
        <>
          {' · '}
          {strict ? 'STRICT' : 'SUGGESTIVE'}
        </>
      )}
    </span>
  );
}
