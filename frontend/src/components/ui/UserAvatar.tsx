import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { User, Settings, LogOut } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth';
import { signOut } from '@/lib/firebase';
import type { WorkspaceRole } from '@/lib/api';

// Generate DiceBear Adventurer avatar URL
function getAvatarUrl(seed: string): string {
  return `https://api.dicebear.com/7.x/adventurer/svg?seed=${encodeURIComponent(seed)}`;
}

// Role badge component
function RoleBadge({ role }: { role: WorkspaceRole }) {
  const roleStyles: Record<WorkspaceRole, string> = {
    owner: 'bg-accent-bg text-accent border-accent/30',
    csm: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    viewer: 'bg-surface-2 text-fg-400 border-border',
  };

  const roleLabels: Record<WorkspaceRole, string> = {
    owner: 'Owner',
    csm: 'CSM',
    viewer: 'Viewer',
  };

  return (
    <span className={cn(
      'text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded border',
      roleStyles[role]
    )}>
      {roleLabels[role]}
    </span>
  );
}

export function UserAvatar() {
  const [isOpen, setIsOpen] = React.useState(false);
  const menuRef = React.useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { user: firebaseUser, isStaff, hasCompletedSetup, loading } = useAuth();

  // Close menu when clicking outside
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  // Close menu on escape
  React.useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen]);

  const handleSignOut = async () => {
    setIsOpen(false);
    try {
      await signOut();
      navigate('/login');
    } catch (error) {
      console.error('Sign out failed:', error);
    }
  };

  if (loading) {
    return (
      <div className="w-8 h-8 rounded-full bg-border animate-pulse" />
    );
  }

  // Use Firebase auth user data
  const avatarSeed = firebaseUser?.uid || 'default';
  const displayName = firebaseUser?.displayName || firebaseUser?.email?.split('@')[0] || 'User';
  const email = firebaseUser?.email || '';
  // Use Google profile photo if available, otherwise generate avatar
  const avatarUrl = firebaseUser?.photoURL || getAvatarUrl(avatarSeed);
  // TODO: Get role from workspace membership in database
  // For now: if user completed setup (created workspace), they're the owner
  // Staff are also owners, invited users would be 'csm' or 'viewer'
  const role: WorkspaceRole = (hasCompletedSetup || isStaff) ? 'owner' : 'csm';

  return (
    <div ref={menuRef} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'w-8 h-8 rounded-full overflow-hidden border-2 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-page',
          isOpen ? 'border-accent' : 'border-border hover:border-accent'
        )}
        aria-label="User menu"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <img
          src={avatarUrl}
          alt={displayName}
          className="w-full h-full object-cover"
        />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className="absolute right-0 mt-2 w-60 bg-surface border border-border shadow-lift overflow-hidden z-50"
          >
            {/* User info header */}
            <div className="p-4 border-b border-border">
              <div className="flex items-start gap-3">
                <img
                  src={avatarUrl}
                  alt={displayName}
                  className="w-10 h-10 rounded-full border border-border object-cover"
                />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-fg-100 truncate">{displayName}</div>
                  <div className="text-sm text-fg-400 truncate">{email}</div>
                  <div className="mt-1.5">
                    <RoleBadge role={role} />
                  </div>
                </div>
              </div>
            </div>

            {/* Menu items */}
            <div className="py-1">
              <Link
                to="/app/settings"
                onClick={() => setIsOpen(false)}
                className="flex items-center gap-3 px-4 py-2.5 text-fg-200 hover:bg-surface-2 hover:text-fg-100 transition-colors"
              >
                <User className="w-4 h-4 text-fg-400" />
                <span>User Settings</span>
              </Link>

              {role === 'owner' && (
                <Link
                  to="/app/settings/account"
                  onClick={() => setIsOpen(false)}
                  className="flex items-center gap-3 px-4 py-2.5 text-fg-200 hover:bg-surface-2 hover:text-fg-100 transition-colors"
                >
                  <Settings className="w-4 h-4 text-fg-400" />
                  <span>Account Settings</span>
                </Link>
              )}
            </div>

            {/* Sign out */}
            <div className="border-t border-border py-1">
              <button
                onClick={handleSignOut}
                className="flex items-center gap-3 px-4 py-2.5 text-fg-200 hover:bg-surface-2 hover:text-fg-100 transition-colors w-full"
              >
                <LogOut className="w-4 h-4 text-fg-400" />
                <span>Sign Out</span>
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
