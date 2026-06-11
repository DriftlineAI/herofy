import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  Plug,
  ArrowRight,
  ArrowLeft,
  Mail,
  MessageSquare,
  Calendar,
  FileText,
  Check,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useConnectIntegration, useDisconnectIntegration, useIntegrations, type IntegrationType } from '@/lib/dataconnect-hooks';
import { useWorkspace } from '@/lib/workspace';
import type { OnboardingData, UpdateDataFn } from './index';

interface StepConnectIntegrationsProps {
  data: OnboardingData;
  updateData: UpdateDataFn;
  onComplete: () => void;
  onBack: () => void;
}

// Local integration id (for UI state)
type IntegrationId = 'gmail' | 'slack' | 'calendar' | 'notion';

interface Integration {
  id: IntegrationId;
  provider: IntegrationType; // Maps to OAuth provider
  name: string;
  description: string;
  icon: React.ReactNode;
  color: string;
  benefit: string;
}

const INTEGRATIONS: Integration[] = [
  {
    id: 'gmail',
    provider: 'gmail',
    name: 'Gmail / Google Workspace',
    description: 'Import email threads with your customers',
    icon: <Mail className="w-6 h-6" />,
    color: '#EA4335',
    benefit: "We'll find all email conversations with your imported customers",
  },
  {
    id: 'slack',
    provider: 'slack',
    name: 'Slack',
    description: 'Connect Slack Connect channels',
    icon: <MessageSquare className="w-6 h-6" />,
    color: '#4A154B',
    benefit: "We'll surface Slack conversations and detect sentiment",
  },
  {
    id: 'calendar',
    provider: 'gmail', // Calendar uses Google OAuth (same as Gmail)
    name: 'Google Calendar',
    description: 'Import meetings with customers',
    icon: <Calendar className="w-6 h-6" />,
    color: '#4285F4',
    benefit: "We'll track meetings and prep you before calls",
  },
  {
    id: 'notion',
    provider: 'notion',
    name: 'Notion',
    description: 'Import customer data from Notion databases',
    icon: <FileText className="w-6 h-6" />,
    color: '#000000',
    benefit: "We'll sync customer information and handoff notes",
  },
];

