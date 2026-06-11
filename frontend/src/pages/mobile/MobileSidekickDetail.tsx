import { useParams, useNavigate } from 'react-router-dom';
import { useSidekickQuestions } from '@/lib/dataconnect-hooks';
import { FocusPane } from '@/components/sidekick/FocusPane';
import { BackBar, MobileLoading, MobileEmpty } from '@/components/mobile/mobileShared';

// Full-screen focus pane for one paused agent run. Reuses the desktop FocusPane
// (self-contained question stack + submit), resolving the queue item by run_id.
export default function MobileSidekickDetail() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { data, isLoading } = useSidekickQuestions();

  const item = (data?.items || []).find((i) => i.run_id === runId) || null;

  return (
    <div className="flex min-h-[calc(100dvh-3.5rem-4rem)] flex-col">
      <BackBar
        title={item?.customer_name || 'Sidekick'}
        subtitle={item ? item.agent_type.replace(/_/g, '-') : undefined}
        fallback="/m/sidekick"
      />

      {isLoading && !item ? (
        <MobileLoading rows={3} />
      ) : !item ? (
        <MobileEmpty
          title="Question not found"
          body="It may already be answered. Head back to the queue."
        />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <FocusPane
            item={item}
            onAnswered={() => navigate('/m/sidekick', { replace: true })}
          />
        </div>
      )}
    </div>
  );
}
