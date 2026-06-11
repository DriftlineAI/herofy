import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { SectionOpener, ExtractionPanel } from './components';
import type { ExtractionData } from './components';

/**
 * PlaybookDescribe (Artboard 3) - AI authoring with live extraction
 * User writes prose. Sidekick parses it live into structured fields.
 */
export function PlaybookDescribe() {
  const navigate = useNavigate();
  const [prose, setProse] = useState('');
  const [isExtracting, setIsExtracting] = useState(false);
  const [extraction, setExtraction] = useState<ExtractionData>({
    type: 'onboarding',
    trigger: 'new enterprise customer signs',
    variables: [],
    mandates: [],
    guardrails: [],
    sidekickAdds: 'Structure and step sequencing based on the outcomes you describe.',
  });

  const debounceTimeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Debounced extraction (600ms after typing stops)
  useEffect(() => {
    if (!prose.trim()) return;

    clearTimeout(debounceTimeout.current);
    debounceTimeout.current = setTimeout(() => {
      extractStructure(prose);
    }, 600);

    return () => clearTimeout(debounceTimeout.current);
  }, [prose]);

  const extractStructure = async (text: string) => {
    setIsExtracting(true);

    // TODO: Replace with actual Claude API call
    // Simulate AI extraction
    await new Promise((resolve) => setTimeout(resolve, 1200));

    // Mock extraction based on prose content
    const lowerText = text.toLowerCase();

    const mockExtraction: ExtractionData = {
      type: lowerText.includes('onboard') ? 'onboarding' : 'action',
      trigger: lowerText.includes('enterprise')
        ? 'new enterprise customer signs'
        : 'customer action required',
      variables: extractVariables(text),
      mandates: extractMandates(text),
      guardrails: extractGuardrails(text),
      sidekickAdds: 'Structure and step sequencing based on the outcomes you describe.',
      updatedAt: new Date(),
    };

    setExtraction(mockExtraction);
    setIsExtracting(false);
  };

  // Simple extraction helpers (replace with real AI)
  const extractVariables = (text: string): string[] => {
    const vars: string[] = [];
    if (text.includes('customer')) vars.push('customer.name');
    if (text.includes('champion')) vars.push('customer.champion');
    if (text.includes('goal')) vars.push('customer.business_goal');
    if (text.includes('integration')) vars.push('customer.integration_needs');
    return vars;
  };

  const extractMandates = (text: string): string[] => {
    const mandates: string[] = [];
    if (text.match(/by (day|week|end of)/i)) {
      mandates.push('SSO + champion by week 2');
    }
    if (text.includes('first') && text.includes('outcome')) {
      mandates.push('First business outcome by day 90');
    }
    return mandates;
  };

  const extractGuardrails = (text: string): string[] => {
    const guardrails: string[] = [];
    if (text.match(/never|don't|avoid/i)) {
      guardrails.push('No kickoff Friday or holiday week');
    }
    return guardrails;
  };

  const handleOpenEditor = () => {
    // TODO: Save prose + extraction to playbook
    navigate('/app/handbook/playbooks/new/editor', {
      state: { prose, extraction },
    });
  };

  return (
    <div className="pb-describe">
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
        <Link to="/app/handbook/playbooks/new" className="hover:text-rust-500 transition-colors">
          New
        </Link>
        <span>/</span>
        <span className="text-app-fg-200">Describe</span>
      </div>

      <SectionOpener label="DESCRIBE YOUR PLAYBOOK" />

      {/* Prompt */}
      <h1 className="pb-describe__prompt">
        Tell me what <em>good</em> looks like.
      </h1>
      <p className="pb-describe__sub">
        A paragraph is enough. I'll listen for outcomes, mandates, and the variables I'll need
        from each customer.
      </p>

      {/* Input area */}
      <div
        contentEditable
        className="pb-describe__input"
        onInput={(e) => setProse(e.currentTarget.textContent || '')}
        suppressContentEditableWarning
        data-placeholder="When a new enterprise customer signs, good looks like..."
      />

      {/* Extraction panel */}
      {prose.trim() && (
        <ExtractionPanel extraction={extraction} isExtracting={isExtracting} />
      )}

      {/* Footer actions */}
      <div className="flex justify-end gap-4 mt-8">
        <button
          className="px-5 py-2.5 text-sm font-mono uppercase tracking-wider text-app-fg-300 hover:text-app-fg-100"
          disabled={!prose.trim()}
        >
          Keep typing
        </button>
        <button
          onClick={handleOpenEditor}
          disabled={!prose.trim() || isExtracting}
          className="px-6 py-2.5 text-sm font-mono uppercase tracking-wider bg-rust-500 text-cream-50 hover:bg-rust-400 rounded-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Open in editor · refine →
        </button>
      </div>
    </div>
  );
}
