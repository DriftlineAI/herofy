// VoiceEditor — dual-pane editor for Core Voice and Scenario voices
// Left: Prose editor, Right: Live AI preview (static for MVP)

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useVoiceDoc, useUpdateHandbookDoc } from '@/lib/dataconnect-hooks';
import { Timestamp } from '@/components/ui/huds';
import { ArrowLeft, Save, TestTube } from 'lucide-react';
import { cn } from '@/lib/utils';

interface VoiceEditorProps {
  slug: string;
}

// Parse NEVER DRAFT blocks from body
function parseAvoidBlocks(body: string): string[] {
  const match = body.match(/⌐ NEVER[^⌐]+([\s\S]*?)(?=\n\n|$)/i);
  if (!match) return [];

  const content = match[0].replace(/⌐ NEVER[^\n]*\n?/i, '');
  return content
    .split(/[\n·-]/)
    .map(s => s.trim().replace(/^["']|["']$/g, ''))
    .filter(s => s.length > 0 && !s.startsWith('Any reference'));
}

// Extract pull quote from body - look for quotes that start a line/paragraph
function extractPullQuote(body: string): string | null {
  const match = body.match(/(?:^|\n)\s*"([^"]{20,})"/m);
  return match ? match[1] : null;
}

// Prose display component
function ProseDisplay({ body, title, kind }: { body: string; title: string; kind: string }) {
  const avoidItems = parseAvoidBlocks(body);
  const pullQuote = extractPullQuote(body);

  // Clean body of NEVER DRAFT blocks for display
  const cleanBody = body
    .replace(/⌐ NEVER[^⌐]+(?:[\s\S]*?)(?=\n\n|$)/gi, '')
    .trim();

  // Split into paragraphs
  const paragraphs = cleanBody
    .split(/\n\n+/)
    .filter(p => p.trim())
    .map(p => p.trim());

  return (
    <div className="flex-1 overflow-y-auto">
      <h1 className="font-display text-3xl text-fg-100 mb-2">{title}</h1>
      <div className="text-[10px] font-mono uppercase tracking-widest text-fg-400 mb-6">
        {kind === 'VOICE_CORE' ? 'CORE VOICE · INHERITED BY ALL SCENARIOS' :
         kind === 'VOICE_FOUNDATION' ? 'FOUNDATION · INFORMS ALL DRAFTS' :
         'SCENARIO · INHERITS FROM CORE VOICE'}
      </div>

      <div className="font-serif text-lg leading-relaxed text-fg-200 space-y-4">
        {paragraphs.map((p, i) => {
          // Check if this paragraph IS the pull quote (starts with quote mark)
          const isStandalonePullQuote = p.startsWith('"') && pullQuote && p.includes(pullQuote);
          if (isStandalonePullQuote) {
            return (
              <div key={i} className="border-l-2 border-accent pl-4 py-1 italic text-fg-100">
                {pullQuote}
              </div>
            );
          }

          // Format paragraph with emphasis
          const formatted = p
            .replace(/\*\*([^*]+)\*\*/g, '<strong class="text-fg-100 font-medium font-serif italic">$1</strong>')
            .replace(/\*([^*]+)\*/g, '<em class="text-accent">$1</em>');

          return (
            <p key={i} dangerouslySetInnerHTML={{ __html: formatted }} />
          );
        })}
      </div>

      {avoidItems.length > 0 && (
        <div className="mt-6 p-4 bg-signal-warn/5 border border-signal-warn/20 border-l-2 border-l-signal-warn">
          <span className="block text-[9px] font-mono uppercase tracking-widest text-signal-warn font-bold mb-2">
            ⌐ NEVER DRAFT
          </span>
          <p className="text-sm text-fg-200 leading-relaxed">
            {avoidItems.map((item, i) => (
              <span key={i}>
                {i > 0 && ' · '}
                <span className="px-1 bg-signal-warn/10 line-through decoration-signal-warn/60 text-fg-300 italic">
                  {item}
                </span>
              </span>
            ))}
          </p>
        </div>
      )}
    </div>
  );
}

// Prose edit component (textarea) - raw markdown editing
function ProseEdit({ body, onChange }: { body: string; onChange: (body: string) => void }) {
  return (
    <textarea
      value={body}
      onChange={(e) => onChange(e.target.value)}
      className="w-full h-full bg-transparent border-none outline-none resize-none font-mono text-sm text-fg-200"
      placeholder="Write your voice guidelines here..."
      style={{
        minHeight: 400,
        lineHeight: 1.7,
        whiteSpace: 'pre-wrap',
        wordWrap: 'break-word',
        overflowWrap: 'break-word',
      }}
    />
  );
}

// Sample reply preview (static for MVP)
function SampleReplies() {
  const samples = [
    {
      where: 'SIDEKICK · TIP (in the customer page)',
      content: (
        <>
          <strong className="text-fg-100 font-semibold">Tip:</strong> Last touch was a frustrated Slack from Sarah, 16 days ago — she'd asked for our SAML docs and we never sent them.
          <span className="block mt-1 font-serif italic text-fg-100">Suggest opening with the docs, not with the silence.</span>
        </>
      )
    },
    {
      where: 'EMAIL DRAFT (to Sarah Chen)',
      content: (
        <>
          Hi Sarah —
          <span className="block mt-1 font-serif italic text-fg-100">"I owe you the SAML docs from our last thread. Attached. The short version: you'll want to point your IdP at the URLs in section 2 and skip the test domain — that one's stale."</span>
          <span className="block mt-1 font-serif italic text-fg-100">"If you've already solved it another way, no need to reply. If not, I'm around Thursday."</span>
          — Scott
        </>
      )
    },
    {
      where: 'SIDEKICK · ASKING (HITL question)',
      content: (
        <>
          <strong className="text-fg-100 font-semibold">Question:</strong> Acme hasn't replied in 16 days and the last thread was about SAML.{' '}
          <em className="text-accent">Do you want to send the docs + a one-sentence opening, or wait until their renewal window?</em>
          <span className="block mt-1 font-serif italic text-fg-100">If "send now," I'll draft it for your review — no auto-send.</span>
        </>
      )
    }
  ];

  return (
    <div className="flex-1 overflow-y-auto space-y-5">
      {samples.map((sample, i) => (
        <div key={i} className="pb-5 border-b border-dashed border-rule last:border-b-0 last:pb-0">
          <div className="flex items-center gap-2 text-[9px] font-mono uppercase tracking-widest text-fg-400 mb-2">
            <span className="w-1 h-1 bg-accent rounded-full" />
            {sample.where}
          </div>
          <div className="p-4 border border-border border-l-2 border-l-accent bg-surface text-sm text-fg-200 leading-relaxed">
            {sample.content}
          </div>
        </div>
      ))}
    </div>
  );
}

// Loading skeleton
function EditorSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="flex items-center gap-4 mb-6">
        <div className="h-6 w-48 bg-surface-2 rounded" />
        <div className="ml-auto flex gap-2">
          <div className="h-8 w-24 bg-surface-2 rounded" />
          <div className="h-8 w-32 bg-surface-2 rounded" />
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="hud-pane">
          <div className="hud-pane__header">
            <div className="h-3 w-32 bg-surface-2 rounded" />
          </div>
          <div className="hud-pane__body">
            <div className="h-8 w-full bg-surface-2 rounded mb-4" />
            <div className="h-96 w-full bg-surface-2 rounded" />
          </div>
        </div>
        <div className="hud-pane">
          <div className="hud-pane__header">
            <div className="h-3 w-40 bg-surface-2 rounded" />
          </div>
          <div className="hud-pane__body">
            <div className="h-96 w-full bg-surface-2 rounded" />
          </div>
        </div>
      </div>
    </div>
  );
}

