import React from 'react';
import { cn } from '@/lib/utils';

export type PlaybookScenarioFilter = 'all' | 'onboarding' | 'renewal' | 'risk';

interface PlaybookFilterProps {
  active: PlaybookScenarioFilter;
  onChange: (filter: PlaybookScenarioFilter) => void;
  counts: {
    all: number;
    onboarding: number;
    renewal: number;
    risk: number;
  };
}

/**
 * PlaybookFilter - Scenario filter chips with counts
 */
export function PlaybookFilter({ active, onChange, counts }: PlaybookFilterProps) {
  const options: { key: PlaybookScenarioFilter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'onboarding', label: 'Onboarding' },
    { key: 'renewal', label: 'Renewal' },
    { key: 'risk', label: 'At-Risk' },
  ];

  return (
    <div className="pb-filter">
      {options.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={cn(
            'pb-filter__btn',
            active === key && 'is-on'
          )}
        >
          {label} · {counts[key]}
        </button>
      ))}
    </div>
  );
}
