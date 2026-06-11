import { NavLink } from 'react-router-dom';
import { Home, MessageSquare, Users, Calendar, Zap, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SkBadge } from '@/components/sidekick';

export interface TabBadges {
  today?: number;
  conversations?: boolean;
  sidekick?: number;
}

interface Tab {
  to: string;
  end?: boolean;
  label: string;
  icon: LucideIcon;
  key: keyof TabBadges | 'customers' | 'meetings';
}

const TABS: Tab[] = [
  { to: '/m', end: true, label: 'Today', icon: Home, key: 'today' },
  { to: '/m/conversations', label: 'Inbox', icon: MessageSquare, key: 'conversations' },
  { to: '/m/customers', label: 'Customers', icon: Users, key: 'customers' },
  { to: '/m/meetings', label: 'Meetings', icon: Calendar, key: 'meetings' },
  { to: '/m/sidekick', label: 'Sidekick', icon: Zap, key: 'sidekick' },
];

export function MobileTabBar({ badges }: { badges?: TabBadges }) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-50 grid h-16 grid-cols-5 border-t border-border bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
      {TABS.map((tab) => {
        const Icon = tab.icon;
        return (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              cn(
                'relative flex flex-col items-center justify-center gap-1 transition-colors',
                isActive ? 'text-accent' : 'text-fg-400 hover:text-fg-200',
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute inset-x-7 top-0 h-0.5 bg-accent" />}
                <span className="relative">
                  <Icon className="h-5 w-5" strokeWidth={isActive ? 2.4 : 1.8} />
                  {tab.key === 'sidekick' && !!badges?.sidekick && (
                    <span className="absolute -right-2.5 -top-1.5">
                      <SkBadge count={badges.sidekick} />
                    </span>
                  )}
                  {tab.key === 'today' && !!badges?.today && (
                    <span className="absolute -right-2.5 -top-1.5 flex h-[15px] min-w-[15px] items-center justify-center rounded-full bg-accent px-0.5 font-mono text-[9px] font-bold text-page">
                      {badges.today}
                    </span>
                  )}
                  {tab.key === 'conversations' && badges?.conversations && (
                    <span className="absolute -right-1 -top-0.5 h-1.5 w-1.5 rounded-full bg-rust-500" />
                  )}
                </span>
                <span className="font-mono text-[9px] uppercase tracking-[0.12em]">{tab.label}</span>
              </>
            )}
          </NavLink>
        );
      })}
    </nav>
  );
}
