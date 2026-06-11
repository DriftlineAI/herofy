import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Loader2, Check, ChevronRight, ChevronDown, AlertCircle, Database, Sparkles, FileText, Link2, Upload, X, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useCustomers, useNotionDatabases, useIntegrationStatus, useImportNotionCustomers, useNotionDatabaseSchema, useSearchNotionPages, useLinkPageToCustomer, useUnlinkPageFromCustomer, useClassifyCustomers, useClassifyCustomersStreaming, type NotionPropertySchema, type NotionPageResult, type CustomerClassification } from '@/lib/dataconnect-hooks';
import { useSetupProgress, type CustomerProgress } from '@/lib/realtime-hooks';
import { useWorkspace } from '@/lib/workspace';
import type { OnboardingData, UpdateDataFn } from './index';
import { NotionLinkPasteModal } from './NotionLinkPasteModal';

interface StepCustomersProps {
  data: OnboardingData;
  updateData: UpdateDataFn;
  onComplete: () => void;
  onBack: () => void;
}

// Customer with onboarding state
interface CustomerWithState {
  id: string;
  name: string;
  tier?: string;
  lifecycle?: string;
  source?: string;
  // Onboarding-specific
  onboardingState?: 'pointer-needed' | 'mid-onboarding' | 'ready' | 'auto-handled';
  onboardingDayCurrent?: number;
  onboardingDayTotal?: number;
  hasOnboardingPlan?: boolean;
  hasMeetingRecaps?: boolean;
  hasRenewalPlan?: boolean;
}

// Property with metadata for column picker (extends NotionPropertySchema)
interface NotionProperty extends NotionPropertySchema {
  role: 'lifecycle' | 'name' | 'tier' | 'arr' | 'date' | 'other';
  valuePreview?: string; // e.g., "Onboarding · Active · Renewal · Churned"
}

type SubStep = 'found' | 'column-picker' | 'bucketed';

// Detect property role from name
function detectPropertyRole(propName: string): NotionProperty['role'] {
  const normalized = propName.toLowerCase().replace(/[_\-\s]/g, '');
  if (/^(name|title|company|customer|account|client|org)/.test(normalized)) return 'name';
  if (/^(stage|lifecycle|status|phase|state)/.test(normalized)) return 'lifecycle';
  if (/^(tier|plan|package|level|segment)/.test(normalized)) return 'tier';
  if (/^(arr|revenue|mrr|contract|value)/.test(normalized)) return 'arr';
  if (/^(start|created|date|joined|signed)/.test(normalized)) return 'date';
  return 'other';
}

// Categorize customer by onboarding state
function categorizeCustomer(customer: CustomerWithState): CustomerWithState['onboardingState'] {
  const lifecycle = customer.lifecycle?.toLowerCase() || '';

  if (lifecycle === 'onboarding') {
    // Check if we have enough info to handle automatically
    if (customer.hasOnboardingPlan) {
      return 'mid-onboarding';
    }
    return 'pointer-needed';
  }

  if (lifecycle === 'active' || lifecycle === 'renewing') {
    return 'auto-handled';
  }

  // Default: ready for sidekick to process
  return 'ready';
}

