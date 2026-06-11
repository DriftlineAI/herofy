import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useSearchParams } from 'react-router-dom';
import {
  Users,
  ArrowRight,
  ArrowLeft,
  FileSpreadsheet,
  Database,
  Upload,
  Check,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  validateCSVFile,
  parseCSV,
  MAX_CSV_FILE_SIZE,
  generateCSRFToken,
  storeCSRFToken,
} from '@/lib/validation';
import { useConnectIntegration, useDisconnectIntegration, useIntegrationStatus } from '@/lib/dataconnect-hooks';
import { useWorkspace } from '@/lib/workspace';
import type { OnboardingData, UpdateDataFn } from './index';

// Import source icons (using simple colored boxes for now)
const NotionIcon = () => (
  <div className="w-8 h-8 bg-white rounded flex items-center justify-center">
    <span className="text-black font-bold text-lg">N</span>
  </div>
);

const HubSpotIcon = () => (
  <div className="w-8 h-8 bg-[#ff7a59] rounded flex items-center justify-center">
    <span className="text-white font-bold text-sm">HS</span>
  </div>
);

const PipedriveIcon = () => (
  <div className="w-8 h-8 bg-[#017737] rounded flex items-center justify-center">
    <span className="text-white font-bold text-sm">PD</span>
  </div>
);

interface StepImportCustomersProps {
  data: OnboardingData;
  updateData: UpdateDataFn;
  onComplete: () => void;
  onBack: () => void;
}

type ImportSource = OnboardingData['importSource'];
type ImportView = 'select' | 'notion' | 'csv' | 'hubspot' | 'pipedrive' | 'manual';

interface ImportOption {
  id: ImportSource;
  label: string;
  description: string;
  icon: React.ReactNode;
  recommended?: boolean;
}

const IMPORT_OPTIONS: ImportOption[] = [
  {
    id: 'notion',
    label: 'Notion',
    description: 'Import from a Notion database',
    icon: <NotionIcon />,
    recommended: true,
  },
  {
    id: 'csv',
    label: 'CSV File',
    description: 'Upload a spreadsheet',
    icon: <FileSpreadsheet className="w-8 h-8 text-emerald-500" />,
  },
  {
    id: 'hubspot',
    label: 'HubSpot',
    description: 'Connect your CRM',
    icon: <HubSpotIcon />,
  },
  {
    id: 'pipedrive',
    label: 'Pipedrive',
    description: 'Connect your CRM',
    icon: <PipedriveIcon />,
  },
  {
    id: 'manual',
    label: 'Add Manually',
    description: "I'll add customers later",
    icon: <Database className="w-8 h-8 text-charcoal-400" />,
  },
];

