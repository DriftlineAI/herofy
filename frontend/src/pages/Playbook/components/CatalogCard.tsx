import React from 'react';
import { cn } from '@/lib/utils';

interface CatalogCardProps {
  type: 'onboarding' | 'action';
  strict?: boolean;
  title: string;
  description: string;
  onClick: () => void;
  className?: string;
}

/**
 * CatalogCard - Compact starter playbook cards
 * Used in PlaybookStart catalog (Artboard 2)
 */
export function CatalogCard({
  type,
  strict,
  title,
  description,
  onClick,
  className
}: CatalogCardProps) {
  const isOnboarding = type === 'onboarding';

  return (
    <button
      onClick={onClick}
      className={cn('pb-catalog__item', className)}
    >
      {/* Type label */}
      <div className={cn(
        'pb-catalog__type',
        isOnboarding ? 'pb-catalog__type--onboarding' : 'pb-catalog__type--action'
      )}>
        {type.toUpperCase()} · {strict ? 'STRICT' : 'SUGGESTIVE'}
      </div>

      {/* Title */}
      <h4 className="pb-catalog__title">{title}</h4>

      {/* Description */}
      <p className="pb-catalog__desc">{description}</p>
    </button>
  );
}
