import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { getAuth } from 'firebase/auth';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth';
import { useWorkspace } from '@/lib/workspace';
import { useCreateWorkspace, useUpdateWorkspace, seedWorkspaceDefaults } from '@/lib/dataconnect-hooks';
import { useGetUserById, useCompleteWorkspaceSetup } from '@/dataconnect-generated/react';

import { StepWorkspace } from './StepWorkspace';
import { StepIntegrations } from './StepIntegrations';
import { StepPlaybooks } from './StepPlaybooks';
import { StepCustomers } from './StepCustomers';
import { StepFirstRun } from './StepFirstRun';

const SETUP_PROGRESS_KEY = 'herofy_setup_progress';
const WORKSPACE_DATA_KEY = 'herofy_workspace_data';

export type UpdateDataFn = (updates: Partial<OnboardingData> | ((prev: OnboardingData) => Partial<OnboardingData>)) => void;

export interface OnboardingData {
  workspace: {
    name: string;
    slug?: string;
    logo?: string;
    valueProp?: string;
    teamSize?: 'solo' | 'small' | 'growing';
    invites?: Array<{ email: string; role: 'owner' | 'admin' | 'csm' }>;
  };
  workspaceId?: string; // Created after workspace step
  importSource: 'notion' | 'csv' | 'hubspot' | 'pipedrive' | 'manual' | null;
  notionConfig?: {
    primaryDatabaseId: string;  // Source of truth for customers - import from here
    linkedDatabaseIds?: string[];  // Additional databases for page linking (handoff docs, trackers)
    fieldMappings: Record<string, string>;
    triggerMode?: 'crm' | 'pipeline';
    statusValues?: string[];
  };
  csvData?: {
    customers: Array<{ name: string; domain?: string; contacts?: string[] }>;
  };
  integrations: {
    gmail: boolean;
    slack: boolean;
    calendar: boolean;
    notion: boolean;
  };
  // Voice data (Core Voice + Foundations)
  coreVoice?: {
    industry?: string;
    targetCustomer?: string;
    valueProps: string[];
    tone: 'formal' | 'friendly' | 'technical' | 'conversational';
    perspective: '1st-person-plural' | '3rd-person';
  };
  foundations?: Array<{
    slug: string;
    title: string;
    description: string;
    body: string;
    blastRadius: 'low' | 'medium' | 'high';
  }>;
  customPlaybooks?: Array<{
    name: string;
    archetype: string;
    fitNote: string;
    milestones: Array<{
      title: string;
      ownerSide: 'us' | 'customer' | 'joint';
      durationDays: number;
      description: string;
      sortOrder: number;
    }>;
  }>;
  playbooksSeeded?: boolean;
  voiceSeeded?: boolean;
}

const STEPS = [
  { id: 'workspace', label: 'Workspace' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'playbooks', label: 'Playbooks' },
  { id: 'customers', label: 'Customers' },
  { id: 'handoff', label: 'Hand off' },
] as const;

type StepId = typeof STEPS[number]['id'];

// Load saved progress from sessionStorage
function loadSavedProgress(): {
  currentStep: StepId;
  completedSteps: StepId[];
  data: OnboardingData;
} | null {
  try {
    const saved = sessionStorage.getItem(SETUP_PROGRESS_KEY);
    if (!saved) return null;
    const parsed = JSON.parse(saved);
    // Migrate old step IDs if needed
    if (parsed.currentStep === 'import') parsed.currentStep = 'customers';
    if (parsed.currentStep === 'connect') parsed.currentStep = 'integrations';
    if (parsed.currentStep === 'processing') parsed.currentStep = 'handoff';
    if (parsed.currentStep === 'onboarding') parsed.currentStep = 'playbooks';
    return parsed;
  } catch {
    return null;
  }
}