export function StepConnectIntegrations({
  data,
  updateData,
  onComplete,
  onBack,
}: StepConnectIntegrationsProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { workspaceId } = useWorkspace();
  const { connect: startOAuth, isPending: isOAuthPending } = useConnectIntegration();
  const { disconnect: disconnectIntegration, isPending: isDisconnectPending } = useDisconnectIntegration();
  const { data: backendIntegrations, refetch: refetchIntegrations } = useIntegrations();
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [disconnectingId, setDisconnectingId] = useState<string | null>(null);
  const [connected, setConnected] = useState<Set<string>>(() => {
    // Initialize from data prop (for resuming after OAuth redirect)
    const initialConnected = new Set<string>();
    if (data.integrations.gmail) initialConnected.add('gmail');
    if (data.integrations.slack) initialConnected.add('slack');
    if (data.integrations.calendar) initialConnected.add('calendar');
    if (data.integrations.notion) initialConnected.add('notion');
    return initialConnected;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Sync with actual backend integration status (handles cases where
  // Notion was connected in step 2 but data wasn't propagated correctly)
  useEffect(() => {
    console.log('[StepConnectIntegrations] Backend integrations changed:', backendIntegrations);
    if (backendIntegrations) {
      const newConnected = new Set(connected);
      let updated = false;

      for (const integration of backendIntegrations) {
        console.log('[StepConnectIntegrations] Checking integration:', integration.integration_type, 'connected:', integration.connected);
        if (integration.connected) {
          const integrationId = integration.integration_type as IntegrationId;
          if (!newConnected.has(integrationId)) {
            console.log('[StepConnectIntegrations] Adding to connected set:', integrationId);
            newConnected.add(integrationId);
            updated = true;
          }
        }
      }

      if (updated) {
        console.log('[StepConnectIntegrations] Updating connected state:', Array.from(newConnected));
        setConnected(newConnected);
        // Also update the data prop - use functional update
        updateData(prev => ({
          integrations: {
            ...prev.integrations,
            gmail: newConnected.has('gmail'),
            slack: newConnected.has('slack'),
            calendar: newConnected.has('calendar'),
            notion: newConnected.has('notion'),
          },
        }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendIntegrations]);

  // Handle OAuth callback result from URL params
  const hasHandledOAuthCallback = useRef(false);
  useEffect(() => {
    const success = searchParams.get('success');
    const error = searchParams.get('error');
    const provider = searchParams.get('provider');

    console.log('[StepConnectIntegrations] OAuth callback check:', { success, error, provider, hasHandled: hasHandledOAuthCallback.current });

    // Only process once per OAuth flow
    if ((success === 'true' || error) && provider && !hasHandledOAuthCallback.current) {
      console.log('[StepConnectIntegrations] Processing OAuth callback');
      hasHandledOAuthCallback.current = true;

      if (success === 'true') {
        // Find the integration that matches this provider
        const integration = INTEGRATIONS.find(i => i.provider === provider);
        if (integration) {
          setConnected(prev => new Set([...prev, integration.id]));
          // Use functional update to avoid dependency loop
          updateData(prev => ({
            integrations: {
              ...prev.integrations,
              [integration.id]: true,
            },
          }));
        }
        // Clear URL params
        setSearchParams({});
      } else if (error) {
        // Find the integration that matches this provider
        const integration = INTEGRATIONS.find(i => i.provider === provider);
        if (integration) {
          setErrors(prev => ({
            ...prev,
            [integration.id]: `Connection failed: ${error}`,
          }));
        }
        // Clear URL params
        setSearchParams({});
      }

      // Reset the ref after a delay to allow future OAuth flows
      setTimeout(() => {
        hasHandledOAuthCallback.current = false;
      }, 1000);
    }
  }, [searchParams, setSearchParams, updateData]);

  const handleConnect = async (integration: Integration) => {
    console.log('[StepConnectIntegrations] handleConnect called for:', integration.id);
    console.log('[StepConnectIntegrations] workspaceId:', data.workspaceId);

    if (!data.workspaceId) {
      setErrors(prev => ({
        ...prev,
        [integration.id]: 'Workspace not created yet. Please go back and complete the first step.',
      }));
      return;
    }

    console.log('[StepConnectIntegrations] Starting OAuth for:', integration.provider);
    setConnectingId(integration.id);
    setErrors((prev) => ({ ...prev, [integration.id]: '' }));

    try {
      // Mark that we're in setup mode so callback redirects back here
      sessionStorage.setItem('herofy_oauth_return', '/setup');
      console.log('[StepConnectIntegrations] Calling startOAuth...');
      // Start real OAuth flow - this will redirect to the provider
      await startOAuth(integration.provider);
      console.log('[StepConnectIntegrations] startOAuth completed (should have redirected)');
    } catch (error) {
      console.error('[StepConnectIntegrations] OAuth error:', error);
      setErrors((prev) => ({
        ...prev,
        [integration.id]: error instanceof Error ? error.message : 'Connection failed. Please try again.',
      }));
      setConnectingId(null);
    }
  };

  const handleDisconnect = async (integrationId: keyof OnboardingData['integrations']) => {
    setDisconnectingId(integrationId);
    setErrors((prev) => ({ ...prev, [integrationId]: '' }));

    try {
      // Map integration ID to provider type
      const integration = INTEGRATIONS.find(i => i.id === integrationId);
      if (!integration) {
        throw new Error('Integration not found');
      }

      // Actually disconnect from backend
      await disconnectIntegration(integration.provider);

      // Update local state
      setConnected((prev) => {
        const next = new Set(prev);
        next.delete(integrationId);
        return next;
      });
      updateData({
        integrations: {
          ...data.integrations,
          [integrationId]: false,
        },
      });

      // Refresh integration status
      refetchIntegrations();
    } catch (error) {
      setErrors((prev) => ({
        ...prev,
        [integrationId]: error instanceof Error ? error.message : 'Disconnect failed. Please try again.',
      }));
    } finally {
      setDisconnectingId(null);
    }
  };

  const connectedCount = connected.size;
  const hasAnyConnection = connectedCount > 0;

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 bg-rust-500/20 rounded-lg flex items-center justify-center">
            <Plug className="w-5 h-5 text-rust-500" />
          </div>
          <h1 className="font-serif text-3xl text-cream-100">Connect your tools</h1>
        </div>
        <p className="text-cream-400 text-lg">
          Connect your communication tools so we can find conversations with your customers.
        </p>
      </div>

      {/* Integration Cards */}
      <div className="space-y-4 mb-8">
        {INTEGRATIONS.map((integration) => {
          const isConnected = connected.has(integration.id);
          const isConnecting = connectingId === integration.id;
          const isDisconnecting = disconnectingId === integration.id;
          const error = errors[integration.id];

          return (
            <motion.div
              key={integration.id}
              layout
              className={cn(
                "border p-5 transition-all",
                isConnected
                  ? "border-emerald-500/50 bg-emerald-500/5"
                  : "border-charcoal-700 bg-charcoal-800/50"
              )}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-4">
                  <div
                    className="w-12 h-12 rounded-lg flex items-center justify-center"
                    style={{ backgroundColor: `${integration.color}20` }}
                  >
                    <div style={{ color: integration.color }}>{integration.icon}</div>
                  </div>
                  <div>
                    <div className="font-medium text-cream-100 mb-1">{integration.name}</div>
                    <div className="text-sm text-charcoal-400 mb-2">
                      {integration.description}
                    </div>
                    {isConnected && (
                      <div className="text-sm text-emerald-400 flex items-center gap-2">
                        <Check className="w-4 h-4" />
                        {integration.benefit}
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex-shrink-0">
                  {isConnected ? (
                    <button
                      onClick={() => handleDisconnect(integration.id)}
                      disabled={isDisconnecting || isDisconnectPending}
                      className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-4 py-2 hover:border-red-500 hover:text-red-400 transition-colors disabled:opacity-50"
                    >
                      {isDisconnecting ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Disconnecting...
                        </>
                      ) : (
                        'Disconnect'
                      )}
                    </button>
                  ) : (
                    <button
                      onClick={() => handleConnect(integration)}
                      disabled={isConnecting || isOAuthPending}
                      className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-white px-4 py-2 transition-colors disabled:opacity-50"
                      style={{ backgroundColor: integration.color }}
                    >
                      {isConnecting ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Connecting...
                        </>
                      ) : (
                        'Connect'
                      )}
                    </button>
                  )}
                </div>
              </div>

              {error && (
                <div className="flex items-center gap-2 text-red-400 text-sm mt-3">
                  <AlertCircle className="w-4 h-4" />
                  {error}
                </div>
              )}
            </motion.div>
          );
        })}
      </div>

      {/* Status Message */}
      {hasAnyConnection && (
        <div className="border border-charcoal-700 bg-charcoal-800/50 p-4 mb-6">
          <div className="text-sm text-cream-300">
            <span className="text-rust-400 font-mono">{connectedCount}</span> integration
            {connectedCount !== 1 ? 's' : ''} connected. After setup, we'll scan for:
          </div>
          <ul className="text-sm text-charcoal-400 mt-2 space-y-1">
            {connected.has('gmail') && <li>• Email threads with your customers</li>}
            {connected.has('slack') && <li>• Slack conversations and sentiment signals</li>}
            {connected.has('calendar') && <li>• Past and upcoming customer meetings</li>}
            {connected.has('notion') && <li>• Customer data and handoff notes from Notion</li>}
          </ul>
        </div>
      )}

      {/* Skip Option */}
      {!hasAnyConnection && (
        <div className="text-center mb-6">
          <p className="text-charcoal-500 text-sm">
            You can skip this step and connect integrations later from settings.
          </p>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between pt-4">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <button
          onClick={onComplete}
          className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold"
        >
          {hasAnyConnection ? 'Continue' : 'Skip for now'}
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
