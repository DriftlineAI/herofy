import React from 'react';
import { Zap, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Sidekick Atoms - The AI voice in five states
 *
 * All share: 2px rust left-border + mono tag breaking the top edge
 * Differ in: tag wording, pulse state, and what sits below the body
 *
 * Per ai-atoms.jsx design from Claude Design export.
 */

// Sidekick Sigil (lightning bolt)
export const SkSigil: React.FC<{ size?: number; className?: string }> = ({
  size = 11,
  className
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="currentColor"
    aria-hidden="true"
    className={className}
  >
    <path d="M13 2L4.09 12.97a1 1 0 00.78 1.63H11l-1 7.4 8.91-10.97a1 1 0 00-.78-1.63H13L13 2z" />
  </svg>
);

// Base Sidekick component structure
interface SidekickBaseProps {
  children: React.ReactNode;
  className?: string;
}

const SidekickBase: React.FC<SidekickBaseProps & { variant: string; tag: React.ReactNode }> = ({
  children,
  className,
  variant,
  tag
}) => (
  <div className={cn('sk', variant, className)}>
    <div className="sk__tag">{tag}</div>
    {children}
  </div>
);

// 1. TIP - The original. Factual suggestion. No action needed.
interface SidekickTipProps {
  children: React.ReactNode;
  className?: string;
}

export const SidekickTip: React.FC<SidekickTipProps> = ({ children, className }) => (
  <SidekickBase
    variant="sk--tip"
    className={className}
    tag={
      <>
        <SkSigil />
        <span>Sidekick</span>
      </>
    }
  >
    <p className="sk__body">
      <strong>Tip:</strong> {children}
    </p>
  </SidekickBase>
);

// 2. ASKING - Needs a human answer to unblock an agent
interface SidekickAskingProps {
  question: string;
  why?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export const SidekickAsking: React.FC<SidekickAskingProps> = ({
  question,
  why,
  children,
  footer,
  className
}) => (
  <SidekickBase
    variant="sk--ask"
    className={className}
    tag={
      <>
        <SkSigil />
        <span>Sidekick · Asking</span>
      </>
    }
  >
    <p className="sk__question">{question}</p>
    {children}
    {why && (
      <div className="sk__why">
        <span className="sk__why-label">Why this matters</span>
        {why}
      </div>
    )}
    {footer}
  </SidekickBase>
);

// 3. OBSERVED - Factual note. Quieter than TIP, no recommendation.
interface SidekickObservedProps {
  children: React.ReactNode;
  timestamp?: string;
  className?: string;
}

export const SidekickObserved: React.FC<SidekickObservedProps> = ({
  children,
  timestamp,
  className
}) => (
  <SidekickBase
    variant="sk--obs"
    className={className}
    tag={
      <>
        <SkSigil />
        <span>Sidekick · Observed</span>
        {timestamp && (
          <span className="text-fg-400 ml-1.5">{timestamp}</span>
        )}
      </>
    }
  >
    <p className="sk__body">{children}</p>
  </SidekickBase>
);

// 4. WORKING - Agent is running. Live pulse + current step.
interface SidekickWorkingProps {
  task: string;
  step: string;
  stepNum: number;
  total: number;
  className?: string;
}

export const SidekickWorking: React.FC<SidekickWorkingProps> = ({
  task,
  step,
  stepNum,
  total,
  className
}) => (
  <SidekickBase
    variant="sk--work"
    className={className}
    tag={
      <>
        <span className="pulse continuous" style={{ background: 'transparent', width: 8, height: 8 }} />
        <span>Sidekick · Working</span>
      </>
    }
  >
    <p className="sk__body" style={{ margin: 0 }}>{task}</p>
    <div className="sk__step">
      <span className="text-accent">{stepNum}/{total}</span>
      <span className="text-fg-400">//</span>
      <span>{step}</span>
    </div>
    <div className="sk__progress">
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={i < stepNum - 1 ? 'on' : i === stepNum - 1 ? 'cur' : ''}
        />
      ))}
    </div>
  </SidekickBase>
);

// 5. RESOLVED - History. Dimmed, with resolution + by-line.
interface SidekickResolvedProps {
  question: string;
  resolution: string;
  by: string;
  timestamp: string;
  className?: string;
}

export const SidekickResolved: React.FC<SidekickResolvedProps> = ({
  question,
  resolution,
  by,
  timestamp,
  className
}) => (
  <SidekickBase
    variant="sk--done"
    className={className}
    tag={
      <>
        <Check className="w-[11px] h-[11px]" strokeWidth={2.5} />
        <span>Sidekick · Resolved</span>
      </>
    }
  >
    <p className="sk__body text-fg-400 text-[14px] m-0">
      {question}
    </p>
    <p className="sk__resolution">{resolution}</p>
    <div className="sk__by">
      <span>{by}</span>
      <span className="text-fg-400">·</span>
      <span>{timestamp}</span>
    </div>
  </SidekickBase>
);

// HITL Answer Affordances - Option component for questions
interface SidekickOptionProps {
  name: string;
  role: string;
  signal: 'engaged' | 'neutral' | 'cooling';
  last: string;
  avatar: string;
  onSelect?: () => void;
  className?: string;
}

export const SidekickOption: React.FC<SidekickOptionProps> = ({
  name,
  role,
  signal,
  last,
  avatar,
  onSelect,
  className
}) => (
  <button className={cn('sk-option', className)} onClick={onSelect}>
    <span className="sk-option__avatar">
      <img
        src={`https://api.dicebear.com/7.x/adventurer/svg?seed=${avatar}`}
        alt={name}
      />
    </span>
    <div>
      <div className="sk-option__name">{name}</div>
      <div className="sk-option__role">{role}</div>
    </div>
    <div className="sk-option__meta">
      <div
        className="sk-option__signal"
        style={{
          color: signal === 'engaged' ? 'var(--color-signal-ok)' : 'var(--color-fg-400)'
        }}
      >
        {signal}
      </div>
      <div className="sk-option__last">{last}</div>
    </div>
  </button>
);

export default {
  SkSigil,
  SidekickTip,
  SidekickAsking,
  SidekickObserved,
  SidekickWorking,
  SidekickResolved,
  SidekickOption,
};
