import { AnimatePresence, motion } from 'framer-motion';
import { SupportContextRail } from './SupportContextRail';
import { OnboardingContextRail } from './OnboardingContextRail';
import { RenewalContextRail } from './RenewalContextRail';
import type { ThreadDetail, NeedType } from '@/lib/api';

interface ContextRailProps {
  thread: ThreadDetail;
}

type RailCategory = 'support' | 'onboarding' | 'renewal';

function determineRailCategory(thread: ThreadDetail): RailCategory {
  const { need_type, customer } = thread;

  // First check need type
  if (need_type) {
    const supportTypes: NeedType[] = [
      'urgent_support',
      'frustrated_signal',
      'escalation',
      'draft_response_ready',
      'going_dark',
      'check_in_due',
      'positive_signal',
      'expansion_signal',
    ];
    const onboardingTypes: NeedType[] = [
      'onboarding_behind',
      'stalled_milestone',
      'new_handoff',
      'plan_approval_required',
    ];
    const renewalTypes: NeedType[] = [
      'approaching_renewal',
      'renewal_at_risk',
      'meeting_prep_ready',
      'champion_departed',
    ];

    if (onboardingTypes.includes(need_type)) return 'onboarding';
    if (renewalTypes.includes(need_type)) return 'renewal';
    if (supportTypes.includes(need_type)) return 'support';
  }

  // Fall back to customer lifecycle
  if (customer.lifecycle === 'onboarding' || customer.lifecycle === 'handoff') {
    return 'onboarding';
  }
  if (customer.lifecycle === 'renewing' || customer.lifecycle === 'at_risk') {
    return 'renewal';
  }

  // Default to support
  return 'support';
}

export function ContextRail({ thread }: ContextRailProps) {
  const category = determineRailCategory(thread);

  return (
    <div className="h-full bg-charcoal-900 border-l border-charcoal-700">
      <AnimatePresence mode="wait">
        {category === 'support' && (
          <motion.div
            key="support"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.2 }}
            className="h-full"
          >
            <SupportContextRail thread={thread} />
          </motion.div>
        )}
        {category === 'onboarding' && (
          <motion.div
            key="onboarding"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.2 }}
            className="h-full"
          >
            <OnboardingContextRail thread={thread} />
          </motion.div>
        )}
        {category === 'renewal' && (
          <motion.div
            key="renewal"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.2 }}
            className="h-full"
          >
            <RenewalContextRail thread={thread} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export { determineRailCategory };
