import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Send,
  Paperclip,
  Zap,
  X,
  Check,
  Edit3,
  Loader2,
  FileText,
  Image as ImageIcon,
  AtSign,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DraftResponse, TeamMember, Attachment } from '@/lib/api';

interface ConversationComposerProps {
  threadId: string;
  currentDraft: DraftResponse | null;
  teamMembers: TeamMember[];
  onSendMessage: (content: string, isInternal: boolean, mentions: string[]) => Promise<void>;
  onUploadAttachment: (file: File) => Promise<Attachment>;
  onRequestDraft: (vibeInput?: string) => Promise<void>;
  onAcceptDraft: (draftId: string, editedContent?: string) => Promise<void>;
  onRejectDraft: (draftId: string) => Promise<void>;
  isRequestingDraft?: boolean;
  isSending?: boolean;
}

export function ConversationComposer({
  threadId,
  currentDraft,
  teamMembers,
  onSendMessage,
  onUploadAttachment,
  onRequestDraft,
  onAcceptDraft,
  onRejectDraft,
  isRequestingDraft = false,
  isSending = false,
}: ConversationComposerProps) {
  const [content, setContent] = useState('');
  const [isInternal, setIsInternal] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [showVibeInput, setShowVibeInput] = useState(false);
  const [vibeInput, setVibeInput] = useState('');
  const [showMentions, setShowMentions] = useState(false);
  const [mentionSearch, setMentionSearch] = useState('');
  const [selectedMentions, setSelectedMentions] = useState<string[]>([]);
  const [cursorPosition, setCursorPosition] = useState(0);
  const [isEditingDraft, setIsEditingDraft] = useState(false);
  const [editedDraftContent, setEditedDraftContent] = useState('');
  const [isDraftExpanded, setIsDraftExpanded] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [content, editedDraftContent]);

  // Handle @mention detection
  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    const position = e.target.selectionStart;
    setContent(value);
    setCursorPosition(position);

    // Check for @mention trigger
    const textBeforeCursor = value.slice(0, position);
    const atMatch = textBeforeCursor.match(/@(\w*)$/);

    if (atMatch) {
      setShowMentions(true);
      setMentionSearch(atMatch[1].toLowerCase());
    } else {
      setShowMentions(false);
      setMentionSearch('');
    }
  };

  // Filter team members for mention autocomplete
  const filteredMembers = teamMembers.filter(
    (member) =>
      member.name.toLowerCase().includes(mentionSearch) ||
      member.email.toLowerCase().includes(mentionSearch)
  );

  // Insert mention
  const insertMention = (member: TeamMember) => {
    const textBeforeCursor = content.slice(0, cursorPosition);
    const textAfterCursor = content.slice(cursorPosition);
    const atIndex = textBeforeCursor.lastIndexOf('@');
    const newText = textBeforeCursor.slice(0, atIndex) + `@${member.name} ` + textAfterCursor;

    setContent(newText);
    setShowMentions(false);
    setMentionSearch('');

    if (!selectedMentions.includes(member.id)) {
      setSelectedMentions([...selectedMentions, member.id]);
    }

    // Focus back on textarea
    textareaRef.current?.focus();
  };

  // Handle file upload
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsUploading(true);
    try {
      for (const file of Array.from(files)) {
        const attachment = await onUploadAttachment(file);
        setAttachments((prev) => [...prev, attachment]);
      }
    } catch (error) {
      console.error('Failed to upload attachment:', error);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  // Remove attachment
  const removeAttachment = (attachmentId: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== attachmentId));
  };

  // Handle send
  const handleSend = async () => {
    if (!content.trim() && attachments.length === 0) return;

    try {
      await onSendMessage(content, isInternal, selectedMentions);
      setContent('');
      setAttachments([]);
      setSelectedMentions([]);
      setIsInternal(false);
    } catch (error) {
      console.error('Failed to send message:', error);
    }
  };

  // Handle draft request
  const handleRequestDraft = async () => {
    if (showVibeInput && vibeInput.trim()) {
      await onRequestDraft(vibeInput);
      setVibeInput('');
      setShowVibeInput(false);
    } else if (!showVibeInput) {
      setShowVibeInput(true);
    } else {
      await onRequestDraft();
      setShowVibeInput(false);
    }
  };

  // Handle draft accept
  const handleAcceptDraft = async () => {
    if (!currentDraft) return;

    if (isEditingDraft) {
      await onAcceptDraft(currentDraft.id, editedDraftContent);
    } else {
      await onAcceptDraft(currentDraft.id);
    }
    setIsEditingDraft(false);
    setEditedDraftContent('');
  };

  // Handle draft reject
  const handleRejectDraft = async () => {
    if (!currentDraft) return;
    await onRejectDraft(currentDraft.id);
    setIsEditingDraft(false);
    setEditedDraftContent('');
  };

  // Start editing draft
  const startEditingDraft = () => {
    if (currentDraft) {
      setEditedDraftContent(currentDraft.content);
      setIsEditingDraft(true);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Cmd/Ctrl + Enter
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSend();
    }
  };

  // Get truncated preview of draft content
  const getDraftPreview = (content: string, maxLength: number = 100) => {
    if (content.length <= maxLength) return content;
    return content.slice(0, maxLength).trim() + '...';
  };

  return (
    <div className="border-t border-charcoal-700 bg-charcoal-900">
      {/* AI Draft Card - Collapsible */}
      <AnimatePresence>
        {currentDraft && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="m-3 mb-0"
          >
            <div className="rounded-lg border-2 border-rust-500/60 bg-gradient-to-r from-rust-950/80 to-charcoal-900 overflow-hidden shadow-lg shadow-rust-900/20">
              {/* Collapsed Header - Always Visible */}
              <div
                className={cn(
                  "flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-rust-900/20 transition-colors",
                  !isDraftExpanded && !isEditingDraft && "border-b-0"
                )}
                onClick={() => !isEditingDraft && setIsDraftExpanded(!isDraftExpanded)}
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div className="flex items-center justify-center w-8 h-8 rounded-full bg-rust-500/20 flex-shrink-0">
                    <Zap className="w-4 h-4 text-rust-400 fill-rust-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-rust-300">
                        AI Draft Ready
                      </span>
                      <span className="text-xs text-charcoal-500 hidden sm:inline">
                        {new Date(currentDraft.generated_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                      </span>
                    </div>
                    {!isDraftExpanded && !isEditingDraft && (
                      <p className="text-xs text-cream-400/70 truncate mt-0.5">
                        {getDraftPreview(currentDraft.content)}
                      </p>
                    )}
                  </div>
                </div>

                {/* Action Buttons - Always visible */}
                <div className="flex items-center gap-2 ml-3 flex-shrink-0">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleAcceptDraft();
                    }}
                    disabled={isSending}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-rust-600 hover:bg-rust-500 text-cream-100 text-xs font-medium rounded transition-colors disabled:opacity-50"
                  >
                    {isSending ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Check className="w-3 h-3" />
                    )}
                    <span className="hidden sm:inline">{isEditingDraft ? 'Send' : 'Use'}</span>
                  </button>

                  {!isEditingDraft && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setIsDraftExpanded(true);
                        startEditingDraft();
                      }}
                      className="flex items-center gap-1.5 px-2 py-1.5 border border-charcoal-600 hover:border-rust-500/50 text-cream-300 text-xs rounded transition-colors"
                    >
                      <Edit3 className="w-3 h-3" />
                      <span className="hidden sm:inline">Edit</span>
                    </button>
                  )}

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRejectDraft();
                    }}
                    className="p-1.5 text-charcoal-500 hover:text-cream-300 transition-colors"
                    title="Dismiss draft"
                  >
                    <X className="w-4 h-4" />
                  </button>

                  {!isEditingDraft && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setIsDraftExpanded(!isDraftExpanded);
                      }}
                      className="p-1 text-charcoal-500 hover:text-cream-300 transition-colors"
                    >
                      {isDraftExpanded ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </button>
                  )}
                </div>
              </div>

              {/* Expanded Content */}
              <AnimatePresence>
                {(isDraftExpanded || isEditingDraft) && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-4 pt-2 border-t border-rust-500/20">
                      {isEditingDraft ? (
                        <textarea
                          value={editedDraftContent}
                          onChange={(e) => setEditedDraftContent(e.target.value)}
                          className="w-full bg-charcoal-900 border border-charcoal-700 rounded p-3 text-sm text-cream-200 resize-none focus:outline-none focus:border-rust-500/50"
                          rows={6}
                          autoFocus
                        />
                      ) : (
                        <p className="text-sm text-cream-300 leading-relaxed whitespace-pre-wrap">
                          {currentDraft.content}
                        </p>
                      )}

                      {currentDraft.reasoning && !isEditingDraft && (
                        <p className="text-xs text-charcoal-500 mt-3 italic border-t border-charcoal-700/50 pt-2">
                          {currentDraft.reasoning}
                        </p>
                      )}

                      {isEditingDraft && (
                        <div className="flex items-center gap-2 mt-3">
                          <button
                            onClick={() => {
                              setIsEditingDraft(false);
                              setEditedDraftContent('');
                            }}
                            className="text-xs text-charcoal-400 hover:text-cream-300 transition-colors"
                          >
                            Cancel editing
                          </button>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Vibe Input for Draft Request */}
      <AnimatePresence>
        {showVibeInput && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="border-b border-charcoal-700 bg-charcoal-800 p-4"
          >
            <div className="flex items-center gap-2 mb-2">
              <Zap className="w-4 h-4 text-rust-500" />
              <span className="font-mono text-xs uppercase tracking-wider text-rust-400">
                Draft Reply
              </span>
            </div>
            <input
              type="text"
              value={vibeInput}
              onChange={(e) => setVibeInput(e.target.value)}
              placeholder="Optional: Give the AI some context... (e.g., 'be apologetic, mention we're investigating')"
              className="w-full bg-charcoal-900 border border-charcoal-700 rounded px-3 py-2 text-sm text-cream-200 placeholder:text-charcoal-500 focus:outline-none focus:border-rust-500/50"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleRequestDraft();
                } else if (e.key === 'Escape') {
                  setShowVibeInput(false);
                  setVibeInput('');
                }
              }}
              autoFocus
            />
            <div className="flex items-center gap-2 mt-2">
              <button
                onClick={handleRequestDraft}
                disabled={isRequestingDraft}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-rust-600 hover:bg-rust-500 text-cream-100 text-sm font-medium rounded transition-colors disabled:opacity-50"
              >
                {isRequestingDraft ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4" />
                )}
                <span>Generate Draft</span>
              </button>
              <button
                onClick={() => {
                  setShowVibeInput(false);
                  setVibeInput('');
                }}
                className="text-charcoal-400 hover:text-cream-300 text-sm transition-colors"
              >
                Cancel
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Attachments Preview */}
      {attachments.length > 0 && (
        <div className="px-4 pt-3 flex flex-wrap gap-2">
          {attachments.map((attachment) => (
            <div
              key={attachment.id}
              className="flex items-center gap-2 px-2 py-1 bg-charcoal-800 rounded border border-charcoal-700 text-sm"
            >
              {attachment.mime_type.startsWith('image/') ? (
                <ImageIcon className="w-4 h-4 text-charcoal-400" />
              ) : (
                <FileText className="w-4 h-4 text-charcoal-400" />
              )}
              <span className="text-cream-300 max-w-32 truncate">{attachment.filename}</span>
              <button
                onClick={() => removeAttachment(attachment.id)}
                className="text-charcoal-500 hover:text-cream-300 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Main Composer */}
      <div className="p-4">
        <div className="relative">
          {/* @Mention Autocomplete */}
          <AnimatePresence>
            {showMentions && filteredMembers.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                className="absolute bottom-full left-0 right-0 mb-2 bg-charcoal-800 border border-charcoal-700 rounded shadow-lg max-h-48 overflow-y-auto z-10"
              >
                {filteredMembers.map((member) => (
                  <button
                    key={member.id}
                    onClick={() => insertMention(member)}
                    className="w-full flex items-center gap-3 px-3 py-2 hover:bg-charcoal-700 transition-colors text-left"
                  >
                    <div className="w-8 h-8 rounded-full bg-charcoal-600 flex items-center justify-center text-sm font-medium text-cream-300">
                      {member.name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm text-cream-200">{member.name}</p>
                      <p className="text-xs text-charcoal-400">{member.email}</p>
                    </div>
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>

          <textarea
            ref={textareaRef}
            value={content}
            onChange={handleContentChange}
            onKeyDown={handleKeyDown}
            placeholder={isInternal ? 'Write an internal note...' : 'Write a reply...'}
            className={cn(
              "w-full bg-charcoal-800 border rounded px-4 py-3 text-sm text-cream-200 placeholder:text-charcoal-500 resize-none focus:outline-none",
              isInternal
                ? "border-rust-500/50 focus:border-rust-500"
                : "border-charcoal-700 focus:border-rust-500/50"
            )}
            rows={3}
          />
        </div>

        {/* Actions Row */}
        <div className="flex items-center justify-between mt-3">
          <div className="flex items-center gap-2">
            {/* File Upload */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileChange}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="flex items-center gap-1.5 px-2 py-1.5 text-charcoal-400 hover:text-cream-300 transition-colors disabled:opacity-50"
              title="Attach file"
            >
              {isUploading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Paperclip className="w-4 h-4" />
              )}
            </button>

            {/* @Mention Trigger */}
            <button
              onClick={() => {
                const newContent = content + '@';
                setContent(newContent);
                setCursorPosition(newContent.length);
                setShowMentions(true);
                textareaRef.current?.focus();
              }}
              className="flex items-center gap-1.5 px-2 py-1.5 text-charcoal-400 hover:text-cream-300 transition-colors"
              title="Mention someone"
            >
              <AtSign className="w-4 h-4" />
            </button>

            {/* AI Draft Button */}
            {!currentDraft && !showVibeInput && (
              <button
                onClick={handleRequestDraft}
                disabled={isRequestingDraft}
                className="flex items-center gap-1.5 px-2 py-1.5 text-rust-400 hover:text-rust-300 transition-colors disabled:opacity-50"
                title="Draft reply with AI"
              >
                {isRequestingDraft ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4" />
                )}
                <span className="font-mono text-xs uppercase tracking-wider">Draft</span>
              </button>
            )}

            {/* Internal Note Toggle */}
            <button
              onClick={() => setIsInternal(!isInternal)}
              className={cn(
                "flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors font-mono text-xs uppercase tracking-wider",
                isInternal
                  ? "bg-rust-900/30 text-rust-400 border border-rust-500/30"
                  : "text-charcoal-400 hover:text-cream-300"
              )}
            >
              {isInternal ? 'Internal Note' : 'Reply'}
            </button>
          </div>

          {/* Send Button */}
          <button
            onClick={handleSend}
            disabled={isSending || (!content.trim() && attachments.length === 0)}
            className="flex items-center gap-1.5 px-4 py-2 bg-rust-600 hover:bg-rust-500 text-cream-100 text-sm font-medium rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            <span>{isInternal ? 'Save Note' : 'Send'}</span>
          </button>
        </div>

        {/* Keyboard Shortcut Hint */}
        <div className="text-xs text-charcoal-500 mt-2 font-mono">
          Press <kbd className="px-1 py-0.5 bg-charcoal-800 rounded text-charcoal-400">Cmd+Enter</kbd> to send
        </div>
      </div>
    </div>
  );
}
