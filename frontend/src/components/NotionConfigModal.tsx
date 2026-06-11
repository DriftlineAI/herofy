import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, RefreshCw, Check, ChevronDown, Database, ArrowRight, Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWorkspace } from '@/lib/workspace';
import { getAuth } from 'firebase/auth';

const PYTHON_URL = import.meta.env.VITE_PYTHON_URL || 'http://localhost:8081';

// Types
interface NotionDatabase {
  id: string;
  name: string;
  icon: string | null;
  url: string | null;
}

interface NotionProperty {
  name: string;
  type: string;
  options?: { name: string; color: string }[];
}

interface NotionConfig {
  configured: boolean;
  database_id: string | null;
  database_name: string | null;
  field_mappings: Record<string, string>;
  trigger_config: {
    mode: string;
    status_property: string | null;
    trigger_values: string[];
  } | null;
  rich_text_fields: string[];
  last_sync_at: string | null;
}

// Herofy fields that can be mapped
const HEROFY_FIELDS = [
  { key: 'name', label: 'Company Name', required: true },
  { key: 'lifecycle', label: 'Lifecycle Stage', required: false },
  { key: 'arr_cents', label: 'ARR (cents)', required: false },
  { key: 'stakeholder_name', label: 'Primary Contact Name', required: false },
  { key: 'stakeholder_email', label: 'Primary Contact Email', required: false },
  { key: 'owner_name', label: 'Account Owner', required: false },
  { key: 'domain', label: 'Domain', required: false },
  { key: 'one_liner', label: 'One-liner Description', required: false },
];

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSave: () => void;
}

