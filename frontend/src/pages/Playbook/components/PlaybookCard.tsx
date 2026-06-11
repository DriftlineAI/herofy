import React from 'react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { PlaybookTypeChip } from './PlaybookTypeChip';

export interface PlaybookCardData {
  id: string;
  scenario: 'onboarding' | 'renewal' | 'risk';
  name: string;
  fitNote: string | null;
  milestoneCount: number;
}

interface PlaybookCardProps {
  playbook: PlaybookCardData;
  className?: string;
}

const SCENARIO_BORDER: Record<string, string> = {
  onboarding: 'pb-card--onboarding',
  renewal: 'pb-card--renewal',
  risk: 'pb-card--action',
};

/**
 * PlaybookCard - Scenario-differentiated card
 */
export function PlaybookCard({ playbook, className }: PlaybookCardProps) {
  return (
    <Link
      to={`/app/handbook/playbook/${playbook.id}`}
      className={cn(
        'pb-card',
        SCENARIO_BORDER[playbook.scenario] || 'pb-card--action',
        className
      )}
    >
      <div className="pb-card__head">
        <PlaybookTypeChip type={playbook.scenario} />
        <div className="spacer" />
        <span className="pb-card__meta">{playbook.milestoneCount} steps</span>
      </div>

      <h3 className="pb-card__title">{playbook.name}</h3>

      {playbook.fitNote && (
        <p className="pb-card__intent">{playbook.fitNote}</p>
      )}
    </Link>
  );
}
