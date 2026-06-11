import React from 'react';
import { cn } from '@/lib/utils';

export interface VariableResolution {
  key: string;
  value: string;
}

interface ProvenanceAsideProps {
  variables: VariableResolution[];
  className?: string;
}

/**
 * ProvenanceAside - Shows variable resolution for a customer plan
 * Used in PlaybookRunning (Artboard 6)
 */
export function ProvenanceAside({ variables, className }: ProvenanceAsideProps) {
  return (
    <div className={cn('pb-provenance', className)}>
      <h3 className="text-xs font-mono uppercase tracking-widest text-app-fg-400 mb-4">
        Provenance
      </h3>

      <p className="text-sm text-app-fg-300 leading-relaxed mb-6">
        Every step traces back to a line in the playbook. Edit the playbook and
        Acme's plan updates next run — or override just for Acme.
      </p>

      {/* Variables panel */}
      <div className="pb-provenance__vars">
        <div className="pb-provenance__vars-head">
          VARIABLES SIDEKICK FILLED
        </div>
        <div className="pb-provenance__vars-body">
          {variables.map((v, i) => (
            <div key={i} className="pb-provenance__var-row">
              <span className="pb-provenance__var-key">{v.key}</span>
              <span className="pb-provenance__var-arrow">→</span>
              <span className="pb-provenance__var-val">{v.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
