import { createContext, useContext, useState, useEffect, useCallback, useMemo, type ReactNode } from 'react';
import { useAuth } from './auth';

// Default workspace ID for development (matches seed data)
const DEFAULT_WORKSPACE_ID = '11111111-1111-1111-1111-111111111111';
const WORKSPACE_ID_KEY = 'herofy_workspace_id';

interface WorkspaceContextType {
  workspaceId: string | null;
  workspaceName: string | null;
  loading: boolean;
  setWorkspaceId: (id: string) => void;
}

const WorkspaceContext = createContext<WorkspaceContextType>({
  workspaceId: null,
  workspaceName: null,
  loading: true,
  setWorkspaceId: () => {},
});

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const [workspaceId, setWorkspaceIdState] = useState<string | null>(null);
  const [workspaceName, setWorkspaceName] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;

    if (user) {
      // Try to load saved workspace ID for this user
      const savedId = localStorage.getItem(`${WORKSPACE_ID_KEY}_${user.uid}`);

      if (savedId) {
        setWorkspaceIdState(savedId);
      } else if (!user.isAnonymous) {
        // Use default workspace ID for development
        // TODO: When backend is ready, fetch user's workspace from database
        setWorkspaceIdState(DEFAULT_WORKSPACE_ID);
      }
      // Anonymous (demo) users: leave workspaceId null until /demo provisioning sets the real one,
      // so AppLayout never briefly queries the default workspace.

      // Load workspace name from onboarding data
      try {
        const workspaceData = localStorage.getItem('herofy_workspace_data');
        if (workspaceData) {
          const parsed = JSON.parse(workspaceData);
          setWorkspaceName(parsed.name || null);
        }
      } catch {
        // Ignore parse errors
      }
    } else {
      setWorkspaceIdState(null);
      setWorkspaceName(null);
    }

    setLoading(false);
  }, [user, authLoading]);

  const setWorkspaceId = useCallback((id: string) => {
    if (user) {
      localStorage.setItem(`${WORKSPACE_ID_KEY}_${user.uid}`, id);
    }
    setWorkspaceIdState(id);
  }, [user]);

  const value = useMemo(
    () => ({ workspaceId, workspaceName, loading, setWorkspaceId }),
    [workspaceId, workspaceName, loading, setWorkspaceId]
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return context;
}

// Hook that ensures workspace ID is available (throws if not)
export function useRequiredWorkspaceId(): string {
  const { workspaceId, loading } = useWorkspace();

  if (loading) {
    throw new Error('Workspace is still loading');
  }

  if (!workspaceId) {
    throw new Error('No workspace ID available');
  }

  return workspaceId;
}
