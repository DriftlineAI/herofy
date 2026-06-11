import React from 'react';
import { cn } from '@/lib/utils';

interface VariableChipProps {
  variable: string;
  value?: string | null;
  pending?: boolean;
  className?: string;
}

/**
 * VariableChip - Display a variable with its resolved value
 * E.g., "customer.name → Acme Corp" or "customer.champion → (pending HITL)"
 */
export function VariableChip({ variable, value, pending, className }: VariableChipProps) {
  return (
    <span className={cn('pb-var-chip', className)}>
      <span className="pb-var-chip__key">{variable}</span>
      {' → '}
      <span className={cn(
        'pb-var-chip__val',
        pending && 'pb-var-chip__val--pending'
      )}>
        {pending ? '(pending HITL)' : value || '—'}
      </span>
    </span>
  );
}
