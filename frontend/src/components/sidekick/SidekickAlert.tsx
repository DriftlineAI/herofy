import React from 'react';
import { Zap, HelpCircle } from 'lucide-react';
import { motion } from 'motion/react';

interface SidekickAlertProps {
  customer: string;
  items: string[];
  onAction: () => void;
}

export function SidekickAlert({ customer, items, onAction }: SidekickAlertProps) {
  const questionCount = items.length;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden border-2 border-rust-500/50 bg-gradient-to-r from-rust-900/30 to-charcoal-800"
    >
      {/* Background pattern */}
      <div className="absolute inset-0 opacity-5 pointer-events-none">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `repeating-linear-gradient(
              45deg,
              transparent,
              transparent 10px,
              rgba(217, 105, 66, 0.3) 10px,
              rgba(217, 105, 66, 0.3) 11px
            )`,
          }}
        />
      </div>

      {/* Content */}
      <div className="relative z-10 flex items-center gap-4 p-4">
        {/* Icon */}
        <div className="flex items-center justify-center w-10 h-10 rounded-full bg-rust-500/20 border border-rust-500/50 shrink-0">
          <Zap className="w-5 h-5 text-rust-400 fill-rust-400" />
        </div>

        {/* Message */}
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-[10px] uppercase tracking-widest font-bold text-rust-400">
              Sidekick Needs Help
            </span>
            <span className="text-charcoal-500">//</span>
            <span className="font-mono text-[10px] uppercase tracking-widest text-rust-400/80">
              {questionCount} Question{questionCount !== 1 ? 's' : ''}
            </span>
          </div>
          <p className="text-sm text-cream-200">
            Sidekick has questions about <span className="font-medium text-cream-100">{customer}</span> that need your input
          </p>
          {items.length > 0 && (
            <p className="text-xs text-charcoal-400 mt-1 italic">
              "{items[0]}"
              {items.length > 1 && ` +${items.length - 1} more`}
            </p>
          )}
        </div>

        {/* Action Button */}
        <button
          onClick={onAction}
          className="inline-flex items-center gap-2 bg-rust-500 hover:bg-rust-400 text-charcoal-900 px-4 py-2 font-mono text-xs uppercase tracking-widest font-bold transition-colors shrink-0"
        >
          <HelpCircle className="w-4 h-4" />
          <span>Answer</span>
        </button>
      </div>
    </motion.div>
  );
}

export default SidekickAlert;
