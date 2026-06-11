import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { SectionOpener, ImportProgress } from './components';
import type { ProgressStep } from './components';
import { Upload } from 'lucide-react';

/**
 * PlaybookImport (Artboard 5) - Import from Notion
 * Lets a team bring in an existing onboarding doc rather than start from scratch
 */
export function PlaybookImport() {
  const navigate = useNavigate();
  const [importing, setImporting] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [notionUrl, setNotionUrl] = useState('');

  const importSteps: ProgressStep[] = [
    { label: 'Fetching Notion page "Enterprise Onboarding Playbook"', state: 'pending' },
    { label: 'Parsing markdown structure', state: 'pending' },
    { label: 'Extracting outcomes and mandates', state: 'pending' },
    { label: 'Identifying variables', state: 'pending' },
    { label: 'Detecting guardrails', state: 'pending' },
    { label: 'Building playbook scaffold', state: 'pending' },
  ];

  const [steps, setSteps] = useState(importSteps);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      startImport(files[0].name);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      startImport(files[0].name);
    }
  };

  const handlePaste = () => {
    if (!notionUrl.trim()) return;
    startImport('Enterprise Onboarding Playbook');
  };

  const startImport = async (filename: string) => {
    setImporting(true);
    const updatedSteps = [...steps];

    // Simulate progress through steps
    for (let i = 0; i < steps.length; i++) {
      setCurrentStep(i + 1);

      // Update current step to 'current'
      updatedSteps[i] = { ...updatedSteps[i], state: 'current' };
      setSteps([...updatedSteps]);

      await new Promise((resolve) => setTimeout(resolve, 800 + Math.random() * 400));

      // Update to 'done'
      updatedSteps[i] = { ...updatedSteps[i], state: 'done' };
      setSteps([...updatedSteps]);
    }

    // Navigate to editor with extracted data
    setTimeout(() => {
      navigate('/app/handbook/playbooks/new/editor', {
        state: { imported: true, filename },
      });
    }, 800);
  };

  return (
    <div className="max-w-[720px] mx-auto px-8 py-12">
      {/* Breadcrumb header */}
      <div className="font-mono text-xs uppercase tracking-wider text-app-fg-400 flex items-center gap-2 mb-8">
        <Link to="/app/handbook" className="hover:text-rust-500 transition-colors">
          Handbook
        </Link>
        <span>/</span>
        <Link to="/app/handbook/playbooks" className="hover:text-rust-500 transition-colors">
          Playbooks
        </Link>
        <span>/</span>
        <Link to="/app/handbook/playbooks/new" className="hover:text-rust-500 transition-colors">
          New
        </Link>
        <span>/</span>
        <span className="text-app-fg-200">Import</span>
      </div>

      <SectionOpener label="IMPORT FROM NOTION" />

      {/* Headline */}
      <h1 className="font-serif text-[38px] font-medium leading-tight tracking-tight text-app-fg-100 mb-3">
        Have a doc that already works?
      </h1>
      <p className="font-serif italic text-lg text-app-fg-300 mb-10">
        I'll read it for the bits that matter — outcomes, mandates, guardrails — and ignore the
        meeting-notes cruft.
      </p>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        className="border-2 border-dashed border-charcoal-700 bg-rgba(15,13,12,0.3) rounded-sm p-16 text-center mb-6 hover:border-charcoal-600 transition-colors cursor-pointer"
      >
        <label className="cursor-pointer">
          <input
            type="file"
            accept=".md,.markdown,.zip"
            onChange={handleFileUpload}
            className="hidden"
          />
          <Upload className="w-12 h-12 mx-auto mb-4 text-app-fg-400" />
          <div className="font-serif italic text-lg text-app-fg-200 mb-2">
            Drop a file here
          </div>
          <div className="font-mono text-[10px] uppercase tracking-[0.4em] text-app-fg-400">
            MARKDOWN · ZIP · OR INDIVIDUAL .MD FILES
          </div>
        </label>
      </div>

      {/* Divider */}
      <div className="flex items-center gap-4 my-8">
        <div className="flex-1 h-px bg-charcoal-700" />
        <span className="font-mono text-[10px] uppercase tracking-[0.4em] text-app-fg-400">
          — OR —
        </span>
        <div className="flex-1 h-px bg-charcoal-700" />
      </div>

      {/* Paste row */}
      <div className="flex gap-3 mb-8">
        <input
          type="url"
          value={notionUrl}
          onChange={(e) => setNotionUrl(e.target.value)}
          placeholder="Paste a Notion share link..."
          className="flex-1 px-4 py-3 bg-charcoal-900/50 border border-charcoal-700 rounded-sm font-mono text-[13px] text-app-fg-100 placeholder:text-app-fg-400 outline-none focus:border-rust-500"
        />
        <button
          onClick={handlePaste}
          disabled={!notionUrl.trim() || importing}
          className="px-6 py-3 text-sm font-mono uppercase tracking-wider bg-rust-500 text-cream-50 hover:bg-rust-400 rounded-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Read it
        </button>
      </div>

      {/* Progress card */}
      {importing && (
        <ImportProgress
          filename="Enterprise Onboarding Playbook"
          currentStep={currentStep}
          totalSteps={steps.length}
          steps={steps}
        />
      )}

      {/* Footer note */}
      <p className="font-serif italic text-sm text-app-fg-400 text-center mt-8">
        I'll surface anything ambiguous as a HITL batch — you'll review it before this playbook
        goes live.
      </p>
    </div>
  );
}
