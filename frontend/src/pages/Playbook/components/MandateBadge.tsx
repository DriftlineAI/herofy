import React from 'react';
import { cn } from '@/lib/utils';

interface MandateBadgeProps {
  locked?: boolean; // For "MANDATE · LOCKED" in onboarding
  className?: string;
}

/**
 * MandateBadge - Small inline mono pill for mandate indicators
 * Emerald border and text
 */
export function MandateBadge({ locked, className }: MandateBadgeProps) {
  return (
    <span className={cn('pb-mandate-badge', className)}>
      MANDATE
      {locked && ' · LOCKED'}
    </span>
  );
}