export function StepCustomers({
  data,
  updateData: _updateData,  // TODO: Use for saving column selections
  onComplete,
  onBack,
}: StepCustomersProps) {
  const { workspaceId } = useWorkspace();
  const { data: customersData, isLoading, refetch: refetchCustomers } = useCustomers();
  const { data: integrationStatus } = useIntegrationStatus('notion');
  const { data: notionDatabasesData } = useNotionDatabases({ enabled: integrationStatus?.connected });
  const { importCustomers, reimportWithLifecycleColumn, isLoading: isImporting } = useImportNotionCustomers();
  const { fetchFullSchema } = useNotionDatabaseSchema();
  const {
    classifyCustomers,
    getClassification,
    clearClassifications,
    updateClassification,
    classifications,
    isLoading: isClassifying,
  } = useClassifyCustomers();

  // Streaming classification with Firestore real-time updates
  const { startClassification, isStarting: isStartingStreaming } = useClassifyCustomersStreaming();
  const firestoreProgress = useSetupProgress(workspaceId);

  // Track if we've started streaming classification
  const [useStreamingMode, setUseStreamingMode] = useState(false);

  // Local state for customers from import (used immediately, before DataConnect syncs)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [localImportedCustomers, setLocalImportedCustomers] = useState<any[]>([]);

  // Use local imported customers if DataConnect hasn't synced yet
  // This prevents the "Loading..." block after import completes
  const customers = useMemo(() => {
    const dcCustomers = customersData?.customers || [];
    // If we have DataConnect customers, use those (they're the source of truth)
    if (dcCustomers.length > 0) return dcCustomers;
    // Otherwise, use locally imported customers (immediate display after import)
    return localImportedCustomers;
  }, [customersData?.customers, localImportedCustomers]);

  const notionDatabases = notionDatabasesData || [];
  const isNotionConnected = integrationStatus?.connected ?? false;

  const [subStep, setSubStep] = useState<SubStep>('found');
  const [selectedColumn, setSelectedColumn] = useState<string>('');
  const [importState, setImportState] = useState<'idle' | 'importing' | 'success' | 'failed'>('idle');
  const [importError, setImportError] = useState<string | null>(null);
  // Store full property schemas with options (for bucket preview)
  const [propertySchemas, setPropertySchemas] = useState<NotionPropertySchema[]>([]);
  const [importedDatabaseId, setImportedDatabaseId] = useState<string | null>(null);
  const [isFetchingSchema, setIsFetchingSchema] = useState(false);
  const [isReimporting, setIsReimporting] = useState(false);
  const [hasClassified, setHasClassified] = useState(false);

  // Derived: just the property names (for backwards compat)
  const availableProperties = useMemo(() => propertySchemas.map(p => p.name), [propertySchemas]);

  // Actual customer count
  const customerCount = customers.length;

  // Auto-classify customers when they exist but haven't been classified
  // Uses streaming mode with Firestore real-time updates
  useEffect(() => {
    // Check if any customers need classification
    // (don't have aiClassificationGroup set in DB)
    const customersNeedingClassification = customers.filter(c => !c.aiClassificationGroup);
    const hasDbClassifications = customers.length > 0 && customersNeedingClassification.length === 0;

    // Skip if all customers already have DB classifications
    if (hasDbClassifications) {
      console.log('All customers have DB classifications, skipping');
      return;
    }

    // Trigger classification if:
    // 1. We have customers that need classification
    // 2. We haven't classified yet (this session)
    // 3. We're not currently classifying
    const shouldClassify = customersNeedingClassification.length > 0 &&
                          !hasClassified &&
                          !isClassifying &&
                          !isStartingStreaming;

    if (shouldClassify) {
      console.log('Triggering streaming AI classification for', customersNeedingClassification.length, 'customers');
      setHasClassified(true);
      setUseStreamingMode(true);
      // Only classify customers that don't have DB classifications
      const idsToClassify = customersNeedingClassification.map(c => c.id);

      // Use streaming classification - results come via Firestore
      startClassification(idsToClassify).then((result) => {
        console.log('Streaming classification started:', result);
        // Don't refetch immediately - Firestore updates will drive the UI
        // We'll refetch when all customers are classified
      }).catch((err) => {
        console.error('Streaming classification failed to start:', err);
        // Fall back to batch classification
        setUseStreamingMode(false);
        classifyCustomers(idsToClassify).then((result) => {
          console.log('Batch AI Classification result:', result);
          refetchCustomers();
        }).catch((batchErr) => {
          console.error('Batch AI Classification also failed:', batchErr);
        });
      });
    }
  }, [customers, hasClassified, isClassifying, isStartingStreaming, classifyCustomers, startClassification, refetchCustomers]);

  // When all Firestore progress items are classified, refetch customers
  useEffect(() => {
    if (!useStreamingMode) return;
    if (customers.length === 0) return;

    const progressEntries = Object.entries(firestoreProgress);
    if (progressEntries.length === 0) return;

    // Only consider complete when ALL customers have progress AND all are classified
    const allCustomersHaveProgress = progressEntries.length >= customers.length;
    const allClassified = progressEntries.every(
      ([, p]) => p.status === 'classified' || p.status === 'error'
    );

    if (allCustomersHaveProgress && allClassified) {
      console.log('All streaming classifications complete, refetching customers');
      refetchCustomers();
    }
  }, [firestoreProgress, useStreamingMode, refetchCustomers, customers.length]);

  // Categorize customers by AI classification (with Firestore progress + fallback)
  const categorizedCustomers = useMemo(() => {
    return customers.map(c => {
      // First check Firestore real-time progress
      const fsProgress = firestoreProgress[c.id];

      // First check if customer has classification in DB (persisted)
      let aiClassification: CustomerClassification | undefined;

      // Priority: Firestore (real-time) > DB > in-memory
      if (fsProgress?.status === 'classified' && fsProgress.group) {
        // Use Firestore classification (most recent, streaming)
        aiClassification = {
          customer_id: c.id,
          group: fsProgress.group as CustomerClassification['group'],
          confidence: fsProgress.confidence || 0,
          reasoning: fsProgress.reasoning || '',
          what_i_know: fsProgress.what_i_know || [],
          what_im_uncertain_about: fsProgress.what_im_uncertain_about || [],
        };
      } else if (c.aiClassificationGroup) {
        // Use DB classification
        aiClassification = {
          customer_id: c.id,
          group: c.aiClassificationGroup as CustomerClassification['group'],
          confidence: c.aiClassificationConfidence || 0,
          reasoning: c.aiClassificationReasoning || '',
          what_i_know: c.aiClassificationWhatIKnow ? JSON.parse(c.aiClassificationWhatIKnow) : [],
          what_im_uncertain_about: c.aiClassificationUncertainties ? JSON.parse(c.aiClassificationUncertainties) : [],
        };
      } else {
        // Fall back to in-memory classification (from current session)
        aiClassification = getClassification(c.id);
      }

      // Map AI group to onboardingState
      let onboardingState: CustomerWithState['onboardingState'] = 'ready';
      if (aiClassification) {
        switch (aiClassification.group) {
          case 'not_yet_customer':
            onboardingState = 'auto-handled'; // Will be filtered out or shown separately
            break;
          case 'new_customer':
            onboardingState = 'pointer-needed';
            break;
          case 'pointer_needed':
            onboardingState = 'pointer-needed';
            break;
          case 'ready_to_confirm':
            onboardingState = 'auto-handled';
            break;
        }
      } else {
        // Fallback to hardcoded logic
        onboardingState = categorizeCustomer(c as CustomerWithState);
      }

      return {
        ...c,
        onboardingState,
        aiClassification,
        // Add Firestore streaming state
        streamingStatus: fsProgress?.status,
        streamingStep: fsProgress?.step,
        streamingProgress: fsProgress?.progress_pct,
      };
    }) as (CustomerWithState & {
      aiClassification?: CustomerClassification;
      streamingStatus?: CustomerProgress['status'];
      streamingStep?: string;
      streamingProgress?: number;
    })[];
  }, [customers, getClassification, classifications, firestoreProgress]);

  // Group customers by state for the Found step
  // IMPORTANT: Each customer should be in exactly ONE group
  const customerGroups = useMemo(() => {
    const reading: typeof categorizedCustomers = [];
    const pointerNeeded: typeof categorizedCustomers = [];
    const ready: typeof categorizedCustomers = [];
    const notYetCustomers: typeof categorizedCustomers = [];

    for (const c of categorizedCustomers) {
      // During streaming mode, categorize primarily by Firestore status
      if (useStreamingMode) {
        // 1. Actively being read
        if (c.streamingStatus === 'reading' || c.streamingStatus === 'pending') {
          reading.push(c);
          continue;
        }

        // 2. Not yet in Firestore = waiting to be processed (show as "reading")
        if (!c.streamingStatus) {
          reading.push(c);
          continue;
        }

        // 3. Classified - sort into groups based on classification result
        if (c.streamingStatus === 'classified' || c.streamingStatus === 'error') {
          const group = c.aiClassification?.group;
          if (group === 'not_yet_customer') {
            notYetCustomers.push(c);
          } else if (group === 'pointer_needed' || group === 'new_customer') {
            pointerNeeded.push(c);
          } else {
            // ready_to_confirm or any other classified result
            ready.push(c);
          }
          continue;
        }
      }

      // Non-streaming mode: use DB classification or fallback to lifecycle
      const group = c.aiClassification?.group;
      if (group === 'not_yet_customer') {
        notYetCustomers.push(c);
      } else if (group === 'pointer_needed' || group === 'new_customer') {
        pointerNeeded.push(c);
      } else if (group === 'ready_to_confirm') {
        ready.push(c);
      } else if (c.onboardingState === 'pointer-needed') {
        pointerNeeded.push(c);
      } else if (c.onboardingState === 'ready' || c.onboardingState === 'auto-handled') {
        ready.push(c);
      } else {
        // Default: mid-onboarding goes to reading for review
        reading.push(c);
      }
    }

    return {
      reading,
      pointerNeeded,
      midOnboarding: [], // Deprecated - merged into reading
      ready,
      autoHandled: [], // Deprecated - merged into ready
      notYetCustomers,
    };
  }, [categorizedCustomers, useStreamingMode]);

  // Track linked pages per customer (synced with database)
  const [linkedPagesFromDb, setLinkedPagesFromDb] = useState<Record<string, Array<{ type: string; title: string; linked: boolean }>>>({});

  // Initialize linkedPages from database when customers load
  useEffect(() => {
    if (categorizedCustomers.length > 0) {
      const pagesFromDb: Record<string, Array<{ type: string; title: string; linked: boolean }>> = {};

      for (const customer of categorizedCustomers) {
        // Parse linkedPages JSON from database
        const linkedPagesRaw = (customer as any).linkedPages;
        if (linkedPagesRaw) {
          try {
            const parsed = typeof linkedPagesRaw === 'string' ? JSON.parse(linkedPagesRaw) : linkedPagesRaw;
            if (Array.isArray(parsed) && parsed.length > 0) {
              pagesFromDb[customer.id] = parsed.map((p: any) => ({
                type: p.page_type || p.type || 'onboarding',
                title: p.title || 'Linked page',
                linked: true
              }));
            }
          } catch (e) {
            console.error('Failed to parse linkedPages for', customer.id, e);
          }
        }
      }

      // Only update if we found pages from DB
      if (Object.keys(pagesFromDb).length > 0) {
        setLinkedPagesFromDb(pagesFromDb);
      }
    }
  }, [categorizedCustomers]);

  // Tally counts for streaming UI
  const tallyCounts = useMemo(() => {
    const progressEntries = Object.values(firestoreProgress);
    return {
      reading: progressEntries.filter(p => p.status === 'reading' || p.status === 'pending').length,
      classified: progressEntries.filter(p => p.status === 'classified').length,
      error: progressEntries.filter(p => p.status === 'error').length,
      onboarding: customerGroups.pointerNeeded.length + customerGroups.midOnboarding.length,
      confirm: customerGroups.ready.length,
    };
  }, [firestoreProgress, customerGroups]);

  // Actual customer counts grouped by lifecycle (for BucketedStep)
  const customerBuckets = useMemo(() => {
    const grouped: Record<string, number> = {};
    for (const c of customers) {
      const key = c.lifecycle || 'unknown';
      grouped[key] = (grouped[key] || 0) + 1;
    }
    return Object.entries(grouped)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([name, count]) => ({ name, count }));
  }, [customers]);

  // Build bucket preview based on selected column (for column picker)
  // Uses actual Notion column options when available to show what buckets will be created
  const bucketPreview = useMemo(() => {
    // If we have a selected column, try to use its options from the Notion schema
    if (selectedColumn && propertySchemas.length > 0) {
      const selectedProp = propertySchemas.find(p => p.name === selectedColumn);
      if (selectedProp?.options && selectedProp.options.length > 0) {
        // Use the actual Notion select/multi-select options
        // Show as preview without counts (counts come after import)
        return selectedProp.options.slice(0, 6).map(opt => ({ name: opt, count: -1 }));
      }
    }

    // Fallback: use actual customer data
    return customerBuckets;
  }, [customerBuckets, selectedColumn, propertySchemas]);

  // Get the primary database to import from (user's selection or fallback to first available)
  const primaryDatabaseId = data.notionConfig?.primaryDatabaseId;
  const primaryDatabase = primaryDatabaseId
    ? notionDatabases.find(db => db.id === primaryDatabaseId)
    : notionDatabases[0]; // Fallback to first if nothing selected

  // Auto-import customers from Notion if connected and no customers exist
  useEffect(() => {
    const shouldImport =
      isNotionConnected &&
      customers.length === 0 &&
      primaryDatabase &&
      importState === 'idle' &&
      !isImporting &&
      !isLoading;

    if (shouldImport) {
      setImportState('importing');
      console.log('Importing customers from primary Notion database:', primaryDatabase.id, primaryDatabase.name);
      setImportedDatabaseId(primaryDatabase.id);

      importCustomers(primaryDatabase.id)
        .then(async (result) => {
          console.log('Import result:', result);
          console.log('Available properties from import:', result.availableProperties);
          console.log('Detected mappings:', result.detectedMappings);
          console.log('Imported customers with lifecycle:', result.customers?.map(c => ({ name: c.name, lifecycle: c.lifecycle })));

          // Store property names as basic schemas (options will be fetched later)
          if (result.availableProperties && result.availableProperties.length > 0) {
            setPropertySchemas(result.availableProperties.map(name => ({ name, type: 'unknown' })));
          }

          if (result.imported_count > 0) {
            setImportState('success');

            // Use imported customers immediately (no need to wait for DataConnect sync)
            // This unblocks the UI right away
            if (result.customers && result.customers.length > 0) {
              console.log('Setting local imported customers:', result.customers.length);
              // Transform to match Customer type expected by UI
              setLocalImportedCustomers(result.customers.map((c: any) => ({
                id: c.id,
                name: c.name,
                slug: c.slug || c.name?.toLowerCase().replace(/\s+/g, '-') || '',
                lifecycle: c.lifecycle || 'prospect',
                tier: c.tier,
                arr: c.arr,
                healthScore: c.healthScore,
                healthTrend: c.healthTrend,
                aiClassificationGroup: c.aiClassificationGroup,
                aiClassificationReasoning: c.aiClassificationReasoning,
                aiClassificationConfidence: c.aiClassificationConfidence,
                externalSourceType: c.externalSourceType,
                externalSourceId: c.externalSourceId,
              })));
            }

            // Fire off a background refetch to sync DataConnect (non-blocking)
            refetchCustomers().then(refetchResult => {
              const count = refetchResult?.data?.customers?.length || 0;
              console.log('Background DataConnect sync complete:', count, 'customers');
            });

            console.log('Import complete, classification will trigger automatically.');
          } else {
            setImportState('failed');
            setImportError(
              result.errors.length > 0
                ? result.errors[0]
                : 'No customers were imported from Notion'
            );
          }
        })
        .catch((error) => {
          console.error('Import failed:', error);
          setImportState('failed');
          setImportError(error.message || 'Failed to import customers from Notion');
        });
    }
  }, [isNotionConnected, customers.length, primaryDatabase?.id, importState, isImporting, isLoading, importCustomers, refetchCustomers, classifyCustomers]);

  // Fetch full schema when entering column picker if we don't have properties (or need options)
  useEffect(() => {
    // Use the primary database from config, or fallback to importedDatabaseId
    const databaseId = data.notionConfig?.primaryDatabaseId || importedDatabaseId || (notionDatabases.length > 0 ? notionDatabases[0].id : null);

    // Need to fetch if: entering column picker AND (no properties OR properties lack options)
    const needsOptions = propertySchemas.length > 0 && !propertySchemas.some(p => p.options && p.options.length > 0);
    const shouldFetch = subStep === 'column-picker' && databaseId && !isFetchingSchema &&
                        (propertySchemas.length === 0 || needsOptions);

    if (shouldFetch) {
      console.log('Fetching full schema for column picker, databaseId:', databaseId);
      setIsFetchingSchema(true);

      fetchFullSchema(databaseId)
        .then((schemas) => {
          console.log('Fetched full schema:', schemas);
          if (schemas.length > 0) {
            setPropertySchemas(schemas);
          }
        })
        .catch((error) => {
          console.error('Failed to fetch schema:', error);
        })
        .finally(() => {
          setIsFetchingSchema(false);
        });
    }
  }, [subStep, propertySchemas, data.notionConfig?.primaryDatabaseId, importedDatabaseId, notionDatabases, fetchFullSchema, isFetchingSchema]);

  // Show loading state
  const showLoading = isLoading || isImporting || importState === 'importing' ||
    (importState === 'success' && customers.length === 0);

  if (showLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 text-rust-500 animate-spin" />
        <span className="ml-3 text-charcoal-400">
          {isImporting || importState === 'importing'
            ? 'Importing customers from Notion...'
            : importState === 'success'
              ? 'Loading imported customers...'
              : 'Loading customers...'}
        </span>
      </div>
    );
  }

  // No Notion connected state
  if (!isNotionConnected && customers.length === 0) {
    return (
      <>
        <div className="setup__head">
          <div>
            <h1>No customers <em>yet</em>.</h1>
            <p className="lede">
              Connect Notion to import your existing customers, or skip this step to add them manually later.
            </p>
          </div>
          <div className="setup__head-aside">
            <div className="label">WHY IMPORT?</div>
            <p>
              Sidekick works best when it knows your customers. Import now to hit the ground running.
            </p>
          </div>
        </div>

        <div className="setup-sidekick-note" style={{ marginBottom: 24 }}>
          <span className="tag">SIDEKICK</span>
          You haven't connected Notion yet. Go back to Integrations to connect, or skip this step and add customers manually later.
        </div>

        <div className="setup__footer">
          <button type="button" className="sk-btn" onClick={onBack}>
            ← Back · Connect Notion
          </button>
          <button type="button" className="sk-btn sk-btn--primary" onClick={onComplete}>
            Skip for now →
          </button>
        </div>
      </>
    );
  }

  // No databases found state
  if (isNotionConnected && notionDatabases.length === 0 && customers.length === 0 && importState === 'idle') {
    return (
      <>
        <div className="setup__head">
          <div>
            <h1>No databases <em>found</em>.</h1>
            <p className="lede">
              Notion is connected, but we couldn't find any databases shared with Herofy.
              Make sure you've shared your customer database with the integration.
            </p>
          </div>
        </div>

        <div className="setup-sidekick-note" style={{ marginBottom: 24 }}>
          <span className="tag">SIDEKICK</span>
          In Notion, open your customer database and click "Share" → "Invite" → search for "Herofy" and add it.
          Then come back and retry.
        </div>

        <div className="setup__footer">
          <button type="button" className="sk-btn" onClick={onBack}>
            ← Back · Integrations
          </button>
          <button type="button" className="sk-btn sk-btn--primary" onClick={onComplete}>
            Skip for now →
          </button>
        </div>
      </>
    );
  }

  // Import failed state
  if (importState === 'failed' && customers.length === 0) {
    return (
      <>
        <div className="setup__head">
          <div>
            <h1>Couldn't auto-detect <em>customer fields</em>.</h1>
            <p className="lede">
              Sidekick tried to import customers from your Notion database but couldn't find the required fields.
              You'll need to map them manually or rename your Notion properties.
            </p>
          </div>
          <div className="setup__head-aside">
            <div className="label">WHAT WENT WRONG</div>
            <p className="text-sm">{importError || 'Could not detect customer name field in your Notion database.'}</p>
          </div>
        </div>

        <div className="section-opener" style={{ marginBottom: 16 }}>
          <div className="hair" />
          <span className="eyebrow">YOUR NOTION PROPERTIES</span>
          <div className="hair-fill" />
        </div>

        {availableProperties.length > 0 ? (
          <div className="space-y-2 mb-6">
            {availableProperties.map((prop) => (
              <div key={prop} className="cust-row">
                <div>
                  <div className="name font-mono">{prop}</div>
                  <div className="meta">NOTION PROPERTY</div>
                </div>
                <div className="text-sm text-charcoal-400">
                  {detectPropertyRole(prop) === 'name'
                    ? '✓ Could be mapped to Customer Name'
                    : detectPropertyRole(prop) === 'lifecycle'
                      ? '→ Could be mapped to Lifecycle'
                      : detectPropertyRole(prop) === 'tier'
                        ? '→ Could be mapped to Tier'
                        : '—'}
                </div>
                <div>
                  <span className="state">
                    {detectPropertyRole(prop) === 'name' ? 'NAME CANDIDATE' : 'UNMAPPED'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="cust-row is-pointer-needed" style={{ marginBottom: 24 }}>
            <div>
              <div className="name">No properties found</div>
              <div className="meta">CHECK YOUR NOTION DATABASE CONNECTION</div>
            </div>
            <div>
              <span className="state pending">
                <AlertCircle className="w-3 h-3" />
                ERROR
              </span>
            </div>
          </div>
        )}

        <div className="setup-sidekick-note" style={{ marginBottom: 24 }}>
          <span className="tag">SIDEKICK</span>
          I look for properties named: <strong>Name</strong>, <strong>Title</strong>, <strong>Company</strong>, <strong>Customer</strong>, <strong>Account</strong>, <strong>Client</strong>, or <strong>Organization</strong>.
          If none of your properties match, rename one in Notion or use manual mapping.
        </div>

        <div className="setup__footer">
          <button type="button" className="sk-btn" onClick={onBack}>
            ← Back · Integrations
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="sk-btn"
              onClick={() => {
                setImportState('idle');
                setImportError(null);
                setPropertySchemas([]);
              }}
            >
              Retry auto-import
            </button>
            <button
              type="button"
              className="sk-btn sk-btn--primary"
              onClick={() => setSubStep('column-picker')}
            >
              Map fields manually →
            </button>
          </div>
        </div>
      </>
    );
  }

  return (
    <AnimatePresence mode="wait">
      {subStep === 'found' && (
        <motion.div
          key="found"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
        >
          <FoundStep
            customerCount={customerCount}
            customerGroups={customerGroups}
            tallyCounts={tallyCounts}
            useStreamingMode={useStreamingMode}
            firestoreProgress={firestoreProgress}
            linkedPagesFromDb={linkedPagesFromDb}
            setLinkedPagesFromDb={setLinkedPagesFromDb}
            onContinue={() => setSubStep('column-picker')}
            onSkipToBucketed={() => setSubStep('bucketed')}
            onBack={onBack}
            isClassifying={isClassifying || isStartingStreaming}
            updateClassification={updateClassification}
            refetchCustomers={refetchCustomers}
          />
        </motion.div>
      )}

      {subStep === 'column-picker' && (
        <motion.div
          key="column-picker"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
        >
          <ColumnPickerStep
            customerCount={customerCount}
            propertySchemas={propertySchemas}
            selectedColumn={selectedColumn}
            bucketPreview={bucketPreview}
            onSelectColumn={setSelectedColumn}
            onApply={async () => {
              // If a column is selected, re-import with that column as lifecycle
              const databaseId = data.notionConfig?.primaryDatabaseId || importedDatabaseId;
              if (selectedColumn && databaseId) {
                setIsReimporting(true);
                try {
                  const result = await reimportWithLifecycleColumn(databaseId, selectedColumn);
                  if (result.imported_count > 0) {
                    // Refetch and wait for fresh data before proceeding
                    await refetchCustomers();
                    // Small delay to ensure React Query cache is updated
                    await new Promise(resolve => setTimeout(resolve, 100));
                  }
                } catch (error) {
                  console.error('Re-import failed:', error);
                } finally {
                  setIsReimporting(false);
                }
              }
              setSubStep('bucketed');
            }}
            onBack={() => setSubStep('found')}
            isLoadingSchema={isFetchingSchema}
            isReimporting={isReimporting}
          />
        </motion.div>
      )}

      {subStep === 'bucketed' && (
        <motion.div
          key="bucketed"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
        >
          <BucketedStep
            customerCount={customerCount}
            bucketCounts={customerBuckets}
            onComplete={onComplete}
            onBack={() => setSubStep('column-picker')}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// =============================================================================
// Ready to Confirm Section - Shows what Sidekick inferred about each customer
// =============================================================================
function ReadyToConfirmSection({
  customers,
  expandedCustomer,
  setExpandedCustomer,
  confirmedCustomers,
  setConfirmedCustomers,
  updateClassification,
  refetchCustomers,
}: {
  customers: (CustomerWithState & { aiClassification?: CustomerClassification })[];
  expandedCustomer: string | null;
  setExpandedCustomer: (id: string | null) => void;
  confirmedCustomers: Set<string>;
  setConfirmedCustomers: React.Dispatch<React.SetStateAction<Set<string>>>;
  updateClassification: (customerId: string, group: string, reasoning?: string) => Promise<void>;
  refetchCustomers: () => Promise<void>;
}) {
  // Get inferred data from AI classification or fall back to mock data
  const getInferredData = (customer: CustomerWithState & { aiClassification?: CustomerClassification }) => {
    const ai = customer.aiClassification;

    if (ai) {
      return {
        playbook: ai.suggested_playbook || 'Active account monitoring',
        playbookCode: ai.playbook_code || 'PB-ACTIVE',
        confidence: ai.confidence,
        currentState: ai.current_state || 'Analyzing...',
        currentDetail: ai.reasoning,
        nextMilestone: ai.next_milestone || 'TBD',
        nextDetail: ai.what_i_know.length > 0 ? ai.what_i_know[0] : '',
        whatIKnow: ai.what_i_know,
        whatImUncertain: ai.what_im_uncertain_about,
      };
    }

    // Fallback to mock data
    const lifecycle = customer.lifecycle?.toLowerCase() || 'active';
    const isActive = lifecycle === 'active' || lifecycle === 'renewing';

    return {
      playbook: isActive ? 'Active account monitoring' : 'SMB fast path · 14-day',
      playbookCode: isActive ? 'PB-ACTIVE-MON' : 'PB-SMB-ONB',
      confidence: isActive ? 94 : 87,
      currentState: isActive
        ? 'Healthy · no signals'
        : `Day ${customer.onboardingDayCurrent || 5} of ${customer.onboardingDayTotal || 14}`,
      currentDetail: isActive
        ? 'Last activity 2 days ago'
        : 'Initial setup complete · integration in flight',
      nextMilestone: isActive ? 'QBR in 45 days' : 'First production traffic',
      nextDetail: isActive ? 'I\'ll prep materials beforehand.' : 'Target: 5 days · I\'ll watch for it.',
      whatIKnow: [] as string[],
      whatImUncertain: [] as string[],
    };
  };

  return (
    <>
      <div className="section-opener" style={{ marginBottom: 12, marginTop: 24 }}>
        <div className="hair" />
        <span className="eyebrow">READY TO CONFIRM</span>
        <div className="hair-fill" />
      </div>

      <div className="space-y-3 mb-6">
        <AnimatePresence mode="popLayout">
        {customers.map((customer) => {
          const isExpanded = expandedCustomer === customer.id;
          const isConfirmed = confirmedCustomers.has(customer.id);
          const inferred = getInferredData(customer);
          const arrDisplay = customer.tier ? `$${customer.tier}` : '$60K';

          if (isExpanded) {
            return (
              <motion.div
                key={`${customer.id}-expanded`}
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.15, ease: 'easeOut' }}
                className="cust-row is-confirm"
                style={{ display: 'block', padding: 0 }}
              >
                {/* Header row */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '220px minmax(0,1fr) 220px 160px',
                    gap: 24,
                    alignItems: 'center',
                    padding: '16px 20px',
                    borderBottom: '1px dashed rgba(31,29,27,0.5)',
                    cursor: 'pointer',
                  }}
                  onClick={() => setExpandedCustomer(null)}
                >
                  <div>
                    <div className="name">{customer.name}</div>
                    <div className="meta">{arrDisplay} · {(customer.lifecycle || 'ACTIVE').toUpperCase()}</div>
                  </div>
                  <div>
                    <span className="state done">
                      <span style={{ width: 6, height: 6, background: 'currentColor', borderRadius: '50%' }} />
                      Read · confirm classification
                    </span>
                    <div className="state__detail">
                      From Notion CRM · {inferred.confidence}% match.
                    </div>
                  </div>
                  <div></div>
                  <div className="action">
                    <button className="sk-btn" onClick={(e) => e.stopPropagation()}>
                      Edit
                    </button>
                  </div>
                </div>

                {/* Expanded confirm content */}
                <div className="cust-confirm">
                  <div className="cust-confirm__head">
                    <Sparkles className="w-4 h-4" />
                    <span>Sidekick · Here's what I think</span>
                  </div>

                  <div className="cust-confirm__grid">
                    <div className="cust-confirm__cell">
                      <span className="k">PLAYBOOK MATCH</span>
                      <span className="v"><em>{inferred.playbook}</em></span>
                      <span className="sub">{inferred.playbookCode}</span>
                      <span className="cust-confirm__confidence">▲ {inferred.confidence}% MATCH</span>
                    </div>
                    <div className="cust-confirm__cell">
                      <span className="k">CURRENT STATE</span>
                      <span className="v"><em>{inferred.currentState}</em></span>
                      <span className="sub">{inferred.currentDetail}</span>
                    </div>
                    <div className="cust-confirm__cell">
                      <span className="k">NEXT MILESTONE</span>
                      <span className="v">{inferred.nextMilestone}</span>
                      <span className="sub">{inferred.nextDetail}</span>
                    </div>
                  </div>

                  {/* AI Insights: What I know & What I'm uncertain about */}
                  {(inferred.whatIKnow?.length > 0 || inferred.whatImUncertain?.length > 0) && (
                    <div className="grid grid-cols-2 gap-6 mt-4 pt-4 border-t border-charcoal-700/50">
                      {inferred.whatIKnow?.length > 0 && (
                        <div>
                          <div className="text-xs font-mono text-emerald-500 tracking-wider mb-2">
                            WHAT I KNOW
                          </div>
                          <ul className="text-sm text-charcoal-300 space-y-1">
                            {inferred.whatIKnow.map((item, i) => (
                              <li key={i} className="flex items-start gap-2">
                                <Check className="w-3 h-3 text-emerald-500 mt-1 shrink-0" />
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {inferred.whatImUncertain?.length > 0 && (
                        <div>
                          <div className="text-xs font-mono text-rust-500 tracking-wider mb-2">
                            WHAT I'M UNCERTAIN ABOUT
                          </div>
                          <ul className="text-sm text-charcoal-400 space-y-1">
                            {inferred.whatImUncertain.map((item, i) => (
                              <li key={i} className="flex items-start gap-2">
                                <AlertCircle className="w-3 h-3 text-rust-500 mt-1 shrink-0" />
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="cust-confirm__actions">
                    <button
                      className="sk-btn sk-btn--primary"
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmedCustomers(prev => new Set([...prev, customer.id]));
                        // Move to next unconfirmed customer
                        const unconfirmed = customers.filter(c => !confirmedCustomers.has(c.id) && c.id !== customer.id);
                        if (unconfirmed.length > 0) {
                          setExpandedCustomer(unconfirmed[0].id);
                        } else {
                          setExpandedCustomer(null);
                        }
                      }}
                    >
                      Looks right · run with it
                    </button>
                    <button className="sk-btn">Pick a different playbook</button>
                    <button
                      className="sk-btn"
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          setExpandedCustomer(null);
                          await updateClassification(customer.id, 'pointer_needed', 'Needs more context - moved by user');
                          await new Promise(resolve => setTimeout(resolve, 350));
                          await refetchCustomers();
                        } catch (err) {
                          console.error('Failed to move to need info:', err);
                        }
                      }}
                    >
                      ← Need more info
                    </button>
                    <button
                      className="sk-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedCustomer(null);
                      }}
                    >
                      Skip for now
                    </button>
                  </div>
                </div>
              </motion.div>
            );
          }

          // Collapsed row
          return (
            <motion.div
              key={customer.id}
              layout
              layoutId={`customer-${customer.id}`}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.2 } }}
              transition={{ duration: 0.3, ease: 'easeInOut' }}
              className={cn('cust-row', isConfirmed ? 'is-imported' : 'is-confirm')}
              onClick={() => setExpandedCustomer(customer.id)}
              style={{ cursor: 'pointer' }}
            >
              <div>
                <div className="name">{customer.name}</div>
                <div className="meta">{arrDisplay} · {(customer.lifecycle || 'ACTIVE').toUpperCase()}</div>
              </div>
              <div>
                <span className={cn('state', isConfirmed ? 'done' : 'cur')}>
                  <span style={{ width: 6, height: 6, background: 'currentColor', borderRadius: '50%' }} />
                  {isConfirmed ? 'Confirmed' : 'Read · confirm classification'}
                </span>
                <div className="state__detail">
                  {isConfirmed
                    ? `Matched to ${inferred.playbookCode}`
                    : `${inferred.confidence}% match to ${inferred.playbookCode}`
                  }
                </div>
              </div>
              <div></div>
              <div className="action" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                {isConfirmed ? (
                  <>
                    <span className="state done">
                      <Check className="w-3 h-3" />
                      CONFIRMED
                    </span>
                    <button
                      className="sk-btn"
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          await updateClassification(customer.id, 'pointer_needed', 'Needs more context - moved by user');
                          await refetchCustomers();
                        } catch (err) {
                          console.error('Failed to move to need info:', err);
                        }
                      }}
                      title="Move back to Need Info list"
                    >
                      ← Need info
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      className="sk-btn"
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          await updateClassification(customer.id, 'pointer_needed', 'Needs more context - moved by user');
                          await refetchCustomers();
                        } catch (err) {
                          console.error('Failed to move to need info:', err);
                        }
                      }}
                      title="Move to Need Info list"
                    >
                      ← Need info
                    </button>
                    <button
                      className="sk-btn sk-btn--primary"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedCustomer(customer.id);
                      }}
                    >
                      Review →
                    </button>
                  </>
                )}
              </div>
            </motion.div>
          );
        })}
        </AnimatePresence>
      </div>
    </>
  );
}

