import React from 'react';
import { motion } from 'motion/react';
import { ArrowLeft, RefreshCw, Save, Bell, Mail } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth';

// Generate DiceBear Adventurer avatar URL
function getAvatarUrl(seed: string): string {
  return `https://api.dicebear.com/7.x/adventurer/svg?seed=${encodeURIComponent(seed)}`;
}

// Generate a random seed for avatar regeneration
function generateRandomSeed(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export default function UserSettings() {
  const { user: firebaseUser, loading } = useAuth();

  const [displayName, setDisplayName] = React.useState('');
  const [avatarSeed, setAvatarSeed] = React.useState('');
  const [emailNotifications, setEmailNotifications] = React.useState(true);
  const [inAppNotifications, setInAppNotifications] = React.useState(true);
  const [hasChanges, setHasChanges] = React.useState(false);
  const [isSaving, setIsSaving] = React.useState(false);
  const [saveSuccess, setSaveSuccess] = React.useState(false);
  const [saveError, setSaveError] = React.useState(false);

  // Initialize form state from Firebase user
  React.useEffect(() => {
    if (firebaseUser) {
      setDisplayName(firebaseUser.displayName || '');
      setAvatarSeed(firebaseUser.uid || 'default');
    }
  }, [firebaseUser]);

  // Track changes
  React.useEffect(() => {
    if (firebaseUser) {
      const originalName = firebaseUser.displayName || '';
      const originalSeed = firebaseUser.uid || 'default';

      const changed =
        displayName !== originalName ||
        avatarSeed !== originalSeed;

      setHasChanges(changed);
    }
  }, [firebaseUser, displayName, avatarSeed]);

  const handleRegenerateAvatar = () => {
    setAvatarSeed(generateRandomSeed());
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveSuccess(false);
    setSaveError(false);

    try {
      // TODO: Save to backend when API is wired up
      // For now, just simulate save
      await new Promise(r => setTimeout(r, 500));
      setSaveSuccess(true);
      setHasChanges(false);
    } catch (error) {
      setSaveError(true);
    } finally {
      setIsSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-pulse text-fg-400">Loading settings...</div>
      </div>
    );
  }

  // Use Google profile photo if available
  const avatarUrl = firebaseUser?.photoURL || getAvatarUrl(avatarSeed);
  const userEmail = firebaseUser?.email || '';

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="max-w-2xl mx-auto"
    >
      {/* Header */}
      <div className="mb-8">
        <Link
          to="/app"
          className="inline-flex items-center gap-2 text-fg-400 hover:text-fg-200 transition-colors text-sm mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Today
        </Link>
        <h1 className="text-2xl font-bold text-fg-100">User Settings</h1>
        <p className="text-fg-400 mt-1">Manage your profile and notification preferences</p>
      </div>

      {/* Avatar Section */}
      <section className="mb-10">
        <h2 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4">Avatar</h2>
        <div className="bg-surface-2/50 border border-border rounded-lg p-6">
          <div className="flex items-center gap-6">
            <div className="relative">
              <img
                src={avatarUrl}
                alt="Your avatar"
                className="w-24 h-24 rounded-full border-2 border-border-strong object-cover"
              />
            </div>
            <div>
              <p className="text-fg-200 text-sm mb-3">
                {firebaseUser?.photoURL
                  ? 'Using your Google profile photo.'
                  : 'Your avatar is generated using DiceBear. Click regenerate to get a new one.'}
              </p>
              {!firebaseUser?.photoURL && (
                <button
                  onClick={handleRegenerateAvatar}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-border hover:bg-border-strong border border-border-strong rounded text-sm text-fg-200 transition-colors cursor-pointer"
                >
                  <RefreshCw className="w-4 h-4" />
                  Regenerate Avatar
                </button>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Profile Section */}
      <section className="mb-10">
        <h2 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4">Profile</h2>
        <div className="bg-surface-2/50 border border-border rounded-lg p-6">
          <div className="space-y-4">
            <div>
              <label htmlFor="displayName" className="block text-sm text-fg-300 mb-1.5">
                Display Name
              </label>
              <input
                id="displayName"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder={userEmail.split('@')[0] || 'Enter your name'}
                className="w-full bg-page border border-border-strong rounded px-3 py-2 text-fg-100 placeholder-fg-500 focus:outline-none focus:border-accent transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm text-fg-300 mb-1.5">
                Email
              </label>
              <div className="w-full bg-page/50 border border-border rounded px-3 py-2 text-fg-400">
                {userEmail}
              </div>
              <p className="text-xs text-fg-500 mt-1">Email cannot be changed here</p>
            </div>
          </div>
        </div>
      </section>

      {/* Notifications Section */}
      <section className="mb-10">
        <h2 className="text-xs font-mono uppercase tracking-widest text-fg-400 mb-4">Notifications</h2>
        <div className="bg-surface-2/50 border border-border rounded-lg p-6">
          <div className="space-y-4">
            <label className="flex items-center justify-between cursor-pointer group">
              <div className="flex items-center gap-3">
                <Mail className="w-5 h-5 text-fg-400" />
                <div>
                  <div className="text-fg-200 group-hover:text-fg-100 transition-colors">Email Notifications</div>
                  <div className="text-sm text-fg-500">Receive email alerts for urgent items</div>
                </div>
              </div>
              <button
                onClick={() => setEmailNotifications(!emailNotifications)}
                className={cn(
                  'w-11 h-6 rounded-full relative transition-colors cursor-pointer flex-shrink-0',
                  emailNotifications ? 'bg-accent' : 'bg-border-strong'
                )}
              >
                <motion.span
                  animate={{ x: emailNotifications ? 22 : 2 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                  className="absolute top-1 left-0 w-4 h-4 bg-white rounded-full shadow-sm"
                />
              </button>
            </label>

            <label className="flex items-center justify-between cursor-pointer group">
              <div className="flex items-center gap-3">
                <Bell className="w-5 h-5 text-fg-400" />
                <div>
                  <div className="text-fg-200 group-hover:text-fg-100 transition-colors">In-App Notifications</div>
                  <div className="text-sm text-fg-500">Show notifications within Herofy</div>
                </div>
              </div>
              <button
                onClick={() => setInAppNotifications(!inAppNotifications)}
                className={cn(
                  'w-11 h-6 rounded-full relative transition-colors cursor-pointer flex-shrink-0',
                  inAppNotifications ? 'bg-accent' : 'bg-border-strong'
                )}
              >
                <motion.span
                  animate={{ x: inAppNotifications ? 22 : 2 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                  className="absolute top-1 left-0 w-4 h-4 bg-white rounded-full shadow-sm"
                />
              </button>
            </label>
          </div>
        </div>
      </section>

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={!hasChanges || isSaving}
          className={cn(
            'inline-flex items-center gap-2 px-6 py-2.5 rounded font-medium transition-colors cursor-pointer',
            hasChanges
              ? 'bg-accent hover:bg-accent-hover text-page'
              : 'bg-border text-fg-400 cursor-not-allowed'
          )}
        >
          {isSaving ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save className="w-4 h-4" />
              Save Changes
            </>
          )}
        </button>
      </div>

      {/* Success/Error Messages */}
      {saveSuccess && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 p-3 bg-signal-ok/10 border border-signal-ok/30 rounded text-signal-ok text-sm text-center"
        >
          Settings saved successfully
        </motion.div>
      )}

      {saveError && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 p-3 bg-accent/10 border border-signal-bad/30 rounded text-signal-bad text-sm text-center"
        >
          Failed to save settings. Please try again.
        </motion.div>
      )}
    </motion.div>
  );
}