export function VoiceEditor({ slug }: VoiceEditorProps) {
  const { data, isLoading, error, refetch } = useVoiceDoc(slug);
  const updateDoc = useUpdateHandbookDoc();

  const [isEditing, setIsEditing] = useState(false);
  const [editedBody, setEditedBody] = useState('');
  const [editedTitle, setEditedTitle] = useState('');

  const doc = data?.doc;

  // Start editing
  const handleEdit = () => {
    if (doc) {
      setEditedBody(doc.body);
      setEditedTitle(doc.title);
      setIsEditing(true);
    }
  };

  // Save changes
  const handleSave = async () => {
    if (!doc) return;

    try {
      await updateDoc.mutateAsync({
        id: doc.id,
        body: editedBody,
        title: editedTitle || doc.title,
      });
      setIsEditing(false);
      refetch();
    } catch (err) {
      console.error('Failed to save:', err);
    }
  };

  // Cancel editing
  const handleCancel = () => {
    setIsEditing(false);
    setEditedBody('');
    setEditedTitle('');
  };

  if (isLoading) {
    return <EditorSkeleton />;
  }

  if (error || !doc) {
    return (
      <div className="text-center py-16">
        <h3 className="font-display text-2xl text-fg-100 mb-4">Voice document not found</h3>
        <p className="text-fg-400 mb-6">The voice document "{slug}" doesn't exist.</p>
        <Link to="/app/handbook" className="text-accent hover:text-accent-hover">
          ← Back to Handbook
        </Link>
      </div>
    );
  }

  const isCore = doc.kind === 'VOICE_CORE';
  const isScenario = doc.kind === 'VOICE_SCENARIO';

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <Link
          to="/app/handbook"
          className="text-fg-400 hover:text-fg-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <span className="font-mono text-xs text-fg-400 uppercase tracking-widest">
          Handbook / Voice /{' '}
          <span className="text-accent">
            {isCore ? 'Core voice' : doc.slug}
          </span>
        </span>
        <span className="ml-auto flex gap-2">
          {isEditing ? (
            <>
              <button
                onClick={handleCancel}
                className="px-4 py-2 text-xs font-mono uppercase tracking-widest border border-border text-fg-400 hover:border-fg-400 hover:text-fg-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={updateDoc.isPending}
                className={cn(
                  "px-4 py-2 text-xs font-mono uppercase tracking-widest flex items-center gap-2",
                  "bg-accent text-page hover:bg-accent-hover transition-colors",
                  updateDoc.isPending && "opacity-50 cursor-not-allowed"
                )}
              >
                <Save className="w-3 h-3" />
                {updateDoc.isPending ? 'Saving...' : 'Save'}
              </button>
            </>
          ) : (
            <>
              <button className="px-4 py-2 text-xs font-mono uppercase tracking-widest border border-border text-fg-400 hover:border-fg-400 hover:text-fg-200 transition-colors flex items-center gap-2">
                <TestTube className="w-3 h-3" />
                Test on a draft
              </button>
              <button
                onClick={handleEdit}
                className="px-4 py-2 text-xs font-mono uppercase tracking-widest bg-accent text-page hover:bg-accent-hover transition-colors"
              >
                Edit
              </button>
            </>
          )}
        </span>
      </div>

      {/* Scenario metadata (if scenario) */}
      {isScenario && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
          <div className="hud-pane">
            <div className="p-4">
              <div className="text-[9px] font-mono uppercase tracking-widest text-fg-400 mb-1">When this fires</div>
              <div className="font-serif italic text-fg-100">
                {doc.trigger_expr || '(No trigger defined)'}
              </div>
            </div>
          </div>
          <div className="hud-pane">
            <div className="p-4">
              <div className="text-[9px] font-mono uppercase tracking-widest text-fg-400 mb-1">Inherits from</div>
              <div className="font-serif italic text-accent">
                {doc.inherits_from ? `← ${doc.inherits_from.title}` : '← Core voice'}
              </div>
            </div>
          </div>
          <div className="hud-pane">
            <div className="p-4">
              <div className="text-[9px] font-mono uppercase tracking-widest text-fg-400 mb-1">Affects</div>
              <div className="font-serif italic text-fg-100">
                {doc.affects_surfaces
                  ? JSON.parse(doc.affects_surfaces).join(' · ')
                  : 'All surfaces'}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Dual-pane editor */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" style={{ minHeight: 'calc(100vh - 280px)' }}>
        {/* Left column: Prose */}
        <div className="hud-pane flex flex-col">
          <div className="hud-pane__header">
            <span className="hud-pane__label">
              {isEditing ? 'EDITING · YOUR VOICE' : 'PROSE · YOUR VOICE'}
            </span>
            <span className="grow" />
            <span className="hud-pane__ref">
              {isEditing ? 'Editing...' : <Timestamp time={doc.updated_at} />}
            </span>
          </div>

          <div className="hud-pane__body flex-1 flex flex-col overflow-hidden">
            {isEditing ? (
              <div className="flex-1 overflow-auto">
                {isCore && (
                  <textarea
                    value={editedTitle}
                    onChange={(e) => setEditedTitle(e.target.value)}
                    className="w-full bg-transparent border-none border-b border-border outline-none font-display text-3xl text-fg-100 mb-4 pb-2 resize-none"
                    placeholder="Voice title..."
                    rows={2}
                    style={{ lineHeight: 1.2, overflow: 'hidden' }}
                  />
                )}
                <ProseEdit body={editedBody} onChange={setEditedBody} />
              </div>
            ) : (
              <ProseDisplay body={doc.body} title={doc.title} kind={doc.kind} />
            )}
          </div>
        </div>

        {/* Right column: Preview */}
        <div className="hud-pane flex flex-col">
          <div className="hud-pane__header">
            <span className="hud-pane__label">LIVE PREVIEW · YOUR VOICE IN PRACTICE</span>
            <span className="grow" />
            <span className="hud-pane__ref">Static preview</span>
          </div>

          <div className="hud-pane__body flex-1 flex flex-col overflow-hidden">
            <p className="font-serif italic text-sm text-fg-400 mb-4 pb-4 border-b border-dashed border-rule leading-relaxed">
              The same situation — Acme Corp went quiet 16 days ago — drafted three ways.
              Each one obeys the prose at left.
            </p>

            <SampleReplies />
          </div>
        </div>
      </div>
    </div>
  );
}

export default VoiceEditor;