// =============================================================================
// Sub-step 1: "You're not starting fresh" - Point me at existing progress
// =============================================================================
// Extended customer type with AI classification and streaming state
type CustomerWithClassification = CustomerWithState & {
  aiClassification?: CustomerClassification;
  streamingStatus?: CustomerProgress['status'];
  streamingStep?: string;
  streamingProgress?: number;
};

function FoundStep({
  customerCount,
  customerGroups,
  tallyCounts,
  useStreamingMode,
  firestoreProgress,
  linkedPagesFromDb,
  setLinkedPagesFromDb,
  onContinue,
  onSkipToBucketed,
  onBack,
  isClassifying,
  updateClassification,
  refetchCustomers,
}: {
  customerCount: number;
  customerGroups: {
    reading: CustomerWithClassification[];
    pointerNeeded: CustomerWithClassification[];
    midOnboarding: CustomerWithClassification[];
    ready: CustomerWithClassification[];
    autoHandled: CustomerWithClassification[];
    notYetCustomers?: CustomerWithClassification[];
  };
  tallyCounts: {
    reading: number;
    classified: number;
    error: number;
    onboarding: number;
    confirm: number;
  };
  useStreamingMode: boolean;
  firestoreProgress: Record<string, CustomerProgress>;
  linkedPagesFromDb: Record<string, Array<{ type: string; title: string; linked: boolean }>>;
  setLinkedPagesFromDb: React.Dispatch<React.SetStateAction<Record<string, Array<{ type: string; title: string; linked: boolean }>>>>;
  onContinue: () => void;
  onSkipToBucketed: () => void;
  onBack: () => void;
  isClassifying?: boolean;
  updateClassification: (customerId: string, group: string, reasoning?: string) => Promise<void>;
  refetchCustomers: () => Promise<any>;
}) {
  const { searchPages, isLoading: isSearching } = useSearchNotionPages();
  const { linkPage, isLoading: isLinking } = useLinkPageToCustomer();
  const { unlinkPage } = useUnlinkPageFromCustomer();

  const { reading, pointerNeeded, midOnboarding, ready, autoHandled, notYetCustomers = [] } = customerGroups;

  // All onboarding customers (pointer needed + mid-onboarding combined)
  const onboardingCustomers = [...pointerNeeded, ...midOnboarding];

  // Reading customers from Firestore streaming
  const readingCustomers = reading;

  // First onboarding customer should be expanded by default
  const [expandedCustomer, setExpandedCustomer] = useState<string | null>(
    onboardingCustomers.length > 0 ? onboardingCustomers[0].id : null
  );

  // Paste link modal state (kept as modal)
  const [pasteModalCustomer, setPasteModalCustomer] = useState<{ id: string; name: string } | null>(null);

  // Track linked pages per customer (local state for new links)
  const [linkedPages, setLinkedPages] = useState<Record<string, Array<{ type: string; title: string; linked: boolean }>>>({});

  // Track save success state
  const [savedCustomers, setSavedCustomers] = useState<Set<string>>(new Set());

  // Inline search state (per customer)
  const [activeSearchCustomer, setActiveSearchCustomer] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<NotionPageResult[]>([]);

  // Handle inline search
  useEffect(() => {
    if (!activeSearchCustomer) {
      setSearchResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const result = await searchPages(searchQuery || undefined);
        setSearchResults(result.pages);
      } catch (e) {
        console.error('Search failed:', e);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, activeSearchCustomer, searchPages]);

  // Handle linking a page inline
  const handleLinkPage = async (customerId: string, page: NotionPageResult) => {
    try {
      const result = await linkPage(customerId, {
        source: 'notion',
        page_id: page.id,
        page_type: 'handoff',
        url: page.url,
        title: page.title,
      });

      // Update local state immediately for responsive UI
      setLinkedPages(prev => ({
        ...prev,
        [customerId]: [
          ...(prev[customerId] || []),
          { type: 'onboarding', title: page.title, linked: true }
        ]
      }));

      // Refetch customers to get updated linkedPages from database
      await refetchCustomers();

      // Don't clear searchQuery or searchResults - keep the filter active
      // The linked page will be filtered out automatically by the display filter
      // (see searchResults.filter() that excludes pages matching customerLinkedPages)
      // This maintains the user's scroll position and filter context
    } catch (e) {
      console.error('Failed to link page:', e);
    }
  };

  return (
    <>
      {/* Header */}
      <div className="setup__head">
        <div>
          <h1>Point me at the <em>data.</em></h1>
          <p className="lede">
            I'm reading through your customers to understand what I know and what I need.
            Some are ready to confirm, others need more context — tell me where their docs live.
          </p>
        </div>
        <div className="setup__head-aside">
          <div className="label">WHAT HAPPENS NEXT</div>
          <p>
            Once I have enough info, I'll read their docs and pick up where you left off.
            No need to recreate progress that's already been made.
          </p>
        </div>
      </div>

      {/* Tally by import status - where we are in processing */}
      <div className="cust-tally" style={{ marginBottom: 24 }}>
        {readingCustomers.length > 0 && (
          <>
            <div className="cust-tally__cell">
              <div className="v" style={{ color: 'var(--rust-400)' }}>
                <Loader2 className="w-4 h-4 inline-block animate-spin mr-1" />
                {readingCustomers.length}
              </div>
              <div className="k">READING</div>
            </div>
            <div className="cust-tally__sep" />
          </>
        )}
        <div className="cust-tally__cell">
          <div className="v ok">{ready.length}</div>
          <div className="k">READY</div>
        </div>
        <div className="cust-tally__sep" />
        <div className="cust-tally__cell">
          <div className="v warn">{onboardingCustomers.length}</div>
          <div className="k">NEED INFO</div>
        </div>
        {notYetCustomers.length > 0 && (
          <>
            <div className="cust-tally__sep" />
            <div className="cust-tally__cell">
              <div className="v" style={{ color: 'var(--charcoal-500)' }}>{notYetCustomers.length}</div>
              <div className="k">NOT CUSTOMERS</div>
            </div>
          </>
        )}
      </div>

      {/* SIDEKICK IS READING Section - Real-time streaming progress */}
      {readingCustomers.length > 0 && (
        <>
          <div className="section-opener" style={{ marginBottom: 12 }}>
            <div className="hair" />
            <span className="eyebrow">
              <Loader2 className="w-3 h-3 inline-block animate-spin mr-1" />
              SIDEKICK IS READING
            </span>
            <div className="hair-fill" />
          </div>

          <div className="space-y-3 mb-6">
            <AnimatePresence mode="popLayout">
            {readingCustomers.map((customer) => {
              const fsProgress = firestoreProgress[customer.id];
              const progressPct = fsProgress?.progress_pct || 0;
              const step = fsProgress?.step || 'Starting...';
              const arrDisplay = customer.tier ? `$${customer.tier}` : '$—';

              return (
                <motion.div
                  key={customer.id}
                  layout
                  layoutId={`customer-${customer.id}`}
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: 100, transition: { duration: 0.3 } }}
                  transition={{ duration: 0.3, ease: 'easeInOut' }}
                  className="cust-row is-reading"
                  style={{ position: 'relative', overflow: 'hidden' }}
                >
                  {/* Progress bar background */}
                  <div
                    className="cust-reading__bar"
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: `${progressPct}%`,
                      background: 'rgba(var(--rust-500-rgb), 0.1)',
                      transition: 'width 0.3s ease',
                    }}
                  />

                  <div style={{ position: 'relative', zIndex: 1 }}>
                    <div className="name">{customer.name}</div>
                    <div className="meta">{arrDisplay} · {(customer.lifecycle || 'ANALYZING').toUpperCase()}</div>
                  </div>

                  <div style={{ position: 'relative', zIndex: 1 }}>
                    <span className="state cur">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      {step}
                    </span>
                    <div className="state__detail">
                      ~30 seconds. You don't have to wait.
                    </div>
                  </div>

                  <div style={{ position: 'relative', zIndex: 1 }}>
                    <span className="text-xs text-charcoal-500 font-mono">
                      {progressPct}%
                    </span>
                  </div>

                  <div></div>
                </motion.div>
              );
            })}
            </AnimatePresence>
          </div>
        </>
      )}

      {/* Need More Info Section - customers where we need docs/context */}
      {onboardingCustomers.length > 0 && (
        <>
          <div className="section-opener" style={{ marginBottom: 12 }}>
            <div className="hair" />
            <span className="eyebrow">I NEED MORE INFO</span>
            <div className="hair-fill" />
          </div>

          <div className="space-y-3 mb-6">
            <AnimatePresence mode="popLayout">
            {onboardingCustomers.map((customer) => {
              const isExpanded = expandedCustomer === customer.id;
              const isSaved = savedCustomers.has(customer.id);
              // Merge DB linked pages with local state
              const customerLinkedPages = [
                ...(linkedPagesFromDb[customer.id] || []),
                ...(linkedPages[customer.id] || [])
              ];
              const hasLinkedPages = customerLinkedPages.some(p => p.linked);
              const isSearchActive = activeSearchCustomer === customer.id;

              // Format ARR display
              const arrDisplay = customer.tier ? `$${customer.tier}` : '$20K';

              // Use proper cust-row--expanded class when expanded
              if (isExpanded) {
                return (
                  <motion.div
                    key={`${customer.id}-expanded`}
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.98 }}
                    transition={{ duration: 0.15, ease: 'easeOut' }}
                    className={cn(
                      'cust-row cust-row--expanded',
                      hasLinkedPages || isSaved ? 'is-generated' : 'is-pointer-needed'
                    )}
                  >
                    {/* Header row - 4-column grid matching design */}
                    <div
                      className="cust-row__row cursor-pointer"
                      onClick={() => setExpandedCustomer(null)}
                    >
                      {/* Col 1: Name + Meta */}
                      <div>
                        <div className="name">{customer.name}</div>
                        <div className="meta">{arrDisplay} · NEED CONTEXT</div>
                      </div>

                      {/* Col 2: Status */}
                      <div>
                        <span className={cn('state', hasLinkedPages ? 'done' : 'cur')}>
                          <span style={{ width: 6, height: 6, background: 'currentColor', borderRadius: '50%' }} />
                          {hasLinkedPages ? `${customerLinkedPages.length} page(s) linked` : 'Point me at it'}
                        </span>
                        <div className="state__detail">
                          {hasLinkedPages ? 'Choose what to do next below' : 'Tell me where their onboarding progress lives.'}
                        </div>
                      </div>

                      {/* Col 3: Empty */}
                      <div></div>

                      {/* Col 4: Actions */}
                      <div className="action" style={{ display: 'flex', gap: 8 }}>
                        <button
                          className="sk-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSavedCustomers(prev => new Set([...prev, customer.id]));
                            setExpandedCustomer(null);
                          }}
                        >
                          Treat as new
                        </button>
                        <button
                          className="sk-btn"
                          onClick={async (e) => {
                            e.stopPropagation();
                            try {
                              setExpandedCustomer(null);
                              await updateClassification(customer.id, 'ready_to_confirm', 'Not in onboarding - marked by user');
                              // Delay refetch slightly to let animation complete
                              await new Promise(resolve => setTimeout(resolve, 350));
                              await refetchCustomers();
                            } catch (err) {
                              console.error('Failed to update classification:', err);
                            }
                          }}
                        >
                          Not onboarding
                        </button>
                      </div>
                    </div>

                    {/* Expanded content - 2-column grid: 1fr | 280px */}
                    <div className="cust-row__expand">
                      {/* Left: Picker options + search */}
                      <div>
                        <div className="picker-options">
                          <button
                            className={cn('picker-option', isSearchActive && 'is-on')}
                            onClick={(e) => {
                              e.stopPropagation();
                              setActiveSearchCustomer(isSearchActive ? null : customer.id);
                              setSearchQuery('');
                            }}
                          >
                            <div className="picker-option__head"><span className="radio" />FROM NOTION</div>
                            <p className="picker-option__title">Browse Notion pages</p>
                            <p className="picker-option__sub">Search your connected workspace.</p>
                          </button>
                          <button
                            className="picker-option"
                            onClick={(e) => {
                              e.stopPropagation();
                              setPasteModalCustomer({ id: customer.id, name: customer.name });
                            }}
                          >
                            <div className="picker-option__head"><span className="radio" />PASTE URL</div>
                            <p className="picker-option__title">Paste a Notion link</p>
                            <p className="picker-option__sub">If you know exactly which page.</p>
                          </button>
                          <button className="picker-option">
                            <div className="picker-option__head"><span className="radio" />UPLOAD</div>
                            <p className="picker-option__title">Drop markdown / CSV</p>
                            <p className="picker-option__sub">For sheets we can't reach.</p>
                          </button>
                        </div>

                        {/* Inline Notion search */}
                        {isSearchActive && (
                          <div className="notion-list">
                            <div className="notion-search">
                              <Search className="w-4 h-4 text-charcoal-500" />
                              <input
                                type="text"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                placeholder="Search Notion pages…"
                                autoFocus
                                onClick={(e) => e.stopPropagation()}
                              />
                              {isSearching ? (
                                <Loader2 className="w-4 h-4 text-charcoal-400 animate-spin" />
                              ) : searchResults.length > 0 ? (
                                <span className="badge">{searchResults.length} PAGES</span>
                              ) : null}
                            </div>

                            {/* Show linked pages */}
                            {customerLinkedPages.length > 0 && (
                              <div className="bg-rust-500/5 rounded p-3 mb-2">
                                <div className="text-[11px] font-semibold text-rust-600 mb-1.5 uppercase tracking-wide">
                                  Linked ({customerLinkedPages.length})
                                </div>
                                {customerLinkedPages.map((page, idx) => (
                                  <div key={idx} className="text-sm text-foreground/80 mb-1 flex items-center gap-1.5 group">
                                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="flex-shrink-0">
                                      <path d="M10 3L4.5 8.5L2 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-rust-500"/>
                                    </svg>
                                    <span className="flex-1 truncate">
                                      {page.title}
                                    </span>
                                    <button
                                      onClick={async (e) => {
                                        e.stopPropagation();
                                        const pageTitle = page.title;

                                        try {
                                          // Call backend to unlink
                                          await unlinkPage(customer.id, pageTitle);

                                          // Remove from both local states immediately for responsive UI
                                          setLinkedPages(prev => {
                                            const updated = { ...prev };
                                            const current = updated[customer.id] || [];
                                            updated[customer.id] = current.filter(p => p.title !== pageTitle);
                                            if (updated[customer.id].length === 0) {
                                              delete updated[customer.id];
                                            }
                                            return updated;
                                          });

                                          // Refetch to sync with database
                                          await refetchCustomers();
                                        } catch (err) {
                                          console.error('Failed to unlink page:', err);
                                        }
                                      }}
                                      className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:bg-rust-500/10 rounded"
                                      title="Remove this link"
                                    >
                                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                                        <path d="M10.5 3.5L3.5 10.5M3.5 3.5L10.5 10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-foreground/40"/>
                                      </svg>
                                    </button>
                                  </div>
                                ))}
                              </div>
                            )}

                            {searchResults.slice(0, 3).filter((page) => {
                              // Filter out already linked pages by title
                              return !customerLinkedPages.some(linked => linked.title === page.title);
                            }).map((page) => (
                              <div
                                key={page.id}
                                className="notion-page"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleLinkPage(customer.id, page);
                                }}
                              >
                                <span className="notion-page__icon">
                                  {page.icon || '📄'}
                                </span>
                                <div className="notion-page__title">
                                  {page.title}
                                </div>
                                <span className="notion-page__meta">
                                  {isLinking ? <Loader2 className="w-3 h-3 animate-spin" /> : 'LINK'}
                                </span>
                              </div>
                            ))}
                            {(() => {
                              const availableResults = searchResults.filter(page =>
                                !customerLinkedPages.some(linked => linked.title === page.title)
                              );
                              const hiddenCount = availableResults.length - 3;

                              if (searchResults.length > 0 && availableResults.length === 0) {
                                return (
                                  <div className="text-xs text-foreground/50 py-2 text-center font-mono tracking-wider">
                                    All search results already linked
                                  </div>
                                );
                              }

                              if (hiddenCount > 0) {
                                return (
                                  <div className="text-xs text-foreground/50 py-2 text-center font-mono tracking-wider">
                                    + {hiddenCount} more · refine your search
                                  </div>
                                );
                              }

                              return null;
                            })()}

                            {searchResults.length === 0 && !isSearching && searchQuery && (
                              <div className="text-sm text-charcoal-500 py-4 text-center">
                                No pages found
                              </div>
                            )}
                          </div>
                        )}

                        {/* Action buttons */}
                        <div style={{ display: 'flex', gap: 8, marginTop: 18 }}>
                          <button
                            className="sk-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              setExpandedCustomer(null);
                              setActiveSearchCustomer(null);
                            }}
                          >
                            Cancel
                          </button>
                          <button
                            className="sk-btn sk-btn--primary"
                            onClick={async (e) => {
                              e.stopPropagation();
                              try {
                                // Move to next customer first for smooth UX
                                setActiveSearchCustomer(null);
                                const currentIndex = onboardingCustomers.findIndex(c => c.id === customer.id);
                                if (currentIndex < onboardingCustomers.length - 1) {
                                  setExpandedCustomer(onboardingCustomers[currentIndex + 1].id);
                                } else {
                                  setExpandedCustomer(null);
                                }
                                // Update classification to move customer to READY section
                                await updateClassification(customer.id, 'ready_to_confirm', 'Context provided - ready to proceed');
                                await new Promise(resolve => setTimeout(resolve, 350));
                                await refetchCustomers();
                              } catch (err) {
                                console.error('Failed to save and continue:', err);
                              }
                            }}
                          >
                            Save & continue →
                          </button>
                        </div>
                      </div>

                      {/* Right: Sidekick panel with AI insights */}
                      <div className="picker-aside">
                        <div className="picker-aside__title">
                          <Sparkles className="w-4 h-4" />
                          SIDEKICK
                        </div>

                        {/* Show AI reasoning if available */}
                        {customer.aiClassification ? (
                          <>
                            <p>{customer.aiClassification.reasoning}</p>

                            {customer.aiClassification.what_i_know.length > 0 && (
                              <>
                                <div className="picker-aside__rule" />
                                <p className="text-xs">
                                  <strong>What I know:</strong>
                                </p>
                                <ul className="text-xs text-charcoal-300 ml-3 mt-1 space-y-1">
                                  {customer.aiClassification.what_i_know.map((item, i) => (
                                    <li key={i}>• {item}</li>
                                  ))}
                                </ul>
                              </>
                            )}

                            {customer.aiClassification.what_im_uncertain_about.length > 0 && (
                              <>
                                <div className="picker-aside__rule" />
                                <p className="text-xs text-rust-400">
                                  <strong>What I'm uncertain about:</strong>
                                </p>
                                <ul className="text-xs text-charcoal-400 ml-3 mt-1 space-y-1">
                                  {customer.aiClassification.what_im_uncertain_about.map((item, i) => (
                                    <li key={i}>• {item}</li>
                                  ))}
                                </ul>
                              </>
                            )}
                          </>
                        ) : (
                          <p>
                            I'll read through <em>{customer.name}</em>'s existing docs and
                            preserve their progress. You won't have to recreate milestones
                            that are already done.
                          </p>
                        )}

                        {customerLinkedPages.filter(p => p.linked).length > 0 && (
                          <>
                            <div className="picker-aside__rule" />
                            <p className="text-xs">
                              <strong>Linked:</strong>{' '}
                              {customerLinkedPages.filter(p => p.linked).map(p => p.title).join(', ')}
                            </p>
                          </>
                        )}
                      </div>
                    </div>
                  </motion.div>
                );
              }

              // Collapsed row - standard 4-column grid
              return (
                <motion.div
                  key={customer.id}
                  layout
                  layoutId={`customer-${customer.id}`}
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: 100, transition: { duration: 0.3 } }}
                  transition={{ duration: 0.3, ease: 'easeInOut' }}
                  className={cn(
                    'cust-row',
                    hasLinkedPages || isSaved ? 'is-generated' : 'is-pointer-needed'
                  )}
                  onClick={() => setExpandedCustomer(customer.id)}
                >
                  {/* Col 1: Name + Meta */}
                  <div>
                    <div className="name">{customer.name}</div>
                    <div className="meta">{arrDisplay} · NEED CONTEXT</div>
                  </div>

                  {/* Col 2: Status */}
                  <div>
                    <span className={cn('state', hasLinkedPages ? 'done' : 'cur')}>
                      <span style={{ width: 6, height: 6, background: 'currentColor', borderRadius: '50%' }} />
                      {hasLinkedPages ? 'Ready to classify' : 'Point me at it'}
                    </span>
                    {hasLinkedPages ? (
                      <div className="state__detail">
                        {customerLinkedPages.length} page(s) linked · click to classify
                      </div>
                    ) : (
                      <div className="state__detail">
                        I can't tell where they are in onboarding from the DB record alone.
                      </div>
                    )}
                  </div>

                  {/* Col 3: Empty */}
                  <div></div>

                  {/* Col 4: Actions */}
                  <div className="action">
                    <button
                      className="sk-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSavedCustomers(prev => new Set([...prev, customer.id]));
                      }}
                    >
                      Treat as new
                    </button>
                    <button
                      className="sk-btn"
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          await updateClassification(customer.id, 'ready_to_confirm', 'Not in onboarding - marked by user');
                          // Delay refetch slightly to let animation complete
                          await new Promise(resolve => setTimeout(resolve, 350));
                          await refetchCustomers();
                        } catch (err) {
                          console.error('Failed to update classification:', err);
                        }
                      }}
                    >
                      Not onboarding
                    </button>
                    <button
                      className="sk-btn sk-btn--primary"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedCustomer(customer.id);
                      }}
                    >
                      Point me →
                    </button>
                  </div>
                </motion.div>
              );
            })}
            </AnimatePresence>
          </div>
        </>
      )}

      {/* Ready to Confirm Section */}
      {(ready.length > 0 || autoHandled.length > 0) && (
        <ReadyToConfirmSection
          customers={[...ready, ...autoHandled]}
          expandedCustomer={expandedCustomer}
          setExpandedCustomer={setExpandedCustomer}
          confirmedCustomers={savedCustomers}
          setConfirmedCustomers={setSavedCustomers}
          updateClassification={updateClassification}
          refetchCustomers={refetchCustomers}
        />
      )}

      {/* Sidekick note */}
      <div className="setup-sidekick-note">
        <span className="tag">SIDEKICK</span>
        {onboardingCustomers.length > 0 ? (
          <>
            {onboardingCustomers.length} customer{onboardingCustomers.length !== 1 && 's'} in onboarding.
            Point me at their existing docs and I'll preserve their progress. Or skip — I'll ask as I work through them.
          </>
        ) : (
          <>
            All {customerCount} customers look ready to go. I'll read their history and surface what needs attention.
          </>
        )}
      </div>

      {/* Footer */}
      <div className="setup__footer">
        <button type="button" className="sk-btn" onClick={onBack}>
          ← Back · Playbooks
        </button>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="sk-btn sk-btn--primary" onClick={onSkipToBucketed}>
            Continue →
          </button>
        </div>
      </div>

      {/* Notion Link Paste Modal (kept as modal for URL input) */}
      <NotionLinkPasteModal
        isOpen={!!pasteModalCustomer}
        customerId={pasteModalCustomer?.id || ''}
        customerName={pasteModalCustomer?.name || ''}
        onClose={() => setPasteModalCustomer(null)}
        onSuccess={(linkedPage) => {
          // Track the linked page
          if (pasteModalCustomer) {
            setLinkedPages(prev => ({
              ...prev,
              [pasteModalCustomer.id]: [
                ...(prev[pasteModalCustomer.id] || []),
                { type: 'onboarding', title: linkedPage?.title || 'Linked page', linked: true }
              ]
            }));
          }
          setPasteModalCustomer(null);
        }}
      />
    </>
  );
}

