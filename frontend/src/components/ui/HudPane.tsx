import React from 'react';
import { Zap } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * HudPane — The single card primitive for Herofy
 *
 * Every card-shaped surface uses this component:
 * - Situation rows on Today
 * - Sidekick cards
 * - Right-rail context blocks
 * - Detail-screen panels
 *
 * Anatomy:
 * ┌──────────────────────────────────────────────┐
 * │ ▌ HEADER STRIP                       ref     │  ← optional
 * ├──────────────────────────────────────────────┤
 * │   BODY                                       │
 * └──────────────────────────────────────────────┘
 *   ↑ 4px gold left rail (always)
 *
 * Variants:
 * - intel (default): Gold left rail, standard header
 * - asks: Filled gold pulsing header, action required
 */

export interface HudPaneProps {
  variant?: 'intel' | 'asks';
  /** Header content - if omitted, no header strip rendered */
  header?: React.ReactNode;
  /** Reference code shown in header right side */
  refCode?: string;
  /** Show pulse indicator in header */
  pulse?: boolean;
  /** For asks variant: count shown in header */
  count?: number | string;
  /** Main body content */
  children: React.ReactNode;
  /** CTA at bottom (asks variant) */
  cta?: {
    label: string;
    badge?: string;
    onClick?: () => void;
  };
  /** Compact mode for Today rows */
  compact?: boolean;
  className?: string;
  onClick?: () => void;
}

export const HudPane: React.FC<HudPaneProps> = ({
  variant = 'intel',
  header,
  refCode,
  pulse = false,
  count,
  children,
  cta,
  compact = false,
  className,
  onClick,
}) => {
  const isAsks = variant === 'asks';

  return (
    <div
      className={cn(
        'hud-pane',
        isAsks && 'hud-pane--asks',
        compact && 'hud-pane--compact',
        onClick && 'cursor-pointer',
        className
      )}
      onClick={onClick}
    >
      {/* Header Strip */}
      {header && (
        <div className={cn('hud-pane__header', isAsks && 'hud-pane__header--asks')}>
          {isAsks ? (
            <Zap className="w-3.5 h-3.5 fill-current" />
          ) : pulse ? (
            <span className="hud-pane__pulse" />
          ) : null}
          <span className="hud-pane__label">{header}</span>
          <span className="grow" />
          {count !== undefined && (
            <span className="hud-pane__count">{count} OPEN</span>
          )}
          {refCode && <span className="hud-pane__ref">{refCode}</span>}
        </div>
      )}

      {/* Body */}
      <div className={cn('hud-pane__body', compact && 'hud-pane__body--compact')}>
        {children}
      </div>

      {/* CTA (asks variant) */}
      {cta && (
        <button
          className="hud-pane__cta"
          onClick={(e) => {
            e.stopPropagation();
            cta.onClick?.();
          }}
        >
          <span>{cta.label}</span>
          {cta.badge && <span className="hud-pane__cta-badge">{cta.badge}</span>}
        </button>
      )}
    </div>
  );
};

/**
 * Compact situation row for Today queue
 * Target height: 100-130px
 */
export interface SituationRowProps {
  /** Reference code (e.g., "A51CA54") */
  refCode: string;
  /** Need type (e.g., "URGENT SUPPORT") */
  type: string;
  /** Customer lifecycle (e.g., "ONBOARDING") */
  lifecycle?: string;
  /** Additional issues count */
  moreCount?: number;
  /** Time ago (e.g., "T-14H") */
  timestamp: string;
  /** Customer name */
  customerName: string;
  /** ARR display (e.g., "$150K ARR") */
  arr?: string;
  /** One-line story/headline */
  headline: string;
  onClick?: () => void;
  onHover?: () => void;
  isHovered?: boolean;
  className?: string;
}

