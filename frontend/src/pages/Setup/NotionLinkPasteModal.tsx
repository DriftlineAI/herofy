import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { X, Link2, Loader2, Check, AlertCircle, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useValidateNotionLink, useLinkPageToCustomer } from '@/lib/dataconnect-hooks';

interface LinkedPageInfo {
  title: string;
  type: string;
  url: string;
}

interface NotionLinkPasteModalProps {
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

export function NotionLinkPasteModal({
  isOpen,
  customerId,
  customerName,
  onClose,
  onSuccess,
}: NotionLinkPasteModalProps) {
  const { validateLink, isLoading: isValidating } = useValidateNotionLink();
  const { linkPage, isLoading: isLinking } = useLinkPageToCustomer();

  const [url, setUrl] = useState('');
  const [selectedType, setSelectedType] = useState<string>('handoff');
  const [error, setError] = useState<string | null>(null);
  const [validatedPage, setValidatedPage] = useState<{
    page_id: string;
    title: string;
    url: string;
    has_access: boolean;
  } | null>(null);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setUrl('');
      setSelectedType('handoff');
      setError(null);
      setValidatedPage(null);
    }
  }, [isOpen]);

  const handleValidate = async () => {
    if (!url.trim()) return;

    try {
      setError(null);
      setValidatedPage(null);

      const result = await validateLink(url.trim());

      if (!result.valid) {
        setError(result.error || 'Invalid Notion URL');
        return;
      }

      if (!result.has_access) {
        setError(result.error || 'We don\'t have access to this page. Share it with the Herofy integration.');
        setValidatedPage({
          page_id: result.page_id!,
          title: 'No access',
          url: url.trim(),
          has_access: false,
        });
        return;
      }

      setValidatedPage({
        page_id: result.page_id!,
        title: result.title!,
        url: result.url || url.trim(),
        has_access: true,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to validate link');
    }
  };

  const handleConfirm = async () => {
    if (!validatedPage || !validatedPage.has_access) return;

    try {
      setError(null);
      await linkPage(customerId, {
        source: 'notion',
        page_id: validatedPage.page_id,
        page_type: selectedType,
        url: validatedPage.url,
        title: validatedPage.title,
      });
      // Pass linked page info to parent
      onSuccess?.({
        title: validatedPage.title,
        type: selectedType,
        url: validatedPage.url,
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to link page');
    }
  };

  if (!isOpen) return null;

  const isValid = validatedPage?.has_access;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/80" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="relative bg-charcoal-900 border border-charcoal-700 w-full max-w-lg p-6"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-lg font-serif text-cream-100">
              Paste Notion Link
            </h2>
            <p className="text-sm text-charcoal-400">
              Link a Notion page to {customerName}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-charcoal-500 hover:text-cream-200 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* URL Input */}
        <div className="mb-4">
          <label className="block text-sm text-charcoal-400 mb-2">
            Notion page URL
          </label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Link2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-charcoal-500" />
              <input
                type="url"
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value);
                  setValidatedPage(null);
                  setError(null);
                }}
                placeholder="https://notion.so/..."
                className="w-full bg-charcoal-800 border border-charcoal-700 pl-10 pr-4 py-2 text-cream-200 placeholder:text-charcoal-500 focus:outline-none focus:border-rust-400"
              />
            </div>
            <button
              onClick={handleValidate}
              disabled={!url.trim() || isValidating}
              className="sk-btn sk-btn--primary px-4"
            >
              {isValidating ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Check'}
            </button>
          </div>
        </div>

        {/* Validation result */}
        {validatedPage && (
          <div className={cn(
            "p-3 border mb-4",
            validatedPage.has_access
              ? "bg-green-900/20 border-green-800"
              : "bg-rust-900/20 border-rust-800"
          )}>
            <div className="flex items-start gap-3">
              {validatedPage.has_access ? (
                <Check className="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-5 h-5 text-rust-400 shrink-0 mt-0.5" />
              )}
              <div className="flex-1 min-w-0">
                <div className={cn(
                  "font-medium truncate",
                  validatedPage.has_access ? "text-green-300" : "text-rust-300"
                )}>
                  {validatedPage.title}
                </div>
                <div className="text-xs text-charcoal-500 truncate flex items-center gap-1">
                  <span className="truncate">{validatedPage.url}</span>
                  <a
                    href={validatedPage.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="shrink-0 hover:text-charcoal-300"
                  >
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Error */}
        {error && !validatedPage && (
          <div className="flex items-center gap-2 p-3 bg-rust-900/20 border border-rust-800 text-rust-300 text-sm mb-4">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Page type selection - only show when validated */}
        {isValid && (
          <div className="mb-6">
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
        )}

        {/* Actions */}
        <div className="flex gap-2">
          <button onClick={onClose} className="sk-btn text-sm">
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!isValid || isLinking}
            className={cn(
              "sk-btn sk-btn--primary text-sm flex items-center gap-2 flex-1 justify-center",
              (!isValid || isLinking) && "opacity-50 cursor-not-allowed"
            )}
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
    </div>
  );
}
