import React, { useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { Moon, Sun } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Pulse, TickerItem } from '@/components/ui/huds';
import { UserAvatar } from '@/components/ui/UserAvatar';
import { useDashboard } from '@/lib/dataconnect-hooks';
import { useWorkspaceNotifications } from '@/lib/realtime-hooks';
import { useWorkspace } from '@/lib/workspace';
import { useAuth } from '@/lib/auth';
import { isDemoHost } from '@/lib/demo';
import { SkBadge, CopilotFab, CopilotModal } from '@/components/sidekick';

const NAV_ITEMS = [
  { path: '/app', label: 'Today', exact: true, badgeKey: 'today' as const },
  { path: '/app/conversations', label: 'Conversations', badgeKey: 'conversations' as const },
  { path: '/app/customers', label: 'Customers' },
  { path: '/app/meetings', label: 'Meetings' },
  { path: '/app/renewals', label: 'Renewals' },
  { path: '/app/sidekick', label: 'Sidekick', showBadge: true },
  { path: '/app/handbook', label: 'Handbook' },
];


// Format ARR for ticker display
function formatARR(cents: number): string {
  const amount = cents / 100;
  if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
  if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
  return `$${amount}`;
}

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  // Dark mode is default (class="dark" on <html>)
  const [isDark, setIsDark] = React.useState(true);
  const { workspaceId } = useWorkspace();
  const { isAnonymous } = useAuth();
  const { data: stats } = useDashboard();

  // Real-time notifications from Firestore
  const notifications = useWorkspaceNotifications(workspaceId);

  // Sidekick questions count - prefer real-time, fall back to stats
  const unansweredCount = notifications?.sidekick_questions ?? 0;

  // Today queue count
  const todayCount = notifications?.today_count ?? 0;

  // Conversations new-message dot: appears when conversations_count changes after mount
  const conversationsCountRef = useRef<number | undefined>(undefined);
  const [hasNewConversations, setHasNewConversations] = useState(false);

  React.useEffect(() => {
    const count = notifications?.conversations_count;
    if (count === undefined) return;
    if (conversationsCountRef.current !== undefined && count !== conversationsCountRef.current) {
      setHasNewConversations(true);
    }
    conversationsCountRef.current = count;
  }, [notifications?.conversations_count]);

  React.useEffect(() => {
    if (location.pathname.startsWith('/app/conversations')) {
      setHasNewConversations(false);
    }
  }, [location.pathname]);

  // Copilot modal state
  const [copilotOpen, setCopilotOpen] = React.useState(false);

  // Demo mode: Sidekick auto-opens once as the guided tour — but only for an
  // anonymous demo visitor. A real logged-in account (even locally with
  // VITE_DEMO_ENABLED) never gets the auto-popup. Waits for the workspace to load so
  // the guide's sweep button has a workspaceId to act on. Fires once per session.
  const demoAutoOpenedRef = useRef(false);
  React.useEffect(() => {
    if (!isDemoHost() || !isAnonymous || !workspaceId || demoAutoOpenedRef.current) return;
    // Auto-open once per workspace (survives refresh via sessionStorage; keyed to the
    // workspace so a brand-new demo account in the same tab still opens). After the
    // first open the FAB pulse invites the visitor back and reopening resumes the
    // right beat — so a refresh doesn't re-pop the tour in their face.
    // Open immediately once workspaceId + isAnonymous are both true (no timer): a
    // delayed open's cleanup races with the provisioning settle and can be cancelled
    // before it fires.
    const openedKey = `herofy_demo_tour_opened:${workspaceId}`;
    try {
      if (sessionStorage.getItem(openedKey) === '1') return;
      sessionStorage.setItem(openedKey, '1');
    } catch {
      /* storage unavailable — fall through and auto-open this mount */
    }
    demoAutoOpenedRef.current = true;
    setCopilotOpen(true);
  }, [workspaceId, isAnonymous]);

  // Cmd+K / Ctrl+K keyboard shortcut for Copilot
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCopilotOpen(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Toggle dark class on <html> element
  React.useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  return (
    <div
      className={cn(
        'min-h-screen flex flex-col pt-8 pl-4 pr-6 sm:pl-8 sm:pr-12 max-w-[1600px] mx-auto pb-32',
        // Push-drawer: when the Sidekick drawer (28rem) is open, reflow the content to
        // its left instead of letting it overlay the right rail. md+ only — on small
        // screens the drawer is ~full width, so it stays an overlay there.
        'transition-[margin] duration-300 ease-out',
        copilotOpen && 'md:mr-[28rem]'
      )}
    >
      <header className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-16 gap-8">
        <NavLink to="/app" className="flex items-center gap-4">
          <img src={isDark ? "/logo.svg" : "/logo-light.svg"} alt="Herofy" className="h-14" />
        </NavLink>
        <nav className="flex flex-wrap items-center gap-6 sm:gap-8">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.exact}
              className={({ isActive }) => cn(
                "text-xs tracking-[0.2em] uppercase transition-colors relative hover:text-accent",
                isActive ? "text-fg-100 font-bold" : "text-fg-400"
              )}
            >
              {({ isActive }) => (
                <span className="flex items-center gap-1.5">
                  {item.label}
                  {item.showBadge && unansweredCount > 0 && <SkBadge count={unansweredCount} />}
                  {item.badgeKey === 'today' && todayCount > 0 && (
                    <span className="px-1 min-w-[18px] h-[18px] flex items-center justify-center text-[10px] font-mono font-bold bg-surface-2 border border-border text-fg-300 rounded-sm">
                      {todayCount}
                    </span>
                  )}
                  {item.badgeKey === 'conversations' && hasNewConversations && (
                    <span className="w-1.5 h-1.5 rounded-full bg-rust-500 shrink-0" />
                  )}
                  {isActive && (
                    <motion.div
                      layoutId="nav-indicator"
                      className="absolute -bottom-2 left-0 right-0 h-[1px] bg-accent"
                      initial={false}
                      transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    />
                  )}
                </span>
              )}
            </NavLink>
          ))}

          <div className="flex items-center gap-2 ml-4">
            <button
              onClick={() => setIsDark(!isDark)}
              className={cn(
                "w-8 h-8 relative outline-none flex items-center justify-center border cursor-pointer transition-colors",
                isDark
                  ? "bg-surface-2 border-border text-fg-400 hover:text-accent"
                  : "bg-accent-bg border-accent/30 text-accent"
              )}
              title={isDark ? "Switch to day mode" : "Switch to night mode"}
            >
              {isDark ? (
                <Moon className="w-4 h-4" />
              ) : (
                <Sun className="w-4 h-4" />
              )}
            </button>
          </div>

          <div className="ml-4">
            <UserAvatar />
          </div>
        </nav>
      </header>

      <main className="flex-1 relative">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, scale: 0.995 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.005 }}
            transition={{ duration: 0.4, ease: [0.19, 1, 0.22, 1] }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Fixed Ticker Bar — reflows to the drawer's left edge when it's open (push-drawer). */}
      <footer
        className={cn(
          'fixed bottom-0 left-0 right-0 h-12 border-t border-border bg-surface z-50 flex items-center overflow-hidden transition-all duration-300',
          copilotOpen && 'md:right-[28rem]'
        )}
      >
        <div className="bg-accent h-full px-6 flex items-center gap-3 relative z-20 shadow-[12px_0_24px_rgba(0,0,0,0.3)]">
          <Pulse active continuous className="h-3 w-3" />
          <span className="text-page font-mono text-sm font-bold tracking-[0.15em] uppercase">LIVE_OPS</span>
        </div>
        <div className="flex-1 flex items-center overflow-x-auto no-scrollbar relative z-10">
          <TickerItem
            label="SK_OPEN_QS"
            value={String(unansweredCount).padStart(2, '0')}
            className={unansweredCount > 0 ? "text-accent" : undefined}
          />
          <TickerItem
            label="ESCALATIONS"
            value={String(stats?.escalations ?? '-').padStart(2, '0')}
            trend={stats?.escalations && stats.escalations > 0 ? "down" : undefined}
          />
          <TickerItem
            label="ONBOARDING"
            value={String(stats?.active_onboardings ?? '-').padStart(2, '0')}
          />
          <TickerItem
            label="RENEWALS_30D"
            value={String(stats?.renewals_30_days ?? '-').padStart(2, '0')}
            trend={stats?.renewals_30_days && stats.renewals_30_days > 2 ? "neutral" : undefined}
          />
          <TickerItem
            label="PENDING_APPROVALS"
            value={String(stats?.pending_approvals ?? '-').padStart(2, '0')}
            trend={stats?.pending_approvals && stats.pending_approvals > 0 ? "up" : undefined}
          />
          <TickerItem
            label="PORTFOLIO_ARR"
            value={stats?.total_arr_cents ? formatARR(stats.total_arr_cents) : '-'}
          />
        </div>
        <div className="px-6 border-l border-border bg-surface h-full flex items-center gap-4 relative z-20 transition-colors shadow-[-12px_0_24px_rgba(0,0,0,0.3)]">
          <span className="text-[11px] font-mono uppercase tracking-[0.25em] text-fg-400 hidden sm:block">Herofy v1.0</span>
          <div className="h-2 w-2 rounded-full bg-signal-ok shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
        </div>
      </footer>

      {/* Floating Copilot FAB - always visible */}
      <div className="fixed bottom-24 right-6 z-40">
        <CopilotFab
          count={unansweredCount}
          tour={isDemoHost() && isAnonymous && !copilotOpen}
          onClick={() => setCopilotOpen(true)}
        />
      </div>

      {/* Copilot Modal */}
      <CopilotModal
        isOpen={copilotOpen}
        onClose={() => setCopilotOpen(false)}
      />
    </div>
  );
}
