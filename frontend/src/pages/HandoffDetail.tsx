import React, { useState } from 'react';
import { useParams, useNavigate, NavLink } from 'react-router-dom';
import { RefCode, Timestamp, Pulse, Sidekick } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import { useHandoff, useUpdateHandoff, useConfirmHandoff } from '@/lib/dataconnect-hooks';
import type { HandoffBrief, AIPlan, HandoffOpenQuestion, SalesCommitment, TechnicalContext } from '@/lib/api';
import {
  ChevronRight,
  Check,
  AlertTriangle,
  FileText,
  Sparkles,
  Plus,
  Trash2,
  GripVertical,
  HelpCircle,
  ExternalLink
} from 'lucide-react';

// Loading skeleton
function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-8">
      <div className="h-8 w-64 bg-charcoal-700 rounded" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="h-96 bg-charcoal-800 rounded" />
        <div className="h-96 bg-charcoal-800 rounded" />
      </div>
    </div>
  );
}

// Editable list component
function EditableList<T extends { item: string; details?: string }>({
  title,
  items,
  onChange,
  placeholder
}: {
  title: string;
  items: T[];
  onChange: (items: T[]) => void;
  placeholder: string;
}) {
  const addItem = () => {
    onChange([...items, { item: '', details: '' } as T]);
  };

  const updateItem = (index: number, field: keyof T, value: string) => {
    const updated = [...items];
    updated[index] = { ...updated[index], [field]: value };
    onChange(updated);
  };

  const removeItem = (index: number) => {
    onChange(items.filter((_, i) => i !== index));
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs font-mono uppercase tracking-widest text-charcoal-400">
          {title}
        </h3>
        <button
          onClick={addItem}
          className="text-xs font-mono uppercase tracking-widest text-rust-500 hover:text-rust-400 flex items-center gap-1"
        >
          <Plus className="w-3 h-3" /> Add
        </button>
      </div>
      <div className="space-y-3">
        {items.length === 0 ? (
          <div className="text-sm text-charcoal-500 italic">{placeholder}</div>
        ) : (
          items.map((item, index) => (
            <div key={index} className="group border border-charcoal-700 bg-charcoal-900/50 p-4">
              <div className="flex items-start gap-3">
                <GripVertical className="w-4 h-4 text-charcoal-600 mt-1 cursor-grab" />
                <div className="flex-1 space-y-2">
                  <input
                    type="text"
                    value={item.item}
                    onChange={(e) => updateItem(index, 'item', e.target.value)}
                    placeholder="Item..."
                    className="w-full bg-transparent border-b border-charcoal-700 pb-1 text-cream-200 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                  />
                  <input
                    type="text"
                    value={item.details || ''}
                    onChange={(e) => updateItem(index, 'details', e.target.value)}
                    placeholder="Details (optional)..."
                    className="w-full bg-transparent text-sm text-cream-400 placeholder:text-charcoal-600 focus:outline-none"
                  />
                </div>
                <button
                  onClick={() => removeItem(index)}
                  className="opacity-0 group-hover:opacity-100 text-charcoal-500 hover:text-rust-500 transition-opacity"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// Open questions component
function OpenQuestions({ questions }: { questions: HandoffOpenQuestion[] }) {
  if (questions.length === 0) return null;

  const unresolved = questions.filter(q => !q.resolved);
  const resolved = questions.filter(q => q.resolved);

  return (
    <div className="hud-border p-6 border-l-2 border-l-amber-500">
      <h3 className="text-xs font-mono uppercase tracking-widest text-amber-500 mb-4 flex items-center gap-2">
        <HelpCircle className="w-4 h-4" />
        Open Questions ({unresolved.length})
      </h3>
      <div className="space-y-3">
        {unresolved.map((q) => (
          <div key={q.id} className="flex items-start gap-3">
            <div className="w-2 h-2 rounded-full bg-amber-500 mt-2" />
            <p className="text-cream-300">{q.text}</p>
          </div>
        ))}
        {resolved.length > 0 && (
          <div className="mt-4 pt-4 border-t border-charcoal-700">
            <span className="text-xs text-charcoal-500">{resolved.length} resolved</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default function HandoffDetail() {
  const { briefId } = useParams<{ briefId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, error, refetch } = useHandoff(briefId || '');
  const updateHandoff = useUpdateHandoff();
  const confirmHandoff = useConfirmHandoff();

  // Local state for editing
  const [salesCommitments, setSalesCommitments] = useState<SalesCommitment[]>([]);
  const [technicalContext, setTechnicalContext] = useState<TechnicalContext[]>([]);
  const [confidenceNote, setConfidenceNote] = useState('');
  const [risksNote, setRisksNote] = useState('');
  const [hasChanges, setHasChanges] = useState(false);
  const [initialized, setInitialized] = useState(false);

  // Initialize state from data
  React.useEffect(() => {
    if (data?.brief && !initialized) {
      setSalesCommitments(data.brief.sales_commitments || []);
      setTechnicalContext(data.brief.technical_context || []);
      setConfidenceNote(data.brief.reality_check_confidence || '');
      setRisksNote(data.brief.reality_check_risks || '');
      setInitialized(true);
    }
  }, [data, initialized]);

  // Track changes
  React.useEffect(() => {
    if (data?.brief) {
      const originalSales = JSON.stringify(data.brief.sales_commitments || []);
      const originalTech = JSON.stringify(data.brief.technical_context || []);
      const currentSales = JSON.stringify(salesCommitments);
      const currentTech = JSON.stringify(technicalContext);

      setHasChanges(
        originalSales !== currentSales ||
        originalTech !== currentTech ||
        confidenceNote !== (data.brief.reality_check_confidence || '') ||
        risksNote !== (data.brief.reality_check_risks || '')
      );
    }
  }, [salesCommitments, technicalContext, confidenceNote, risksNote, data]);

  if (!briefId) {
    return (
      <div className="max-w-5xl mx-auto">
        <div className="hud-border p-8 text-center">
          <p className="text-cream-400">No handoff selected.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto">
        <div className="hud-border p-8 border-l-4 border-l-rust-500">
          <div className="text-[10px] uppercase tracking-[0.3em] text-rust-500 font-bold mb-4">
            Error Loading Handoff
          </div>
          <p className="text-cream-200 mb-4">{(error as Error).message}</p>
          <button
            onClick={() => refetch()}
            className="text-xs font-mono uppercase tracking-widest border border-rust-500 text-rust-500 px-4 py-2 hover:bg-rust-500 hover:text-charcoal-900 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="max-w-5xl mx-auto">
        <LoadingSkeleton />
      </div>
    );
  }

  const { brief, plan, open_questions } = data;
  const isDraft = brief.status === 'draft';
  const needsCorrection = brief.status === 'needs_correction';

  const handleSave = () => {
    updateHandoff.mutate({
      briefId: brief.id,
      data: {
        sales_commitments: salesCommitments,
        technical_context: technicalContext,
        reality_check_confidence: confidenceNote,
        reality_check_risks: risksNote,
      },
    });
  };

  const handleConfirm = () => {
    confirmHandoff.mutate(brief.id, {
      onSuccess: () => {
        // If there's a plan, navigate to plan approval
        if (plan) {
          navigate(`/app/plans/${plan.id}`);
        }
      },
    });
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center gap-2 text-xs font-mono text-charcoal-400 mb-4">
          <NavLink to="/app/handoffs" className="hover:text-cream-200 transition-colors">
            Handoffs
          </NavLink>
          <ChevronRight className="w-3 h-3" />
          <span className="text-cream-200">Brief</span>
        </div>

        <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b border-charcoal-700 pb-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              {isDraft && <Pulse active />}
              <RefCode>{brief.id.slice(0, 8).toUpperCase()}</RefCode>
              <span className={cn(
                "text-xs font-mono uppercase tracking-widest px-2 py-0.5 border",
                brief.status === 'draft'
                  ? "border-charcoal-500 text-charcoal-400"
                  : brief.status === 'confirmed'
                  ? "border-emerald-500 text-emerald-500"
                  : "border-amber-500 text-amber-500"
              )}>
                {brief.status.replace('_', ' ')}
              </span>
            </div>
            <h1 className="font-serif text-3xl text-cream-100">Handoff Brief</h1>
            <Timestamp
              time={`Captured ${new Date(brief.captured_at).toLocaleDateString()}`}
              className="mt-2"
            />
          </div>

          <div className="flex gap-3">
            {brief.notion_deal_url && (
              <a
                href={brief.notion_deal_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-4 py-2 hover:border-cream-400 hover:text-cream-200 transition-colors flex items-center gap-2"
              >
                <ExternalLink className="w-4 h-4" />
                Notion
              </a>
            )}
            {plan && (
              <NavLink
                to={`/app/plans/${plan.id}`}
                className="text-xs font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-4 py-2 hover:bg-rust-400 transition-colors font-bold flex items-center gap-2"
              >
                <Sparkles className="w-4 h-4" />
                View Plan
              </NavLink>
            )}
          </div>
        </div>
      </header>

      {/* Open Questions Alert */}
      {open_questions.length > 0 && (
        <div className="mb-8">
          <OpenQuestions questions={open_questions} />
        </div>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left: Sales Commitments */}
        <div className="hud-border p-6">
          <EditableList
            title="Sales Commitments"
            items={salesCommitments}
            onChange={setSalesCommitments}
            placeholder="No sales commitments recorded"
          />
        </div>

        {/* Right: Technical Context */}
        <div className="hud-border p-6">
          <EditableList
            title="Technical Context"
            items={technicalContext}
            onChange={setTechnicalContext}
            placeholder="No technical context recorded"
          />
        </div>
      </div>

      {/* Reality Check */}
      <div className="mt-8 hud-border p-6">
        <h3 className="text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-4">
          Reality Check
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="text-sm text-cream-400 block mb-2">Confidence Assessment</label>
            <textarea
              value={confidenceNote}
              onChange={(e) => setConfidenceNote(e.target.value)}
              placeholder="How confident are we in this deal?"
              className="w-full h-24 bg-charcoal-900 border border-charcoal-700 p-3 text-cream-200 text-sm placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none resize-none"
            />
          </div>
          <div>
            <label className="text-sm text-cream-400 block mb-2">Known Risks</label>
            <textarea
              value={risksNote}
              onChange={(e) => setRisksNote(e.target.value)}
              placeholder="What could derail this onboarding?"
              className="w-full h-24 bg-charcoal-900 border border-charcoal-700 p-3 text-cream-200 text-sm placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none resize-none"
            />
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="mt-8 flex flex-wrap gap-4 justify-end">
        {hasChanges && (
          <button
            onClick={handleSave}
            disabled={updateHandoff.isPending}
            className="text-xs font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors disabled:opacity-50"
          >
            {updateHandoff.isPending ? 'Saving...' : 'Save Changes'}
          </button>
        )}
        {(isDraft || needsCorrection) && (
          <button
            onClick={handleConfirm}
            disabled={confirmHandoff.isPending}
            className="text-xs font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold disabled:opacity-50 flex items-center gap-2"
          >
            <Check className="w-4 h-4" />
            {confirmHandoff.isPending ? 'Confirming...' : 'Confirm Handoff'}
          </button>
        )}
      </div>

      {/* Plan Preview (if exists) */}
      {plan && (
        <div className="mt-12 border-t border-charcoal-700 pt-8">
          <div className="flex items-center gap-3 mb-6">
            <Sparkles className="w-5 h-5 text-rust-500" />
            <h2 className="text-sm font-mono uppercase tracking-widest text-cream-200">
              Generated Plan
            </h2>
            <span className={cn(
              "text-xs font-mono uppercase tracking-widest px-2 py-0.5 border",
              plan.status === 'pending_approval'
                ? "border-rust-500 text-rust-500"
                : plan.status === 'approved'
                ? "border-emerald-500 text-emerald-500"
                : "border-charcoal-500 text-charcoal-500"
            )}>
              {plan.status.replace('_', ' ')}
            </span>
          </div>

          <div className="hud-border p-6 border-l-2 border-l-rust-500/30">
            {plan.headline && (
              <p className="text-cream-300 font-serif italic mb-4">{plan.headline}</p>
            )}
            <div className="flex items-center gap-6 text-sm text-charcoal-400">
              {plan.archetype_name && <span>{plan.archetype_name}</span>}
              {plan.duration_label && <span>{plan.duration_label}</span>}
              {plan.milestone_count && <span>{plan.milestone_count} milestones</span>}
            </div>
            <NavLink
              to={`/app/plans/${plan.id}`}
              className="inline-block mt-4 text-xs font-mono uppercase tracking-widest text-rust-500 hover:text-rust-400 transition-colors"
            >
              Review Full Plan →
            </NavLink>
          </div>
        </div>
      )}
    </div>
  );
}
