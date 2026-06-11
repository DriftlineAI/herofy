import React, { useState } from 'react';
import {
  Users,
  ArrowRight,
  ArrowLeft,
  Loader2,
  Check,
  AlertCircle,
  Sparkles,
  Play,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useCustomers } from '@/lib/dataconnect-hooks';
import { useWorkspace } from '@/lib/workspace';
import { getAuth } from 'firebase/auth';
import type { OnboardingData, UpdateDataFn } from './index';

interface StepOnboardingProps {
  data: OnboardingData;
  updateData: UpdateDataFn;
  onComplete: () => void;
  onBack: () => void;
}

interface GenerationStatus {
  customerId: string;
  status: 'pending' | 'running' | 'success' | 'error';
  error?: string;
  runId?: string;
}

export function StepOnboarding({
  data,
  updateData,
  onComplete,
  onBack,
}: StepOnboardingProps) {
  const { workspaceId } = useWorkspace();
  const { data: customersData, isLoading } = useCustomers();
  const customers = customersData?.customers || [];

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationStatus, setGenerationStatus] = useState<GenerationStatus[]>([]);
  const [generationComplete, setGenerationComplete] = useState(false);

  const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

  const getAuthHeaders = async () => {
    const token = await getAuth().currentUser?.getIdToken();
    return {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  };

  const toggleCustomer = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAll = () => {
    setSelectedIds(new Set(customers.map((c) => c.id)));
  };

  const selectNone = () => {
    setSelectedIds(new Set());
  };

  const generatePlans = async () => {
    if (!workspaceId || selectedIds.size === 0) return;

    setIsGenerating(true);
    setGenerationComplete(false);

    // Initialize status for all selected customers
    const initialStatus: GenerationStatus[] = Array.from(selectedIds).map((id) => ({
      customerId: id,
      status: 'pending',
    }));
    setGenerationStatus(initialStatus);

    const headers = await getAuthHeaders();

    // Process each customer sequentially (could be parallel, but sequential is easier to follow)
    for (const customerId of selectedIds) {
      // Update status to running
      setGenerationStatus((prev) =>
        prev.map((s) =>
          s.customerId === customerId ? { ...s, status: 'running' } : s
        )
      );

      try {
        // Trigger the handoff agent for this existing customer
        // We pass customer_id directly - the backend will look up the customer
        const response = await fetch(`${PYTHON_URL}/agents/handoff-auto/run`, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            workspace_id: workspaceId,
            customer_id: customerId,
            trigger_type: 'setup_wizard',
          }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Failed to generate plan');
        }

        const result = await response.json();

        // Update status to success
        setGenerationStatus((prev) =>
          prev.map((s) =>
            s.customerId === customerId
              ? { ...s, status: 'success', runId: result.run_id }
              : s
          )
        );
      } catch (error) {
        // Update status to error
        setGenerationStatus((prev) =>
          prev.map((s) =>
            s.customerId === customerId
              ? {
                  ...s,
                  status: 'error',
                  error: error instanceof Error ? error.message : 'Unknown error',
                }
              : s
          )
        );
      }
    }

    setIsGenerating(false);
    setGenerationComplete(true);
  };

  const successCount = generationStatus.filter((s) => s.status === 'success').length;
  const errorCount = generationStatus.filter((s) => s.status === 'error').length;

  // Get customer name by ID
  const getCustomerName = (id: string) => {
    return customers.find((c) => c.id === id)?.name || 'Unknown';
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 bg-rust-500/20 rounded-lg flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-rust-500" />
          </div>
          <h1 className="font-serif text-3xl text-cream-100">Generate Onboarding Plans</h1>
        </div>
        <p className="text-cream-400 text-lg">
          Select customers who need onboarding plans. Our AI will create customized milestones based on their profile.
        </p>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center gap-3 text-charcoal-400 py-12 justify-center">
          <Loader2 className="w-5 h-5 animate-spin" />
          Loading customers...
        </div>
      )}

      {/* No Customers State */}
      {!isLoading && customers.length === 0 && (
        <div className="border border-charcoal-700 bg-charcoal-800/50 p-8 text-center mb-8">
          <Users className="w-12 h-12 text-charcoal-500 mx-auto mb-4" />
          <div className="text-cream-300 mb-2">No customers imported</div>
          <p className="text-sm text-charcoal-400">
            Go back and import customers first, or skip this step to add them later.
          </p>
        </div>
      )}

      {/* Customer Selection */}
      {!isLoading && customers.length > 0 && !generationComplete && (
        <>
          {/* Selection Controls */}
          <div className="flex items-center justify-between mb-4">
            <div className="text-sm text-charcoal-400">
              {selectedIds.size} of {customers.length} selected
            </div>
            <div className="flex gap-2">
              <button
                onClick={selectAll}
                disabled={isGenerating}
                className="text-xs font-mono uppercase tracking-widest text-rust-400 hover:text-rust-300 disabled:opacity-50"
              >
                Select All
              </button>
              <span className="text-charcoal-600">|</span>
              <button
                onClick={selectNone}
                disabled={isGenerating}
                className="text-xs font-mono uppercase tracking-widest text-charcoal-400 hover:text-cream-300 disabled:opacity-50"
              >
                Clear
              </button>
            </div>
          </div>

          {/* Customer List */}
          <div className="border border-charcoal-700 divide-y divide-charcoal-700 mb-6 max-h-80 overflow-y-auto">
            {customers.map((customer) => {
              const status = generationStatus.find((s) => s.customerId === customer.id);
              const isSelected = selectedIds.has(customer.id);

              return (
                <button
                  key={customer.id}
                  onClick={() => !isGenerating && toggleCustomer(customer.id)}
                  disabled={isGenerating}
                  className={cn(
                    "w-full flex items-center gap-4 p-4 text-left transition-colors",
                    isSelected
                      ? "bg-rust-500/10"
                      : "bg-charcoal-800/50 hover:bg-charcoal-800",
                    isGenerating && "cursor-not-allowed opacity-75"
                  )}
                >
                  {/* Checkbox */}
                  <div
                    className={cn(
                      "w-5 h-5 border flex items-center justify-center flex-shrink-0",
                      isSelected
                        ? "border-rust-500 bg-rust-500"
                        : "border-charcoal-600"
                    )}
                  >
                    {isSelected && <Check className="w-3 h-3 text-charcoal-900" />}
                  </div>

                  {/* Customer Info */}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-cream-100 truncate">
                      {customer.name}
                    </div>
                    {customer.tier && (
                      <div className="text-xs text-charcoal-400">{customer.tier}</div>
                    )}
                  </div>

                  {/* Status Indicator */}
                  {status && (
                    <div className="flex-shrink-0">
                      {status.status === 'pending' && (
                        <div className="w-4 h-4 rounded-full bg-charcoal-600" />
                      )}
                      {status.status === 'running' && (
                        <Loader2 className="w-4 h-4 animate-spin text-rust-500" />
                      )}
                      {status.status === 'success' && (
                        <Check className="w-4 h-4 text-emerald-500" />
                      )}
                      {status.status === 'error' && (
                        <AlertCircle className="w-4 h-4 text-red-400" />
                      )}
                    </div>
                  )}
                </button>
              );
            })}
          </div>

          {/* Info Note */}
          <div className="border border-charcoal-700 bg-charcoal-800/30 p-4 mb-8">
            <p className="text-sm text-charcoal-400">
              The AI will analyze each customer's profile and create a customized onboarding plan
              based on their tier and playbook. Plans will appear in your Today queue for review.
            </p>
          </div>
        </>
      )}

      {/* Generation Complete */}
      {generationComplete && (
        <div className="mb-8">
          {/* Success Summary */}
          {successCount > 0 && (
            <div className="border border-emerald-500/50 bg-emerald-500/10 p-6 mb-4">
              <div className="flex items-center gap-3 mb-3">
                <Check className="w-6 h-6 text-emerald-500" />
                <span className="text-lg font-medium text-emerald-400">
                  Generated {successCount} onboarding plan{successCount !== 1 ? 's' : ''}
                </span>
              </div>
              <p className="text-sm text-charcoal-400">
                Plans are being created and will appear in your Today queue for review and approval.
              </p>
            </div>
          )}

          {/* Error Summary */}
          {errorCount > 0 && (
            <div className="border border-amber-500/30 bg-amber-500/10 p-4 mb-4">
              <div className="text-amber-400 mb-2">
                {errorCount} plan{errorCount !== 1 ? 's' : ''} failed to generate
              </div>
              <div className="text-sm text-charcoal-400 space-y-1">
                {generationStatus
                  .filter((s) => s.status === 'error')
                  .map((s) => (
                    <div key={s.customerId}>
                      • {getCustomerName(s.customerId)}: {s.error}
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Generation Log */}
          <div className="border border-charcoal-700 bg-charcoal-800/50 p-4">
            <div className="text-xs font-mono uppercase tracking-widest text-charcoal-500 mb-3">
              Generation Summary
            </div>
            <div className="space-y-2">
              {generationStatus.map((s) => (
                <div key={s.customerId} className="flex items-center gap-3 text-sm">
                  {s.status === 'success' && (
                    <Check className="w-4 h-4 text-emerald-500" />
                  )}
                  {s.status === 'error' && (
                    <AlertCircle className="w-4 h-4 text-red-400" />
                  )}
                  <span className={s.status === 'error' ? 'text-red-300' : 'text-cream-300'}>
                    {getCustomerName(s.customerId)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between pt-4">
        <button
          type="button"
          onClick={onBack}
          disabled={isGenerating}
          className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors disabled:opacity-50"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>

        {!generationComplete ? (
          <div className="flex gap-3">
            {/* Skip Button */}
            <button
              onClick={onComplete}
              disabled={isGenerating}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors disabled:opacity-50"
            >
              Skip
            </button>

            {/* Generate Button */}
            <button
              onClick={generatePlans}
              disabled={isGenerating || selectedIds.size === 0}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold disabled:opacity-50"
            >
              {isGenerating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Generate {selectedIds.size > 0 ? `${selectedIds.size} Plan${selectedIds.size !== 1 ? 's' : ''}` : 'Plans'}
                </>
              )}
            </button>
          </div>
        ) : (
          <button
            onClick={onComplete}
            className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold"
          >
            Continue
            <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
