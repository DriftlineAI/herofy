import { useParams, useNavigate } from 'react-router-dom';
import { ExternalLink } from 'lucide-react';
import { useSidekickItems, useCustomerTrends } from '@/lib/dataconnect-hooks';
import { RightRail } from '@/components/sidekick';
import { BackBar, MobileLoading } from '@/components/mobile/mobileShared';

// Slimmed customer profile — NOT the 180KB desktop component. It folds the
// desktop right-rail context (meta, health, trends, Sidekick items) into a single
// column, and links out to the full desktop profile for deep work.
export default function MobileCustomerDetail() {
  const { customerId } = useParams<{ customerId: string }>();
  const navigate = useNavigate();
  const id = customerId || null;

  const { data: sidekickData, isLoading } = useSidekickItems(id);
  const { data: trendsData, isLoading: trendsLoading } = useCustomerTrends(id);

  const railData = sidekickData
    ? {
        customer: {
          id: sidekickData.customer.id,
          name: sidekickData.customer.name,
          refcode: sidekickData.customer.refcode || '',
          tier: sidekickData.customer.tier || 'STANDARD',
          arr: sidekickData.customer.arr || '$0',
          lifecycle: sidekickData.customer.lifecycle || 'active',
          day: sidekickData.customer.day,
          health: sidekickData.customer.health,
          healthColor: sidekickData.customer.health_color,
          healthScore: sidekickData.customer.health_score,
          sentiment: sidekickData.customer.sentiment,
          sentimentColor: sidekickData.customer.sentiment_color,
          signals: sidekickData.customer.signals,
        },
        items: sidekickData.items.map((item) => ({
          id: item.id,
          type: item.type as 'tip' | 'asking' | 'resolved' | 'observed' | 'working',
          question: item.question,
          resolution: item.resolution,
          text: item.text,
          task: item.task,
          step: item.step,
          stepNum: item.step_num,
          total: item.total_steps,
          by: item.resolved_by,
          timestamp: item.timestamp_label,
          isCurrentItem: item.is_current_item,
        })),
        openItemsCount: sidekickData.open_count,
        resolvedItemsCount: sidekickData.resolved_count,
      }
    : null;

  return (
    <div>
      <BackBar
        title={railData?.customer.name || 'Customer'}
        subtitle={railData ? `${railData.customer.arr} ARR · ${railData.customer.lifecycle}` : undefined}
        fallback="/m/customers"
      />

      {isLoading && !railData ? (
        <MobileLoading rows={3} />
      ) : !railData ? (
        <div className="px-4 py-10 text-center text-sm text-fg-400">No context available for this account.</div>
      ) : (
        <div className="p-4">
          <RightRail
            customer={railData.customer}
            items={railData.items}
            openItemsCount={railData.openItemsCount}
            resolvedItemsCount={railData.resolvedItemsCount}
            sentimentTrend={trendsData?.sentiment}
            engagementTrend={trendsData?.engagement}
            trendsLoading={trendsLoading}
            onOpenCustomer={() => navigate(`/m/customers/${railData.customer.id}`)}
            onOpenSidekick={() => navigate('/m/sidekick')}
            onViewPlans={() => navigate(`/app/customers/${railData.customer.id}?tab=plans`)}
          />

          <a
            href={`/app/customers/${railData.customer.id}`}
            className="mt-4 flex w-full items-center justify-center gap-2 border border-border px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-fg-300 transition-colors hover:text-fg-100"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open full profile
          </a>
        </div>
      )}
    </div>
  );
}
