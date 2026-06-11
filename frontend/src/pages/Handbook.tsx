import React, { useState } from 'react';
import { NavLink, useParams, useNavigate } from 'react-router-dom';
import { RefCode, Timestamp, Sidekick } from '@/components/ui/huds';
import { cn } from '@/lib/utils';
import {
  useHandbook,
  useHandbookDoc,
  useUpdateHandbookDoc,
  usePlaybooks,
  useCreatePlaybookHook,
  useUpdatePlaybook,
  useDeletePlaybook,
  useCreatePlaybookMilestoneHook,
  useUpdatePlaybookMilestone,
  useDeletePlaybookMilestone,
  useVoiceDocs,
} from '@/lib/dataconnect-hooks';
import { VoiceIndex, VoiceEditor } from '@/components/voice';
import { OwnerSide } from '@/dataconnect-generated';
import type { HandbookDoc } from '@/lib/api';
import {
  Book,
  Plus,
  PlayCircle,
  ChevronRight,
  Trash2,
  Edit3,
  X,
  GripVertical,
  Users,
  Building,
  Clock,
  Mic,
} from 'lucide-react';

// Types for playbooks
interface PlaybookMilestone {
  id: string;
  title: string;
  owner_side: 'us' | 'customer' | 'joint';
  duration_days: number | null;
  description: string | null;
  sort_order: number;
}

interface Playbook {
  id: string;
  name: string;
  archetype: string | null;
  fit_note: string | null;
  drawn_from_count: number;
  milestones: PlaybookMilestone[];
}

// Blast radius indicator colors
function getBlastRadiusColor(blastRadius: HandbookDoc['blast_radius']): string {
  switch (blastRadius) {
    case 'high': return 'text-signal-bad border-signal-bad';
    case 'medium': return 'text-signal-warn border-signal-warn';
    case 'low': return 'text-signal-ok border-signal-ok';
    default: return 'text-fg-400 border-fg-400';
  }
}

// Owner side badge
function OwnerBadge({ side }: { side: 'us' | 'customer' | 'joint' }) {
  const config = {
    us: { label: 'Us', color: 'bg-accent/20 text-accent border-accent/30' },
    customer: { label: 'Customer', color: 'bg-signal-warn/20 text-signal-warn border-signal-warn/30' },
    joint: { label: 'Joint', color: 'bg-signal-ok/20 text-signal-ok border-signal-ok/30' },
  };
  const { label, color } = config[side];
  return (
    <span className={cn('text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 border', color)}>
      {label}
    </span>
  );
}

// Archetype badge
function ArchetypeBadge({ archetype }: { archetype: string | null }) {
  if (!archetype) return null;
  const isOnboarding = archetype.toLowerCase().includes('onboarding');
  return (
    <span className={cn(
      'text-[9px] font-mono uppercase tracking-widest px-2 py-0.5 border flex items-center gap-1',
      isOnboarding ? 'bg-accent/20 text-accent border-accent/30' : 'bg-fg-300/20 text-fg-300 border-fg-300/30'
    )}>
      {isOnboarding ? <Building className="w-3 h-3" /> : <Users className="w-3 h-3" />}
      {archetype}
    </span>
  );
}

// Loading skeleton
function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-6">
      {[1, 2, 3].map((i) => (
        <div key={i} className="p-6 hud-pane">
          <div className="flex items-center gap-4 mb-4">
            <div className="h-4 w-16 bg-border rounded" />
            <div className="h-[1px] flex-1 bg-border/50" />
          </div>
          <div className="h-8 w-48 bg-border rounded mb-3" />
          <div className="h-4 w-full bg-border/50 rounded" />
        </div>
      ))}
    </div>
  );
}

