import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useCustomers, useToday, useThreads, useMeetings } from '@/lib/dataconnect-hooks';
import { useWorkspace } from '@/lib/workspace';
import type { OnboardingData } from './index';

interface StepFirstRunProps {
  data: OnboardingData;
  onComplete: () => void;
  onBack: () => void;
}

export function StepFirstRun({ data, onComplete, onBack }: StepFirstRunProps) {
  const navigate = useNavigate();
  const { workspaceId, setWorkspaceId } = useWorkspace();

  // Ensure workspace context is synced with setup data
  useEffect(() => {
    if (data.workspaceId && data.workspaceId !== workspaceId) {
      console.log('[StepFirstRun] Syncing workspace ID:', data.workspaceId);
      setWorkspaceId(data.workspaceId);
    }
  }, [data.workspaceId, workspaceId, setWorkspaceId]);

  // Fetch real data (these hooks use useWorkspace internally)
  const { data: customersData, isLoading: isLoadingCustomers } = useCustomers();
  const { data: todayData, isLoading: isLoadingToday } = useToday();
  const { data: threadsData, isLoading: isLoadingThreads } = useThreads();
  const { data: meetingsData, isLoading: isLoadingMeetings } = useMeetings();

  // Also wait for workspace ID to be synced
  const isWorkspaceSyncing = data.workspaceId && data.workspaceId !== workspaceId;
  const isLoading = isWorkspaceSyncing || isLoadingCustomers || isLoadingToday || isLoadingThreads || isLoadingMeetings;

  // Debug: Log workspace and data state
  console.log('[StepFirstRun] State:', {
    'data.workspaceId': data.workspaceId,
    'context.workspaceId': workspaceId,
    'isWorkspaceSyncing': isWorkspaceSyncing,
    'customersCount': customersData?.customers?.length ?? 'loading',
  });

  // Calculate real stats
  const customers = customersData?.customers || [];
  const todayNeeds = todayData?.items || [];
  const threads = threadsData?.threads || [];
  const meetings = meetingsData?.meetings || [];

  // Count urgent needs (those requiring immediate attention)
  const urgentNeeds = todayNeeds.filter(n =>
    n.type === 'urgent_support' ||
    n.type === 'going_dark' ||
    n.type === 'escalation'
  );

  // Count waiting sidekick questions
  const waitingQuestions = todayNeeds.filter(n =>
    n.type === 'sidekick_question' ||
    n.type === 'plan_approval_required'
  );

  // Format thread count
  const formatCount = (count: number) => {
    if (count >= 1000) return `${(count / 1000).toFixed(1)}K`;
    return count.toString();
  };

  const stats = {
    customers: customers.length,
    emails: formatCount(threads.length),
    meetings: meetings.length,
    waiting: waitingQuestions.length,
    urgent: urgentNeeds.length,
  };

  const handleOpenToday = () => {
    onComplete();
  };

  const handleTakeTour = () => {
    // For now, just complete - tour can be added later
    onComplete();
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 text-rust-500 animate-spin" />
        <span className="ml-3 text-charcoal-400">
          Reading your workspace...
        </span>
      </div>
    );
  }

  // Build the lede text dynamically
  const ledeParts = [];
  if (stats.customers > 0) ledeParts.push(`${stats.customers} active customers`);
  if (threads.length > 0) ledeParts.push(`${stats.emails} emails`);
  if (stats.meetings > 0) ledeParts.push(`${stats.meetings} meetings`);

  let ledeText = ledeParts.join(', ');
  if (stats.waiting > 0) {
    ledeText += `. ${stats.waiting} ${stats.waiting === 1 ? 'question' : 'questions'} waiting`;
  }
  if (stats.urgent > 0) {
    ledeText += ` and ${stats.urgent} ${stats.urgent === 1 ? 'customer who already needs you' : 'customers who already need you'}.`;
  } else {
    ledeText += '.';
  }

  // Find the most urgent customer if there is one
  // The today items have customer_name from the joined data
  const urgentCustomerName = urgentNeeds.length > 0 && (urgentNeeds[0] as any).customer_name
    ? (urgentNeeds[0] as any).customer_name
    : null;

  return (
    <>
      {/* First-run content */}
      <div className="firstrun">
        <div className="firstrun__hello">SIDEKICK · INITIAL READ COMPLETE</div>

        <h1 className="firstrun__title">
          I've read everything. <em>Here's what I found.</em>
        </h1>

        <p className="firstrun__lede">
          {ledeText || 'Your workspace is ready. Connect some integrations to get started.'}
        </p>

        {/* Stats grid */}
        <div className="firstrun__stats">
          <div className="firstrun__stat">
            <div className="v">{stats.customers}</div>
            <div className="k">CUSTOMERS</div>
          </div>
          <div className="firstrun__stat">
            <div className="v">{stats.emails}</div>
            <div className="k">THREADS</div>
          </div>
          <div className="firstrun__stat">
            <div className="v">{stats.meetings}</div>
            <div className="k">MEETINGS</div>
          </div>
          <div className="firstrun__stat">
            <div className="v">
              {stats.waiting}
              {stats.urgent > 0 && <span className="small">+ {stats.urgent}</span>}
            </div>
            <div className="k">WAITING IN TODAY</div>
          </div>
        </div>

        {/* Handoff cards */}
        <div className="firstrun__handoff">
          <div
            className="firstrun__handoff-card firstrun__handoff-card--primary"
            onClick={handleOpenToday}
          >
            <div className="eyebrow">RECOMMENDED · FIRST 5 MINUTES</div>
            <h3 className="label">Open Today →</h3>
            <p className="sub">
              {urgentCustomerName
                ? `${urgentCustomerName} needs attention. ${stats.waiting > 0 ? `Plus ${stats.waiting} Sidekick questions waiting.` : ''} I've prioritized the queue.`
                : stats.waiting > 0
                  ? `${stats.waiting} Sidekick questions waiting for your input. I've prioritized your queue.`
                  : 'Your prioritized queue is ready. Start with the customers that need attention most.'}
            </p>
          </div>

          <div
            className="firstrun__handoff-card"
            onClick={handleTakeTour}
          >
            <div className="eyebrow">LATER</div>
            <h3 className="label">Take a tour</h3>
            <p className="sub">
              I'll walk you through the queue, conversations, and how I surface things. Two minutes.
            </p>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="setup__footer">
        <button type="button" className="sk-btn" onClick={onBack}>
          ← Back · Customers
        </button>
        <span className="font-mono text-[10px] text-charcoal-400 tracking-[0.2em] uppercase">
          You're done.
        </span>
        <button type="button" className="sk-btn sk-btn--primary" onClick={handleOpenToday}>
          Open Today →
        </button>
      </div>
    </>
  );
}
