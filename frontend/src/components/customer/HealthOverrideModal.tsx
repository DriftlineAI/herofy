import React from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface HealthOverrideModalProps {
  isOpen: boolean;
  currentHealth: string | null;
  currentScore: number | null;
  currentReason: string | null;
  onClose: () => void;
  onSubmit: (data: {
    relationshipHealth: string;
    relationshipHealthScore: number;
    relationshipHealthReason: string;
  }) => void;
  isSubmitting: boolean;
}

const HEALTH_OPTIONS = [
  { value: 'strong', label: 'Strong', color: '#10b981', score: 90 },
  { value: 'healthy', label: 'Healthy', color: '#10b981', score: 75 },
  { value: 'stable', label: 'Stable', color: '#f59e0b', score: 50 },
  { value: 'at_risk', label: 'At Risk', color: '#d96942', score: 30 },
  { value: 'deteriorating', label: 'Deteriorating', color: '#d96942', score: 15 },
];

export function HealthOverrideModal({
  isOpen,
  currentHealth,
  currentScore,
  currentReason,
  onClose,
  onSubmit,
  isSubmitting,
}: HealthOverrideModalProps) {
  const [health, setHealth] = React.useState(currentHealth || 'stable');
  const [score, setScore] = React.useState(currentScore || 50);
  const [reason, setReason] = React.useState(currentReason || '');

  React.useEffect(() => {
    if (isOpen) {
      setHealth(currentHealth || 'stable');
      setScore(currentScore || 50);
      setReason(currentReason || '');
    }
  }, [isOpen, currentHealth, currentScore, currentReason]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (reason.trim()) {
      onSubmit({
        relationshipHealth: health,
        relationshipHealthScore: score,
        relationshipHealthReason: reason.trim(),
      });
    }
  };

  const selectedOption = HEALTH_OPTIONS.find(o => o.value === health) || HEALTH_OPTIONS[2];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/80" onClick={onClose} />
      <div className="relative bg-charcoal-900 border border-charcoal-700 w-full max-w-lg p-6">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-charcoal-500 hover:text-cream-200 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        <h2 className="text-xl font-serif text-cream-100 mb-2">
          Override Health Score
        </h2>
        <p className="text-sm text-charcoal-400 mb-6">
          This will override the AI-calculated health score. Provide a reason for the manual update.
        </p>

        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            {/* Health Selection */}
            <div>
              <label className="text-xs font-mono uppercase tracking-widest text-charcoal-400 block mb-3">
                Health Status
              </label>
              <div className="space-y-2">
                {HEALTH_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => {
                      setHealth(option.value);
                      setScore(option.score);
                    }}
                    className={cn(
                      'w-full text-left px-4 py-3 border transition-colors',
                      health === option.value
                        ? 'border-cream-200 bg-charcoal-800'
                        : 'border-charcoal-700 hover:border-charcoal-600'
                    )}
                  >
                    <span
                      className="font-medium"
                      style={{ color: option.color }}
                    >
                      {option.label}
                    </span>
                    <span className="text-charcoal-500 ml-2 text-sm">· {option.score}/100</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Score Adjustment */}
            <div>
              <label className="text-xs font-mono uppercase tracking-widest text-charcoal-400 block mb-2">
                Fine-tune Score: <span style={{ color: selectedOption.color }}>{score}/100</span>
              </label>
              <input
                type="range"
                min="0"
                max="100"
                value={score}
                onChange={(e) => setScore(parseInt(e.target.value))}
                className="w-full h-2 bg-charcoal-700 rounded-lg appearance-none cursor-pointer"
                style={{
                  accentColor: selectedOption.color,
                }}
              />
            </div>

            {/* Reason */}
            <div>
              <label className="text-xs font-mono uppercase tracking-widest text-charcoal-400 block mb-2">
                Reason for Override *
              </label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                required
                placeholder="Explain why you're overriding the AI score..."
                className="w-full bg-charcoal-800 border border-charcoal-700 px-3 py-2 text-cream-200 placeholder:text-charcoal-500 focus:outline-none focus:border-cream-400 font-sans"
              />
              <p className="text-xs text-charcoal-500 mt-1">
                This will be logged for audit purposes
              </p>
            </div>
          </div>

          <div className="flex gap-3 mt-6">
            <button
              type="submit"
              disabled={!reason.trim() || isSubmitting}
              className="flex-1 bg-rust-500 text-charcoal-900 px-4 py-2 font-medium hover:bg-rust-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? 'Saving...' : 'Confirm Override'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-charcoal-400 hover:text-cream-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