// Document card component
function DocCard({ doc, isSelected }: { doc: HandbookDoc; isSelected: boolean }) {
  return (
    <NavLink
      to={`/app/handbook/doc/${doc.slug}`}
      className={cn(
        "block p-6 hud-pane group transition-all",
        isSelected ? "border-l-2 border-l-accent hud-accent" : "hover:border-border-strong"
      )}
    >
      <div className="flex items-center gap-4 mb-4">
        <RefCode>{doc.slug.toUpperCase()}</RefCode>
        <div className="h-[1px] flex-1 bg-border/50" />
        <span className={cn(
          "text-[9px] font-mono uppercase tracking-widest border px-2 py-0.5",
          getBlastRadiusColor(doc.blast_radius)
        )}>
          {doc.blast_radius}
        </span>
      </div>
      <h3 className={cn(
        "font-serif text-2xl mb-3 transition-colors",
        isSelected ? "text-accent" : "text-fg-100 group-hover:text-accent-hover"
      )}>
        {doc.title}
      </h3>
      {doc.description && (
        <p className="text-fg-300 font-sans leading-relaxed text-sm">{doc.description}</p>
      )}
    </NavLink>
  );
}

// Playbook card component
function PlaybookCard({ playbook, isSelected, onClick }: {
  playbook: Playbook;
  isSelected: boolean;
  onClick: () => void;
}) {
  const totalDays = playbook.milestones.reduce((sum, m) => sum + (m.duration_days || 0), 0);

  return (
    <button
      onClick={onClick}
      className={cn(
        "block w-full text-left p-6 hud-pane group transition-all",
        isSelected ? "border-l-2 border-l-accent hud-accent" : "hover:border-border-strong"
      )}
    >
      <div className="flex items-center gap-3 mb-4">
        <PlayCircle className={cn(
          "w-5 h-5 transition-colors",
          isSelected ? "text-accent" : "text-fg-400 group-hover:text-accent-hover"
        )} />
        <div className="h-[1px] flex-1 bg-border/50" />
        <ArchetypeBadge archetype={playbook.archetype} />
      </div>
      <h3 className={cn(
        "font-serif text-xl mb-2 transition-colors",
        isSelected ? "text-accent" : "text-fg-100 group-hover:text-accent-hover"
      )}>
        {playbook.name}
      </h3>
      {playbook.fit_note && (
        <p className="text-fg-300 text-sm mb-3 line-clamp-2">{playbook.fit_note}</p>
      )}
      <div className="flex items-center gap-4 text-xs text-fg-400">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {totalDays} days
        </span>
        <span>{playbook.milestones.length} milestones</span>
        {playbook.drawn_from_count > 0 && (
          <span className="text-signal-ok">Used {playbook.drawn_from_count}x</span>
        )}
      </div>
    </button>
  );
}

