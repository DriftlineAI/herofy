import { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Calendar as CalendarIcon } from 'lucide-react';
import { DayPicker } from 'react-day-picker';
import { format, parse } from 'date-fns';
import 'react-day-picker/dist/style.css';

// ============================================================================
// DateInput — shared click-to-open calendar (react-day-picker), themed to
// Midnight·Gold. Promoted out of sidekick/HITLComponents so any feature can use it.
// ============================================================================

export interface DateInputProps {
  value: string;                 // yyyy-MM-dd
  onChange: (value: string) => void;
  minDate?: string;              // yyyy-MM-dd
  maxDate?: string;              // yyyy-MM-dd
  placeholder?: string;
}

export function DateInput({ value, onChange, minDate, maxDate, placeholder }: DateInputProps) {
  const [isOpen, setIsOpen] = useState(false);
  const calendarRef = useRef<HTMLDivElement>(null);

  // Parse string dates to Date objects
  const selectedDate = value ? parse(value, 'yyyy-MM-dd', new Date()) : undefined;
  const minDateObj = minDate ? parse(minDate, 'yyyy-MM-dd', new Date()) : undefined;
  const maxDateObj = maxDate ? parse(maxDate, 'yyyy-MM-dd', new Date()) : undefined;

  const handleSelect = (date: Date | undefined) => {
    if (date) {
      const formatted = format(date, 'yyyy-MM-dd');
      onChange(formatted);
      setIsOpen(false);
    }
  };

  // Close on click outside - use setTimeout to let DayPicker's click handler fire first
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      setTimeout(() => {
        if (calendarRef.current && !calendarRef.current.contains(event.target as Node)) {
          setIsOpen(false);
        }
      }, 0);
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [isOpen]);

  const displayValue = selectedDate ? format(selectedDate, 'MMM d, yyyy') : placeholder || 'Select a date';

  // Build disabled date ranges
  // Always disable past dates (can't schedule in the past)
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Use backend minDate only if it's further in the future than today
  const effectiveMinDate = minDateObj && minDateObj > today ? minDateObj : today;

  // Only apply maxDate restriction if it's actually in the future
  // (ignore bad seed data where maxDate is in the past)
  const disabledDates = [
    { before: effectiveMinDate },
    ...(maxDateObj && maxDateObj >= today ? [{ after: maxDateObj }] : []),
  ];

  return (
    <div className="relative">
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "flex items-center gap-3 px-4 py-3 border-2 transition-all",
          "bg-page text-fg-200",
          selectedDate
            ? "border-accent bg-accent/10"
            : "border-border hover:border-border-strong"
        )}
      >
        <CalendarIcon className="w-4 h-4 text-accent" />
        <span className={cn(
          "font-mono text-sm",
          !selectedDate && "italic text-fg-400"
        )}>
          {displayValue}
        </span>
      </button>

      {/* Calendar dropdown */}
      {isOpen && (
        <div
          ref={calendarRef}
          className="absolute z-50 mt-2 p-4 bg-page border-2 border-border shadow-xl"
        >
          <style>
            {`
              .rdp {
                --rdp-cell-size: 40px;
                --rdp-accent-color: var(--color-accent);
                --rdp-background-color: var(--color-accent);
                margin: 0;
              }

              .rdp-months {
                color: var(--color-fg-100);
              }

              .rdp-head_cell {
                color: var(--color-fg-400);
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.05em;
              }

              .rdp-caption {
                color: var(--color-fg-100);
                margin-bottom: 1rem;
              }

              .rdp-day {
                color: var(--color-fg-200);
                font-size: 13px;
              }

              .rdp-day:hover:not(.rdp-day_selected):not(.rdp-day_disabled) {
                background-color: var(--color-surface-2) !important;
                color: var(--color-fg-100) !important;
              }

              /* Selected day - target ALL possible selectors for the blue circle */
              .rdp-day_selected,
              .rdp-day_selected:hover,
              .rdp-day_selected:focus,
              .rdp-day_selected:active,
              .rdp-selected,
              .rdp-selected .rdp-day_button,
              .rdp-button[aria-selected="true"],
              button.rdp-day_selected,
              button[aria-selected="true"] {
                background-color: var(--color-accent) !important;
                color: var(--color-page) !important;
                font-weight: 600 !important;
                border: none !important;
                outline: none !important;
                box-shadow: none !important;
              }

              /* Today's date - accent text, no blue */
              .rdp-day_today,
              .rdp-day_today .rdp-day_button,
              .rdp-today,
              .rdp-day_today:not(.rdp-day_selected),
              .rdp-day_today:not(.rdp-day_selected) .rdp-day_button,
              button.rdp-day_today:not(.rdp-day_selected) {
                font-weight: 600 !important;
                color: var(--color-accent) !important;
                background-color: transparent !important;
                border: none !important;
                outline: none !important;
                box-shadow: none !important;
              }

              .rdp-day_disabled {
                color: var(--color-fg-400);
                opacity: 0.5;
                cursor: not-allowed;
              }

              .rdp-day_outside {
                color: var(--color-fg-400);
              }

              .rdp-button:hover:not([disabled]):not(.rdp-day_selected) {
                background-color: var(--color-surface-2);
              }

              /* Navigation arrows */
              .rdp-nav_button {
                color: var(--color-accent) !important;
              }

              .rdp-nav_button:hover {
                background-color: var(--color-surface-2) !important;
              }

              .rdp-chevron {
                fill: var(--color-accent) !important;
              }
            `}
          </style>
          <DayPicker
            mode="single"
            selected={selectedDate}
            onSelect={handleSelect}
            disabled={disabledDates.length > 0 ? disabledDates : undefined}
            defaultMonth={selectedDate || new Date()}
            showOutsideDays
          />
        </div>
      )}
    </div>
  );
}