export default function NotionConfigModal({ isOpen, onClose, onSave }: Props) {
  const { workspaceId } = useWorkspace();

  // Loading states
  const [isLoadingDatabases, setIsLoadingDatabases] = useState(false);
  const [isLoadingSchema, setIsLoadingSchema] = useState(false);
  const [isLoadingConfig, setIsLoadingConfig] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Data
  const [databases, setDatabases] = useState<NotionDatabase[]>([]);
  const [properties, setProperties] = useState<NotionProperty[]>([]);
  const [currentConfig, setCurrentConfig] = useState<NotionConfig | null>(null);

  // Form state
  const [selectedDatabase, setSelectedDatabase] = useState<NotionDatabase | null>(null);
  const [fieldMappings, setFieldMappings] = useState<Record<string, string>>({});
  const [triggerMode, setTriggerMode] = useState<'existence_based' | 'status_based'>('existence_based');
  const [statusProperty, setStatusProperty] = useState<string>('');
  const [triggerValues, setTriggerValues] = useState<string[]>([]);

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Fetch helper
  const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
    const auth = getAuth();
    const user = auth.currentUser;
    if (!user) throw new Error('Not authenticated');

    const token = await user.getIdToken();
    const response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }

    return response.json();
  };

  // Load current config on open
  useEffect(() => {
    if (isOpen && workspaceId) {
      loadCurrentConfig();
      loadDatabases();
    }
  }, [isOpen, workspaceId]);

  // Load schema when database is selected
  useEffect(() => {
    if (selectedDatabase) {
      loadSchema(selectedDatabase.id);
    }
  }, [selectedDatabase]);

  const loadCurrentConfig = async () => {
    if (!workspaceId) return;

    setIsLoadingConfig(true);
    setError(null);

    try {
      const config = await fetchWithAuth(
        `${PYTHON_URL}/integrations/notion/config?workspace_id=${workspaceId}`
      );
      setCurrentConfig(config);

      // If already configured, set form state
      if (config.configured && config.database_id) {
        setSelectedDatabase({
          id: config.database_id,
          name: config.database_name || 'Selected Database',
          icon: null,
          url: null,
        });
        setFieldMappings(config.field_mappings || {});

        if (config.trigger_config) {
          setTriggerMode(config.trigger_config.mode as 'existence_based' | 'status_based');
          setStatusProperty(config.trigger_config.status_property || '');
          setTriggerValues(config.trigger_config.trigger_values || []);
        }
      }
    } catch (err) {
      console.error('Failed to load config:', err);
    } finally {
      setIsLoadingConfig(false);
    }
  };

  const loadDatabases = async () => {
    if (!workspaceId) return;

    setIsLoadingDatabases(true);
    setError(null);

    try {
      const data = await fetchWithAuth(
        `${PYTHON_URL}/integrations/notion/databases?workspace_id=${workspaceId}`
      );
      setDatabases(data.databases || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load databases');
    } finally {
      setIsLoadingDatabases(false);
    }
  };

  const loadSchema = async (databaseId: string) => {
    if (!workspaceId) return;

    setIsLoadingSchema(true);

    try {
      const data = await fetchWithAuth(
        `${PYTHON_URL}/integrations/notion/databases/${databaseId}/schema?workspace_id=${workspaceId}`
      );
      setProperties(data.properties || []);
    } catch (err) {
      console.error('Failed to load schema:', err);
    } finally {
      setIsLoadingSchema(false);
    }
  };

  const handleSave = async () => {
    if (!workspaceId || !selectedDatabase) return;

    setIsSaving(true);
    setError(null);

    try {
      await fetchWithAuth(
        `${PYTHON_URL}/integrations/notion/config?workspace_id=${workspaceId}`,
        {
          method: 'PUT',
          body: JSON.stringify({
            database_id: selectedDatabase.id,
            database_name: selectedDatabase.name,
            field_mappings: fieldMappings,
            trigger_config: {
              mode: triggerMode,
              status_property: triggerMode === 'status_based' ? statusProperty : null,
              trigger_values: triggerMode === 'status_based' ? triggerValues : [],
            },
          }),
        }
      );

      onSave();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save configuration');
    } finally {
      setIsSaving(false);
    }
  };

  const updateMapping = (herofyField: string, notionProperty: string) => {
    setFieldMappings(prev => {
      if (!notionProperty) {
        const { [herofyField]: _, ...rest } = prev;
        return rest;
      }
      return { ...prev, [herofyField]: notionProperty };
    });
  };

  // Get status/select properties for trigger config
  const statusProperties = properties.filter(p =>
    p.type === 'select' || p.type === 'status' || p.type === 'multi_select'
  );

  const selectedStatusProp = properties.find(p => p.name === statusProperty);
  const statusOptions = selectedStatusProp?.options || [];

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        />

        {/* Modal */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          className="relative w-full max-w-2xl max-h-[85vh] overflow-hidden bg-charcoal-800 border border-charcoal-700 rounded-xl shadow-2xl"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-charcoal-700">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-charcoal-700 rounded-lg">
                <Database className="w-5 h-5 text-fg-300" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-fg-100">Configure Notion</h2>
                <p className="text-sm text-fg-400">Set up database sync and field mappings</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 text-fg-400 hover:text-fg-200 transition-colors rounded-lg hover:bg-charcoal-700"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="overflow-y-auto max-h-[calc(85vh-140px)] px-6 py-4 space-y-6">
            {/* Error */}
            {error && (
              <div className="p-3 bg-rust-500/10 border border-rust-500/30 rounded-lg text-rust-400 text-sm">
                {error}
              </div>
            )}

            {/* Database Selection */}
            <section>
              <h3 className="text-sm font-medium text-fg-200 mb-3">1. Select Database</h3>
              {isLoadingDatabases ? (
                <div className="flex items-center gap-2 text-fg-400 text-sm">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Loading databases...
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {databases.map(db => (
                    <button
                      key={db.id}
                      onClick={() => setSelectedDatabase(db)}
                      className={cn(
                        'flex items-center gap-2 p-3 rounded-lg border text-left transition-all',
                        selectedDatabase?.id === db.id
                          ? 'bg-rust-500/10 border-rust-500/50 text-fg-100'
                          : 'bg-charcoal-900/50 border-charcoal-700 text-fg-300 hover:border-charcoal-600'
                      )}
                    >
                      <span className="text-lg">{db.icon || '📄'}</span>
                      <span className="truncate">{db.name}</span>
                      {selectedDatabase?.id === db.id && (
                        <Check className="w-4 h-4 text-rust-400 ml-auto flex-shrink-0" />
                      )}
                    </button>
                  ))}
                </div>
              )}
            </section>

            {/* Field Mappings */}
            {selectedDatabase && (
              <section>
                <h3 className="text-sm font-medium text-fg-200 mb-3">2. Map Fields</h3>
                {isLoadingSchema ? (
                  <div className="flex items-center gap-2 text-fg-400 text-sm">
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Loading schema...
                  </div>
                ) : (
                  <div className="space-y-2">
                    {HEROFY_FIELDS.map(field => (
                      <div key={field.key} className="flex items-center gap-3">
                        <div className="w-40 flex-shrink-0">
                          <span className={cn(
                            'text-sm',
                            field.required ? 'text-fg-200' : 'text-fg-400'
                          )}>
                            {field.label}
                            {field.required && <span className="text-rust-400 ml-1">*</span>}
                          </span>
                        </div>
                        <ArrowRight className="w-4 h-4 text-fg-500 flex-shrink-0" />
                        <select
                          value={fieldMappings[field.key] || ''}
                          onChange={(e) => updateMapping(field.key, e.target.value)}
                          className="flex-1 bg-charcoal-900 border border-charcoal-700 rounded px-3 py-2 text-sm text-fg-200 focus:outline-none focus:border-rust-500"
                        >
                          <option value="">-- Not mapped --</option>
                          {properties.map(prop => (
                            <option key={prop.name} value={prop.name}>
                              {prop.name} ({prop.type})
                            </option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            )}

            {/* Trigger Configuration */}
            {selectedDatabase && properties.length > 0 && (
              <section>
                <h3 className="text-sm font-medium text-fg-200 mb-3">3. New Customer Trigger</h3>
                <p className="text-xs text-fg-400 mb-3">
                  When should a new record in Notion create a new customer in Herofy?
                </p>

                <div className="space-y-3">
                  <label className="flex items-start gap-3 p-3 rounded-lg border border-charcoal-700 cursor-pointer hover:border-charcoal-600 transition-colors">
                    <input
                      type="radio"
                      name="triggerMode"
                      checked={triggerMode === 'existence_based'}
                      onChange={() => setTriggerMode('existence_based')}
                      className="mt-0.5"
                    />
                    <div>
                      <div className="text-sm text-fg-200">Any new record</div>
                      <div className="text-xs text-fg-400">
                        Create a customer whenever a new row is added to the database
                      </div>
                    </div>
                  </label>

                  <label className="flex items-start gap-3 p-3 rounded-lg border border-charcoal-700 cursor-pointer hover:border-charcoal-600 transition-colors">
                    <input
                      type="radio"
                      name="triggerMode"
                      checked={triggerMode === 'status_based'}
                      onChange={() => setTriggerMode('status_based')}
                      className="mt-0.5"
                    />
                    <div className="flex-1">
                      <div className="text-sm text-fg-200">When status matches</div>
                      <div className="text-xs text-fg-400 mb-2">
                        Only create a customer when a status field has specific values
                      </div>

                      {triggerMode === 'status_based' && (
                        <div className="space-y-2 mt-3">
                          <select
                            value={statusProperty}
                            onChange={(e) => {
                              setStatusProperty(e.target.value);
                              setTriggerValues([]);
                            }}
                            className="w-full bg-charcoal-900 border border-charcoal-700 rounded px-3 py-2 text-sm text-fg-200 focus:outline-none focus:border-rust-500"
                          >
                            <option value="">Select status property...</option>
                            {statusProperties.map(prop => (
                              <option key={prop.name} value={prop.name}>
                                {prop.name}
                              </option>
                            ))}
                          </select>

                          {statusProperty && statusOptions.length > 0 && (
                            <div className="flex flex-wrap gap-2 mt-2">
                              {statusOptions.map(opt => (
                                <button
                                  key={opt.name}
                                  type="button"
                                  onClick={() => {
                                    setTriggerValues(prev =>
                                      prev.includes(opt.name)
                                        ? prev.filter(v => v !== opt.name)
                                        : [...prev, opt.name]
                                    );
                                  }}
                                  className={cn(
                                    'px-2 py-1 text-xs rounded border transition-colors',
                                    triggerValues.includes(opt.name)
                                      ? 'bg-rust-500/20 border-rust-500/50 text-rust-300'
                                      : 'bg-charcoal-900 border-charcoal-700 text-fg-400 hover:border-charcoal-600'
                                  )}
                                >
                                  {opt.name}
                                  {triggerValues.includes(opt.name) && (
                                    <Check className="w-3 h-3 inline ml-1" />
                                  )}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </label>
                </div>
              </section>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-charcoal-700 bg-charcoal-850">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-fg-300 hover:text-fg-100 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!selectedDatabase || isSaving}
              className={cn(
                'px-4 py-2 text-sm rounded transition-colors flex items-center gap-2',
                selectedDatabase && !isSaving
                  ? 'bg-rust-500 hover:bg-rust-600 text-white cursor-pointer'
                  : 'bg-charcoal-700 text-fg-500 cursor-not-allowed'
              )}
            >
              {isSaving ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Check className="w-4 h-4" />
                  Save Configuration
                </>
              )}
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
