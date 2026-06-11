import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { Check } from 'lucide-react';
import type { QuestionOption, PersonOption } from '@/lib/api';

// ============================================================================
// HITLChip - Single or multi-select chip button
// ============================================================================

interface HITLChipProps {
  children: React.ReactNode;
  selected: boolean;
  onClick: () => void;
  multi?: boolean;
  decide?: boolean;
  other?: boolean;
}

export function HITLChip({ children, selected, onClick, multi, decide, other }: HITLChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-2 px-4 py-2 border-2 font-sans text-sm transition-all',
        'hover:border-accent/60',
        selected
          ? decide
            ? 'border-accent bg-accent/10 text-accent'
            : other
              ? 'border-fg-400 bg-surface-2 text-fg-200'
              : 'border-accent bg-accent/10 text-fg-100'
          : 'border-border bg-page text-fg-400'
      )}
    >
      {multi && !decide && !other && (
        <span className={cn(
          'flex items-center justify-center w-4 h-4 border-2 transition-colors',
          selected
            ? 'border-accent bg-accent text-page'
            : 'border-border-strong bg-page'
        )}>
          {selected && <Check className="w-3 h-3" strokeWidth={3.5} />}
        </span>
      )}
      {!multi && !decide && !other && (
        <span className={cn(
          'w-4 h-4 rounded-full border-2 relative transition-colors',
          selected
            ? 'border-accent'
            : 'border-border-strong'
        )}>
          {selected && (
            <span className="absolute inset-1 rounded-full bg-accent" />
          )}
        </span>
      )}
      <span>{children}</span>
    </button>
  );
}

// ============================================================================
// HITLQuestion - Question wrapper with numbered gutter
// ============================================================================

interface HITLQuestionProps {
  number: string;
  title: React.ReactNode;
  sub?: React.ReactNode;
  hint?: string;
  children: React.ReactNode;
}

