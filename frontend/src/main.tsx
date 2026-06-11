import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App.tsx';
import './index.css';
import './components/sidekick/sidekick.css';

// Initialize Firebase & Data Connect (must import before using SDK hooks)
import './lib/firebase';
import { AuthProvider } from './lib/auth';
import { WorkspaceProvider } from './lib/workspace';
import { UserProvisioner } from './lib/user-provisioning';

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <WorkspaceProvider>
          <UserProvisioner>
            <App />
          </UserProvisioner>
        </WorkspaceProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
