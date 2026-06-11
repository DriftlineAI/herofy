import React from 'react';
import { SkSigil } from './SidekickAtoms';
import { cn } from '@/lib/utils';

/**
 * Sidekick Presence Components
 *
 * The connective tissue - how Sidekick announces itself outside its own tab:
 * - Nav Badge (rust pill with count)
 * - Contextual Alert Banner (page-level alert on customer detail)
 * - Floating Copilot FAB (bottom-right, always visible)
 *
 * Per ai-native.css design from Claude Design export.
 */

// Nav Badge - sits next to "Sidekick" in navigation
interface SkBadgeProps {
  count: number;
  className?: string;
}

export const SkBadge: React.FC<SkBadgeProps> = ({ count, className }) => (
  <span className={cn('sk-badge', className)}>{count}</span>
);

// Contextual Alert Banner - shown atop customer detail when Sidekick has open questions
interface SidekickAlertProps {
  customer: string;
  items: Array<string | React.ReactNode>;
  onAction?: () => void;
  className?: string;
}

export const SidekickAlert: React.FC<SidekickAlertProps> = ({
  customer,
  items,
  onAction,
  className
}) => (
  <div className={cn('sk-alert', className)}>
    <div className="sk-alert__glyph">
      <SkSigil size={14} />
    </div>
    <div className="sk-alert__body">
      <div className="sk-alert__title">
        Sidekick has {items.length} {items.length === 1 ? 'question' : 'questions'} about{' '}
        {customer}
      </div>
      <ul className="sk-alert__items">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
    {onAction && (
      <div className="sk-alert__action">
        <button className="sk-btn sk-btn--rust" onClick={onAction}>
          Answer in Sidekick →
        </button>
      </div>
    )}
  </div>
);

// Floating Copilot FAB - bottom right, always present (Cmd+K)
interface CopilotFabProps {
  count?: number;
  /** Pulsing dot signalling a guided tour is waiting (demo mode). Shown only when
   *  there's no numeric count badge already drawing the eye. */
  tour?: boolean;
  onClick?: () => void;
  className?: string;
}

export const CopilotFab: React.FC<CopilotFabProps> = ({
  count = 0,
  tour = false,
  onClick,
  className
}) => (
  <button className={cn('copilot-fab', className)} onClick={onClick} type="button">
    <span className="copilot-fab__sigil">
      <SkSigil size={14} />
    </span>
    <span>Sidekick</span>
    {count > 0 ? (
      <span className="copilot-fab__count">{count}</span>
    ) : (
      tour && <span className="copilot-fab__tour pulse continuous" aria-label="Guided tour ready" />
    )}
    <span className="copilot-fab__kbd">⌘K</span>
  </button>
);

export default {
  SkBadge,
  SidekickAlert,
  CopilotFab,
};