// =============================================================================
// Sub-step 2: "One decision unlocks all" - Column picker with two-column layout
// =============================================================================
function ColumnPickerStep({
  customerCount,
  propertySchemas,
  selectedColumn,
  bucketPreview,
  onSelectColumn,
  onApply,
  onBack,
  isLoadingSchema = false,
  isReimporting = false,
}: {
  customerCount: number;
  propertySchemas: NotionPropertySchema[];
  selectedColumn: string;
  bucketPreview: Array<{ name: string; count: number }>;
  onSelectColumn: (columnId: string) => void;
  onApply: () => void | Promise<void>;
  onBack: () => void;
  isLoadingSchema?: boolean;
  isReimporting?: boolean;
}) {
  // Categorize properties with full schema info
  const categorizedProps = useMemo(() => {
    const searchingProps: NotionProperty[] = [];
    const pipelineProps: NotionProperty[] = [];

    for (const schema of propertySchemas) {
      const role = detectPropertyRole(schema.name);
      const item: NotionProperty = {
        ...schema,
        role,
        // Build value preview from options if available
        valuePreview: schema.options?.slice(0, 4).join(' · '),
      };

      // Put lifecycle/status in "searching" (left column), others in "pipeline" (right column)
      if (role === 'lifecycle' || role === 'name') {
        searchingProps.push(item);
      } else {
        pipelineProps.push(item);
      }
    }

    return { searchingProps, pipelineProps };
  }, [propertySchemas]);

  // Auto-select first lifecycle property if none selected
  useEffect(() => {
    if (!selectedColumn && categorizedProps.searchingProps.length > 0) {
      const lifecycleProp = categorizedProps.searchingProps.find(p => p.role === 'lifecycle');
      if (lifecycleProp) {
        onSelectColumn(lifecycleProp.name);
      }
    }
  }, [selectedColumn, categorizedProps.searchingProps, onSelectColumn]);

  return (
    <>
      {/* Header */}
      <div className="setup__head">
        <div>
          <h1>One decision unlocks <em>all {customerCount}</em>.</h1>
          <p className="lede">
            I couldn't auto-detect a stage column. Tell me which one represents where each customer
            is in their journey — I'll bucket everyone from there.
          </p>
        </div>
        <div className="setup__head-aside">
          <div className="label">WHAT IF NONE FIT?</div>
          <p>
            I can read each Notion page individually. Slower, same result. Just skip this step.
          </p>
        </div>
      </div>

      {/* Section divider */}
      <div className="section-opener" style={{ marginBottom: 16 }}>
        <div className="hair" />
        <span className="eyebrow">SEARCHING · SORTING</span>
        <div className="hair-fill" />
        <span className="eyebrow" style={{ marginLeft: 16 }}>PIPELINE STATUS</span>
        <div className="hair-fill" />
      </div>

      {/* Two-column property picker */}
      {isLoadingSchema ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-rust-500 animate-spin" />
          <span className="ml-3 text-charcoal-400">Loading Notion properties...</span>
        </div>
      ) : propertySchemas.length > 0 ? (
        <div className="grid grid-cols-2 gap-6 mb-6">
          {/* Left column: Searching/Sorting properties */}
          <div className="space-y-2">
            <div className="text-xs font-mono text-charcoal-500 mb-2">
              Which column tells me <em className="text-cream-100">where</em> each customer is?
            </div>
            {categorizedProps.searchingProps.map((prop) => {
              const isSelected = selectedColumn === prop.name;

              return (
                <button
                  key={prop.name}
                  type="button"
                  className={cn(
                    'cust-row w-full text-left',
                    isSelected && 'is-imported'
                  )}
                  onClick={() => onSelectColumn(prop.name)}
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "w-4 h-4 rounded border flex items-center justify-center",
                        isSelected
                          ? "border-emerald-500 bg-emerald-500/20"
                          : "border-charcoal-600"
                      )}>
                        {isSelected && <Check className="w-3 h-3 text-emerald-400" />}
                      </span>
                      <span className="name font-mono">{prop.name}</span>
                      {prop.type && prop.type !== 'unknown' && (
                        <span className="text-xs text-charcoal-500 font-mono">{prop.type}</span>
                      )}
                    </div>
                    <div className="meta ml-6">
                      {prop.role === 'lifecycle' && 'PRIORITY · Looks like lifecycle'}
                      {prop.role === 'name' && 'Customer name field'}
                      {prop.role === 'other' && 'Other property'}
                      {prop.valuePreview && (
                        <span className="text-charcoal-500 ml-1">({prop.valuePreview})</span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
            {categorizedProps.searchingProps.length === 0 && (
              <div className="text-sm text-charcoal-500 py-4">
                No lifecycle-type properties found
              </div>
            )}
          </div>

          {/* Right column: Pipeline Status properties */}
          <div className="space-y-2">
            <div className="text-xs font-mono text-charcoal-500 mb-2">
              Additional fields I'll use
            </div>
            {categorizedProps.pipelineProps.slice(0, 6).map((prop) => (
              <div key={prop.name} className="cust-row opacity-60">
                <div className="flex-1">
                  <div className="name font-mono">{prop.name}</div>
                  <div className="meta">
                    {prop.role === 'tier' && 'Tier · Plan level'}
                    {prop.role === 'arr' && 'ARR · Revenue'}
                    {prop.role === 'date' && 'Date field'}
                    {prop.role === 'other' && 'Other'}
                  </div>
                </div>
              </div>
            ))}
            {categorizedProps.pipelineProps.length > 6 && (
              <div className="text-xs text-charcoal-500">
                + {categorizedProps.pipelineProps.length - 6} more
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="cust-row is-pointer-needed" style={{ marginBottom: 24 }}>
          <div>
            <div className="name">No properties found</div>
            <div className="meta">Could not load Notion database schema</div>
          </div>
        </div>
      )}

      {/* Bucket preview */}
      {selectedColumn && bucketPreview.length > 0 && (
        <div className="p-4 border border-charcoal-700 bg-charcoal-800/30 mb-6">
          <div className="text-xs font-mono text-charcoal-500 mb-2">
            IF I USE {selectedColumn.toUpperCase()}, I SEE THESE BUCKETS:
          </div>
          <div className="flex flex-wrap gap-2">
            {bucketPreview.map((bucket, idx) => (
              <span key={bucket.name} className="text-sm">
                {/* Show count if available (from imported customers), otherwise just show option name */}
                {bucket.count >= 0 ? (
                  <>
                    <span className="text-rust-400 font-mono">{bucket.count}</span>
                    <span className="text-charcoal-300 ml-1">{bucket.name}</span>
                  </>
                ) : (
                  <span className="text-charcoal-300">{bucket.name}</span>
                )}
                {idx < bucketPreview.length - 1 && (
                  <span className="text-charcoal-600 mx-1">·</span>
                )}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Sidekick note */}
      <div className="setup-sidekick-note" style={{ marginBottom: 24 }}>
        <span className="tag">SIDEKICK</span>
        Or — I can read each Notion page individually. Slower, same result.
      </div>

      {/* Footer */}
      <div className="setup__footer">
        <button type="button" className="sk-btn" onClick={onBack}>
          ← Back · Customers
        </button>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="sk-btn" onClick={onApply}>
            Skip · Assign one by one
          </button>
          <button
            type="button"
            className="sk-btn sk-btn--primary"
            onClick={onApply}
            disabled={!selectedColumn || isReimporting}
          >
            {isReimporting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
                Updating lifecycles...
              </>
            ) : selectedColumn ? (
              `Use "${selectedColumn}" →`
            ) : (
              'Select a column'
            )}
          </button>
        </div>
      </div>
    </>
  );
}

// =============================================================================
// Sub-step 3: "Bucketed" - Review the categorization
// =============================================================================
function BucketedStep({
  customerCount,
  bucketCounts,
  onComplete,
  onBack,
}: {
  customerCount: number;
  bucketCounts: Array<{ name: string; count: number }>;
  onComplete: () => void;
  onBack: () => void;
}) {
  return (
    <>
      {/* Header */}
      <div className="setup__head">
        <div>
          <h1><em>{customerCount}</em> customers found. <em>Bucketed.</em></h1>
          <p className="lede">
            Here's how Sidekick has categorized your customers based on the lifecycle data.
            Review and adjust if needed.
          </p>
        </div>
        <div className="setup__head-aside">
          <div className="label">WHAT'S NEXT</div>
          <p>
            Sidekick will start reading each customer's history and generating
            insights. You'll see the results in your Today queue.
          </p>
        </div>
      </div>

      {/* Bucket tally */}
      <div className="cust-tally" style={{ marginBottom: 24 }}>
        <div className="cust-tally__cell">
          <div className="v">{customerCount}</div>
          <div className="k">TOTAL</div>
        </div>
        <div className="cust-tally__sep" />
        {bucketCounts.slice(0, 4).map((bucket, idx) => (
          <React.Fragment key={bucket.name}>
            <div className="cust-tally__cell">
              <div className={cn(
                'v',
                bucket.name.toLowerCase() === 'active' && 'ok',
                bucket.name.toLowerCase() === 'onboarding' && 'warn',
              )}>
                {bucket.count}
              </div>
              <div className="k">{bucket.name.toUpperCase()}</div>
            </div>
            {idx < 3 && <div className="cust-tally__sep" />}
          </React.Fragment>
        ))}
      </div>

      {/* Bucket cards */}
      <div className="space-y-3 mb-6">
        {bucketCounts.map((bucket) => {
          const isOnboarding = bucket.name.toLowerCase() === 'onboarding';
          const isActive = bucket.name.toLowerCase() === 'active';

          return (
            <div
              key={bucket.name}
              className={cn(
                'cust-row',
                isActive && 'is-imported',
                isOnboarding && 'is-generated',
              )}
            >
              <div>
                <div className="name">{bucket.name}</div>
                <div className="meta">
                  {bucket.count} CUSTOMERS
                  {isOnboarding && <span className="text-rust-500 ml-2">· NEED PLANS</span>}
                </div>
              </div>

              <div>
                <span className={cn(
                  'state',
                  isActive && 'done',
                  isOnboarding && 'cur',
                )}>
                  {isActive && <Check className="w-3 h-3" />}
                  {isOnboarding && <Sparkles className="w-3 h-3" />}
                  {bucket.name.toUpperCase()}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Onboarding note */}
      {bucketCounts.some(b => b.name.toLowerCase() === 'onboarding' && b.count > 0) && (
        <div className="picker-aside" style={{ marginBottom: 24 }}>
          <div className="picker-aside__title">
            <Sparkles className="w-4 h-4" />
            ABOUT ONBOARDING CUSTOMERS
          </div>
          <p>
            For customers in <strong>Onboarding</strong>, I'll need to understand their implementation plan.
            As I work through each one, I may ask you to <em>point me at their docs</em> — handoff briefs,
            implementation trackers, or milestone pages in Notion.
          </p>
          <div className="picker-aside__rule" />
          <p className="text-xs text-charcoal-400">
            Don't worry about this now. I'll ask as I go, and you can always add more Notion access later.
          </p>
        </div>
      )}

      {/* Success message */}
      <div className="setup-sidekick-note">
        <span className="tag">SIDEKICK</span>
        All {customerCount} customers have been categorized. I'll start reading their
        history and surface what needs attention in your <em>Today</em> queue.
      </div>

      {/* Footer */}
      <div className="setup__footer">
        <button type="button" className="sk-btn" onClick={onBack}>
          ← Back · Adjust columns
        </button>
        <button type="button" className="sk-btn sk-btn--primary" onClick={onComplete}>
          Finish setup →
        </button>
      </div>
    </>
  );
}
