import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Check, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useConnectIntegration, useIntegrations, useNotionDatabases, type IntegrationType } from '@/lib/dataconnect-hooks';
import { useWorkspace } from '@/lib/workspace';
import type { OnboardingData, UpdateDataFn } from './index';

interface StepIntegrationsProps {
  data: OnboardingData;
  updateData: UpdateDataFn;
  onComplete: () => void;
  onBack: () => void;
}

type IntegrationId = 'gmail' | 'slack' | 'notion';

interface Integration {
  id: IntegrationId;
  provider: IntegrationType;
  name: string;
  description: string;
  logo: string;
}

const INTEGRATIONS: Integration[] = [
  {
    id: 'gmail',
    provider: 'gmail',
    name: 'Gmail + Calendar',
    description: 'One connection covers both Gmail and Google Calendar. Herofy reads customer threads and the meeting invites tied to them so it can surface replies and prep you for calls.',
    logo: 'M',
  },
  {
    id: 'slack',
    provider: 'slack',
    name: 'Slack',
    description: 'Import shared channels and DMs with customer contacts.',
    logo: '#',
  },
  {
    id: 'notion',
    provider: 'notion',
    name: 'Notion (CRM)',
    description: 'Notion is your CRM here — customer accounts, handoff docs, and onboarding trackers all live in it. Connecting lets Herofy read those records and keep context in sync.',
    logo: 'N',
  },
];