export default function Onboarding() {
  const navigate = useNavigate();
  const { user, isStaff, completeSetup, signOut } = useAuth();
  const { workspaceId: existingWorkspaceId, setWorkspaceId } = useWorkspace();
  const createWorkspace = useCreateWorkspace();
  const updateWorkspace = useUpdateWorkspace();
  const completeWorkspaceSetup = useCompleteWorkspaceSetup();

  // Query current user to get workspace info (using explicit userId for emulator compatibility)
  const { data: currentUserData } = useGetUserById(
    { userId: user?.uid || '' },
    { enabled: !!user?.uid }
  );

  // Initialize from saved progress or defaults
  const savedProgress = loadSavedProgress();

  const [currentStep, setCurrentStep] = useState<StepId>(
    savedProgress?.currentStep || 'workspace'
  );
  const [completedSteps, setCompletedSteps] = useState<Set<StepId>>(
    new Set(savedProgress?.completedSteps || [])
  );
  const [data, setData] = useState<OnboardingData>(
    savedProgress?.data || {
      workspace: { name: '' },
      importSource: null,
      integrations: {
        gmail: false,
        slack: false,
        calendar: false,
        notion: false,
      },
    }
  );

  const currentStepIndex = STEPS.findIndex(s => s.id === currentStep);

  // Load existing workspace data on mount - only run when currentUserData changes
  const hasLoadedWorkspace = useRef(false);
  useEffect(() => {
    // Only run once when currentUserData becomes available
    const setupDbUser = currentUserData?.users?.[0];
    if (setupDbUser && !hasLoadedWorkspace.current) {
      const memberships = setupDbUser.workspaceMembers_on_user || [];
      if (memberships.length > 0) {
        const workspace = memberships[0].workspace;
        setWorkspaceId(workspace.id);
        setData(prev => {
          // Only update if we don't already have a workspaceId
          if (!prev.workspaceId) {
            return {
              ...prev,
              workspaceId: workspace.id,
              workspace: { ...prev.workspace, name: prev.workspace.name || workspace.name },
            };
          }
          return prev;
        });
        hasLoadedWorkspace.current = true;
      }
    }
  }, [currentUserData, setWorkspaceId]); // Removed data.workspaceId from deps to prevent infinite loop

  // Save progress to sessionStorage whenever state changes
  useEffect(() => {
    if (currentStep === 'handoff') return;

    const progressToSave = {
      currentStep,
      completedSteps: Array.from(completedSteps),
      data,
    };
    sessionStorage.setItem(SETUP_PROGRESS_KEY, JSON.stringify(progressToSave));
  }, [currentStep, completedSteps, data]);

  const clearSavedProgress = useCallback(() => {
    sessionStorage.removeItem(SETUP_PROGRESS_KEY);
  }, []);

  const handleStepComplete = async (stepId: StepId) => {
    // If completing workspace step, update or create the workspace
    if (stepId === 'workspace') {
      try {
        const workspaceId = data.workspaceId || existingWorkspaceId;

        if (workspaceId) {
          // Update existing workspace with new values (name, slug, valueProp)
          await updateWorkspace.mutateAsync({
            id: workspaceId,
            name: data.workspace.name,
            slug: data.workspace.slug || '',
          });
          setWorkspaceId(workspaceId);
          setData(prev => ({ ...prev, workspaceId }));
        } else {
          const result = await createWorkspace.mutateAsync({
            name: data.workspace.name,
            slug: data.workspace.slug,
          });
          const newWorkspaceId = result.workspace.id;
          setWorkspaceId(newWorkspaceId);
          setData(prev => ({ ...prev, workspaceId: newWorkspaceId }));
        }
      } catch (error) {
        console.error('Failed to create/update workspace:', error);
      }
    }

    // After integrations step, seed defaults if not done
    if (stepId === 'integrations') {
      const workspaceId = data.workspaceId || existingWorkspaceId;
      if (workspaceId && !data.playbooksSeeded) {
        try {
          await seedWorkspaceDefaults(workspaceId);
          setData(prev => ({ ...prev, playbooksSeeded: true, voiceSeeded: true }));
        } catch (error) {
          console.error('Failed to seed workspace defaults:', error);
        }
      }
    }

    setCompletedSteps(prev => new Set([...prev, stepId]));

    const currentIndex = STEPS.findIndex(s => s.id === stepId);
    if (currentIndex < STEPS.length - 1) {
      setCurrentStep(STEPS[currentIndex + 1].id);
    }
  };

  const handleBack = () => {
    if (currentStepIndex > 0) {
      setCurrentStep(STEPS[currentStepIndex - 1].id);
    }
  };

  const handleComplete = async () => {
    try {
      let workspaceId = data.workspaceId;

      if (!workspaceId) {
        const result = await createWorkspace.mutateAsync({ name: data.workspace.name });
        workspaceId = result.workspace.id;
        setWorkspaceId(workspaceId);
      }

      localStorage.setItem(WORKSPACE_DATA_KEY, JSON.stringify({
        name: data.workspace.name,
        importSource: data.importSource,
        integrations: data.integrations,
        createdAt: new Date().toISOString(),
      }));

      clearSavedProgress();
      await completeSetup();

      const workspaceIdToComplete = workspaceId || existingWorkspaceId;
      if (workspaceIdToComplete) {
        try {
          await completeWorkspaceSetup.mutateAsync({ workspaceId: workspaceIdToComplete });
        } catch (err) {
          console.error('Failed to mark workspace setup complete:', err);
        }

        // Trigger onboarding agents for customers needing plans
        try {
          const PYTHON_URL = import.meta.env.VITE_PYTHON_URL;
          if (!PYTHON_URL) {
            console.error('VITE_PYTHON_URL not configured - agents will not be triggered');
            throw new Error('Backend URL not configured');
          }

          const token = await getAuth().currentUser?.getIdToken();

          if (!token) {
            console.warn('No auth token available - agents will not be triggered. Setup otherwise complete.');
          } else {
            const response = await fetch(`${PYTHON_URL}/api/setup/${workspaceIdToComplete}/complete`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
              },
              body: JSON.stringify({
                trigger_agents: true,
                max_retries: 3,
                initial_backoff: 30,
              }),
            });

            if (response.ok) {
              const result = await response.json();
              console.log('Setup agents triggered:', result);
              // Note: Agents run in background, user will see progress in Today queue
            } else {
              console.error('Failed to trigger setup agents:', await response.text());
            }
          }
        } catch (err) {
          console.error('Failed to trigger onboarding agents:', err);
          // Non-fatal - user can manually trigger agents from customer pages
        }
      }

      navigate('/app');
    } catch (error) {
      console.error('Failed to create workspace:', error);
      clearSavedProgress();
      await completeSetup();
      navigate('/app');
    }
  };

  const updateData = useCallback((updates: Partial<OnboardingData> | ((prev: OnboardingData) => Partial<OnboardingData>)) => {
    if (typeof updates === 'function') {
      setData(prev => ({ ...prev, ...updates(prev) }));
    } else {
      setData(prev => ({ ...prev, ...updates }));
    }
  }, []);

  return (
    <div className="min-h-screen bg-charcoal-900">
      {/* Header */}
      <header className="border-b border-charcoal-700/50 px-6 py-4">
        <div className="max-w-[1200px] mx-auto flex items-center justify-between">
          <img src="/logo.svg" alt="Herofy" className="h-8" />
          <div className="flex items-center gap-3">
            <span className="text-xs text-charcoal-400 font-mono">
              {user?.email}
            </span>
            {isStaff && (
              <span className="text-[10px] font-mono uppercase tracking-widest bg-rust-500/20 text-rust-400 px-2 py-0.5">
                Staff
              </span>
            )}
            <button
              onClick={async () => {
                await signOut();
                navigate('/login');
              }}
              className="text-xs text-charcoal-400 hover:text-cream-100 transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main>
        <AnimatePresence mode="wait">
          <motion.div
            key={currentStep}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            {/* Progress stepper is now inside each step component */}
            {currentStep === 'workspace' && (
              <SetupContainer currentStep={1}>
                <StepWorkspace
                  data={data}
                  updateData={updateData}
                  onComplete={() => handleStepComplete('workspace')}
                />
              </SetupContainer>
            )}

            {currentStep === 'integrations' && (
              <SetupContainer currentStep={2}>
                <StepIntegrations
                  data={data}
                  updateData={updateData}
                  onComplete={() => handleStepComplete('integrations')}
                  onBack={handleBack}
                />
              </SetupContainer>
            )}

            {currentStep === 'playbooks' && (
              <SetupContainer currentStep={3}>
                <StepPlaybooks
                  data={data}
                  updateData={updateData}
                  onComplete={() => handleStepComplete('playbooks')}
                  onBack={handleBack}
                />
              </SetupContainer>
            )}

            {currentStep === 'customers' && (
              <SetupContainer currentStep={4}>
                <StepCustomers
                  data={data}
                  updateData={updateData}
                  onComplete={() => handleStepComplete('customers')}
                  onBack={handleBack}
                />
              </SetupContainer>
            )}

            {currentStep === 'handoff' && (
              <SetupContainer currentStep={5}>
                <StepFirstRun
                  data={data}
                  onComplete={handleComplete}
                  onBack={handleBack}
                />
              </SetupContainer>
            )}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}

// Progress stepper component
function SetupSteps({ current }: { current: number }) {
  return (
    <div className="setup__steps">
      {STEPS.map((step, index) => {
        const stepNum = index + 1;
        const isDone = stepNum < current;
        const isCurrent = stepNum === current;

        return (
          <React.Fragment key={step.id}>
            {index > 0 && (
              <div className={cn('setup__step-conn', isDone && 'done')} />
            )}
            <div className={cn(
              'setup__step',
              isDone && 'done',
              isCurrent && 'current'
            )}>
              <span className="n">{isDone ? '✓' : stepNum}</span>
              <span>{step.label}</span>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

// Container that includes the stepper
function SetupContainer({ children, currentStep }: { children: React.ReactNode; currentStep: number }) {
  return (
    <div className="setup">
      <SetupSteps current={currentStep} />
      {children}
    </div>
  );
}
