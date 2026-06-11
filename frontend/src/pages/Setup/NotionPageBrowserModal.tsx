import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, Search, Loader2, FileText, Check, ChevronRight, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useSearchNotionPages, useLinkPageToCustomer, type NotionPageResult } from '@/lib/dataconnect-hooks';

interface LinkedPageInfo {
  title: string;
  type: string;
  url: string;
}

interface NotionPageBrowserModalProps {
  isOpen: boolean;
  customerId: string;
  customerName: string;
  onClose: () => void;
  onSuccess?: (linkedPage?: LinkedPageInfo) => void;
}

const PAGE_TYPES = [
  { value: 'handoff', label: 'Handoff Doc', description: 'Sales-to-CS handoff notes' },
  { value: 'tracker', label: 'Onboarding Tracker', description: 'Progress tracking doc' },
  { value: 'notes', label: 'Meeting Notes', description: 'Meeting recaps and notes' },
  { value: 'other', label: 'Other', description: 'General reference' },
];

export function NotionPageBrowserModal({
  isOpen,
  customerId,
  customerName,
  onClose,
  onSuccess,
}: NotionPageBrowserModalProps) {
  const { searchPages, isLoading: isSearching } = useSearchNotionPages();
  const { linkPage, isLoading: isLinking } = useLinkPageToCustomer();

  const [query, setQuery] = useState('');
  const [pages, setPages] = useState<NotionPageResult[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<NotionPageResult | null>(null);
  const [selectedType, setSelectedType] = useState<string>('handoff');
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<'browse' | 'confirm'>('browse');

  // Search on query change (debounced)
  useEffect(() => {
    if (!isOpen) return;

    const timer = setTimeout(async () => {
      try {
        setError(null);
        const result = await searchPages(query || undefined);
        setPages(result.pages);
        setHasMore(result.has_more);
        setNextCursor(result.next_cursor);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to search pages');
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query, isOpen, searchPages]);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setPages([]);
      setSelectedPage(null);
      setSelectedType('handoff');
      setError(null);
      setStep('browse');
    }
  }, [isOpen]);

  const handleSelectPage = (page: NotionPageResult) => {
    setSelectedPage(page);
    setStep('confirm');
  };

  const handleConfirm = async () => {
    if (!selectedPage) return;

    try {
      setError(null);
      await linkPage(customerId, {
        source: 'notion',
        page_id: selectedPage.id,
        page_type: selectedType,
        url: selectedPage.url,
        title: selectedPage.title,
      });
      // Pass linked page info to parent
      onSuccess?.({
        title: selectedPage.title,
        type: selectedType,
        url: selectedPage.url,
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to link page');
    }
  };

  const loadMore = async () => {
    if (!hasMore || !nextCursor || isSearching) return;

    try {
      const result = await searchPages(query || undefined, nextCursor);
      setPages(prev => [...prev, ...result.pages]);
      setHasMore(result.has_more);
      setNextCursor(result.next_cursor);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load more');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/80" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="relative bg-charcoal-900 border border-charcoal-700 w-full max-w-xl max-h-[80vh] flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-charcoal-700">
          <div>
            <h2 className="text-lg font-serif text-cream-100">
              {step === 'browse' ? 'Browse Notion Pages' : 'Link Page'}
            </h2>
            <p className="text-sm text-charcoal-400">
              {step === 'browse'
                ? `Find a page to link to ${customerName}`
                : `Confirm linking to ${customerName}`}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-charcoal-500 hover:text-cream-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden flex flex-col">
          <AnimatePresence mode="wait">
            {step === 'browse' ? (
              <motion.div
                key="browse"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="flex-1 flex flex-col overflow-hidden"
              >
                {/* Search */}
                <div className="p-4 border-b border-charcoal-800">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-charcoal-500" />
                    <input
                      type="text"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search pages..."
                      className="w-full bg-charcoal-800 border border-charcoal-700 pl-10 pr-4 py-2 text-cream-200 placeholder:text-charcoal-500 focus:outline-none focus:border-rust-400"
                    />
                    {isSearching && (
                      <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-charcoal-400 animate-spin" />
                    )}
                  </div>
                </div>

                {/* Results */}
                <div className="flex-1 overflow-y-auto p-2">
                  {error && (
                    <div className="flex items-center gap-2 p-3 bg-rust-900/20 border border-rust-800 text-rust-300 text-sm mb-2">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      {error}
                    </div>
                  )}

                  {pages.length === 0 && !isSearching && !error && (
                    <div className="text-center py-8 text-charcoal-500">
                      {query ? 'No pages found' : 'Start typing to search pages'}
                    </div>
                  )}

                  <div className="space-y-1">
                    {pages.map((page) => (
                      <button
                        key={page.id}
                        onClick={() => handleSelectPage(page)}
                        className={cn(
                          "w-full flex items-center gap-3 p-3 text-left",
                          "hover:bg-charcoal-800 transition-colors group"
                        )}
                      >
                        <span className="w-6 h-6 flex items-center justify-center text-lg shrink-0">
                          {page.icon || <FileText className="w-4 h-4 text-charcoal-500" />}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-cream-200 truncate">{page.title}</div>
                          {page.last_edited && (
                            <div className="text-xs text-charcoal-500">
                              Edited {new Date(page.last_edited).toLocaleDateString()}
                            </div>
                          )}
                        </div>
                        <ChevronRight className="w-4 h-4 text-charcoal-600 group-hover:text-charcoal-400" />
                      </button>
                    ))}
                  </div>

                  {hasMore && (
                    <button
                      onClick={loadMore}
                      disabled={isSearching}
                      className="w-full py-3 text-sm text-charcoal-400 hover:text-cream-200 transition-colors"
                    >
                      {isSearching ? 'Loading...' : 'Load more'}
                    </button>
                  )}
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="confirm"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="p-4 space-y-4"
              >
                {/* Selected page preview */}
                {selectedPage && (
                  <div className="flex items-center gap-3 p-3 bg-charcoal-800 border border-charcoal-700">
                    <span className="w-8 h-8 flex items-center justify-center text-xl">
                      {selectedPage.icon || <FileText className="w-5 h-5 text-charcoal-500" />}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-cream-200 font-medium truncate">{selectedPage.title}</div>
                      <div className="text-xs text-charcoal-500 truncate">{selectedPage.url}</div>
                    </div>
                  </div>
                )}

                {/* Page type selection */}
                <div>
                  <label className="block text-sm text-charcoal-400 mb-2">
                    What type of document is this?
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {PAGE_TYPES.map((type) => (
                      <button
                        key={type.value}
                        onClick={() => setSelectedType(type.value)}
                        className={cn(
                          "p-3 text-left border transition-colors",
                          selectedType === type.value
                            ? "bg-rust-900/30 border-rust-600 text-cream-200"
                            : "bg-charcoal-800 border-charcoal-700 text-charcoal-300 hover:border-charcoal-600"
                        )}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          {selectedType === type.value && <Check className="w-3 h-3 text-rust-400" />}
                          <span className="text-sm font-medium">{type.label}</span>
                        </div>
                        <div className="text-xs text-charcoal-500">{type.description}</div>
                      </button>
                    ))}
                  </div>
                </div>

                {error && (
                  <div className="flex items-center gap-2 p-3 bg-rust-900/20 border border-rust-800 text-rust-300 text-sm">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    {error}
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 pt-2">
                  <button
                    onClick={() => setStep('browse')}
                    className="sk-btn text-sm"
                  >
                    ← Back
                  </button>
                  <button
                    onClick={handleConfirm}
                    disabled={isLinking}
                    className="sk-btn sk-btn--primary text-sm flex items-center gap-2 flex-1 justify-center"
                  >
                    {isLinking ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Linking...
                      </>
                    ) : (
                      <>
                        <Check className="w-4 h-4" />
                        Link Page
                      </>
                    )}
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