export const SituationRow: React.FC<SituationRowProps> = ({
  refCode,
  type,
  lifecycle,
  moreCount,
  timestamp,
  customerName,
  arr,
  headline,
  onClick,
  onHover,
  isHovered,
  className,
}) => {
  const headerParts = [refCode];
  if (lifecycle) headerParts.push(lifecycle);
  headerParts.push(type);

  return (
    <div
      className={cn(
        'hud-pane hud-pane--compact',
        isHovered && 'hud-pane--hovered',
        className
      )}
      onClick={onClick}
      onMouseEnter={onHover}
    >
      {/* Header Strip */}
      <div className="hud-pane__header">
        <span className="hud-pane__label">
          {headerParts.join(' · ')}
          {moreCount && moreCount > 0 && (
            <span className="hud-pane__more">+{moreCount} MORE</span>
          )}
        </span>
        <span className="grow" />
        <span className="hud-pane__ref">{timestamp}</span>
      </div>

      {/* Body */}
      <div className="hud-pane__body hud-pane__body--compact">
        {/* Customer + ARR line */}
        <div className="hud-pane__title-row">
          <h3 className="hud-pane__customer">{customerName}</h3>
          {arr && <span className="hud-pane__arr">{arr}</span>}
        </div>
        {/* Story line - clamped to 2 lines */}
        <p className="hud-pane__story">{headline}</p>
      </div>
    </div>
  );
};

/**
 * Sidekick Asks Row for Today queue
 * Uses the "asks" variant with filled gold header
 */
export interface SidekickAsksRowProps {
  /** Customer name */
  customerName: string;
  /** Question count */
  questionCount: number;
  /** Brief description */
  description: string;
  /** Time ago */
  timestamp: string;
  onClick?: () => void;
  onAnswer?: () => void;
  className?: string;
}

export const SidekickAsksRow: React.FC<SidekickAsksRowProps> = ({
  customerName,
  questionCount,
  description,
  timestamp,
  onClick,
  onAnswer,
  className,
}) => {
  return (
    <div
      className={cn('hud-pane hud-pane--asks hud-pane--compact', className)}
      onClick={onClick}
    >
      {/* Header Strip - gold filled */}
      <div className="hud-pane__header hud-pane__header--asks">
        <Zap className="w-3.5 h-3.5 fill-current" />
        <span className="hud-pane__label">SIDEKICK NEEDS HELP</span>
        <span className="grow" />
        <span className="hud-pane__count">{questionCount} QUESTIONS</span>
      </div>

      {/* Body */}
      <div className="hud-pane__body hud-pane__body--compact">
        <div className="hud-pane__title-row">
          <h3 className="hud-pane__customer">{customerName}</h3>
          <span className="hud-pane__ref">{timestamp}</span>
        </div>
        <p className="hud-pane__story">{description}</p>
      </div>

      {/* CTA */}
      <button
        className="hud-pane__cta"
        onClick={(e) => {
          e.stopPropagation();
          onAnswer?.();
        }}
      >
        <span>Answer questions →</span>
        <span className="hud-pane__cta-badge">{questionCount} OPEN</span>
      </button>
    </div>
  );
};

/**
 * Grouped Asks Pane - When 2+ customers need Sidekick input
 * Collapses multiple asks into one pane with hairline-separated rows
 */
export interface GroupedAsksItem {
  id: string;
  customerName: string;
  customerId: string;
  context: string; // e.g., "Onboarding · new workspace"
  questionCount: number;
}

export interface GroupedAsksPaneProps {
  items: GroupedAsksItem[];
  totalQuestions: number;
  onItemClick?: (item: GroupedAsksItem) => void;
  onItemHover?: (item: GroupedAsksItem) => void;
  className?: string;
}

export const GroupedAsksPane: React.FC<GroupedAsksPaneProps> = ({
  items,
  totalQuestions,
  onItemClick,
  onItemHover,
  className,
}) => {
  return (
    <section className={cn('hud-pane hud-pane--asks hud-pane--asks-group', className)}>
      {/* Header Strip - gold filled */}
      <header className="hud-pane__header hud-pane__header--asks">
        <Zap className="w-3.5 h-3.5 fill-current" />
        <span className="hud-pane__label">SIDEKICK NEEDS HELP</span>
        <span className="grow" />
        <span className="hud-pane__ref">{items.length} CUSTOMERS · {totalQuestions} OPEN</span>
      </header>

      {/* Body with hairline-separated rows */}
      <div className="hud-pane__body">
        <ul className="asks-group__list">
          {items.map((item) => (
            <li
              key={item.id}
              className="asks-group__row"
              onClick={() => onItemClick?.(item)}
              onMouseEnter={() => onItemHover?.(item)}
            >
              <span className="asks-group__name">{item.customerName}</span>
              <span className="asks-group__ctx">{item.context}</span>
              <span className="asks-group__count">{item.questionCount} Qs</span>
              <button
                className="asks-group__action"
                onClick={(e) => {
                  e.stopPropagation();
                  onItemClick?.(item);
                }}
              >
                Answer →
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
};

export default HudPane;
