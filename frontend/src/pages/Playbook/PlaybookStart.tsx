import React from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { SectionOpener, StarterTile, CatalogCard } from './components';

const CATALOG_PLAYBOOKS = [
  {
    type: 'onboarding' as const,
    strict: true,
    title: 'Enterprise onboarding · 90-day',
    description: 'Higher-touch customer. Measured milestones at week 2, 6, 12.',
  },
  {
    type: 'onboarding' as const,
    strict: true,
    title: 'SMB fast path · 14-day',
    description: 'Self-serve first. Three checkpoints. No custom config.',
  },
  {
    type: 'onboarding' as const,
    strict: true,
    title: 'Implementation kickoff',
    description: 'For devtools with mandatory SSO. ~30d to prod.',
  },
  {
    type: 'action' as const,
    strict: false,
    title: 'Save-the-account',
    description: 'Churn risk is real and concrete — escalate risk & AI open framework.',
  },
  {
    type: 'action' as const,
    strict: false,
    title: 'Going-dark revival',
    description: 'Re-engagement innings. Three touch-point steps. Note nuances.',
  },
  {
    type: 'action' as const,
    strict: false,
    title: 'Expansion conversation',
    description: 'When usage trends suggest seat or module upsell. Light, opportunistic.',
  },
];

/**
 * PlaybookStart (Artboard 2) - Three entry points + starter catalog
 * The "new playbook" landing with featured tiles and 6-card catalog
 */
export function PlaybookStart() {
  const navigate = useNavigate();

  const handleCatalogSelect = (index: number) => {
    // TODO: Pre-fill editor with selected catalog playbook
    navigate('/app/handbook/playbooks/new/describe', {
      state: { catalogIndex: index },
    });
  };

  return (
    <div className="max-w-7xl mx-auto px-8 py-12">
      {/* Breadcrumb header */}
      <div className="font-mono text-xs uppercase tracking-wider text-app-fg-400 flex items-center gap-2 mb-8">
        <Link to="/app/handbook" className="hover:text-rust-500 transition-colors">
          Handbook
        </Link>
        <span>/</span>
        <Link to="/app/handbook/playbooks" className="hover:text-rust-500 transition-colors">
          Playbooks
        </Link>
        <span>/</span>
        <span className="text-app-fg-200">New</span>
      </div>

      <SectionOpener label="NEW PLAYBOOK" />

      {/* Hero */}
      <div className="mb-8">
        <h1 className="font-serif text-[44px] font-medium leading-tight tracking-tight text-app-fg-100 mb-3">
          Three ways to start.
        </h1>
        <p className="font-serif italic text-lg text-app-fg-300 max-w-3xl">
          The fastest is to describe what good looks like — Sidekick fills in the scaffolding.
        </p>
      </div>

      {/* Three tiles */}
      <div className="pb-start">
        <StarterTile
          featured
          eyebrow="FASTEST · 60 SECONDS"
          title="Describe it to Sidekick"
          subtitle="Write a paragraph. When a new enterprise customer signs, describe what good looks like in their first 90 days. Sidekick extracts outcomes, mandates, and variables in real time."
          cta="OPEN THE EDITOR →"
          to="/app/handbook/playbooks/new/describe"
        />

        <StarterTile
          title="Start from a starter"
          subtitle="Six common motions, specialized by your team. Fork one and roll — most playbooks land in the catalog within 30 minutes."
          cta="BROWSE CATALOG →"
          to="#catalog"
        />

        <StarterTile
          title="Import from Notion"
          subtitle="Paste a Notion link or drop a markdown export. Sidekick reads it for the bits that matter — outcomes, mandates, guardrails."
          cta="IMPORT →"
          to="/app/handbook/playbooks/new/import"
        />
      </div>

      {/* Starter catalog */}
      <div className="mt-20" id="catalog">
        <SectionOpener label="STARTER CATALOG" />

        <div className="pb-catalog">
          {CATALOG_PLAYBOOKS.map((playbook, index) => (
            <CatalogCard
              key={index}
              type={playbook.type}
              strict={playbook.strict}
              title={playbook.title}
              description={playbook.description}
              onClick={() => handleCatalogSelect(index)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
