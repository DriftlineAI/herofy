import React from 'react';

/**
 * SectionOpener - The signature visual pattern used across all playbook artboards
 * Renders: ——— [LABEL] ————————————————
 * A 48px rust hairline + mono eyebrow text + hairline filling the rest
 */
export function SectionOpener({ label }: { label: string }) {
  return (
    <div className="pb-section-opener">
      <div className="pb-section-opener__seed" />
      <span className="pb-section-opener__label">{label}</span>
      <div className="pb-section-opener__line" />
    </div>
  );
}
