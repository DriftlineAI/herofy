import React, { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { SectionOpener, PlanStep, ProgressBar, ProvenanceAside, PlaybookEditableStep } from './components';
import type { PlanStepData } from './components';

/**
 * PlaybookRunning (Artboard 6) - Running on a customer (instantiated plan)
 * What a CSM sees when they open a customer who is on a playbook
 */
export function PlaybookRunning() {
  const { customerId } = useParams<{ customerId: string }>();
  const navigate = useNavigate();
  const [editingStepIndex, setEditingStepIndex] = useState<number | null>(null);

  // Mock customer plan data
  const plan = {
    customerId: customerId || 'mock-customer-id',
    playbookSlug: 'PB-ENT-ONB',
    playbookTitle: 'Enterprise onboarding · 90-day',
    customerName: 'Acme Corp',
    daysCurrent: 5,
    daysTotal: 90,
    completedSteps: 2,
    totalSteps: 6,
    nextMandate: 'SSO + champion',
    nextMandateDate: 'May 7',
    status: 'Day 5 of 90. On pace — but champion is unconfirmed.',
  };

  const steps: PlanStepData[] = [
    {
      stepNumber: 1,
      title: "Read Acme Corp's onboarding form before kickoff",
      detail: 'Build working hypothesis about business goal. Reference in kickoff agenda.',
      mandate: false,
      provenance: 'from · "reading their onboarding form ahead of time" · view in playbook ↗',
      provenanceLink: '/app/handbook/playbook/PB-ENT-ONB#L12',
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

  const variables = [
    { key: 'customer.name', value: 'Acme Corporation' },
    { key: 'customer.tier', value: 'Enterprise' },
    { key: 'onboarding_form.goal', value: 'Launch articles API for Q2' },
    { key: 'contact.champion', value: '(pending HITL)' },
    { key: 'kickoff.year_end', value: 'Jan 31' },
  ];

  const handleStepClick = (index: number) => {
    setEditingStepIndex(index);
  };

  const handleStepSave = (data: { title: string; detail: string; scope: 'customer' | 'playbook' }) => {
    console.log('Saving step with scope:', data.scope);
    // TODO: Save step changes based on scope
    setEditingStepIndex(null);
  };

  const handleStepCancel = () => {
    setEditingStepIndex(null);
  };

  return (
    <div className="max-w-[1600px] mx-auto px-8 py-8">
      {/* Breadcrumb header */}
      <div className="font-mono text-xs uppercase tracking-wider text-app-fg-400 flex items-center gap-2 mb-6">
        <Link to="/app/customers" className="hover:text-rust-500 transition-colors">
          Customers
        </Link>
        <span>/</span>
        <Link to={`/app/customers/${plan.customerId}`} className="hover:text-rust-500 transition-colors">
          {plan.customerName}
        </Link>
        <span>/</span>
        <span className="text-app-fg-200">Plan</span>
      </div>

      {/* Header */}
      <div className="mb-8">
        <div className="flex justify-between items-start mb-4">
          <div>
            <div className="font-mono text-xs uppercase tracking-wider text-app-fg-400 mb-2">
              From playbook ·{' '}
              <Link
                to={`/app/handbook/playbook/${plan.playbookSlug}`}
                className="text-rust-500 font-bold hover:text-rust-400 transition-colors"
              >
                {plan.playbookSlug}
              </Link>
              {' '}· {plan.playbookTitle}
            </div>
            <h1 className="font-serif text-[44px] font-medium leading-tight tracking-tight text-app-fg-100 mb-2">
              {plan.customerName} · onboarding
            </h1>
            <p className="font-serif italic text-lg text-app-fg-300">
              {plan.status}
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => navigate(`/app/handbook/playbook/${plan.playbookSlug}`)}
              className="px-5 py-2 text-sm font-mono uppercase tracking-wider text-app-fg-300 hover:text-app-fg-100 border border-charcoal-700 rounded-sm"
            >
              View playbook
            </button>
            <button
              className="px-6 py-2 text-sm font-mono uppercase tracking-wider bg-rust-500 text-cream-50 hover:bg-rust-400 rounded-sm"
            >
              Customize for {plan.customerName}
            </button>
          </div>
        </div>

        {/* Progress bar */}
        <ProgressBar
          done={plan.completedSteps}
          total={plan.totalSteps}
          nextMandate={plan.nextMandate}
          nextMandateDate={plan.nextMandateDate}
        />
      </div>

      {/* Body grid: plan + provenance */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-8">
        {/* Left: Plan steps */}
        <div>
          <SectionOpener label="PLAN · INSTANTIATED FOR ACME" />

          <div className="space-y-3.5">
            {steps.map((step, index) => (
              editingStepIndex === index ? (
                <PlaybookEditableStep
                  key={index}
                  step={step}
                  customerName={plan.customerName}
                  playbookSlug={plan.playbookSlug}
                  affectedCustomers={3}
                  onSave={handleStepSave}
                  onCancel={handleStepCancel}
                />
              ) : (
                <PlanStep
                  key={index}
                  mode="view"
                  state={index < plan.completedSteps ? 'done' : index === plan.completedSteps ? 'current' : 'pending'}
                  step={step}
                  onEdit={() => handleStepClick(index)}
                />
              )
            ))}
          </div>
        </div>

        {/* Right: Provenance aside */}
        <ProvenanceAside variables={variables} />
      </div>
    </div>
  );
}
