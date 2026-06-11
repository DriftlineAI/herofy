import React, { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { SectionOpener, PlaybookTypeChip, PlanStep } from './components';
import type { PlanStepData } from './components';
import { ChevronLeft, ChevronRight, Edit3, Eye } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * PlaybookEditor (Artboard 4) - Dual pane (prose · live customer preview)
 * Left side: author's prose (intent + mandates + guardrails)
 * Right side: what the playbook looks like instantiated on a real customer
 */
export function PlaybookEditor() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  // Mock data - replace with real playbook data
  const [testCustomerIndex, setTestCustomerIndex] = useState(0);
  const [isEditingProse, setIsEditingProse] = useState(false);
  const [proseContent, setProseContent] = useState('');

  const testCustomers = [
    { name: 'Acme Corp', arr: '$240K', segment: 'Enterprise' },
    { name: 'Globex', arr: '$120K', segment: 'Mid-Market' },
    { name: 'Stark Industries', arr: '$800K', segment: 'Enterprise' },
  ];

  const currentCustomer = testCustomers[testCustomerIndex];

  // Mock playbook prose
  const playbook = {
    slug: slug || 'PB-ENT-ONB',
    title: 'Enterprise onboarding · 90-day',
    type: 'onboarding' as const,
    prose: `When a new enterprise customer signs, good looks like getting them to their first business outcome by day 90.

## What must happen

SSO is configured and a primary champion identified by **week 2**. First integration in production by end of **week 6**. An executive sponsor named and met with by end of **week 10**.

## How to communicate

Warm, prepared, not chatty. Reference their *stated goal* (we know them by the kickoff call — that means reading their onboarding form ahead of time and coming with a working hypothesis about their goal).

## What never to do

- Never schedule a kickoff on a Friday or the week of a major holiday
- Don't ask for a sign or testimonial before week 12`,
    updatedAt: new Date(Date.now() - 2 * 60 * 60 * 1000), // 2 hours ago
  };

  // Initialize prose content
  React.useEffect(() => {
    setProseContent(playbook.prose);
  }, [playbook.prose]);

  // Mock instantiated steps for current customer
  const instantiatedSteps: PlanStepData[] = [
    {
      stepNumber: 1,
      title: `Read ${currentCustomer.name}'s onboarding form before kickoff`,
      detail: 'Build working hypothesis about business goal. Reference in kickoff agenda.',
      mandate: false,
      provenance: 'from · "reading their onboarding form ahead of time" · communicate',
    },
    {
      stepNumber: 2,
      title: 'Kickoff with Alice Johnson. Tues Apr 23, 10am',
      detail: 'Confirm working hypothesis with Alice. Ask: "In 6 months, what does success look like for Acme?"',
      mandate: false,
      provenance: 'from · template · kickoff',
    },
    {
      stepNumber: 3,
      title: 'SSO configured + primary champion identified',
      detail: 'SSO config in progress with Marcus (VP IT). Now last 3 days back to Acme; champion still unclear.',
      mandate: true,
      mandateLocked: true,
      provenance: 'from · mandate · "SSO + champion by week 2"',
    },
    {
      stepNumber: 4,
      title: 'First integration in production',
      detail: 'Target: end of week 6. Launch articles API test endpoint by week 4.',
      mandate: true,
      mandateLocked: true,
      provenance: 'from · mandate · "first integration...by week 6"',
    },
    {
      stepNumber: 5,
      title: 'Executive sponsor named and met',
      detail: 'Aim for 30-minute introductory call by end of week 10.',
      mandate: true,
      mandateLocked: true,
      provenance: 'from · mandate · "exec sponsor...by week 10"',
    },
    {
      stepNumber: 6,
      title: 'First business outcome achievement',
      detail: 'Confirm with champion: "the thing we talked about in kickoff — has it happened?" If yes, surface in QBR.',
      mandate: true,
      mandateLocked: true,
      provenance: 'from · mandate · "first business outcome by day 90"',
    },
  ];

  const handlePrevCustomer = () => {
    setTestCustomerIndex((i) => (i - 1 + testCustomers.length) % testCustomers.length);
  };

  const handleNextCustomer = () => {
    setTestCustomerIndex((i) => (i + 1) % testCustomers.length);
  };

  const handleSaveAndDeploy = () => {
    // TODO: Show confirm dialog
    const activeCustomerCount = 3;
    const confirmed = window.confirm(
      `${activeCustomerCount} customers will see their plan diff. Continue?`
    );
    if (confirmed) {
      // TODO: Save playbook and trigger re-evaluation
      navigate('/app/handbook/playbooks');
    }
  };

  return (
    <div className="max-w-[1600px] mx-auto px-8 py-8">
      {/* Breadcrumb header */}
      <div className="flex justify-between items-center mb-8">
        <div className="font-mono text-xs uppercase tracking-wider text-app-fg-400 flex items-center gap-2">
          <Link to="/app/handbook" className="hover:text-rust-500 transition-colors">
            Handbook
          </Link>
          <span>/</span>
          <Link to="/app/handbook/playbooks" className="hover:text-rust-500 transition-colors">
            Playbooks
          </Link>
          <span>/</span>
          <span className="text-app-fg-200">{playbook.slug}</span>
        </div>
        <div className="flex gap-3">
          <button
            className="px-5 py-2 text-sm font-mono uppercase tracking-wider text-app-fg-300 hover:text-app-fg-100 border border-charcoal-700 rounded-sm"
          >
            Test on a customer
          </button>
          <button
            onClick={handleSaveAndDeploy}
            className="px-6 py-2 text-sm font-mono uppercase tracking-wider bg-rust-500 text-cream-50 hover:bg-rust-400 rounded-sm"
          >
            Save & deploy
          </button>
        </div>
      </div>

      {/* Dual pane editor */}
      <div className="pb-editor">
        {/* Left pane: Prose */}
        <div className="pb-editor__col">
          <div className="pb-editor__col-head">
            <div className="pb-editor__col-title">PROSE · YOUR INTENTION</div>
            <div className="pb-editor__col-time">
              EDITED {Math.floor((Date.now() - playbook.updatedAt.getTime()) / (1000 * 60 * 60))}H AGO
            </div>
          </div>

          {/* Playbook title & type */}
          <h2 className="font-serif text-[32px] font-medium text-app-fg-100 mb-2 tracking-tight">
            {playbook.title}
          </h2>
          <div className="mb-8">
            <PlaybookTypeChip type={playbook.type} strict />
          </div>

          {/* Edit/Preview toggle */}
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setIsEditingProse(true)}
              className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider flex items-center gap-2 rounded-sm transition-colors ${
                isEditingProse
                  ? 'bg-rust-500 text-cream-50'
                  : 'text-app-fg-400 hover:text-app-fg-200 border border-charcoal-700'
              }`}
            >
              <Edit3 className="w-3 h-3" />
              Edit
            </button>
            <button
              onClick={() => setIsEditingProse(false)}
              className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider flex items-center gap-2 rounded-sm transition-colors ${
                !isEditingProse
                  ? 'bg-rust-500 text-cream-50'
                  : 'text-app-fg-400 hover:text-app-fg-200 border border-charcoal-700'
              }`}
            >
              <Eye className="w-3 h-3" />
              Preview
            </button>
          </div>

          {/* Prose body - Edit or Preview mode */}
          {isEditingProse ? (
            <textarea
              value={proseContent}
              onChange={(e) => setProseContent(e.target.value)}
              className="pb-prose flex-1 w-full min-h-[400px] bg-transparent border border-charcoal-700 rounded-sm p-4 outline-none focus:border-rust-500 resize-vertical"
              placeholder="Write your playbook prose here..."
            />
          ) : (
            <div className="pb-prose flex-1 prose-custom">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {proseContent}
              </ReactMarkdown>
            </div>
          )}

          {/* Sidekick observations */}
          <div className="mt-8 border-l-2 border-rust-500 pl-5 space-y-4">
            <div className="text-sm text-app-fg-300 leading-relaxed">
              <strong className="text-app-fg-100">Tip:</strong>{' '}
              <em className="text-rust-500 not-italic font-serif">The mandates look good.</em>{' '}
              You've got four — week 2, 6, 10, 90. That gives me clear checkpoints.
            </div>
            <div className="text-sm text-app-fg-300 leading-relaxed">
              <strong className="text-app-fg-100">Observation:</strong>{' '}
              "Their stated goal" appears as a variable. I'll need{' '}
              <code className="text-rust-500">customer.business_goal</code> from each account's
              kickoff. If it's missing, I'll ask via HITL before instantiating.
            </div>
          </div>
        </div>

        {/* Right pane: Live preview */}
        <div className="pb-editor__col">
          <div className="pb-editor__col-head">
            <div className="pb-editor__col-title">LIVE PREVIEW · INSTANTIATED</div>
            <div className="pb-editor__col-time">UPDATES IN REAL TIME</div>
          </div>

          {/* Customer scrubber */}
          <div className="flex items-center justify-between mb-6 p-4 border border-charcoal-700 bg-charcoal-900/30">
            <button
              onClick={handlePrevCustomer}
              className="p-1 hover:bg-charcoal-700 rounded"
            >
              <ChevronLeft className="w-5 h-5 text-app-fg-400" />
            </button>
            <div className="font-mono text-xs uppercase tracking-wider text-app-fg-300">
              Test on{' '}
              <span className="text-app-fg-100 font-bold">{currentCustomer.name}</span>{' '}
              · {currentCustomer.arr} · {currentCustomer.segment}
            </div>
            <button
              onClick={handleNextCustomer}
              className="p-1 hover:bg-charcoal-700 rounded"
            >
              <ChevronRight className="w-5 h-5 text-app-fg-400" />
            </button>
          </div>

          {/* Instantiated steps */}
          <div className="space-y-3.5">
            {instantiatedSteps.map((step, i) => (
              <PlanStep
                key={i}
                mode="preview"
                state={i === 2 ? 'current' : i < 2 ? 'done' : 'pending'}
                step={step}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
