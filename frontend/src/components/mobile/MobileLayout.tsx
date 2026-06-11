import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useWorkspace } from '@/lib/workspace';
import { useWorkspaceNotifications } from '@/lib/realtime-hooks';
import { UserAvatar } from '@/components/ui/UserAvatar';
import { CopilotFab, CopilotModal } from '@/components/sidekick';
import { MobileTabBar } from './MobileTabBar';

// Parallel shell to AppLayout for the /m route tree: a sticky top bar, a single
// scrolling content column, a floating Copilot FAB, and a fixed bottom tab bar.
// No desktop ticker / horizontal nav — those don't fit a phone.
export function MobileLayout() {
  const { workspaceId } = useWorkspace();
  const notifications = useWorkspaceNotifications(workspaceId);
  const location = useLocation();

  const [copilotOpen, setCopilotOpen] = useState(false);

  // Mobile is dark-first (matches the home-screen install theme color).
  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  const sidekickCount = notifications?.sidekick_questions ?? 0;
  const todayCount = notifications?.today_count ?? 0;

  // New-conversation dot: flips on when the live count changes off a route.
  const convCountRef = useRef<number | undefined>(undefined);
  const [hasNewConversations, setHasNewConversations] = useState(false);
  useEffect(() => {
    const count = notifications?.conversations_count;
    if (count === undefined) return;
    if (convCountRef.current !== undefined && count !== convCountRef.current) {
      setHasNewConversations(true);
    }
    convCountRef.current = count;
  }, [notifications?.conversations_count]);
  useEffect(() => {
    if (location.pathname.startsWith('/m/conversations')) setHasNewConversations(false);
  }, [location.pathname]);

  return (
    <div className="flex min-h-[100dvh] flex-col bg-page">
      <header className="z-40 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-surface/95 px-4 pt-[env(safe-area-inset-top)] backdrop-blur">
        <NavLink to="/m" className="flex items-center gap-2">
          <img src="/logo.svg" alt="Herofy" className="h-7" />
          <span className="rounded-sm border border-border px-1 py-0.5 font-mono text-[9px] uppercase tracking-[0.2em] text-fg-400">
            Mobile
          </span>
        </NavLink>
        <UserAvatar />
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto pb-20">
        <Outlet />
      </main>

      <div className="fixed bottom-20 right-4 z-40">
        <CopilotFab count={sidekickCount} onClick={() => setCopilotOpen(true)} />
      </div>
      <CopilotModal isOpen={copilotOpen} onClose={() => setCopilotOpen(false)} />

      <MobileTabBar
        badges={{ today: todayCount, sidekick: sidekickCount, conversations: hasNewConversations }}
      />
    </div>
  );
}
