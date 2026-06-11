import React from 'react';
import { RefCode } from '@/components/ui/huds';
import { NavLink, Link } from 'react-router-dom';
import { useWeeklyDispatch } from '@/lib/dataconnect-hooks';
import { useAuth } from '@/lib/auth';
import { Calendar, Settings, Coffee } from 'lucide-react';

// Loading skeleton for the week view
function LoadingSkeleton() {
  return (
    <div className="space-y-16 animate-pulse">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="grid grid-cols-1 md:grid-cols-12 gap-6">
          <div className="md:col-span-3 border-l-2 border-charcoal-700 pl-4">
            <div className="h-4 w-24 bg-charcoal-700 rounded" />
            <div className="h-3 w-16 bg-charcoal-800 rounded mt-2" />
          </div>
          <div className="md:col-span-9 space-y-4">
            <div className="h-14 bg-charcoal-800 rounded border border-charcoal-700" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Empty state component
function EmptyState() {
  const { hasCompletedSetup, isStaff } = useAuth();

  // Only workspace owners (who completed setup) or staff can manage integrations
  const canManageIntegrations = hasCompletedSetup || isStaff;

  return (
    <div className="flex flex-col items-center justify-center py-24">
      <div className="w-20 h-20 rounded-full bg-charcoal-800 flex items-center justify-center mb-6 border border-charcoal-700">
        <Coffee className="w-10 h-10 text-charcoal-500" />
      </div>

      <h2 className="font-serif text-2xl text-cream-100 mb-2">Clear skies ahead</h2>
      <p className="text-charcoal-400 text-center max-w-md mb-8">
        No meetings or activities scheduled for this week. Connect your calendar to start seeing your weekly dispatch.
      </p>

      <div className="flex flex-col sm:flex-row gap-4">
        <Link
          to="/app/calendar"
          className="inline-flex items-center gap-2 bg-charcoal-800 hover:bg-charcoal-700 text-cream-200 px-6 py-3 font-mono text-xs uppercase tracking-widest transition-colors border border-charcoal-700"
        >
          <Calendar className="w-4 h-4" />
          View Calendar
        </Link>

        {canManageIntegrations && (
          <Link
            to="/app/settings/account"
            className="inline-flex items-center gap-2 bg-charcoal-800 hover:bg-charcoal-700 text-cream-200 px-6 py-3 font-mono text-xs uppercase tracking-widest transition-colors border border-charcoal-700"
          >
            <Settings className="w-4 h-4" />
            Connect Calendar
          </Link>
        )}
      </div>
    </div>
  );
}

export default function ThisWeek() {
  const { data, isLoading, error } = useWeeklyDispatch();

  // Check if the week has any items
  const totalItems = data?.days.reduce((sum, day) => sum + day.count, 0) || 0;

  return (
    <div className="max-w-5xl mx-auto">
      <header className="mb-16 border-b border-charcoal-700 pb-6 flex justify-between items-end">
        <div>
          <h1 className="text-xl tracking-widest text-cream-200 uppercase mb-2">The Weekly Dispatch</h1>
          <p className="text-cream-400 font-serif text-lg italic">Patterns emerge from the noise.</p>
        </div>
        <div className="flex gap-4">
          <NavLink to="/app" className="text-xs font-mono uppercase tracking-widest text-charcoal-400 hover:text-cream-200 transition-colors">&larr; Back to Today</NavLink>
        </div>
      </header>

      {isLoading ? (
        <LoadingSkeleton />
      ) : error ? (
        <div className="hud-border p-8 border-l-4 border-l-rust-500">
          <div className="text-[10px] uppercase tracking-[0.3em] text-rust-500 font-bold mb-4">
            Connection Error
          </div>
          <p className="text-cream-200">Unable to load weekly dispatch. Please try again.</p>
        </div>
      ) : totalItems === 0 ? (
        <EmptyState />
      ) : (
        <>
          <div className="space-y-16">
            {data?.days.map((day) => (
              <div key={day.day} className="grid grid-cols-1 md:grid-cols-12 gap-6 group">
                <div className="md:col-span-3 border-l-2 border-charcoal-700 group-hover:border-rust-500 transition-colors pl-4">
                  <h2 className="text-sm tracking-widest text-cream-300 font-mono">{day.day}</h2>
                  <div className="text-rust-500 text-xs mt-1 font-mono">// {day.count} ITEMS</div>
                </div>
                <div className="md:col-span-9 space-y-4">
                  {day.items.length > 0 ? (
                    day.items.map((item, i) => (
                      <div key={item.id} className="flex items-center gap-6 p-4 hud-border group-hover:border-rust-500/50 transition-colors">
                        <RefCode>W-{day.day.substring(0,3)}-0{i+1}</RefCode>
                        <span className="text-cream-100 font-serif text-lg">
                          {item.customer_name} {item.title.toLowerCase().includes(item.customer_name.toLowerCase()) ? '' : `- ${item.title}`}
                        </span>
                        {item.scheduled_at && (
                          <span className="text-charcoal-500 text-xs font-mono ml-auto">
                            {new Date(item.scheduled_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
                          </span>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="p-4 border border-dashed border-charcoal-700 text-charcoal-500 font-mono text-sm uppercase">
                      Clear airspace
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {(data?.resolved_summary || data?.carried_forward_summary) && (
            <div className="mt-24 border-t-2 border-charcoal-700 pt-12">
              <h3 className="text-sm tracking-widest text-cream-300 font-mono mb-8">CLOSING THE WEEK</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {data?.resolved_summary && (
                  <div className="bg-charcoal-900/50 p-6 border border-charcoal-800">
                    <div className="text-rust-400 text-xs uppercase tracking-widest mb-4">Resolved</div>
                    <p className="text-cream-300">{data.resolved_summary}</p>
                  </div>
                )}
                {data?.carried_forward_summary && (
                  <div className="bg-charcoal-900/50 p-6 border border-charcoal-800">
                    <div className="text-charcoal-400 text-xs uppercase tracking-widest mb-4">Carried Forward</div>
                    <p className="text-cream-300">{data.carried_forward_summary}</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
