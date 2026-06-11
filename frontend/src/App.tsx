import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './AppLayout';
import { DataConnectTest } from './components/DataConnectTest';
import { RequireAuth, RequireSetup } from '@/lib/auth';
import { isDemoHost } from '@/lib/demo';

// Pages
import Landing from '@/pages/Landing';
import Login from '@/pages/Login';
import DemoLanding from '@/pages/DemoLanding';
import SetupWizard from '@/pages/Setup';
import JoinWorkspace from '@/pages/JoinWorkspace';
import Today from '@/pages/Today';
import ThisWeek from '@/pages/ThisWeek';
import Conversations from '@/pages/Conversations';
import Customers from '@/pages/Customers';
import CustomerDetail from '@/pages/CustomerDetail';
import AtRisk from '@/pages/AtRisk';
import Onboarding from '@/pages/Onboarding';
import Renewals from '@/pages/Renewals';
import RenewalWorkspace from '@/pages/RenewalWorkspace';
import MeetingPrep from '@/pages/MeetingPrep';
import Meetings from '@/pages/Meetings';
import Handbook from '@/pages/Handbook';
import PlanApproval from '@/pages/PlanApproval';
import Handoffs from '@/pages/Handoffs';
import HandoffDetail from '@/pages/HandoffDetail';
import ConversationDetail from '@/pages/ConversationDetail';
import Sidekick from '@/pages/Sidekick';
import SidekickQuestion from '@/pages/SidekickQuestion';
import NeedDetail from '@/pages/NeedDetail';
import UserSettings from '@/pages/UserSettings';
import AccountSettings from '@/pages/AccountSettings';
import OAuthCallback from '@/pages/OAuthCallback';
import InviteAccept from '@/pages/InviteAccept';
import PipelineTest from '@/pages/PipelineTest';
import Lab from '@/pages/Lab';

// Mobile (/m) route tree — simplified, single-column, drill-down companion views.
import { MobileLayout } from '@/components/mobile/MobileLayout';
import MobileToday from '@/pages/mobile/MobileToday';
import MobileConversations from '@/pages/mobile/MobileConversations';
import MobileConversationDetail from '@/pages/mobile/MobileConversationDetail';
import MobileCustomers from '@/pages/mobile/MobileCustomers';
import MobileCustomerDetail from '@/pages/mobile/MobileCustomerDetail';
import MobileMeetings from '@/pages/mobile/MobileMeetings';
import MobileSidekick from '@/pages/mobile/MobileSidekick';
import MobileSidekickDetail from '@/pages/mobile/MobileSidekickDetail';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* On the demo host, the bare domain is the demo entry point, not the marketing page. */}
        <Route path="/" element={isDemoHost() ? <Navigate to="/demo" replace /> : <Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/demo" element={<DemoLanding />} />
        <Route path="/setup" element={<RequireAuth><SetupWizard /></RequireAuth>} />
        <Route path="/join" element={<RequireAuth><JoinWorkspace /></RequireAuth>} />

        {/* OAuth callback - outside auth guard since user is redirected from provider */}
        <Route path="/integrations/:provider/callback" element={<OAuthCallback />} />

        {/* Invitation acceptance - outside auth guard for login redirect */}
        <Route path="/invite/:token" element={<InviteAccept />} />

        <Route path="/app" element={<RequireAuth><RequireSetup><AppLayout /></RequireSetup></RequireAuth>}>
          <Route index element={<Today />} />
          <Route path="week" element={<ThisWeek />} />
          <Route path="conversations" element={<Conversations />} />
          <Route path="conversations/:threadId" element={<ConversationDetail />} />
          <Route path="needs/:needId" element={<NeedDetail />} />
          <Route path="customers" element={<Customers />} />
          <Route path="customers/:customerId" element={<CustomerDetail />} />
          <Route path="at-risk" element={<AtRisk />} />
          <Route path="onboarding" element={<Onboarding />} />
          <Route path="onboarding/:customerId" element={<Onboarding />} />
          <Route path="renewals" element={<Renewals />} />
          <Route path="renewals/:customerId" element={<RenewalWorkspace />} />
          <Route path="meetings" element={<Meetings />} />
          <Route path="meetings/:meetingId" element={<MeetingPrep />} />
          <Route path="meeting-prep" element={<MeetingPrep />} />
          <Route path="handbook" element={<Handbook />} />
          <Route path="handbook/*" element={<Handbook />} />
          <Route path="plans/:planId" element={<PlanApproval />} />
          <Route path="handoffs" element={<Handoffs />} />
          <Route path="handoffs/:briefId" element={<HandoffDetail />} />
          <Route path="sidekick" element={<Sidekick />} />
          <Route path="sidekick/:runId" element={<SidekickQuestion />} />
          <Route path="today" element={<Today />} />
          <Route path="settings" element={<UserSettings />} />
          <Route path="settings/account" element={<AccountSettings />} />
          <Route path="test-db" element={<DataConnectTest />} />
          <Route path="dev/pipeline" element={<PipelineTest />} />
          <Route path="dev/lab" element={<Lab />} />
        </Route>

        {/* Mobile companion — same auth/setup guards as /app */}
        <Route path="/m" element={<RequireAuth><RequireSetup><MobileLayout /></RequireSetup></RequireAuth>}>
          <Route index element={<MobileToday />} />
          <Route path="conversations" element={<MobileConversations />} />
          <Route path="conversations/:threadId" element={<MobileConversationDetail />} />
          <Route path="customers" element={<MobileCustomers />} />
          <Route path="customers/:customerId" element={<MobileCustomerDetail />} />
          <Route path="meetings" element={<MobileMeetings />} />
          <Route path="sidekick" element={<MobileSidekick />} />
          <Route path="sidekick/:runId" element={<MobileSidekickDetail />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