export function StepIntegrations({
  data,
  updateData,
  onComplete,
  onBack,
}: StepIntegrationsProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { workspaceId } = useWorkspace();
  const { connect: startOAuth, isPending: isOAuthPending } = useConnectIntegration();
  const { data: backendIntegrations } = useIntegrations();

  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [connected, setConnected] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    if (data.integrations.gmail) initial.add('gmail');
    if (data.integrations.slack) initial.add('slack');
    if (data.integrations.notion) initial.add('notion');
    return initial;
  });
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Notion-specific state
  const isNotionConnected = connected.has('notion');
  const {
    data: notionDatabasesRaw,
    isLoading: isLoadingDatabases,
    refetch: refetchDatabases
  } = useNotionDatabases({ enabled: isNotionConnected });

  // Transform to display format
  const notionDatabases = notionDatabasesRaw.map(db => ({
    id: db.id,
    name: db.name,
    detail: db.icon ? `${db.icon} DATABASE` : 'DATABASE',
    rows: 0, // Row count not available from search endpoint
  }));

  // Primary database = source of truth for customers (import from here)
  const [primaryDatabaseId, setPrimaryDatabaseId] = useState<string | null>(
    data.notionConfig?.primaryDatabaseId || null
  );
  // Linked databases = additional databases for page linking (handoff docs, trackers)
  const [linkedDatabaseIds, setLinkedDatabaseIds] = useState<Set<string>>(
    () => new Set(data.notionConfig?.linkedDatabaseIds || [])
  );
  const [triggerMode, setTriggerMode] = useState<'crm' | 'pipeline'>(
    data.notionConfig?.triggerMode || 'crm'
  );
  const [selectedStatuses, setSelectedStatuses] = useState<Set<string>>(
    () => new Set(data.notionConfig?.statusValues || ['closed-won'])
  );

  // Auto-select first database as primary if nothing was previously selected
  useEffect(() => {
    if (notionDatabases.length > 0 && !primaryDatabaseId && !data.notionConfig?.primaryDatabaseId) {
      const firstDb = notionDatabases[0].id;
      setPrimaryDatabaseId(firstDb);
      // Save immediately
      updateData({
        notionConfig: {
          ...data.notionConfig,
          primaryDatabaseId: firstDb,
          fieldMappings: data.notionConfig?.fieldMappings || {},
        },
      });
    }
  }, [notionDatabases.length, data.notionConfig?.primaryDatabaseId]);

  // Sync with backend integration status
  useEffect(() => {
    if (backendIntegrations) {
      const newConnected = new Set(connected);
      let updated = false;

      for (const integration of backendIntegrations) {
        if (integration.connected) {
          const integrationId = integration.integration_type as IntegrationId;
          if (!newConnected.has(integrationId)) {
            newConnected.add(integrationId);
            updated = true;
          }
        }
      }

      if (updated) {
        setConnected(newConnected);
        updateData(prev => ({
          integrations: {
            ...prev.integrations,
            gmail: newConnected.has('gmail'),
            slack: newConnected.has('slack'),
            calendar: newConnected.has('gmail'), // Calendar uses Gmail OAuth
            notion: newConnected.has('notion'),
          },
        }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendIntegrations]);

  // Handle OAuth callback
  const hasHandledOAuthCallback = useRef(false);
  useEffect(() => {
    const success = searchParams.get('success');
    const error = searchParams.get('error');
    const provider = searchParams.get('provider');

    if ((success === 'true' || error) && provider && !hasHandledOAuthCallback.current) {
      hasHandledOAuthCallback.current = true;

      if (success === 'true') {
        const integration = INTEGRATIONS.find(i => i.provider === provider);
        if (integration) {
          setConnected(prev => new Set([...prev, integration.id]));
          updateData(prev => ({
            integrations: {
              ...prev.integrations,
              [integration.id]: true,
              ...(integration.id === 'gmail' ? { calendar: true } : {}),
            },
          }));
          // Auto-expand Notion after connecting to show config and fetch databases
          if (integration.id === 'notion') {
            setExpandedId('notion');
            // Small delay to ensure state is updated before fetching
            setTimeout(() => refetchDatabases(), 500);
          }
        }
        setSearchParams({});

        // Auto-chain the Notion *MCP* consent. Notion's hosted MCP server uses a SEPARATE
        // OAuth flow (PKCE + Dynamic Client Registration) from the REST integration above, and
        // it's interactive — so we capture it now, while the user is here, rather than dead-ending
        // an autonomous agent run later. This kicks a second redirect to mcp.notion.com. We only
        // chain off the REST `notion` success (never off `notion_mcp` itself → no loop). REST
        // Notion is already marked connected above, so even if MCP is declined it stays usable.
        if (provider === 'notion') {
          sessionStorage.setItem('herofy_oauth_return', '/setup');
          startOAuth('notion_mcp').catch((e) => {
            // Non-fatal — REST Notion works; MCP enrichment can be retried from settings.
            console.warn('[StepIntegrations] notion_mcp auto-chain failed', e);
          });
        }
      } else if (error) {
        // `notion_mcp` isn't a tile; surface its failure on the Notion tile but keep REST connected.
        const integration = INTEGRATIONS.find(i => i.provider === provider);
        if (integration) {
          setErrors(prev => ({ ...prev, [integration.id]: `Connection failed: ${error}` }));
        } else if (provider === 'notion_mcp') {
          setErrors(prev => ({
            ...prev,
            notion: `Notion is connected, but enabling MCP enrichment failed: ${error}. You can retry from settings.`,
          }));
        }
        setSearchParams({});
      }

      setTimeout(() => {
        hasHandledOAuthCallback.current = false;
      }, 1000);
    }
  }, [searchParams, setSearchParams, updateData]);

  const handleConnect = async (integration: Integration) => {
    if (!data.workspaceId) {
      setErrors(prev => ({
        ...prev,
        [integration.id]: 'Workspace not created yet. Please go back and complete the first step.',
      }));
      return;
    }

    setConnectingId(integration.id);
    setErrors(prev => ({ ...prev, [integration.id]: '' }));

    try {
      sessionStorage.setItem('herofy_oauth_return', '/setup');
      await startOAuth(integration.provider);
    } catch (error) {
      setErrors(prev => ({
        ...prev,
        [integration.id]: error instanceof Error ? error.message : 'Connection failed. Please try again.',
      }));
      setConnectingId(null);
    }
  };

  // Select primary database (radio-style - only one can be selected)
  const selectPrimaryDatabase = (dbId: string) => {
    setPrimaryDatabaseId(dbId);
    // Remove from linked if it was there
    const newLinked = new Set(linkedDatabaseIds);
    newLinked.delete(dbId);
    setLinkedDatabaseIds(newLinked);
    // Persist
    updateData({
      notionConfig: {
        ...data.notionConfig,
        primaryDatabaseId: dbId,
        linkedDatabaseIds: Array.from(newLinked),
        fieldMappings: data.notionConfig?.fieldMappings || {},
        triggerMode,
        statusValues: Array.from(selectedStatuses),
      },
    });
  };

  // Toggle linked database (checkbox-style - multiple can be selected)
  const toggleLinkedDatabase = (dbId: string) => {
    // Can't link the primary database
    if (dbId === primaryDatabaseId) return;

    const next = new Set(linkedDatabaseIds);
    if (next.has(dbId)) {
      next.delete(dbId);
    } else {
      next.add(dbId);
    }
    setLinkedDatabaseIds(next);
    // Persist
    updateData({
      notionConfig: {
        ...data.notionConfig,
        primaryDatabaseId: primaryDatabaseId || '',
        linkedDatabaseIds: Array.from(next),
        fieldMappings: data.notionConfig?.fieldMappings || {},
        triggerMode,
        statusValues: Array.from(selectedStatuses),
      },
    });
  };

  const handleTriggerModeChange = (mode: 'crm' | 'pipeline') => {
    setTriggerMode(mode);
    updateData({
      notionConfig: {
        ...data.notionConfig,
        primaryDatabaseId: primaryDatabaseId || '',
        linkedDatabaseIds: Array.from(linkedDatabaseIds),
        fieldMappings: data.notionConfig?.fieldMappings || {},
        triggerMode: mode,
        statusValues: Array.from(selectedStatuses),
      },
    });
  };

  const toggleStatus = (status: string) => {
    const next = new Set(selectedStatuses);
    if (next.has(status)) {
      next.delete(status);
    } else {
      next.add(status);
    }
    setSelectedStatuses(next);
    // Persist
    updateData({
      notionConfig: {
        ...data.notionConfig,
        primaryDatabaseId: primaryDatabaseId || '',
        linkedDatabaseIds: Array.from(linkedDatabaseIds),
        fieldMappings: data.notionConfig?.fieldMappings || {},
        triggerMode,
        statusValues: Array.from(next),
      },
    });
  };

  const connectedCount = connected.size;

  return (
    <>
      {/* Header */}
      <div className="setup__head">
        <div>
          <h1>Connect what Sidekick should <em>read</em>.</h1>
          <p className="lede">
            Three tools cover almost everything that happens with a customer. The point is Sidekick listens — it never replies for you.
          </p>
        </div>
        <div className="setup__head-aside">
          <div className="label">READ-ONLY BY DEFAULT</div>
          <p>Sidekick never sends an email or posts to Slack on your behalf without your approval. Even drafts get reviewed first.</p>
        </div>
      </div>

      {/* Integration Tiles */}
      <div className="intg-grid">
        {INTEGRATIONS.map((integration) => {
          const isConnected = connected.has(integration.id);
          const isConnecting = connectingId === integration.id;
          const isExpanded = expandedId === integration.id;
          const error = errors[integration.id];

          return (
            <div
              key={integration.id}
              className={cn(
                'intg-tile',
                isConnected && 'is-connected',
                isExpanded && 'is-expanded'
              )}
            >
              <div className="intg-tile__head">
                <div className="intg-tile__logo">{integration.logo}</div>
                <div className="intg-tile__info">
                  <h3 className="intg-tile__name">{integration.name}</h3>
                  <p className="intg-tile__sub">{integration.description}</p>
                </div>
                <div className="intg-tile__state">
                  {isConnecting && (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      CONNECTING
                    </>
                  )}
                  {isConnected && !isConnecting && (
                    <>
                      <Check className="w-4 h-4" />
                      CONNECTED
                    </>
                  )}
                  {!isConnected && !isConnecting && (
                    <button
                      onClick={() => handleConnect(integration)}
                      disabled={isOAuthPending}
                      className="sk-btn"
                    >
                      Connect
                    </button>
                  )}
                </div>
              </div>

              {/* Error message */}
              {error && (
                <div className="text-red-400 text-sm mt-3 font-sans">
                  {error}
                </div>
              )}

              {/* Expanded Notion config */}
              {integration.id === 'notion' && isConnected && (
                <>
                  <button
                    type="button"
                    onClick={() => setExpandedId(isExpanded ? null : 'notion')}
                    className="w-full flex items-center justify-between text-xs font-mono uppercase tracking-widest text-rust-500 mt-4 pt-4 border-t border-dashed border-charcoal-700/50"
                  >
                    <span>Configure databases</span>
                    {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>

                  {isExpanded && (
                    <div className="intg-tile__body">
                      {/* Primary database - source of truth for customers */}
                      <div className="text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                        Customer source (import from)
                      </div>
                      <div className="intg-dblist">
                        {isLoadingDatabases ? (
                          <div className="flex items-center gap-2 text-charcoal-400 py-4">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span className="text-sm">Loading databases...</span>
                          </div>
                        ) : notionDatabases.length === 0 ? (
                          <div className="text-sm text-charcoal-400 py-4">
                            No databases found. Make sure you've shared databases with the Herofy integration in Notion.
                          </div>
                        ) : (
                          notionDatabases.map((db) => {
                            const isPrimary = primaryDatabaseId === db.id;
                            return (
                              <div
                                key={db.id}
                                className={cn('intg-db', isPrimary && 'is-on')}
                                onClick={() => selectPrimaryDatabase(db.id)}
                              >
                                <div className="intg-db__check" style={{ borderRadius: '50%' }}>
                                  {isPrimary && <Check className="w-3 h-3" />}
                                </div>
                                <div className="intg-db__name">{db.name}</div>
                                <div className="intg-db__detail">{db.detail}</div>
                              </div>
                            );
                          })
                        )}
                      </div>

                      {/* Additional databases for page linking */}
                      {notionDatabases.length > 1 && (
                        <>
                          <div className="text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2 mt-4">
                            Additional databases (for linking docs)
                          </div>
                          <div className="intg-dblist">
                            {notionDatabases
                              .filter(db => db.id !== primaryDatabaseId)
                              .map((db) => {
                                const isLinked = linkedDatabaseIds.has(db.id);
                                return (
                                  <div
                                    key={db.id}
                                    className={cn('intg-db', isLinked && 'is-on')}
                                    onClick={() => toggleLinkedDatabase(db.id)}
                                  >
                                    <div className="intg-db__check">
                                      {isLinked && <Check className="w-3 h-3" />}
                                    </div>
                                    <div className="intg-db__name">{db.name}</div>
                                    <div className="intg-db__detail">{db.detail}</div>
                                  </div>
                                );
                              })}
                          </div>
                          <p className="text-xs text-charcoal-500 mt-2">
                            These databases will be searchable when linking handoff docs, trackers, and notes to customers.
                          </p>
                        </>
                      )}

                      {/* Add more databases - triggers re-auth */}
                      <button
                        type="button"
                        onClick={() => {
                          const integration = INTEGRATIONS.find(i => i.id === 'notion');
                          if (integration) handleConnect(integration);
                        }}
                        className="w-full text-left text-xs text-charcoal-400 hover:text-rust-400 py-2 mt-1 border-t border-dashed border-charcoal-700/50 transition-colors"
                      >
                        + Connect more databases from Notion
                      </button>

                      {/* Trigger mode */}
                      <div className="text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-3 mt-4">
                        When should Sidekick create a customer?
                      </div>
                      <div className="intg-trigger">
                        <button
                          type="button"
                          className={cn('intg-trigger__opt', triggerMode === 'crm' && 'is-on')}
                          onClick={() => handleTriggerModeChange('crm')}
                        >
                          <div className="intg-trigger__opt-head">
                            <span className="radio" />
                            CRM-STYLE
                          </div>
                          <h4 className="intg-trigger__opt-title">
                            Every row is a customer
                          </h4>
                          <p className="intg-trigger__opt-sub">
                            Treat each database row as an active account, regardless of status.
                          </p>
                          <div className="intg-trigger__opt-example">
                            <span className="k">IF</span> row exists in Customer Master
                          </div>
                        </button>
                        <button
                          type="button"
                          className={cn('intg-trigger__opt', triggerMode === 'pipeline' && 'is-on')}
                          onClick={() => handleTriggerModeChange('pipeline')}
                        >
                          <div className="intg-trigger__opt-head">
                            <span className="radio" />
                            PIPELINE-STYLE
                          </div>
                          <h4 className="intg-trigger__opt-title">
                            Only when status matches
                          </h4>
                          <p className="intg-trigger__opt-sub">
                            Only import rows where a status field equals specific values.
                          </p>
                          <div className="intg-trigger__opt-example">
                            <span className="k">IF</span> Status = Closed Won, Onboarding
                          </div>
                        </button>
                      </div>

                      {/* Status picker for pipeline mode */}
                      {triggerMode === 'pipeline' && (
                        <div className="intg-statuses">
                          {['closed-won', 'onboarding', 'active', 'at-risk', 'churned'].map((status) => {
                            const isActive = selectedStatuses.has(status);
                            return (
                              <button
                                key={status}
                                type="button"
                                className={cn('intg-status', isActive && 'is-on')}
                                onClick={() => toggleStatus(status)}
                              >
                                {status.replace('-', ' ')}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="setup__footer">
        <button type="button" className="sk-btn" onClick={onBack}>
          ← Back · Workspace
        </button>
        <div style={{ display: 'flex', gap: 8 }}>
          {connectedCount === 0 && (
            <button type="button" className="sk-btn" onClick={onComplete}>
              Skip · I'll come back
            </button>
          )}
          <button type="button" className="sk-btn sk-btn--primary" onClick={onComplete}>
            Next · Playbooks →
          </button>
        </div>
      </div>
    </>
  );
}
