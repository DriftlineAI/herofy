import React from 'react';
import { cn } from '@/lib/utils';

interface ScopeToggleProps {
  value: 'customer' | 'playbook';
  onChange: (scope: 'customer' | 'playbook') => void;
  customerName: string;
  playbookSlug: string;
  affectedCustomers: number;
}

/**
 * ScopeToggle - The centerpiece of the editing screen
 * TWO option cards: Override for customer only vs Edit the playbook itself
 * This is a crucial decision point - make both options equally legible
 */
export function ScopeToggle({
  value,
  onChange,
  customerName,
  playbookSlug,
  affectedCustomers
}: ScopeToggleProps) {
  return (
    <div className="pb-step-scope">
      <div className="pb-step-scope__divider">SAVE SCOPE</div>

      <div className="pb-step-scope__options">
        {/* Override for customer only */}
        <button
          onClick={() => onChange('customer')}
          className={cn(
            'pb-step-scope__opt',
            value === 'customer' && 'is-selected'
          )}
        >
          <div className="pb-step-scope__radio">
            {value === 'customer' && <div className="pb-step-scope__radio-dot" />}
          </div>
          <div className="pb-step-scope__opt-content">
            <div className="pb-step-scope__opt-label">
              Override for {customerName} only
            </div>
            <div className="pb-step-scope__opt-sub">
              Playbook stays the same. This change lives on {customerName}'s record.
              You can reset it anytime.
            </div>
          </div>
        </button>

        {/* Edit the playbook itself */}
        <button
          onClick={() => onChange('playbook')}
          className={cn(
            'pb-step-scope__opt',
            value === 'playbook' && 'is-selected'
          )}
        >
          <div className="pb-step-scope__radio">
            {value === 'playbook' && <div className="pb-step-scope__radio-dot" />}
          </div>
          <div className="pb-step-scope__opt-content">
            <div className="pb-step-scope__opt-label">
              Edit the playbook itself
            </div>
            <div className="pb-step-scope__opt-sub">
              Affects every customer on {playbookSlug}
              {affectedCustomers > 0 && (
                <> ({affectedCustomers} {affectedCustomers === 1 ? 'customer' : 'customers'})</>
              )}.
              I'll surface a diff to your teammates before going live.
            </div>
          </div>
        </button>
      </div>
    </div>
  );
}