export function HITLQuestion({ number, title, sub, hint, children }: HITLQuestionProps) {
  return (
    <div className="relative pl-20">
      {/* Numbered gutter */}
      <div className="absolute left-0 top-0">
        <div className="text-right">
          <div className="font-serif italic text-4xl text-accent/40 leading-none">
            {number}
          </div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-fg-400 mt-1">
            QUESTION
          </div>
        </div>
      </div>

      {/* Question content */}
      <div>
        <h3 className="text-xl text-fg-100 mb-2 leading-relaxed">
          {title}
        </h3>
        {sub && (
          <p className="text-fg-300 text-sm mb-4 leading-relaxed">
            {sub}
          </p>
        )}
        {hint && (
          <div className="text-[10px] font-mono uppercase tracking-widest text-accent/60 mb-3">
            {hint}
          </div>
        )}
        <div className="mt-4">
          {children}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// HITLPickOne - Single-select chips + decide + other
// ============================================================================

interface HITLPickOneProps {
  options: QuestionOption[];
  value: string;
  onChange: (value: string) => void;
  decideLabel?: string;
}

export function HITLPickOne({ options, value, onChange, decideLabel = "Sidekick, you decide" }: HITLPickOneProps) {
  const [otherOpen, setOtherOpen] = useState(false);
  const [otherText, setOtherText] = useState('');

  const handleDecide = () => {
    onChange('__DECIDE__');
    setOtherOpen(false);
  };

  const handleOther = () => {
    setOtherOpen(true);
    onChange('__OTHER__');
  };

  const handleOtherTextChange = (text: string) => {
    setOtherText(text);
    onChange(`__OTHER__:${text}`);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {options.map((option, i) => (
          <HITLChip
            key={i}
            selected={value === option.value && !otherOpen}
            onClick={() => {
              onChange(option.value);
              setOtherOpen(false);
            }}
          >
            {option.label}
          </HITLChip>
        ))}
        <HITLChip
          decide
          selected={value === '__DECIDE__'}
          onClick={handleDecide}
        >
          {decideLabel}
        </HITLChip>
        <HITLChip
          other
          selected={otherOpen}
          onClick={handleOther}
        >
          Other
        </HITLChip>
      </div>
      {otherOpen && (
        <input
          type="text"
          value={otherText}
          onChange={(e) => handleOtherTextChange(e.target.value)}
          placeholder="Tell Sidekick..."
          autoFocus
          className="w-full bg-page border-b-2 border-border-strong focus:border-accent px-2 py-2 text-fg-200 placeholder-fg-400 focus:outline-none transition-colors"
        />
      )}
    </div>
  );
}

// ============================================================================
// HITLPickMany - Multi-select chips
// ============================================================================

interface HITLPickManyProps {
  options: QuestionOption[];
  value: string[];
  onChange: (values: string[]) => void;
}

export function HITLPickMany({ options, value, onChange }: HITLPickManyProps) {
  const [otherOpen, setOtherOpen] = useState(false);
  const [otherText, setOtherText] = useState('');

  const toggle = (optionValue: string) => {
    const newValue = value.includes(optionValue)
      ? value.filter(v => v !== optionValue)
      : [...value, optionValue];
    onChange(newValue);
  };

  const handleOtherTextChange = (text: string) => {
    setOtherText(text);
    const filtered = value.filter(v => !v.startsWith('__OTHER__:'));
    if (text.trim()) {
      onChange([...filtered, `__OTHER__:${text}`]);
    } else {
      onChange(filtered);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {options.map((option, i) => (
          <HITLChip
            key={i}
            multi
            selected={value.includes(option.value)}
            onClick={() => toggle(option.value)}
          >
            {option.label}
          </HITLChip>
        ))}
        <HITLChip
          other
          selected={otherOpen}
          onClick={() => setOtherOpen(!otherOpen)}
        >
          Other
        </HITLChip>
      </div>
      {otherOpen && (
        <input
          type="text"
          value={otherText}
          onChange={(e) => handleOtherTextChange(e.target.value)}
          placeholder="Anything else?"
          autoFocus
          className="w-full bg-page border-b-2 border-border-strong focus:border-accent px-2 py-2 text-fg-200 placeholder-fg-400 focus:outline-none transition-colors"
        />
      )}
    </div>
  );
}

// ============================================================================
// HITLPickPerson - Avatar-rich person picker
// ============================================================================

interface HITLPickPersonProps {
  people: PersonOption[];
  value: string;
  onChange: (personName: string) => void;
}

export function HITLPickPerson({ people, value, onChange }: HITLPickPersonProps) {
  const [decideMode, setDecideMode] = useState(false);
  const [manualMode, setManualMode] = useState(false);

  const getSignalColor = (signal?: string) => {
    switch (signal) {
      case 'ok': return 'text-signal-ok';
      case 'warn': return 'text-signal-warn';
      default: return 'text-fg-400';
    }
  };

  const handleDecide = () => {
    setDecideMode(true);
    setManualMode(false);
    onChange('__DECIDE__');
  };

  const handleManual = () => {
    setManualMode(true);
    setDecideMode(false);
    onChange('__MANUAL__');
  };

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {people.map((person, i) => (
          <button
            key={i}
            type="button"
            onClick={() => {
              setDecideMode(false);
              setManualMode(false);
              onChange(person.name);
            }}
            className={cn(
              'w-full flex items-center gap-4 p-4 border-2 transition-all text-left',
              value === person.name && !decideMode && !manualMode
                ? 'border-accent bg-accent/10'
                : 'border-border bg-page hover:border-border-strong'
            )}
          >
            {/* Avatar */}
            <div className="w-12 h-12 rounded-full overflow-hidden bg-surface-2 shrink-0">
              <img
                src={`https://api.dicebear.com/7.x/adventurer/svg?seed=${person.avatar_seed}`}
                alt={person.name}
                className="w-full h-full"
              />
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="text-fg-100 font-medium">{person.name}</div>
              <div className="text-fg-400 text-sm">{person.role}</div>
            </div>

            {/* Meta */}
            <div className="text-right shrink-0">
              {person.signal_label && (
                <div className={cn(
                  'text-[10px] font-mono uppercase tracking-widest mb-1',
                  getSignalColor(person.signal)
                )}>
                  {person.signal_label}
                </div>
              )}
              {person.last_contact && (
                <div className="text-xs text-fg-400">
                  {person.last_contact}
                </div>
              )}
            </div>
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <HITLChip
          decide
          selected={decideMode}
          onClick={handleDecide}
        >
          Neither — Sidekick, suggest a third
        </HITLChip>
        <HITLChip
          other
          selected={manualMode}
          onClick={handleManual}
        >
          I'll add manually
        </HITLChip>
      </div>
    </div>
  );
}

// ============================================================================
// HITLFreeform - Editorial underline textarea
// ============================================================================

interface HITLFreeformProps {
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}

export function HITLFreeform({ placeholder, value, onChange }: HITLFreeformProps) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={3}
      className="w-full bg-transparent border-b-2 border-border-strong focus:border-accent px-2 py-3 text-fg-200 placeholder-fg-400 focus:outline-none transition-colors resize-none font-serif italic text-lg leading-relaxed"
    />
  );
}

// ============================================================================
// HITLSlider - Rust track + label
// ============================================================================

interface HITLSliderProps {
  min: number;
  max: number;
  value: number;
  onChange: (value: number) => void;
  labelLow: string;
  labelHigh: string;
  format?: (value: number) => string;
}

export function HITLSlider({ min, max, value, onChange, labelLow, labelHigh, format }: HITLSliderProps) {
  const percentage = ((value - min) / (max - min)) * 100;

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    const newValue = Math.round(min + ratio * (max - min));
    onChange(newValue);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-fg-400">{labelLow}</span>
        <span className="text-lg font-mono text-accent">
          {format ? format(value) : value}
        </span>
        <span className="text-xs text-fg-400">{labelHigh}</span>
      </div>

      <div
        className="relative h-2 bg-surface-2 cursor-pointer group"
        onClick={handleClick}
      >
        {/* Fill */}
        <div
          className="absolute inset-y-0 left-0 bg-accent transition-all"
          style={{ width: `${percentage}%` }}
        />

        {/* Thumb */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-5 h-5 bg-accent border-2 border-page rounded-full transition-all group-hover:scale-110"
          style={{ left: `${percentage}%`, transform: `translate(-50%, -50%)` }}
        />
      </div>
    </div>
  );
}

// ============================================================================
// HITLYesNo - Yes/No choice with "Neither" escape hatch for misclassified questions
// ============================================================================

interface HITLYesNoProps {
  value: string;
  onChange: (value: string) => void;
  yesLabel?: string;
  noLabel?: string;
  allowDecide?: boolean;
  neitherLabel?: string;
}

export function HITLYesNo({
  value,
  onChange,
  yesLabel = "Yes",
  noLabel = "No",
  allowDecide = false,
  neitherLabel = "Neither / Other"
}: HITLYesNoProps) {
  // Check if this is a "neither" response (starts with text: prefix or is custom text)
  const isNeither = value.startsWith('text:') || (value !== '' && value !== 'yes' && value !== 'no' && value !== '__DECIDE__');
  const neitherText = isNeither ? (value.startsWith('text:') ? value.slice(5) : value) : '';

  const handleNeitherClick = () => {
    if (!isNeither) {
      onChange('text:');
    }
  };

  const handleNeitherTextChange = (text: string) => {
    onChange(`text:${text}`);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <HITLChip
          selected={value === 'yes'}
          onClick={() => onChange('yes')}
        >
          {yesLabel}
        </HITLChip>
        <HITLChip
          selected={value === 'no'}
          onClick={() => onChange('no')}
        >
          {noLabel}
        </HITLChip>
        <HITLChip
          other
          selected={isNeither}
          onClick={handleNeitherClick}
        >
          {neitherLabel}
        </HITLChip>
        {allowDecide && (
          <HITLChip
            decide
            selected={value === '__DECIDE__'}
            onClick={() => onChange('__DECIDE__')}
          >
            Sidekick, you decide
          </HITLChip>
        )}
      </div>

      {/* Text input for "Neither" - always show when neither is selected */}
      {isNeither && (
        <div className="pl-0">
          <textarea
            value={neitherText}
            onChange={(e) => handleNeitherTextChange(e.target.value)}
            placeholder="Type your answer..."
            className="w-full min-h-[80px] px-4 py-3 bg-page border-2 border-border text-fg-100 placeholder-fg-400 font-sans text-sm focus:outline-none focus:border-accent/60 resize-y"
            autoFocus
          />
        </div>
      )}
    </div>
  );
}
