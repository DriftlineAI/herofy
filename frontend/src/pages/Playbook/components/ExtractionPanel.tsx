import React from 'react';
import { cn } from '@/lib/utils';
import { Pulse } from '@/components/ui/huds';

export interface ExtractionData {
  type: 'onboarding' | 'action';
  trigger: string;
  variables: string[];
  mandates: string[];
  guardrails: string[];
  sidekickAdds: string;
  updatedAt?: Date;
}

interface ExtractionPanelProps {
  extraction: ExtractionData;
  isExtracting?: boolean;
  className?: string;
}

/**
 * ExtractionPanel - Live AI extraction readout
 * Shows structured data extracted from prose with chips for each field
 * Used in PlaybookDescribe (Artboard 3)
 */
export function ExtractionPanel({
  extraction,
  isExtracting,
  className
}: ExtractionPanelProps) {
  const secondsAgo = extraction.updatedAt
    ? Math.floor((Date.now() - extraction.updatedAt.getTime()) / 1000)
    : 0;

  return (
    <div className={cn('pb-extract', className)}>
      {/* Header */}
      <div className="pb-extract__head">
        <Pulse />
        <span className="pb-extract__label">
          SIDEKICK · {isExtracting ? 'EXTRACTING' : 'EXTRACTED'}
        </span>
        {extraction.updatedAt && (
          <span className="pb-extract__time">
            UPDATED {secondsAgo} {secondsAgo === 1 ? 'SECOND' : 'SECONDS'} AGO
          </span>
        )}
      </div>

      {/* Body grid: 6 rows */}
      <div className="pb-extract__body">
        {/* Type */}
        <div className="pb-extract__row">
          <div className="pb-extract__key">Type</div>
          <div className="pb-extract__val">
            <span className={cn(
              'chip',
              extraction.type === 'onboarding' ? 'ok' : 'default'
            )}>
              {extraction.type.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Triggers when */}
        <div className="pb-extract__row">
          <div className="pb-extract__key">Triggers when</div>
          <div className="pb-extract__val">
            <span className="chip default">{extraction.trigger}</span>
          </div>
        </div>

        {/* Variables */}
        <div className="pb-extract__row">
          <div className="pb-extract__key">Variables I'll fill</div>
          <div className="pb-extract__val">
            {extraction.variables.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {extraction.variables.map((v, i) => (
                  <span key={i} className="chip default">{v}</span>
                ))}
              </div>
            ) : (
              <span className="text-charcoal-400">—</span>
            )}
          </div>
        </div>

        {/* Mandates */}
        <div className="pb-extract__row">
          <div className="pb-extract__key">Mandates</div>
          <div className="pb-extract__val">
            {extraction.mandates.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {extraction.mandates.map((m, i) => (
                  <span key={i} className="chip ok">{m}</span>
                ))}
              </div>
            ) : (
              <span className="text-charcoal-400">—</span>
            )}
          </div>
        </div>

        {/* Guardrails */}
        <div className="pb-extract__row">
          <div className="pb-extract__key">Guardrails</div>
          <div className="pb-extract__val">
            {extraction.guardrails.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {extraction.guardrails.map((g, i) => (
                  <span key={i} className="chip warn">{g}</span>
                ))}
              </div>
            ) : (
              <span className="text-charcoal-400">—</span>
            )}
          </div>
        </div>

        {/* What Sidekick adds */}
        <div className="pb-extract__row">
          <div className="pb-extract__key">What Sidekick adds</div>
          <div className="pb-extract__val">
            <span className="text-app-fg-200 text-sm">
              {extraction.sidekickAdds}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