// Playbook viewer/editor
function PlaybookViewer({
  playbook,
  onClose,
  onUpdate,
}: {
  playbook: Playbook;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedName, setEditedName] = useState(playbook.name);
  const [editedArchetype, setEditedArchetype] = useState(playbook.archetype || 'Onboarding');
  const [editedFitNote, setEditedFitNote] = useState(playbook.fit_note || '');

  const updatePlaybook = useUpdatePlaybook();
  const deletePlaybook = useDeletePlaybook();
  const createMilestone = useCreatePlaybookMilestoneHook();
  const updateMilestone = useUpdatePlaybookMilestone();
  const deleteMilestone = useDeletePlaybookMilestone();

  const [newMilestoneTitle, setNewMilestoneTitle] = useState('');
  const [showAddMilestone, setShowAddMilestone] = useState(false);

  const handleSave = async () => {
    await updatePlaybook.mutateAsync({
      id: playbook.id,
      name: editedName,
      archetype: editedArchetype,
      fitNote: editedFitNote,
    });
    setIsEditing(false);
    onUpdate();
  };

  const handleDelete = async () => {
    if (confirm(`Delete playbook "${playbook.name}"? This cannot be undone.`)) {
      await deletePlaybook.mutateAsync({ id: playbook.id });
      onClose();
      onUpdate();
    }
  };

  const handleAddMilestone = async () => {
    if (!newMilestoneTitle.trim()) return;
    await createMilestone.mutateAsync({
      playbookId: playbook.id,
      title: newMilestoneTitle,
      ownerSide: OwnerSide.joint,
      durationDays: 7,
      sortOrder: playbook.milestones.length + 1,
    });
    setNewMilestoneTitle('');
    setShowAddMilestone(false);
    onUpdate();
  };

  const handleDeleteMilestone = async (milestoneId: string) => {
    await deleteMilestone.mutateAsync({ id: milestoneId });
    onUpdate();
  };

  const totalDays = playbook.milestones.reduce((sum, m) => sum + (m.duration_days || 0), 0);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex-1">
          {isEditing ? (
            <div className="space-y-4">
              <input
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                className="w-full bg-page border border-border px-4 py-2 text-fg-100 font-serif text-2xl focus:border-accent-hover focus:outline-none"
                placeholder="Playbook name"
              />
              <div className="flex gap-4">
                <select
                  value={editedArchetype}
                  onChange={(e) => setEditedArchetype(e.target.value)}
                  className="bg-page border border-border px-4 py-2 text-fg-200 text-sm focus:border-accent-hover focus:outline-none"
                >
                  <option value="Onboarding">Onboarding</option>
                  <option value="CS Play">CS Play</option>
                </select>
              </div>
              <textarea
                value={editedFitNote}
                onChange={(e) => setEditedFitNote(e.target.value)}
                className="w-full bg-page border border-border px-4 py-2 text-fg-300 text-sm focus:border-accent-hover focus:outline-none resize-none"
                rows={2}
                placeholder="When to use this playbook..."
              />
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3 mb-2">
                <ArchetypeBadge archetype={playbook.archetype} />
                <span className="text-xs text-fg-400">•</span>
                <span className="text-xs text-fg-400">{totalDays} days total</span>
              </div>
              <h2 className="font-serif text-4xl text-fg-100 mb-2">{playbook.name}</h2>
              {playbook.fit_note && (
                <p className="text-fg-300 italic">{playbook.fit_note}</p>
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isEditing ? (
            <>
              <button
                onClick={handleSave}
                disabled={updatePlaybook.isPending}
                className="text-xs font-mono uppercase tracking-widest bg-accent text-page px-4 py-2 hover:bg-accent-hover transition-colors disabled:opacity-50"
              >
                {updatePlaybook.isPending ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={() => setIsEditing(false)}
                className="text-xs font-mono uppercase tracking-widest border border-border-strong text-fg-400 px-4 py-2 hover:border-fg-300 hover:text-fg-200 transition-colors"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setIsEditing(true)}
                className="p-2 text-fg-400 hover:text-fg-200 transition-colors"
                title="Edit"
              >
                <Edit3 className="w-4 h-4" />
              </button>
              <button
                onClick={handleDelete}
                className="p-2 text-fg-400 hover:text-accent-hover transition-colors"
                title="Delete"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Milestones */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs font-mono uppercase tracking-widest text-fg-400">
            Milestones ({playbook.milestones.length})
          </h3>
          <button
            onClick={() => setShowAddMilestone(true)}
            className="text-xs font-mono uppercase tracking-widest text-accent hover:text-accent-hover transition-colors flex items-center gap-1"
          >
            <Plus className="w-3 h-3" />
            Add
          </button>
        </div>

        <div className="space-y-2">
          {playbook.milestones
            .sort((a, b) => a.sort_order - b.sort_order)
            .map((milestone, index) => {
              const cumulativeDays = playbook.milestones
                .slice(0, index + 1)
                .reduce((sum, m) => sum + (m.duration_days || 0), 0);

              return (
                <div
                  key={milestone.id}
                  className="group bg-surface-2/50 border border-border p-4 flex items-start gap-4"
                >
                  <div className="text-fg-400 pt-1">
                    <GripVertical className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <span className="text-fg-100 font-medium">{milestone.title}</span>
                      <OwnerBadge side={milestone.owner_side} />
                    </div>
                    {milestone.description && (
                      <p className="text-fg-300 text-sm">{milestone.description}</p>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-xs font-mono text-fg-400">
                      Day {cumulativeDays - (milestone.duration_days || 0) + 1}–{cumulativeDays}
                    </div>
                    <div className="text-xs text-fg-400">
                      {milestone.duration_days || 0} days
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteMilestone(milestone.id)}
                    className="p-1 text-fg-400 hover:text-accent-hover transition-colors opacity-0 group-hover:opacity-100"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              );
            })}

          {/* Add milestone form */}
          {showAddMilestone && (
            <div className="bg-surface-2 border border-accent/50 p-4 flex items-center gap-4">
              <input
                type="text"
                value={newMilestoneTitle}
                onChange={(e) => setNewMilestoneTitle(e.target.value)}
                placeholder="Milestone title..."
                className="flex-1 bg-page border border-border px-3 py-2 text-fg-200 text-sm focus:border-accent-hover focus:outline-none"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleAddMilestone();
                  if (e.key === 'Escape') setShowAddMilestone(false);
                }}
              />
              <button
                onClick={handleAddMilestone}
                disabled={!newMilestoneTitle.trim() || createMilestone.isPending}
                className="text-xs font-mono uppercase tracking-widest bg-accent text-page px-4 py-2 hover:bg-accent-hover transition-colors disabled:opacity-50"
              >
                Add
              </button>
              <button
                onClick={() => setShowAddMilestone(false)}
                className="p-2 text-fg-400 hover:text-fg-200 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {playbook.milestones.length === 0 && !showAddMilestone && (
            <div className="border border-dashed border-border p-8 text-center">
              <p className="text-fg-400 text-sm mb-4">No milestones yet</p>
              <button
                onClick={() => setShowAddMilestone(true)}
                className="text-xs font-mono uppercase tracking-widest text-accent hover:text-accent-hover transition-colors"
              >
                Add first milestone
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Usage stats */}
      {playbook.drawn_from_count > 0 && (
        <div className="border-t border-border pt-6">
          <p className="text-xs text-fg-400">
            This playbook has been used to create plans for <span className="text-signal-ok">{playbook.drawn_from_count}</span> customers.
          </p>
        </div>
      )}
    </div>
  );
}

// Create playbook modal
function CreatePlaybookModal({
  onClose,
  onCreate
}: {
  onClose: () => void;
  onCreate: () => void;
}) {
  const [name, setName] = useState('');
  const [archetype, setArchetype] = useState('Onboarding');
  const [fitNote, setFitNote] = useState('');

  const createPlaybook = useCreatePlaybookHook();

  const handleCreate = async () => {
    if (!name.trim()) return;
    await createPlaybook.mutateAsync({
      name,
      archetype,
      fitNote: fitNote || undefined,
    });
    onCreate();
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-page/80 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-2 border border-border w-full max-w-lg">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-serif text-fg-100">New Playbook</h2>
          <button onClick={onClose} className="p-1 text-fg-400 hover:text-fg-200">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-mono uppercase tracking-widest text-fg-400 mb-2">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-page border border-border px-4 py-3 text-fg-200 focus:border-accent-hover focus:outline-none"
              placeholder="e.g., Enterprise Onboarding"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-widest text-fg-400 mb-2">
              Type
            </label>
            <select
              value={archetype}
              onChange={(e) => setArchetype(e.target.value)}
              className="w-full bg-page border border-border px-4 py-3 text-fg-200 focus:border-accent-hover focus:outline-none"
            >
              <option value="Onboarding">Onboarding Playbook</option>
              <option value="CS Play">CS Play (Issue Resolution)</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-widest text-fg-400 mb-2">
              When to use (optional)
            </label>
            <textarea
              value={fitNote}
              onChange={(e) => setFitNote(e.target.value)}
              className="w-full bg-page border border-border px-4 py-3 text-fg-200 focus:border-accent-hover focus:outline-none resize-none"
              rows={3}
              placeholder="Describe when Sidekick should suggest this playbook..."
            />
          </div>
        </div>
        <div className="flex justify-end gap-4 p-4 border-t border-border">
          <button
            onClick={onClose}
            className="text-xs font-mono uppercase tracking-widest border border-border-strong text-fg-400 px-6 py-2 hover:border-fg-300 hover:text-fg-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={!name.trim() || createPlaybook.isPending}
            className="text-xs font-mono uppercase tracking-widest bg-accent text-page px-6 py-2 hover:bg-accent-hover transition-colors disabled:opacity-50 font-bold"
          >
            {createPlaybook.isPending ? 'Creating...' : 'Create Playbook'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Document viewer/editor
function DocViewer({ slug }: { slug: string }) {
  const { data, isLoading, error } = useHandbookDoc(slug);
  const updateDoc = useUpdateHandbookDoc();
  const [isEditing, setIsEditing] = useState(false);
  const [editedBody, setEditedBody] = useState('');

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-8 w-64 bg-border rounded" />
        <div className="h-4 w-full bg-border/50 rounded" />
        <div className="h-64 w-full bg-surface-2 rounded" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="hud-pane p-8 border-l-4 border-l-accent">
        <div className="text-[10px] uppercase tracking-[0.3em] text-accent font-bold mb-4">
          Document Not Found
        </div>
        <p className="text-fg-200">Could not load this document.</p>
      </div>
    );
  }

  const { doc, versions } = data;

  const handleEdit = () => {
    setEditedBody(doc.body);
    setIsEditing(true);
  };

  const handleSave = () => {
    updateDoc.mutate(
      { id: doc.id, body: editedBody },
      {
        onSuccess: () => setIsEditing(false),
      }
    );
  };

  const handleCancel = () => {
    setIsEditing(false);
    setEditedBody('');
  };

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-4 mb-2">
            <RefCode>{doc.slug.toUpperCase()}</RefCode>
            <span className={cn(
              "text-[9px] font-mono uppercase tracking-widest border px-2 py-0.5",
              getBlastRadiusColor(doc.blast_radius)
            )}>
              Blast Radius: {doc.blast_radius}
            </span>
          </div>
          <h2 className="font-serif text-4xl text-fg-100 mb-2">{doc.title}</h2>
          {doc.description && (
            <p className="text-fg-300 italic">{doc.description}</p>
          )}
        </div>
        {!isEditing && (
          <button
            onClick={handleEdit}
            className="text-xs font-mono uppercase tracking-widest border border-border-strong text-fg-400 px-4 py-2 hover:border-fg-300 hover:text-fg-200 transition-colors"
          >
            Edit
          </button>
        )}
      </div>

      {isEditing ? (
        <div className="space-y-4">
          <textarea
            value={editedBody}
            onChange={(e) => setEditedBody(e.target.value)}
            className="w-full h-96 bg-page border border-border p-4 text-fg-200 font-mono text-sm leading-relaxed focus:border-accent-hover focus:outline-none resize-none"
            placeholder="Document content..."
          />
          <div className="flex gap-4">
            <button
              onClick={handleSave}
              disabled={updateDoc.isPending}
              className="text-xs font-mono uppercase tracking-widest bg-accent text-page px-6 py-2 hover:bg-accent-hover transition-colors disabled:opacity-50"
            >
              {updateDoc.isPending ? 'Saving...' : 'Save Changes'}
            </button>
            <button
              onClick={handleCancel}
              className="text-xs font-mono uppercase tracking-widest border border-border-strong text-fg-400 px-6 py-2 hover:border-fg-300 hover:text-fg-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="prose prose-invert max-w-none">
          <div className="bg-page border border-border p-6 font-mono text-sm text-fg-300 leading-relaxed whitespace-pre-wrap">
            {doc.body}
          </div>
        </div>
      )}

      {versions.length > 0 && (
        <div className="border-t border-border pt-6">
          <h3 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4">
            Version History ({versions.length})
          </h3>
          <div className="space-y-2">
            {versions.slice(0, 5).map((version) => (
              <div key={version.id} className="flex items-center gap-4 text-sm">
                <Timestamp time={new Date(version.edited_at).toLocaleDateString()} />
                <span className="text-fg-400">•</span>
                <span className="text-fg-300 font-mono text-xs">
                  {version.edited_by_user_id || 'System'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Tab type
type TabId = 'voice' | 'playbooks';

export default function Handbook() {
  const { slug, '*': splat } = useParams();
  const navigate = useNavigate();

  // Determine active tab and selected item from URL
  // URL patterns: /app/handbook, /app/handbook/voice/:slug, /app/handbook/playbooks
  const isVoiceRoute = splat?.startsWith('voice/');
  const isPlaybooksRoute = splat === 'playbooks' || splat?.startsWith('playbooks');
  const voiceSlug = isVoiceRoute ? splat.replace('voice/', '') : null;

  // Sync tab state with URL
  const [activeTab, setActiveTab] = useState<TabId>(isPlaybooksRoute ? 'playbooks' : 'voice');
  const [selectedPlaybook, setSelectedPlaybook] = useState<Playbook | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Keep activeTab in sync with URL changes
  React.useEffect(() => {
    if (isPlaybooksRoute && activeTab !== 'playbooks') {
      setActiveTab('playbooks');
    } else if (!isPlaybooksRoute && !isVoiceRoute && activeTab !== 'voice') {
      setActiveTab('voice');
    } else if (isVoiceRoute && activeTab !== 'voice') {
      setActiveTab('voice');
    }
  }, [isPlaybooksRoute, isVoiceRoute, activeTab]);

  const { data: handbookData, isLoading: handbookLoading, error: handbookError, refetch: refetchHandbook } = useHandbook();
  const { data: playbooksData, isLoading: playbooksLoading, refetch: refetchPlaybooks } = usePlaybooks();
  const { data: voiceData, isLoading: voiceLoading, error: voiceError } = useVoiceDocs();

  // Handle playbook selection
  const handleSelectPlaybook = (playbook: Playbook) => {
    setSelectedPlaybook(playbook);
  };

  const handleClosePlaybook = () => {
    setSelectedPlaybook(null);
  };

  if (handbookError) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="hud-pane p-8 border-l-4 border-l-accent">
          <div className="text-[10px] uppercase tracking-[0.3em] text-accent font-bold mb-4">
            Connection Error
          </div>
          <p className="text-fg-200 mb-4">{(handbookError as Error).message}</p>
          <button
            onClick={() => refetchHandbook()}
            className="text-xs font-mono uppercase tracking-widest border border-accent text-accent px-4 py-2 hover:bg-accent hover:text-page transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const voiceCount = voiceData?.count || 0;
  const playbookCount = playbooksData?.count || 0;

  return (
    <div className="min-h-screen">
      <header className="mb-8 border-b border-border pb-6">
        <h1 className="text-xl tracking-widest text-fg-200 uppercase mb-2">How This Product Thinks</h1>
        <p className="text-fg-300 font-serif text-lg italic">
          Rules and playbooks that guide Sidekick's decisions.
        </p>
      </header>

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-8 border-b border-border">
        <button
          onClick={() => {
            setActiveTab('voice');
            setSelectedPlaybook(null);
            navigate('/app/handbook');
          }}
          className={cn(
            "px-6 py-3 text-xs font-mono uppercase tracking-widest transition-colors border-b-2 -mb-[2px] inline-flex items-center",
            activeTab === 'voice'
              ? "text-fg-100 border-accent font-bold"
              : "text-fg-400 border-transparent hover:text-fg-200"
          )}
        >
          <Mic className="w-4 h-4 mr-2 -mt-0.5" />
          Voice · {voiceCount}
        </button>
        <button
          onClick={() => {
            setActiveTab('playbooks');
            navigate('/app/handbook/playbooks');
          }}
          className={cn(
            "px-6 py-3 text-xs font-mono uppercase tracking-widest transition-colors border-b-2 -mb-[2px] inline-flex items-center",
            activeTab === 'playbooks'
              ? "text-fg-100 border-accent font-bold"
              : "text-fg-400 border-transparent hover:text-fg-200"
          )}
        >
          <PlayCircle className="w-4 h-4 mr-2 -mt-0.5" />
          Playbooks · {playbookCount}
        </button>
      </div>

      {/* Voice tab - full width with editor */}
      {activeTab === 'voice' && (
        <div className="w-full">
          {voiceSlug ? (
            <VoiceEditor slug={voiceSlug} />
          ) : (
            <VoiceIndex />
          )}
        </div>
      )}

      {/* Playbooks tab - grid layout */}
      {activeTab === 'playbooks' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left column - List */}
          <div className="lg:col-span-4 space-y-4">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xs font-mono uppercase tracking-widest text-fg-400">
                Playbooks
              </h2>
              <button
                onClick={() => setShowCreateModal(true)}
                className="text-xs font-mono uppercase tracking-widest text-accent hover:text-accent-hover transition-colors flex items-center gap-1"
              >
                <Plus className="w-3 h-3" />
                New
              </button>
            </div>
            {playbooksLoading ? (
              <LoadingSkeleton />
            ) : (
              <div className="space-y-4">
                {playbooksData?.playbooks.map((playbook) => (
                  <PlaybookCard
                    key={playbook.id}
                    playbook={playbook}
                    isSelected={selectedPlaybook?.id === playbook.id}
                    onClick={() => handleSelectPlaybook(playbook)}
                  />
                ))}
                {(!playbooksData?.playbooks || playbooksData.playbooks.length === 0) && (
                  <div className="flex flex-col items-center justify-center py-12">
                    <div className="w-16 h-16 rounded-full bg-surface-2 flex items-center justify-center mb-4">
                      <PlayCircle className="w-8 h-8 text-fg-400" />
                    </div>
                    <h3 className="font-serif text-lg text-fg-100 mb-2">No playbooks yet</h3>
                    <p className="text-fg-400 text-center text-sm mb-6">
                      Playbooks are templates for onboarding plans and CS workflows.
                    </p>
                    <button
                      onClick={() => setShowCreateModal(true)}
                      className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-page px-4 py-2 font-mono text-xs uppercase tracking-widest font-bold transition-colors"
                    >
                      <Plus className="w-3 h-3" />
                      Create Playbook
                    </button>
                    <Sidekick className="mt-6">
                      <strong>Tip:</strong> Playbooks are templates I use when generating onboarding plans. Create one for each customer segment.
                    </Sidekick>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right column - Viewer */}
          <div className="lg:col-span-8">
            {selectedPlaybook ? (
              <PlaybookViewer
                playbook={selectedPlaybook}
                onClose={handleClosePlaybook}
                onUpdate={() => {
                  refetchPlaybooks();
                  // Re-fetch the selected playbook data
                  const updated = playbooksData?.playbooks.find(p => p.id === selectedPlaybook.id);
                  if (updated) setSelectedPlaybook(updated);
                }}
              />
            ) : (
              <div className="hud-pane p-12 text-center">
                <div className="text-fg-400 font-mono text-sm uppercase tracking-widest mb-4">
                  Select a playbook
                </div>
                <p className="text-fg-300 font-serif italic">
                  Choose a playbook from the list to view or edit its milestones.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create playbook modal */}
      {showCreateModal && (
        <CreatePlaybookModal
          onClose={() => setShowCreateModal(false)}
          onCreate={() => refetchPlaybooks()}
        />
      )}
    </div>
  );
}