export function StepImportCustomers({
  data,
  updateData,
  onComplete,
  onBack,
}: StepImportCustomersProps) {
  const [searchParams] = useSearchParams();

  // Check if returning from OAuth callback - if so, go directly to that import view
  const getInitialView = (): ImportView => {
    const provider = searchParams.get('provider');
    const success = searchParams.get('success');
    if (success === 'true' && provider === 'notion') {
      return 'notion';
    }
    return 'select';
  };

  const getInitialSource = (): ImportSource => {
    const provider = searchParams.get('provider');
    const success = searchParams.get('success');
    if (success === 'true' && provider === 'notion') {
      return 'notion';
    }
    return data.importSource;
  };

  const [view, setView] = useState<ImportView>(getInitialView);
  const [selectedSource, setSelectedSource] = useState<ImportSource>(getInitialSource);

  const handleSourceSelect = (source: ImportSource) => {
    setSelectedSource(source);

    if (source === 'manual') {
      // Skip directly to completion
      updateData({ importSource: 'manual' });
      onComplete();
    } else if (source) {
      // Show source-specific UI
      setView(source);
    }
  };

  const handleImportComplete = () => {
    updateData({ importSource: selectedSource });
    onComplete();
  };

  return (
    <div>
      <AnimatePresence mode="wait">
        {view === 'select' && (
          <motion.div
            key="select"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <ImportSourceSelect
              selectedSource={selectedSource}
              onSelect={handleSourceSelect}
              onBack={onBack}
            />
          </motion.div>
        )}

        {view === 'notion' && (
          <motion.div
            key="notion"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <NotionImport
              data={data}
              updateData={updateData}
              onComplete={handleImportComplete}
              onBack={() => setView('select')}
            />
          </motion.div>
        )}

        {view === 'csv' && (
          <motion.div
            key="csv"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <CSVImport
              data={data}
              updateData={updateData}
              onComplete={handleImportComplete}
              onBack={() => setView('select')}
            />
          </motion.div>
        )}

        {view === 'hubspot' && (
          <motion.div
            key="hubspot"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <CRMImport
              source="hubspot"
              onComplete={handleImportComplete}
              onBack={() => setView('select')}
            />
          </motion.div>
        )}

        {view === 'pipedrive' && (
          <motion.div
            key="pipedrive"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <CRMImport
              source="pipedrive"
              onComplete={handleImportComplete}
              onBack={() => setView('select')}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// Source Selection View
function ImportSourceSelect({
  selectedSource,
  onSelect,
  onBack,
}: {
  selectedSource: ImportSource;
  onSelect: (source: ImportSource) => void;
  onBack: () => void;
}) {
  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 bg-rust-500/20 rounded-lg flex items-center justify-center">
            <Users className="w-5 h-5 text-rust-500" />
          </div>
          <h1 className="font-serif text-3xl text-cream-100">Import your customers</h1>
        </div>
        <p className="text-cream-400 text-lg">
          Bring in your existing customers so we can start finding insights right away.
        </p>
      </div>

      {/* Options Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        {IMPORT_OPTIONS.map((option) => (
          <button
            key={option.id}
            onClick={() => onSelect(option.id)}
            className={cn(
              "relative flex items-start gap-4 p-4 border transition-all text-left",
              selectedSource === option.id
                ? "border-rust-500 bg-rust-500/10"
                : "border-charcoal-700 bg-charcoal-800/50 hover:border-charcoal-600"
            )}
          >
            {option.recommended && (
              <span className="absolute -top-2 -right-2 text-[10px] font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-2 py-0.5">
                Popular
              </span>
            )}
            <div className="flex-shrink-0">{option.icon}</div>
            <div>
              <div className="font-medium text-cream-100">{option.label}</div>
              <div className="text-sm text-charcoal-400">{option.description}</div>
            </div>
          </button>
        ))}
      </div>

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
      </div>
    </div>
  );
}

// Herofy fields that can be mapped
const HEROFY_FIELDS = [
  { id: 'name', label: 'Company Name', required: true },
  { id: 'oneLiner', label: 'Description', required: false },
  { id: 'tier', label: 'Tier', required: false },
  { id: 'arr', label: 'ARR (Annual Revenue)', required: false },
  { id: 'lifecycle', label: 'Lifecycle Stage', required: false },
  { id: 'stakeholderName', label: 'Primary Contact Name', required: false },
  { id: 'stakeholderEmail', label: 'Primary Contact Email', required: false },
  { id: 'stakeholderRole', label: 'Primary Contact Role', required: false },
] as const;

type HeroifyFieldId = typeof HEROFY_FIELDS[number]['id'];

interface NotionProperty {
  id: string;
  name: string;
  type: string;
  options?: string[];
}

interface NotionRowPreview {
  id: string;
  properties: Record<string, string | number | string[] | null>;
}

interface ImportedCustomer {
  id: string;
  name: string;
  tier?: string;
  lifecycle?: string;
}

// Notion Import View
function NotionImport({
  data,
  updateData,
  onComplete,
  onBack,
}: {
  data: OnboardingData;
  updateData: UpdateDataFn;
  onComplete: () => void;
  onBack: () => void;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { workspaceId } = useWorkspace();
  const { connect: startOAuth, isPending: isOAuthPending } = useConnectIntegration();
  const { disconnect: disconnectNotion, isPending: isDisconnecting } = useDisconnectIntegration();
  const { data: integrationStatus, isLoading: statusLoading, refetch: refetchStatus } = useIntegrationStatus('notion');

  // Steps: connect -> select-db -> map-fields -> handoff-config -> preview -> importing -> done
  const [step, setStep] = useState<'connect' | 'select-db' | 'map-fields' | 'handoff-config' | 'preview' | 'importing' | 'done'>('connect');

  const [isConnecting, setIsConnecting] = useState(false);
  const [databases, setDatabases] = useState<Array<{ id: string; name: string; icon?: string }>>([]);
  const [selectedDb, setSelectedDb] = useState<string | null>(null);
  const [isFetching, setIsFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Flag to indicate we just completed OAuth and need to fetch databases
  const [justConnected, setJustConnected] = useState(false);

  // Schema and mapping state
  const [schema, setSchema] = useState<NotionProperty[]>([]);
  const [fieldMappings, setFieldMappings] = useState<Record<HeroifyFieldId, string>>({} as Record<HeroifyFieldId, string>);

  // Database type and import filtering state
  const [statusField, setStatusField] = useState<string>('');
  const [availableStatusOptions, setAvailableStatusOptions] = useState<string[]>([]);
  const [importStatusValues, setImportStatusValues] = useState<string[]>([]); // Which statuses to import

  // Preview and import state
  const [previewRows, setPreviewRows] = useState<NotionRowPreview[]>([]);
  const [importedCustomers, setImportedCustomers] = useState<ImportedCustomer[]>([]);
  const [importErrors, setImportErrors] = useState<string[]>([]);
  const [skippedCount, setSkippedCount] = useState<number>(0);

  const isConnected = integrationStatus?.connected ?? false;

  const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

  const getAuthHeaders = useCallback(async () => {
    const token = await (await import('firebase/auth')).getAuth().currentUser?.getIdToken();
    return { Authorization: `Bearer ${token}` };
  }, []);

  const fetchDatabases = useCallback(async () => {
    if (!workspaceId) return;
    setIsFetching(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${PYTHON_URL}/integrations/notion/databases?workspace_id=${workspaceId}`,
        { headers }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to fetch databases');
      }

      const data = await response.json();
      setDatabases(data.databases || []);
    } catch (err) {
      console.error('Failed to fetch Notion databases:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch databases');
    } finally {
      setIsFetching(false);
    }
  }, [workspaceId, getAuthHeaders]);

  const fetchSchema = useCallback(async (databaseId: string) => {
    if (!workspaceId) return;
    setIsFetching(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${PYTHON_URL}/integrations/notion/databases/${databaseId}/schema?workspace_id=${workspaceId}`,
        { headers }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to fetch database schema');
      }

      const data = await response.json();
      setSchema(data.properties || []);

      // Auto-map fields with matching names
      const autoMappings: Record<string, string> = {};
      let autoStatusField = '';
      let autoStatusOptions: string[] = [];

      for (const prop of data.properties || []) {
        const propNameLower = prop.name.toLowerCase();
        // Company fields
        if (propNameLower.includes('name') || propNameLower.includes('company')) {
          autoMappings['name'] = prop.name;
        } else if (propNameLower.includes('description') || propNameLower.includes('oneliner') || propNameLower.includes('about')) {
          autoMappings['oneLiner'] = prop.name;
        } else if (propNameLower.includes('tier') || propNameLower.includes('plan') || propNameLower.includes('package')) {
          autoMappings['tier'] = prop.name;
        } else if (propNameLower.includes('arr') || propNameLower.includes('revenue') || propNameLower.includes('mrr')) {
          autoMappings['arr'] = prop.name;
        } else if (propNameLower.includes('lifecycle') || propNameLower.includes('stage') || propNameLower.includes('status')) {
          autoMappings['lifecycle'] = prop.name;
          // Also use this as the status field for handoff detection
          if (prop.type === 'select' || prop.type === 'status') {
            autoStatusField = prop.name;
            autoStatusOptions = prop.options || [];
          }
        }
        // Stakeholder/Contact fields
        else if (
          propNameLower.includes('decision maker') ||
          propNameLower.includes('champion') ||
          propNameLower.includes('contact name') ||
          propNameLower.includes('primary contact') ||
          propNameLower.includes('stakeholder')
        ) {
          autoMappings['stakeholderName'] = prop.name;
        } else if (
          propNameLower.includes('contact email') ||
          propNameLower.includes('decision maker email') ||
          propNameLower.includes('champion email') ||
          (propNameLower.includes('email') && prop.type === 'email')
        ) {
          autoMappings['stakeholderEmail'] = prop.name;
        } else if (
          propNameLower.includes('contact role') ||
          propNameLower.includes('title') ||
          propNameLower.includes('position')
        ) {
          autoMappings['stakeholderRole'] = prop.name;
        }
      }
      setFieldMappings(autoMappings as Record<HeroifyFieldId, string>);

      // Set up status field defaults
      if (autoStatusField) {
        setStatusField(autoStatusField);
        setAvailableStatusOptions(autoStatusOptions);
      }

      // Reset status selections for fresh configuration
      setImportStatusValues([]);

      setStep('map-fields');
    } catch (err) {
      console.error('Failed to fetch schema:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch database schema');
    } finally {
      setIsFetching(false);
    }
  }, [workspaceId, getAuthHeaders]);

  const fetchPreview = useCallback(async () => {
    if (!workspaceId || !selectedDb) return;
    setIsFetching(true);
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${PYTHON_URL}/integrations/notion/databases/${selectedDb}/rows?workspace_id=${workspaceId}&limit=10`,
        { headers }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to fetch preview');
      }

      const data = await response.json();
      setPreviewRows(data.rows || []);
      setStep('preview');
    } catch (err) {
      console.error('Failed to fetch preview:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch preview');
    } finally {
      setIsFetching(false);
    }
  }, [workspaceId, selectedDb, getAuthHeaders]);

  const handleImport = useCallback(async () => {
    if (!workspaceId || !selectedDb) return;
    setStep('importing');
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const mappingsArray = Object.entries(fieldMappings)
        .filter(([_, notionProp]) => notionProp)
        .map(([herofyField, notionProp]) => ({
          notion_property: notionProp,
          herofy_field: herofyField,
        }));

      const response = await fetch(
        `${PYTHON_URL}/integrations/notion/import?workspace_id=${workspaceId}`,
        {
          method: 'POST',
          headers: { ...headers, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            database_id: selectedDb,
            field_mappings: mappingsArray,
            status_field: statusField || null,
            import_status_values: statusField ? importStatusValues : [],
          }),
        }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Import failed');
      }

      const result = await response.json();
      setImportedCustomers(result.customers || []);
      setImportErrors(result.errors || []);
      setSkippedCount(result.skipped_count || 0);

      // Update onboarding data
      updateData({
        notionConfig: {
          primaryDatabaseId: selectedDb,
          fieldMappings: fieldMappings as Record<string, string>,
        },
        integrations: { ...data.integrations, notion: true },
      });

      setStep('done');
    } catch (err) {
      console.error('Import failed:', err);
      setError(err instanceof Error ? err.message : 'Import failed');
      setStep('preview'); // Go back to preview on error
    }
  }, [workspaceId, selectedDb, fieldMappings, statusField, importStatusValues, getAuthHeaders, updateData, data.integrations]);

  const handleConnect = useCallback(async () => {
    console.log('[StepImportCustomers/NotionImport] handleConnect called', { workspaceId, isConnecting, isOAuthPending });
    if (!workspaceId) {
      setError('Workspace not created yet. Please go back and complete the first step.');
      return;
    }
    setIsConnecting(true);
    setError(null);

    try {
      sessionStorage.setItem('herofy_oauth_return', '/setup');
      console.log('[StepImportCustomers/NotionImport] Calling startOAuth...');
      await startOAuth('notion');
      console.log('[StepImportCustomers/NotionImport] startOAuth completed');
    } catch (err) {
      console.error('[StepImportCustomers/NotionImport] OAuth error:', err);
      setError(err instanceof Error ? err.message : 'Connection failed. Please try again.');
      setIsConnecting(false);
    }
  }, [workspaceId, startOAuth]);

  const handleDisconnect = useCallback(async () => {
    try {
      await disconnectNotion('notion');
      // Reset state after disconnect
      setStep('connect');
      setDatabases([]);
      setSelectedDb(null);
      setSchema([]);
      setFieldMappings({} as Record<HeroifyFieldId, string>);
      setStatusField('');
      setAvailableStatusOptions([]);
      setImportStatusValues([]);
      setPreviewRows([]);
      // Update parent state
      updateData({ integrations: { ...data.integrations, notion: false } });
      // Refetch status to confirm
      refetchStatus();
    } catch (err) {
      console.error('[StepImportCustomers/NotionImport] Disconnect error:', err);
      setError(err instanceof Error ? err.message : 'Failed to disconnect. Please try again.');
    }
  }, [disconnectNotion, updateData, data.integrations, refetchStatus]);

  const handleSelectDatabase = (dbId: string) => {
    setSelectedDb(dbId);
    fetchSchema(dbId);
  };

  const handleMappingChange = (herofyField: HeroifyFieldId, notionProp: string) => {
    setFieldMappings((prev) => ({ ...prev, [herofyField]: notionProp }));
  };

  const getMappedValue = (row: NotionRowPreview, herofyField: HeroifyFieldId): string => {
    const notionProp = fieldMappings[herofyField];
    if (!notionProp) return '—';
    const value = row.properties[notionProp];
    if (value === null || value === undefined) return '—';
    if (Array.isArray(value)) return value.join(', ');
    return String(value);
  };

  // Update step based on connection status
  useEffect(() => {
    console.log('[StepImportCustomers] Connection status changed:', { isConnected, currentStep: step });
    if (isConnected && step === 'connect') {
      console.log('[StepImportCustomers] Already connected, moving to select-db');
      setStep('select-db');
    }
  }, [isConnected, step]);

  // Handle OAuth callback result from URL params
  // Use a ref to prevent re-running this effect after we clear the params
  const hasHandledCallback = useRef(false);
  useEffect(() => {
    const success = searchParams.get('success');
    const errorParam = searchParams.get('error');
    const provider = searchParams.get('provider');

    // Only process if this is a Notion callback and we haven't handled it yet
    if (provider === 'notion' && !hasHandledCallback.current) {
      hasHandledCallback.current = true;

      if (success === 'true') {
        // Clear URL params first to prevent re-triggering
        setSearchParams({});
        // Update integration status
        refetchStatus();
        // Use functional update to avoid dependency on data.integrations
        updateData(prev => ({
          integrations: { ...prev.integrations, notion: true },
        }));
        setStep('select-db');
        // Mark that we just connected - will trigger database fetch when ready
        setJustConnected(true);
      } else if (errorParam) {
        setError(`Connection failed: ${errorParam}`);
        setSearchParams({});
      }
    }
  }, [searchParams, setSearchParams, refetchStatus, updateData]);

  // Fetch databases when connected (either from status check or just after OAuth)
  useEffect(() => {
    const shouldFetch = (isConnected || justConnected) && databases.length === 0 && workspaceId;
    if (shouldFetch) {
      // Small delay to ensure backend has processed the OAuth token
      const timer = setTimeout(() => {
        fetchDatabases();
        setJustConnected(false);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isConnected, justConnected, workspaceId, databases.length, fetchDatabases]);

  const isLoadingStatus = statusLoading || isConnecting || isOAuthPending;
  const hasRequiredMapping = !!fieldMappings['name'];

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          <NotionIcon />
          <h1 className="font-serif text-3xl text-cream-100">Import from Notion</h1>
        </div>
        <p className="text-cream-400">
          {step === 'connect' && 'Connect your Notion workspace to import customer data.'}
          {step === 'select-db' && 'Select the database containing your customers.'}
          {step === 'map-fields' && 'Map Notion columns to Herofy fields.'}
          {step === 'handoff-config' && 'Filter which records to import (optional).'}
          {step === 'preview' && 'Review what will be imported.'}
          {step === 'importing' && 'Importing your customers...'}
          {step === 'done' && 'Import complete!'}
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="flex items-center gap-2 text-red-400 mb-6 p-4 border border-red-500/30 bg-red-500/10">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Step: Connect */}
      {step === 'connect' && (
        <>
          <div className="border border-charcoal-700 bg-charcoal-800/50 p-6 mb-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-cream-100 mb-1">Connect Notion</div>
                <div className="text-sm text-charcoal-400">
                  We'll request read-only access to your databases
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleConnect}
                  disabled={isLoadingStatus}
                  className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-white text-black px-4 py-2 hover:bg-cream-200 transition-colors disabled:opacity-50"
                >
                  {isLoadingStatus ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      {isConnecting ? 'Connecting...' : 'Loading...'}
                    </>
                  ) : (
                    'Connect'
                  )}
                </button>
                <button
                  onClick={handleDisconnect}
                  disabled={isDisconnecting}
                  className="text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
                  title="Force disconnect if stuck with wrong account"
                >
                  {isDisconnecting ? 'Resetting...' : 'Force Reset'}
                </button>
              </div>
            </div>
          </div>
          {error && (
            <div className="border border-red-500/50 bg-red-500/10 p-4 mb-6 text-red-400 text-sm">
              {error}
            </div>
          )}
        </>
      )}

      {/* Step: Select Database */}
      {step === 'select-db' && (
        <>
          <div className="border border-emerald-500/50 bg-emerald-500/10 p-4 mb-6 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Check className="w-5 h-5 text-emerald-500" />
              <span className="text-emerald-400">Connected to Notion</span>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleDisconnect}
                disabled={isDisconnecting}
                className="text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
              >
                {isDisconnecting ? 'Disconnecting...' : 'Change Account'}
              </button>
              <button
                onClick={fetchDatabases}
                disabled={isFetching}
                className="text-xs text-charcoal-400 hover:text-cream-200 transition-colors"
              >
                {isFetching ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
          </div>

          {isFetching && databases.length === 0 && (
            <div className="flex items-center gap-3 text-charcoal-400 mb-6">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading your Notion databases...
            </div>
          )}

          {!isFetching && databases.length === 0 && (
            <div className="border border-amber-500/30 bg-amber-500/10 p-4 mb-6">
              <div className="text-amber-400 mb-2">No databases found</div>
              <div className="text-sm text-charcoal-400">
                Make sure you've shared at least one database with the Herofy integration in Notion.
              </div>
            </div>
          )}

          {databases.length > 0 && (
            <div className="mb-6">
              <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-3">
                Select Database ({databases.length} available)
              </label>
              <div className="space-y-2">
                {databases.map((db) => (
                  <button
                    key={db.id}
                    onClick={() => handleSelectDatabase(db.id)}
                    disabled={isFetching}
                    className={cn(
                      "w-full flex items-center justify-between p-4 border transition-all text-left disabled:opacity-50",
                      selectedDb === db.id
                        ? "border-rust-500 bg-rust-500/10"
                        : "border-charcoal-700 bg-charcoal-800/50 hover:border-charcoal-600"
                    )}
                  >
                    <div className="flex items-center gap-3">
                      {db.icon && <span className="text-lg">{db.icon}</span>}
                      <span className="text-cream-100">{db.name}</span>
                    </div>
                    {isFetching && selectedDb === db.id && <Loader2 className="w-4 h-4 animate-spin text-rust-500" />}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Step: Map Fields */}
      {step === 'map-fields' && (
        <>
          <div className="mb-6">
            <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-3">
              Field Mapping
            </label>
            <p className="text-sm text-charcoal-400 mb-4">
              Map your Notion columns to Herofy customer fields. Company Name is required.
            </p>
            <div className="space-y-3">
              {HEROFY_FIELDS.map((field) => (
                <div key={field.id} className="flex items-center gap-4">
                  <div className="w-40 text-sm text-cream-300">
                    {field.label}
                    {field.required && <span className="text-rust-400 ml-1">*</span>}
                  </div>
                  <ArrowRight className="w-4 h-4 text-charcoal-500" />
                  <select
                    value={fieldMappings[field.id] || ''}
                    onChange={(e) => handleMappingChange(field.id, e.target.value)}
                    className="flex-1 bg-charcoal-800 border border-charcoal-700 text-cream-100 px-3 py-2 text-sm focus:border-rust-500 focus:outline-none"
                  >
                    <option value="">— Select column —</option>
                    {schema.map((prop) => (
                      <option key={prop.id} value={prop.name}>
                        {prop.name} ({prop.type})
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-between pt-4">
            <button
              onClick={() => setStep('select-db')}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            <button
              onClick={() => setStep('handoff-config')}
              disabled={!hasRequiredMapping}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold disabled:opacity-50"
            >
              Continue
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </>
      )}

      {/* Step: Import Filtering */}
      {step === 'handoff-config' && (
        <>
          <div className="mb-6">
            <p className="text-sm text-charcoal-400 mb-6">
              You can set up onboarding plans after import is complete.
            </p>

            {/* Status Field Selection */}
            <div className="mb-6">
              <label className="block text-sm text-cream-300 mb-2">
                Filter by field (optional)
              </label>
              <select
                value={statusField}
                onChange={(e) => {
                  setStatusField(e.target.value);
                  const selectedProp = schema.find(p => p.name === e.target.value);
                  setAvailableStatusOptions(selectedProp?.options || []);
                  setImportStatusValues([]);
                }}
                className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-100 px-3 py-2 text-sm focus:border-rust-500 focus:outline-none"
              >
                <option value="">— Import all records —</option>
                {schema
                  .filter(prop => prop.type === 'select' || prop.type === 'status' || prop.type === 'checkbox')
                  .map((prop) => (
                    <option key={prop.id} value={prop.name}>
                      Filter by: {prop.name} ({prop.type === 'checkbox' ? 'Yes/No' : `${prop.options?.length || 0} options`})
                    </option>
                  ))}
              </select>
            </div>

            {/* Status Values Selection */}
            {statusField && availableStatusOptions.length > 0 && (
              <div className="mb-6">
                <label className="block text-sm text-cream-300 mb-2">
                  Import records where {statusField} is:
                </label>
                <div className="flex flex-wrap gap-2">
                  {availableStatusOptions.map((option) => {
                    const isSelected = importStatusValues.includes(option);
                    return (
                      <button
                        key={option}
                        onClick={() => {
                          if (isSelected) {
                            setImportStatusValues(prev => prev.filter(v => v !== option));
                          } else {
                            setImportStatusValues(prev => [...prev, option]);
                          }
                        }}
                        className={cn(
                          "px-3 py-1.5 text-sm border transition-all",
                          isSelected
                            ? "border-emerald-500 bg-emerald-500/20 text-emerald-400"
                            : "border-charcoal-600 text-charcoal-400 hover:border-charcoal-500"
                        )}
                      >
                        {isSelected && <Check className="w-3 h-3 inline mr-1" />}
                        {option}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* No filter fields available */}
            {schema.filter(p => p.type === 'select' || p.type === 'status' || p.type === 'checkbox').length === 0 && (
              <div className="border border-charcoal-700 bg-charcoal-800/50 p-4 mb-6">
                <div className="text-charcoal-400 text-sm">
                  No status/select/checkbox fields found. All records will be imported.
                </div>
              </div>
            )}

            {/* Summary */}
            {statusField && importStatusValues.length > 0 && (
              <div className="border border-emerald-500/30 bg-emerald-500/10 p-4 mb-6">
                <div className="text-sm text-emerald-400">
                  ✓ Importing records where {statusField} = "{importStatusValues.join('" or "')}"
                </div>
              </div>
            )}

            {!statusField && (
              <div className="border border-charcoal-700 bg-charcoal-800/50 p-4 mb-6">
                <div className="text-sm text-charcoal-400">
                  All records will be imported.
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-between pt-4">
            <button
              onClick={() => setStep('map-fields')}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            <button
              onClick={fetchPreview}
              disabled={isFetching || (statusField && importStatusValues.length === 0)}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold disabled:opacity-50"
            >
              {isFetching ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Preview Import
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </>
      )}

      {/* Step: Preview */}
      {step === 'preview' && (
        <>
          <div className="mb-6">
            <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-3">
              Preview ({previewRows.length} rows shown)
            </label>
            <div className="border border-charcoal-700 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-charcoal-800">
                  <tr>
                    <th className="text-left px-4 py-2 text-charcoal-400 font-mono text-xs">Name</th>
                    <th className="text-left px-4 py-2 text-charcoal-400 font-mono text-xs">Tier</th>
                    <th className="text-left px-4 py-2 text-charcoal-400 font-mono text-xs">ARR</th>
                    <th className="text-left px-4 py-2 text-charcoal-400 font-mono text-xs">Lifecycle</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-charcoal-700">
                  {previewRows.map((row) => (
                    <tr key={row.id} className="bg-charcoal-800/50">
                      <td className="px-4 py-2 text-cream-100">{getMappedValue(row, 'name')}</td>
                      <td className="px-4 py-2 text-cream-300">{getMappedValue(row, 'tier')}</td>
                      <td className="px-4 py-2 text-cream-300">{getMappedValue(row, 'arr')}</td>
                      <td className="px-4 py-2 text-cream-300">{getMappedValue(row, 'lifecycle')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Show import summary */}
          {statusField && importStatusValues.length > 0 && (
            <div className="border border-charcoal-700 bg-charcoal-800/50 p-4 mb-6">
              <div className="text-cream-300 text-sm">
                <strong>Importing:</strong> Records where {statusField} = "{importStatusValues.join('" or "')}"
              </div>
            </div>
          )}

          <div className="flex justify-between pt-4">
            <button
              onClick={() => setStep('handoff-config')}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            <button
              onClick={handleImport}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold"
            >
              Import All Customers
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </>
      )}

      {/* Step: Importing */}
      {step === 'importing' && (
        <div className="text-center py-12">
          <Loader2 className="w-12 h-12 animate-spin text-rust-500 mx-auto mb-4" />
          <p className="text-cream-300">Importing customers from Notion...</p>
        </div>
      )}

      {/* Step: Done */}
      {step === 'done' && (
        <>
          <div className="border border-emerald-500/50 bg-emerald-500/10 p-6 mb-6">
            <div className="flex items-center gap-3 mb-4">
              <Check className="w-6 h-6 text-emerald-500" />
              <span className="text-lg font-medium text-emerald-400">
                Imported {importedCustomers.length} customer{importedCustomers.length !== 1 ? 's' : ''}
              </span>
            </div>
            {importedCustomers.length > 0 && (
              <div className="space-y-2">
                {importedCustomers.slice(0, 5).map((c) => (
                  <div key={c.id} className="text-sm text-cream-300">
                    • {c.name} {c.tier && `(${c.tier})`}
                  </div>
                ))}
                {importedCustomers.length > 5 && (
                  <div className="text-sm text-charcoal-400">
                    ...and {importedCustomers.length - 5} more
                  </div>
                )}
              </div>
            )}
            {skippedCount > 0 && (
              <div className="mt-4 pt-4 border-t border-emerald-500/30 text-sm text-charcoal-400">
                {skippedCount} record{skippedCount !== 1 ? 's' : ''} skipped (didn't match filter)
              </div>
            )}
            <div className="mt-4 pt-4 border-t border-emerald-500/30 text-sm text-charcoal-400">
              AI enrichment is running in the background. You can set up onboarding plans after setup.
            </div>
          </div>

          {importErrors.length > 0 && (
            <div className="border border-amber-500/30 bg-amber-500/10 p-4 mb-6">
              <div className="text-amber-400 mb-2">Some rows had issues:</div>
              <div className="text-sm text-charcoal-400 space-y-1">
                {importErrors.map((err, i) => (
                  <div key={i}>• {err}</div>
                ))}
              </div>
            </div>
          )}

          <div className="flex justify-end pt-4">
            <button
              onClick={onComplete}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold"
            >
              Continue Setup
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </>
      )}

      {/* Back button for connect and select-db steps */}
      {(step === 'connect' || step === 'select-db') && (
        <div className="flex justify-between pt-4">
          <button
            type="button"
            onClick={onBack}
            className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
          {step === 'select-db' && databases.length > 0 && !selectedDb && (
            <button
              onClick={onComplete}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors"
            >
              Skip Import
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// CSV Import View
function CSVImport({
  data,
  updateData,
  onComplete,
  onBack,
}: {
  data: OnboardingData;
  updateData: UpdateDataFn;
  onComplete: () => void;
  onBack: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [preview, setPreview] = useState<Array<Record<string, string>>>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const maxSizeMB = MAX_CSV_FILE_SIZE / 1024 / 1024;

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    setError(null);
    setPreview([]);
    setHeaders([]);

    // Validate file
    const validation = validateCSVFile(selectedFile);
    if (!validation.valid) {
      setError(validation.error || 'Invalid file');
      return;
    }

    setFile(selectedFile);
    setIsProcessing(true);

    // Parse CSV with safe parser
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const text = event.target?.result as string;
        const { headers: parsedHeaders, rows, error: parseError } = parseCSV(text, 5);

        if (parseError) {
          setError(parseError);
          setFile(null);
          return;
        }

        // Count total rows (for display)
        const allLines = text.split(/\r?\n/).filter(line => line.trim());
        setTotalRows(Math.max(0, allLines.length - 1)); // Subtract header

        setHeaders(parsedHeaders);
        setPreview(rows);
      } catch (err) {
        setError('Could not parse CSV file. Please check the format.');
        setFile(null);
      } finally {
        setIsProcessing(false);
      }
    };
    reader.onerror = () => {
      setError('Failed to read file');
      setFile(null);
      setIsProcessing(false);
    };
    reader.readAsText(selectedFile);
  };

  const handleImport = () => {
    // Data is already sanitized by parseCSV
    updateData({
      csvData: {
        customers: preview.map((row) => ({
          name: row['Company'] || row['Name'] || row['company'] || row['name'] || '',
          domain: row['Domain'] || row['domain'] || row['Website'] || row['website'] || '',
          // Stakeholder/Contact fields
          stakeholderName:
            row['Contact'] || row['Contact Name'] || row['Decision Maker'] ||
            row['Champion'] || row['Primary Contact'] ||
            row['contact'] || row['contact_name'] || '',
          stakeholderEmail:
            row['Contact Email'] || row['Email'] || row['Contact_Email'] ||
            row['contact_email'] || row['email'] || '',
          stakeholderRole:
            row['Title'] || row['Role'] || row['Position'] ||
            row['title'] || row['role'] || row['position'] || '',
        })),
      },
    });
    onComplete();
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          <FileSpreadsheet className="w-10 h-10 text-emerald-500" />
          <h1 className="font-serif text-3xl text-cream-100">Import from CSV</h1>
        </div>
        <p className="text-cream-400">
          Upload a CSV file with your customer list. We'll map the columns automatically.
        </p>
      </div>

      {/* File Upload */}
      <div
        onClick={() => !isProcessing && fileInputRef.current?.click()}
        className={cn(
          "border-2 border-dashed p-8 text-center transition-colors mb-6",
          isProcessing
            ? "border-charcoal-600 bg-charcoal-800/50 cursor-wait"
            : file
            ? "border-emerald-500/50 bg-emerald-500/10 cursor-pointer"
            : "border-charcoal-600 hover:border-charcoal-500 bg-charcoal-800/50 cursor-pointer"
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          onChange={handleFileSelect}
          className="hidden"
        />
        {isProcessing ? (
          <div className="flex items-center justify-center gap-3">
            <Loader2 className="w-5 h-5 text-rust-500 animate-spin" />
            <span className="text-cream-400">Processing file...</span>
          </div>
        ) : file ? (
          <div className="flex items-center justify-center gap-3">
            <Check className="w-5 h-5 text-emerald-500" />
            <span className="text-cream-100">{file.name}</span>
            <span className="text-charcoal-400 text-sm">
              ({Math.round(file.size / 1024)} KB)
            </span>
            {totalRows > 0 && (
              <span className="text-emerald-400 text-sm">
                • {totalRows} row{totalRows !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        ) : (
          <div>
            <Upload className="w-8 h-8 text-charcoal-500 mx-auto mb-3" />
            <div className="text-cream-200 mb-1">Drop your CSV here or click to browse</div>
            <div className="text-sm text-charcoal-500">
              Include columns: Company Name, Domain, Contact Name, Contact Email, Title (optional)
            </div>
            <div className="text-xs text-charcoal-600 mt-2">
              Max file size: {maxSizeMB}MB
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 text-red-400 mb-6">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* Preview */}
      {preview.length > 0 && (
        <div className="mb-6">
          <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-3">
            Preview ({preview.length} rows shown)
          </label>
          <div className="border border-charcoal-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-charcoal-800 border-b border-charcoal-700">
                    {Object.keys(preview[0]).map((header) => (
                      <th
                        key={header}
                        className="px-4 py-2 text-left text-xs font-mono uppercase tracking-widest text-charcoal-400"
                      >
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.map((row, i) => (
                    <tr key={i} className="border-b border-charcoal-700/50">
                      {Object.values(row).map((value, j) => (
                        <td key={j} className="px-4 py-2 text-cream-200">
                          {value || <span className="text-charcoal-500">—</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
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
        {preview.length > 0 && (
          <button
            onClick={handleImport}
            className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold"
          >
            Import {preview.length}+ Customers
            <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}

// Generic CRM Import View (HubSpot, Pipedrive)
function CRMImport({
  source,
  onComplete,
  onBack,
}: {
  source: 'hubspot' | 'pipedrive';
  onComplete: () => void;
  onBack: () => void;
}) {
  const [isConnecting, setIsConnecting] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [companies, setCompanies] = useState<Array<{ id: string; name: string }>>([]);

  const config = {
    hubspot: {
      name: 'HubSpot',
      icon: <HubSpotIcon />,
      color: '#ff7a59',
    },
    pipedrive: {
      name: 'Pipedrive',
      icon: <PipedriveIcon />,
      color: '#017737',
    },
  }[source];

  const handleConnect = async () => {
    setIsConnecting(true);
    // TODO: Implement OAuth flow
    await new Promise((r) => setTimeout(r, 1500));
    setIsConnecting(false);
    setIsConnected(true);
    // Mock companies
    setCompanies([
      { id: '1', name: 'Acme Corp' },
      { id: '2', name: 'TechCorp Solutions' },
      { id: '3', name: 'Globex Industries' },
      { id: '4', name: 'Wayne Enterprises' },
      { id: '5', name: 'Stark Industries' },
    ]);
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          {config.icon}
          <h1 className="font-serif text-3xl text-cream-100">Import from {config.name}</h1>
        </div>
        <p className="text-cream-400">
          Connect your {config.name} account to import companies and contacts.
        </p>
      </div>

      {/* Connect Step */}
      {!isConnected ? (
        <div className="border border-charcoal-700 bg-charcoal-800/50 p-6 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-medium text-cream-100 mb-1">Connect {config.name}</div>
              <div className="text-sm text-charcoal-400">
                We'll import your companies, contacts, and deal data
              </div>
            </div>
            <button
              onClick={handleConnect}
              disabled={isConnecting}
              style={{ backgroundColor: config.color }}
              className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest text-white px-4 py-2 hover:opacity-90 transition-opacity disabled:opacity-50"
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
          </div>
        </div>
      ) : (
        <>
          {/* Connected State */}
          <div className="border border-emerald-500/50 bg-emerald-500/10 p-4 mb-6 flex items-center gap-3">
            <Check className="w-5 h-5 text-emerald-500" />
            <span className="text-emerald-400">Connected to {config.name}</span>
          </div>

          {/* Companies Preview */}
          <div className="border border-charcoal-700 bg-charcoal-800/50 p-4 mb-6">
            <div className="text-sm text-cream-100 mb-3">
              Found {companies.length} companies to import:
            </div>
            <div className="space-y-1">
              {companies.slice(0, 5).map((company) => (
                <div key={company.id} className="text-sm text-cream-300">
                  • {company.name}
                </div>
              ))}
              {companies.length > 5 && (
                <div className="text-sm text-charcoal-400">
                  ... and {companies.length - 5} more
                </div>
              )}
            </div>
          </div>
        </>
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
        {isConnected && (
          <button
            onClick={onComplete}
            className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold"
          >
            Import {companies.length} Companies
            <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
