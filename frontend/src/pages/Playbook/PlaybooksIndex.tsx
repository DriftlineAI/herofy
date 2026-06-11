import React, { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { PlaybookCard, PlaybookFilter, SectionOpener } from './components';
import type { PlaybookScenarioFilter } from './components/PlaybookFilter';
import { usePlaybooks } from '@/lib/dataconnect-hooks';

/**
 * PlaybooksIndex - Main catalog with scenario filtering
 */
export function PlaybooksIndex() {
  const [filter, setFilter] = useState<PlaybookScenarioFilter>('all');
  const { data, isLoading } = usePlaybooks();

  const playbooks = data?.playbooks ?? [];

  const filteredPlaybooks = useMemo(() => {
    if (filter === 'all') return playbooks;
    return playbooks.filter((p) => p.scenario === filter);
  }, [playbooks, filter]);

  const counts = useMemo(() => ({
    all: playbooks.length,
    onboarding: playbooks.filter((p) => p.scenario === 'onboarding').length,
    renewal: playbooks.filter((p) => p.scenario === 'renewal').length,
    risk: playbooks.filter((p) => p.scenario === 'risk').length,
  }), [playbooks]);

  return (
    <div className="max-w-7xl mx-auto px-8 py-12">
      <div className="font-mono text-xs uppercase tracking-wider text-app-fg-400 flex items-center gap-2 mb-8">
        <Link to="/app/handbook" className="hover:text-rust-500 transition-colors">
          Handbook
        </Link>
        <span>/</span>
        <span className="text-app-fg-200">Playbooks</span>
      </div>

      <div className="pb-index">
        <div>
          <PlaybookFilter
            active={filter}
            onChange={setFilter}
            counts={counts}
          />

          {isLoading ? (
            <div className="text-center py-16 text-app-fg-400">
              <p className="font-mono text-sm uppercase tracking-wider">Loading playbooks…</p>
            </div>
          ) : (
            <div className="space-y-3.5">
              {filteredPlaybooks.map((playbook) => (
                <PlaybookCard
                  key={playbook.id}
                  playbook={{
                    id: playbook.id,
                    scenario: playbook.scenario as 'onboarding' | 'renewal' | 'risk',
                    name: playbook.name,
                    fitNote: playbook.fit_note,
                    milestoneCount: playbook.milestones.length,
                  }}
                />
              ))}

              {filteredPlaybooks.length === 0 && (
                <div className="text-center py-16 text-app-fg-400">
                  <p className="font-serif italic text-lg mb-2">No playbooks found</p>
                  <p className="text-sm">Try a different filter or create a new playbook</p>
                </div>
              )}
            </div>
          )}
        </div>

        <aside className="pb-aside">
          <h3 className="pb-aside__title">+ Start a new playbook</h3>

          <Link to="/app/handbook/playbooks/new/describe" className="pb-aside__opt">
            <span className="label">Describe to Sidekick</span>
            <span className="sub">
              Write a paragraph. Sidekick scaffolds structure as you go.
            </span>
          </Link>

          <Link to="/app/handbook/playbooks/new" className="pb-aside__opt">
            <span className="label">Start from the catalog</span>
            <span className="sub">
              Six common motions, specialized by your team. Fork one and roll.
            </span>
          </Link>

          <Link to="/app/handbook/playbooks/new/import" className="pb-aside__opt">
            <span className="label">Import from Notion</span>
            <span className="sub">
              Drop in an existing doc. Sidekick reads it for outcomes and mandates.
            </span>
          </Link>
        </aside>
      </div>
    </div>
  );
}
