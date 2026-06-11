import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Loader2, Send, X, Upload, Check, ChevronRight, Clock, Users, Briefcase } from 'lucide-react';
import { getAuth } from 'firebase/auth';
import { cn } from '@/lib/utils';
import { usePlaybooks, usePlaybookTemplates, useAdoptTemplate, type PlaybookTemplate } from '@/lib/dataconnect-hooks';
import { useWorkspace } from '@/lib/workspace';
import type { OnboardingData, UpdateDataFn } from './index';

interface StepPlaybooksProps {
  data: OnboardingData;
  updateData: UpdateDataFn;
  onComplete: () => void;
  onBack: () => void;
}

type PlaybookEntryMode = 'describe' | 'catalog' | 'csv' | null;

// Complexity to display label mapping
const COMPLEXITY_LABELS: Record<string, { label: string; color: string }> = {
  simple: { label: 'QUICK START', color: 'text-green-400' },
  standard: { label: 'STANDARD', color: 'text-blue-400' },
  complex: { label: 'ENTERPRISE', color: 'text-purple-400' },
};

export function StepPlaybooks({
  data,
  updateData,
  onComplete,
  onBack,
}: StepPlaybooksProps) {
  const { workspaceId } = useWorkspace();
  const { data: playbooksData, isLoading: isLoadingPlaybooks, refetch: refetchPlaybooks } = usePlaybooks();
  const { templates, isLoading: isLoadingTemplates } = usePlaybookTemplates();
  const { adoptTemplate, isLoading: isAdopting } = useAdoptTemplate();
  const playbooks = playbooksData?.playbooks || [];

  const [entryMode, setEntryMode] = useState<PlaybookEntryMode>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<PlaybookTemplate | null>(null);

  // Describe mode state
  const [describeText, setDescribeText] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // CSV import state
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvParsing, setCsvParsing] = useState(false);
  const [csvPreview, setCsvPreview] = useState<{ name: string; milestones: Array<{ title: string; days: number; owner: string }> } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Refetch playbooks when data indicates seeding is complete but we don't have data yet
  useEffect(() => {
    if (data.playbooksSeeded && !isLoadingPlaybooks && playbooks.length === 0) {
      refetchPlaybooks();
    }
  }, [data.playbooksSeeded, isLoadingPlaybooks, playbooks.length, refetchPlaybooks]);

  // Focus textarea when entering describe mode
  useEffect(() => {
    if (entryMode === 'describe' && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [entryMode]);

  const showLoading = isLoadingPlaybooks || isLoadingTemplates;

  const handleDescribeSubmit = async () => {
    if (!describeText.trim() || isGenerating || !workspaceId) return;

    setIsGenerating(true);
    try {
      const token = await getAuth().currentUser?.getIdToken();
      if (!token) {
        console.error('No auth token available');
        return;
      }

      const response = await fetch(
        `${import.meta.env.VITE_PYTHON_URL}/api/workspaces/${workspaceId}/playbooks/generate`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({ description: describeText }),
        }
      );

      const result = await response.json();

      if (result.success) {
        console.log('Playbook generated:', result);
        await refetchPlaybooks();
        setEntryMode(null);
        setDescribeText('');
        onComplete();
      } else {
        console.error('Playbook generation failed:', result.message);
      }
    } catch (error) {
      console.error('Playbook generation error:', error);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleAdoptTemplate = async (template: PlaybookTemplate) => {
    try {
      await adoptTemplate(template);
      await refetchPlaybooks();
      setSelectedTemplate(null);
      setEntryMode(null);
    } catch (error) {
      console.error('Failed to adopt template:', error);
    }
  };

  const handleCsvFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setCsvFile(file);
    setCsvParsing(true);

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const lines = text.split('\n').filter(line => line.trim());

      if (lines.length < 2) {
        setCsvParsing(false);
        return;
      }

      // Parse CSV - expect: title, days, owner, description
      const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
      const titleIdx = headers.findIndex(h => h.includes('title') || h.includes('milestone') || h.includes('name'));
      const daysIdx = headers.findIndex(h => h.includes('day') || h.includes('duration'));
      const ownerIdx = headers.findIndex(h => h.includes('owner') || h.includes('side'));

      const milestones = lines.slice(1).map(line => {
        const cols = line.split(',').map(c => c.trim().replace(/^["']|["']$/g, ''));
        return {
          title: cols[titleIdx !== -1 ? titleIdx : 0] || 'Untitled',
          days: parseInt(cols[daysIdx !== -1 ? daysIdx : 1]) || 7,
          owner: cols[ownerIdx !== -1 ? ownerIdx : 2] || 'joint',
        };
      }).filter(m => m.title && m.title !== 'Untitled');

      const playbookName = file.name.replace(/\.csv$/i, '').replace(/[-_]/g, ' ');

      setCsvPreview({
        name: playbookName,
        milestones,
      });
      setCsvParsing(false);
    };
    reader.readAsText(file);
  }, []);

  const handleCsvImport = async () => {
    if (!csvPreview || !workspaceId) return;

    setIsGenerating(true);
    // TODO: Create playbook from CSV data via backend
    await new Promise(resolve => setTimeout(resolve, 1500));
    setIsGenerating(false);

    setCsvFile(null);
    setCsvPreview(null);
    setEntryMode(null);
    await refetchPlaybooks();
  };

  if (showLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 text-rust-500 animate-spin" />
        <span className="ml-3 text-charcoal-400">Loading...</span>
      </div>
    );
  }

  // Describe mode
  if (entryMode === 'describe') {
    return (
      <>
        <div className="setup__head">
          <div>
            <h1>Describe your <em>onboarding</em> to Sidekick.</h1>
            <p className="lede">
              Tell me what a successful onboarding looks like for your most common customer type.
              I'll extract milestones, success criteria, and guardrails.
            </p>
          </div>
          <div className="setup__head-aside">
            <div className="label">SIDEKICK WILL EXTRACT</div>
            <p>
              Milestones, owner assignments, duration estimates, success criteria, and guardrails from your description.
            </p>
          </div>
        </div>

        <div className="border border-charcoal-700 bg-charcoal-800/30 p-6">
          <div className="flex items-start gap-4 mb-6">
            <div className="w-8 h-8 bg-rust-500/20 border border-rust-500/50 flex items-center justify-center flex-shrink-0">
              <span className="text-rust-500 font-mono text-xs">SK</span>
            </div>
            <div className="flex-1">
              <p className="text-cream-200 text-sm leading-relaxed">
                Describe how you onboard a typical customer. Include things like:
              </p>
              <ul className="text-charcoal-300 text-sm mt-2 space-y-1 list-disc list-inside">
                <li>What happens in the first week?</li>
                <li>Who's responsible for what (you vs. the customer)?</li>
                <li>What does "done" look like?</li>
                <li>Any hard rules or things to avoid?</li>
              </ul>
            </div>
          </div>

          <div className="relative">
            <textarea
              ref={textareaRef}
              value={describeText}
              onChange={(e) => setDescribeText(e.target.value)}
              placeholder="Example: We start with a kickoff call in the first 3 days. Then the customer needs to invite their team and connect their data source. We check in weekly. Success is when they've run their first report and shared it with their team. Usually takes 2-3 weeks..."
              className="w-full h-40 bg-charcoal-900 border border-charcoal-600 p-4 text-cream-100 text-sm resize-none focus:outline-none focus:border-rust-500 placeholder:text-charcoal-500"
              disabled={isGenerating}
            />
            <div className="absolute bottom-3 right-3 flex items-center gap-2">
              <span className="text-xs text-charcoal-500 font-mono">
                {describeText.length} chars
              </span>
            </div>
          </div>

          {isGenerating && (
            <div className="mt-4 flex items-center gap-3 text-rust-400">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm font-mono">Extracting playbook structure...</span>
            </div>
          )}
        </div>

        <div className="setup__footer">
          <button type="button" className="sk-btn" onClick={() => setEntryMode(null)}>
            <X className="w-4 h-4 mr-2" />
            Cancel
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="sk-btn" onClick={onComplete}>
              Skip · I'll come back
            </button>
            <button
              type="button"
              className="sk-btn sk-btn--primary"
              onClick={handleDescribeSubmit}
              disabled={!describeText.trim() || isGenerating}
            >
              <Send className="w-4 h-4 mr-2" />
              Generate playbook →
            </button>
          </div>
        </div>
      </>
    );
  }

  // Catalog mode - show all templates
  if (entryMode === 'catalog') {
    return (
      <>
        <div className="setup__head">
          <div>
            <h1>Pick a <em>template</em> to start from.</h1>
            <p className="lede">
              These are battle-tested patterns for different customer types. Pick one, customize it, and you're ready to go.
            </p>
          </div>
          <div className="setup__head-aside">
            <div className="label">YOU CAN CUSTOMIZE</div>
            <p>
              Templates are starting points. Add milestones, change durations, rename steps — make it yours.
            </p>
          </div>
        </div>

        {/* Template detail view */}
        {selectedTemplate ? (
          <div className="space-y-6">
            {/* Selected template header */}
            <div className="border border-rust-500/50 bg-charcoal-800/50 p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <div className={cn('text-xs font-mono mb-2', COMPLEXITY_LABELS[selectedTemplate.complexity]?.color || 'text-charcoal-400')}>
                    {COMPLEXITY_LABELS[selectedTemplate.complexity]?.label || selectedTemplate.complexity.toUpperCase()}
                  </div>
                  <h3 className="text-xl text-cream-100">{selectedTemplate.name}</h3>
                  <p className="text-charcoal-300 text-sm mt-1">{selectedTemplate.description}</p>
                </div>
                <div className="flex items-center gap-4 text-sm text-charcoal-400">
                  <div className="flex items-center gap-1">
                    <Clock className="w-4 h-4" />
                    <span>{selectedTemplate.estimatedDays} days</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Users className="w-4 h-4" />
                    <span>{selectedTemplate.blocks.length} steps</span>
                  </div>
                </div>
              </div>

              {/* Milestone preview */}
              <div className="border-t border-charcoal-700 pt-4 mt-4">
                <div className="text-xs font-mono text-charcoal-500 mb-3">MILESTONES</div>
                <div className="space-y-2">
                  {selectedTemplate.blocks.map((block, idx) => (
                    <div
                      key={block.slug}
                      className="flex items-center gap-3 text-sm py-2 border-b border-charcoal-700/50 last:border-0"
                    >
                      <span className="text-charcoal-500 font-mono w-6">{idx + 1}.</span>
                      <span className="text-cream-200 flex-1">{block.name}</span>
                      <span className={cn(
                        'text-xs px-2 py-0.5',
                        block.ownerSide === 'us' ? 'bg-green-500/10 text-green-400' :
                        block.ownerSide === 'customer' ? 'bg-blue-500/10 text-blue-400' :
                        'bg-charcoal-600 text-charcoal-300'
                      )}>
                        {block.ownerSide === 'us' ? 'You' : block.ownerSide === 'customer' ? 'Customer' : 'Joint'}
                      </span>
                      <span className="text-charcoal-400 text-xs w-16 text-right">
                        {block.durationOverride || block.typicalDays}d
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="setup__footer">
              <button type="button" className="sk-btn" onClick={() => setSelectedTemplate(null)}>
                ← Back to templates
              </button>
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="sk-btn" onClick={onComplete}>
                  Skip · I'll come back
                </button>
                <button
                  type="button"
                  className="sk-btn sk-btn--primary"
                  onClick={() => handleAdoptTemplate(selectedTemplate)}
                  disabled={isAdopting}
                >
                  {isAdopting ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Adopting...
                    </>
                  ) : (
                    <>
                      <Check className="w-4 h-4 mr-2" />
                      Use this template →
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        ) : (
          /* Template grid */
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {templates.map((template) => (
                <div
                  key={template.id}
                  className={cn(
                    'border bg-charcoal-800/30 p-5 cursor-pointer transition-all',
                    'hover:border-rust-500/50 hover:bg-charcoal-800/50',
                    'border-charcoal-700'
                  )}
                  onClick={() => setSelectedTemplate(template)}
                >
                  <div className={cn('text-xs font-mono mb-2', COMPLEXITY_LABELS[template.complexity]?.color || 'text-charcoal-400')}>
                    {COMPLEXITY_LABELS[template.complexity]?.label || template.complexity.toUpperCase()}
                  </div>
                  <h4 className="text-cream-100 mb-2">{template.name}</h4>
                  <p className="text-charcoal-400 text-sm mb-4 line-clamp-2">{template.description}</p>
                  <div className="flex items-center justify-between text-xs text-charcoal-500">
                    <span>{template.estimatedDays} days</span>
                    <span>{template.blocks.length} steps</span>
                  </div>
                  <div className="mt-3 pt-3 border-t border-charcoal-700 flex items-center text-rust-400 text-sm">
                    <span>Preview & customize</span>
                    <ChevronRight className="w-4 h-4 ml-1" />
                  </div>
                </div>
              ))}
            </div>

            <div className="setup__footer">
              <button type="button" className="sk-btn" onClick={() => setEntryMode(null)}>
                ← Back
              </button>
              <button type="button" className="sk-btn" onClick={onComplete}>
                Skip · I'll come back
              </button>
            </div>
          </>
        )}
      </>
    );
  }

  // CSV Import mode
  if (entryMode === 'csv') {
    return (
      <>
        <div className="setup__head">
          <div>
            <h1>Import from <em>CSV</em></h1>
            <p className="lede">
              Upload a CSV with your milestones. We'll create a playbook from it.
            </p>
          </div>
          <div className="setup__head-aside">
            <div className="label">CSV FORMAT</div>
            <p>
              Columns: Title, Days, Owner (us/customer/joint), Description. First row should be headers.
            </p>
          </div>
        </div>

        <div className="border border-charcoal-700 bg-charcoal-800/30 p-6">
          {!csvPreview ? (
            <div
              className="border-2 border-dashed border-charcoal-600 p-12 text-center cursor-pointer hover:border-rust-500/50 transition-colors"
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={handleCsvFileSelect}
              />
              <Upload className="w-12 h-12 text-charcoal-500 mx-auto mb-4" />
              <p className="text-cream-200 mb-2">Drop your CSV here or click to browse</p>
              <p className="text-charcoal-400 text-sm">Supports .csv files</p>

              {csvParsing && (
                <div className="mt-4 flex items-center justify-center gap-2 text-rust-400">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Parsing...</span>
                </div>
              )}
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="text-xs font-mono text-charcoal-500 mb-1">PLAYBOOK NAME</div>
                  <h3 className="text-lg text-cream-100">{csvPreview.name}</h3>
                </div>
                <button
                  type="button"
                  className="text-charcoal-400 hover:text-cream-200"
                  onClick={() => {
                    setCsvFile(null);
                    setCsvPreview(null);
                  }}
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="border-t border-charcoal-700 pt-4">
                <div className="text-xs font-mono text-charcoal-500 mb-3">
                  {csvPreview.milestones.length} MILESTONES FOUND
                </div>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {csvPreview.milestones.map((m, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-3 text-sm py-2 border-b border-charcoal-700/50 last:border-0"
                    >
                      <span className="text-charcoal-500 font-mono w-6">{idx + 1}.</span>
                      <span className="text-cream-200 flex-1">{m.title}</span>
                      <span className={cn(
                        'text-xs px-2 py-0.5',
                        m.owner === 'us' ? 'bg-green-500/10 text-green-400' :
                        m.owner === 'customer' ? 'bg-blue-500/10 text-blue-400' :
                        'bg-charcoal-600 text-charcoal-300'
                      )}>
                        {m.owner === 'us' ? 'You' : m.owner === 'customer' ? 'Customer' : 'Joint'}
                      </span>
                      <span className="text-charcoal-400 text-xs w-16 text-right">{m.days}d</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="setup__footer">
          <button type="button" className="sk-btn" onClick={() => {
            setEntryMode(null);
            setCsvFile(null);
            setCsvPreview(null);
          }}>
            <X className="w-4 h-4 mr-2" />
            Cancel
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="sk-btn" onClick={onComplete}>
              Skip · I'll come back
            </button>
            <button
              type="button"
              className="sk-btn sk-btn--primary"
              onClick={handleCsvImport}
              disabled={!csvPreview || isGenerating}
            >
              {isGenerating ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Check className="w-4 h-4 mr-2" />
                  Create playbook →
                </>
              )}
            </button>
          </div>
        </div>
      </>
    );
  }

  // Default view - entry tiles + popular templates
  return (
    <>
      <div className="setup__head">
        <div>
          <h1>How does your team <em>actually</em> onboard a customer?</h1>
          <p className="lede">
            A playbook tells Sidekick what good looks like for a kind of customer — so it can draft per-customer plans without you starting from scratch.
          </p>
        </div>
        <div className="setup__head-aside">
          <div className="label">YOU CAN SKIP THIS</div>
          <p>
            Sidekick will still work — it'll just ask more questions when generating a plan. Most teams come back here in the first week.
          </p>
        </div>
      </div>

      {/* Entry tiles */}
      <div className="pb-start">
        <div className="pb-start__tile" onClick={() => setEntryMode('describe')}>
          <div className="pb-start__tile-eyebrow">FASTEST · 60 SECONDS</div>
          <h3 className="pb-start__tile-title">
            Describe it to <em>Sidekick</em>
          </h3>
          <p className="pb-start__tile-sub">
            Tell me what good looks like for your most common customer. I'll draft the playbook and you'll edit from there.
          </p>
          <div className="pb-start__tile-cta">Open the editor →</div>
        </div>

        <div className="pb-start__tile" onClick={() => setEntryMode('catalog')}>
          <div className="pb-start__tile-eyebrow">FROM A TEMPLATE</div>
          <h3 className="pb-start__tile-title">Pick from the catalog</h3>
          <p className="pb-start__tile-sub">
            {templates.length} battle-tested templates for different scenarios. Fork one and customize; most teams are done in 10 minutes.
          </p>
          <div className="pb-start__tile-cta">Browse catalog →</div>
        </div>

        <div className="pb-start__tile" onClick={() => setEntryMode('csv')}>
          <div className="pb-start__tile-eyebrow">HAVE A SPREADSHEET</div>
          <h3 className="pb-start__tile-title">Import from CSV</h3>
          <p className="pb-start__tile-sub">
            Upload a CSV with your milestones. Sidekick will parse it and create a playbook you can refine.
          </p>
          <div className="pb-start__tile-cta">Import →</div>
        </div>
      </div>

      {/* Popular templates from catalog */}
      <div className="section-opener" style={{ marginTop: 24 }}>
        <div className="hair" />
        <span className="eyebrow">OR · POPULAR FOR TEAMS LIKE YOURS</span>
        <div className="hair-fill" />
      </div>

      <div className="pb-catalog" style={{ marginTop: 18 }}>
        {templates.slice(0, 3).map((template) => {
          const complexity = COMPLEXITY_LABELS[template.complexity];
          return (
            <div
              key={template.id}
              className={cn(
                'pb-catalog__item cursor-pointer',
                template.complexity === 'simple' ? 'onboarding' : 'action'
              )}
              onClick={() => {
                setEntryMode('catalog');
                setSelectedTemplate(template);
              }}
            >
              <div className="type">
                {complexity?.label || template.complexity.toUpperCase()} · {template.estimatedDays} DAYS
              </div>
              <h4 className="title">{template.name}</h4>
              <p className="desc">{template.description}</p>
            </div>
          );
        })}
      </div>

      <div className="setup__footer">
        <button type="button" className="sk-btn" onClick={onBack}>
          ← Back · Integrations
        </button>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="sk-btn" onClick={onComplete}>
            Skip · I'll come back
          </button>
          <button type="button" className="sk-btn sk-btn--primary" onClick={onComplete}>
            Next · Bring in your customers →
          </button>
        </div>
      </div>
    </>
  );
}
