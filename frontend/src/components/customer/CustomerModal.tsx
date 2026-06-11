import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, Building2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { CustomerLifecycle, CreateCustomerInput } from '@/lib/api';
import { useIntegrationStatus, useSearchNotionPages, type NotionPageResult } from '@/lib/dataconnect-hooks';

interface CustomerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateCustomerInput, notionPages: NotionPageResult[]) => void;
  isSubmitting?: boolean;
}

const LIFECYCLE_OPTIONS: { value: CustomerLifecycle; label: string }[] = [
  { value: 'prospect', label: 'Prospect' },
  { value: 'handoff', label: 'Handoff' },
  { value: 'onboarding', label: 'Onboarding' },
  { value: 'active', label: 'Active' },
  { value: 'renewing', label: 'Renewing' },
  { value: 'at_risk', label: 'At Risk' },
];

const TIER_OPTIONS = ['Enterprise', 'Growth', 'Starter', 'Free'];

// Generate slug from name
function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 32);
}

export function CustomerModal({
  isOpen,
  onClose,
  onSubmit,
  isSubmitting = false,
}: CustomerModalProps) {
  const [formData, setFormData] = React.useState({
    name: '',
    slug: '',
    one_liner: '',
    tier: '',
    arr_cents: '',
    lifecycle: 'prospect' as CustomerLifecycle,
    raw_notes: '',
    linked_pages: [],
  });

  const [selectedPages, setSelectedPages] = React.useState<NotionPageResult[]>([]);
  const [slugEdited, setSlugEdited] = React.useState(false);
  const [notionSearchQuery, setNotionSearchQuery] = React.useState('');
  const [notionSearchResults, setNotionSearchResults] = React.useState<NotionPageResult[]>([]);
  const [showNotionDropdown, setShowNotionDropdown] = React.useState(false);

  const { data: notionStatus } = useIntegrationStatus('notion');
  const { searchPages, isLoading: isSearching } = useSearchNotionPages();

  // Reset form when modal opens
  React.useEffect(() => {
    if (isOpen) {
      setFormData({
        name: '',
        slug: '',
        one_liner: '',
        tier: '',
        arr_cents: '',
        lifecycle: 'prospect',
        raw_notes: '',
        linked_pages: [],
      });
      setSelectedPages([]);
      setSlugEdited(false);
      setNotionSearchQuery('');
      setNotionSearchResults([]);
      setShowNotionDropdown(false);
    }
  }, [isOpen]);

  // Auto-generate slug from name (unless manually edited)
  React.useEffect(() => {
    if (!slugEdited && formData.name) {
      setFormData((prev) => ({ ...prev, slug: generateSlug(formData.name) }));
    }
  }, [formData.name, slugEdited]);
  // Debounced Notion search
  React.useEffect(() => {
    if (!notionStatus?.connected) return;
    const timer = setTimeout(async () => {
      if (!notionSearchQuery.trim()) {
        setNotionSearchResults([]);
        setShowNotionDropdown(false);
        return;
      }
      try {
        const result = await searchPages(notionSearchQuery);
        const alreadySelectedIds = new Set(selectedPages.map((p) => p.id));
        setNotionSearchResults(result.pages.filter((p) => !alreadySelectedIds.has(p.id)));
        setShowNotionDropdown(true);
      } catch {
        setNotionSearchResults([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [notionSearchQuery, notionStatus?.connected, searchPages, selectedPages]);

  const handleAddPage = (page: NotionPageResult) => {
    setSelectedPages((prev) => [...prev, page]);
    setNotionSearchQuery('');
    setNotionSearchResults([]);
    setShowNotionDropdown(false);
  };

  const handleRemovePage = (pageId: string) => {
    setSelectedPages((prev) => prev.filter((p) => p.id !== pageId));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const data: CreateCustomerInput = {
      name: formData.name,
      slug: formData.slug || undefined,
      one_liner: formData.one_liner || undefined,
      tier: formData.tier || undefined,
      arr_cents: formData.arr_cents ? parseInt(formData.arr_cents) * 100 : undefined,
      lifecycle: formData.lifecycle,
      raw_notes: formData.raw_notes || undefined,
      linked_pages: selectedPages.map((p) => ({
        source: 'notion',
        id: p.id,
        type: 'page',
        url: p.url,
        title: p.title,
        hasAccess: true,
      })),
    };

    onSubmit(data, notionSearchResults);
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-charcoal-900/80 backdrop-blur-sm z-50"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="fixed inset-x-4 top-[5%] md:inset-x-auto md:left-1/2 md:-translate-x-1/2 md:w-full md:max-w-md z-50 max-h-[90vh] overflow-y-auto"
          >
            <div className="bg-charcoal-900 border border-charcoal-700">
              {/* Header */}
              <div className="flex items-center justify-between p-6 border-b border-charcoal-700">
                <div className="flex items-center gap-3">
                  <Building2 className="w-5 h-5 text-rust-500" />
                  <h2 className="font-serif text-2xl text-cream-100">New Customer</h2>
                </div>
                <button
                  onClick={onClose}
                  className="text-charcoal-400 hover:text-cream-200 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Form */}
              <form onSubmit={handleSubmit} className="p-6 space-y-5">
                {/* Name */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Company Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.name}
                    onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g., Acme Corporation"
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                  />
                </div>

                {/* Slug */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Slug
                  </label>
                  <input
                    type="text"
                    value={formData.slug}
                    onChange={(e) => {
                      setSlugEdited(true);
                      setFormData((prev) => ({ ...prev, slug: e.target.value }));
                    }}
                    placeholder="auto-generated"
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none font-mono text-sm"
                  />
                  <p className="text-xs text-charcoal-500 mt-1">
                    Used in URLs and references. Auto-generated from name.
                  </p>
                </div>

                {/* One-liner */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    One-Liner
                  </label>
                  <input
                    type="text"
                    value={formData.one_liner}
                    onChange={(e) => setFormData((prev) => ({ ...prev, one_liner: e.target.value }))}
                    placeholder="e.g., Enterprise SaaS platform for logistics"
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                  />
                </div>

                {/* Tier and ARR */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                      Tier
                    </label>
                    <select
                      value={formData.tier}
                      onChange={(e) => setFormData((prev) => ({ ...prev, tier: e.target.value }))}
                      className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 focus:border-rust-500 focus:outline-none"
                    >
                      <option value="">Select...</option>
                      {TIER_OPTIONS.map((tier) => (
                        <option key={tier} value={tier}>
                          {tier}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                      ARR ($)
                    </label>
                    <input
                      type="number"
                      min="0"
                      value={formData.arr_cents}
                      onChange={(e) => setFormData((prev) => ({ ...prev, arr_cents: e.target.value }))}
                      placeholder="e.g., 50000"
                      className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none"
                    />
                  </div>
                </div>

                {/* Lifecycle */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Lifecycle Stage
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {LIFECYCLE_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setFormData((prev) => ({ ...prev, lifecycle: option.value }))}
                        className={cn(
                          "px-3 py-1.5 text-xs font-mono transition-colors",
                          formData.lifecycle === option.value
                            ? option.value === 'at_risk'
                              ? "bg-rust-500 text-charcoal-900"
                              : "bg-cream-300 text-charcoal-900"
                            : "bg-charcoal-800 text-charcoal-400 hover:text-cream-200 border border-charcoal-700"
                        )}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Notes */}
                <div>
                  <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                    Notes or Context{' '}
                    <span className="text-charcoal-500 normal-case font-sans tracking-normal text-xs">optional</span>
                  </label>
                  <textarea
                    value={formData.raw_notes}
                    onChange={(e) => setFormData((prev) => ({ ...prev, raw_notes: e.target.value }))}
                    placeholder="Paste sales notes, CRM export, email history, or anything you know about this customer..."
                    rows={4}
                    className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-3 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none resize-none text-sm"
                  />
                  <p className="text-xs text-charcoal-500 mt-1">
                    Used by AI to generate onboarding plan and insights.
                  </p>
                </div>

                {/* Notion page linking — only shown when Notion is connected */}
                {notionStatus?.connected && (
                  <div>
                    <label className="block text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-2">
                      Link Notion Pages{' '}
                      <span className="text-charcoal-500 normal-case font-sans tracking-normal text-xs">optional</span>
                    </label>
                    <div className="relative">
                      <input
                        type="text"
                        value={notionSearchQuery}
                        onChange={(e) => setNotionSearchQuery(e.target.value)}
                        onFocus={() => notionSearchResults.length > 0 && setShowNotionDropdown(true)}
                        placeholder="Search Notion pages..."
                        className="w-full bg-charcoal-800 border border-charcoal-700 text-cream-200 px-4 py-2.5 placeholder:text-charcoal-500 focus:border-rust-500 focus:outline-none text-sm"
                      />
                      {isSearching && (
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-charcoal-500">
                          Searching…
                        </span>
                      )}
                      {showNotionDropdown && notionSearchResults.length > 0 && (
                        <div className="absolute z-10 w-full border border-charcoal-700 bg-charcoal-800 mt-0.5 max-h-48 overflow-y-auto">
                          {notionSearchResults.map((page) => (
                            <button
                              key={page.id}
                              type="button"
                              onClick={() => handleAddPage(page)}
                              className="w-full text-left px-4 py-2.5 text-sm text-cream-200 hover:bg-charcoal-700 transition-colors"
                            >
                              {page.title}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                    {selectedPages.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {selectedPages.map((page) => (
                          <div
                            key={page.id}
                            className="flex items-center justify-between text-xs text-cream-300 bg-charcoal-800 px-3 py-2 border border-charcoal-700"
                          >
                            <span className="truncate mr-2">{page.title}</span>
                            <button
                              type="button"
                              onClick={() => handleRemovePage(page.id)}
                              className="text-charcoal-400 hover:text-cream-200 flex-shrink-0"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                    <p className="text-xs text-charcoal-500 mt-1">
                      Herofy will read these docs to build the customer profile.
                    </p>
                  </div>
                )}

                {/* Actions */}
                <div className="flex justify-end gap-4 pt-4">
                  <button
                    type="button"
                    onClick={onClose}
                    className="text-xs font-mono uppercase tracking-widest border border-charcoal-600 text-charcoal-400 px-6 py-3 hover:border-cream-400 hover:text-cream-200 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting || !formData.name}
                    className="text-xs font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-6 py-3 hover:bg-rust-400 transition-colors font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSubmitting ? 'Creating...' : 'Create Customer'}
                  </button>
                </div>
              </form>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
