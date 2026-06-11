import { motion } from 'motion/react';
import {
  Check,
  Users,
  Mail,
  MessageSquare,
  Calendar,
  FileText,
  ArrowRight,
} from 'lucide-react';
import type { OnboardingData } from './index';

interface StepProcessingProps {
  data: OnboardingData;
  onComplete: () => void;
}

export function StepProcessing({ data, onComplete }: StepProcessingProps) {
  // Count connected integrations
  const connectedIntegrations = Object.entries(data.integrations)
    .filter(([_, connected]) => connected)
    .map(([name]) => name);

  // Get import source info
  const hasNotionImport = data.importSource === 'notion' && data.notionConfig?.primaryDatabaseId;
  const hasCSVImport = data.importSource === 'csv' && data.csvData?.customers?.length;
  const hasImport = hasNotionImport || hasCSVImport;

  const getIntegrationIcon = (name: string) => {
    switch (name) {
      case 'gmail':
        return <Mail className="w-4 h-4" />;
      case 'slack':
        return <MessageSquare className="w-4 h-4" />;
      case 'calendar':
        return <Calendar className="w-4 h-4" />;
      case 'notion':
        return <FileText className="w-4 h-4" />;
      default:
        return null;
    }
  };

  const getIntegrationLabel = (name: string) => {
    switch (name) {
      case 'gmail':
        return 'Gmail';
      case 'slack':
        return 'Slack';
      case 'calendar':
        return 'Google Calendar';
      case 'notion':
        return 'Notion';
      default:
        return name;
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="mb-8 text-center">
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-4"
        >
          <Check className="w-8 h-8 text-emerald-500" />
        </motion.div>
        <h1 className="font-serif text-3xl text-cream-100 mb-2">
          You're all set!
        </h1>
        <p className="text-cream-400">
          Your workspace "{data.workspace.name}" is ready to go.
        </p>
      </div>

      {/* Summary */}
      <div className="space-y-4 mb-8">
        {/* Customers Imported */}
        {hasImport && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="border border-emerald-500/30 bg-emerald-500/10 p-4"
          >
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-emerald-500/20 rounded-full flex items-center justify-center">
                <Users className="w-4 h-4 text-emerald-500" />
              </div>
              <div>
                <div className="text-sm text-emerald-400 font-medium">
                  Customers imported
                </div>
                <div className="text-xs text-charcoal-400">
                  {hasNotionImport && 'Imported from Notion database'}
                  {hasCSVImport && `${data.csvData?.customers?.length} customers from CSV`}
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {/* Connected Integrations */}
        {connectedIntegrations.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="border border-charcoal-700 bg-charcoal-800/50 p-4"
          >
            <div className="text-xs font-mono uppercase tracking-widest text-charcoal-400 mb-3">
              Connected Integrations
            </div>
            <div className="flex flex-wrap gap-2">
              {connectedIntegrations.map((name) => (
                <div
                  key={name}
                  className="flex items-center gap-2 px-3 py-1.5 bg-charcoal-700 text-cream-300 text-sm"
                >
                  {getIntegrationIcon(name)}
                  <span>{getIntegrationLabel(name)}</span>
                  <Check className="w-3 h-3 text-emerald-500" />
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* No integrations or import */}
        {!hasImport && connectedIntegrations.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="border border-charcoal-700 bg-charcoal-800/50 p-4 text-center"
          >
            <div className="text-sm text-charcoal-400 mb-1">
              No customers imported yet
            </div>
            <div className="text-xs text-charcoal-500">
              You can add customers manually or connect integrations from Settings.
            </div>
          </motion.div>
        )}
      </div>

      {/* What's next */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="border border-rust-500/30 bg-rust-500/5 p-5 mb-8"
      >
        <div className="text-sm font-medium text-cream-100 mb-2">
          What happens next?
        </div>
        <ul className="text-sm text-charcoal-400 space-y-2">
          <li className="flex items-start gap-2">
            <span className="text-rust-400">•</span>
            Your Today Queue will show customers that need attention
          </li>
          {connectedIntegrations.includes('gmail') && (
            <li className="flex items-start gap-2">
              <span className="text-rust-400">•</span>
              Email threads with customers will be synced automatically
            </li>
          )}
          {connectedIntegrations.includes('calendar') && (
            <li className="flex items-start gap-2">
              <span className="text-rust-400">•</span>
              Upcoming meetings will appear with prep suggestions
            </li>
          )}
          <li className="flex items-start gap-2">
            <span className="text-rust-400">•</span>
            AI will surface signals when customers need attention
          </li>
        </ul>
      </motion.div>

      {/* CTA */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}
        className="text-center"
      >
        <button
          onClick={onComplete}
          className="inline-flex items-center gap-2 text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-8 py-4 hover:bg-rust-400 transition-colors font-bold"
        >
          Go to Dashboard
          <ArrowRight className="w-4 h-4" />
        </button>
      </motion.div>
    </div>
  );
}
