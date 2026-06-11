import React, { createContext, useContext, useEffect, useState, useCallback, useMemo, type ReactNode } from 'react';
import { auth, onAuthStateChanged, signOut as firebaseSignOut, type User } from './firebase';
import { useGetUserById, useCompleteUserWorkspaceSetup } from '@/dataconnect-generated/react';
import { isDemoHost } from './demo';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  isAnonymous: boolean;
  isStaff: boolean;
  hasCompletedSetup: boolean;
  setupLoading: boolean;
  completeSetup: () => Promise<void>;
  signOut: () => Promise<void>;
}

// Fallback to localStorage during migration (when SDK not regenerated yet)
const SETUP_COMPLETE_KEY = 'herofy_setup_complete';

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  isAuthenticated: false,
  isAnonymous: false,
  isStaff: false,
  hasCompletedSetup: false,
  setupLoading: true,
  completeSetup: async () => {},
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasCompletedSetupLocal, setHasCompletedSetupLocal] = useState(false);

  // Get current user data from DataConnect using explicit userId
  // (useGetCurrentUser uses auth.uid which doesn't work with real Firebase Auth + DataConnect emulator)
  const { data: currentUserData, isLoading: userDataLoading, refetch: refetchCurrentUser } = useGetUserById(
    { userId: user?.uid || '' },
    { enabled: !!user?.uid }
  );

  // Mutation for completing user setup
  const completeUserWorkspaceSetup = useCompleteUserWorkspaceSetup();

  // DEBUG: Track query refetches
  const queryRefetchCount = React.useRef(0);
  React.useEffect(() => {
    queryRefetchCount.current++;
    console.log('[Auth] useGetUserById refetch #' + queryRefetchCount.current, {
      hasData: !!currentUserData?.users?.[0],
      isLoading: userDataLoading,
      userId: user?.uid
    });
  }, [currentUserData, userDataLoading, user?.uid]);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);

      if (firebaseUser) {
        console.log('User signed in:', firebaseUser.email);
        // Load localStorage fallback while DataConnect loads
        const setupKey = `${SETUP_COMPLETE_KEY}_${firebaseUser.uid}`;
        const completed = localStorage.getItem(setupKey) === 'true';
        setHasCompletedSetupLocal(completed);
      } else {
        console.log('User signed out');
        setHasCompletedSetupLocal(false);
      }
    });

    return () => unsubscribe();
  }, []);

  // Check DataConnect for setup status
  // Look for hasCompletedSetup field on workspace membership
  // This will work after SDK regeneration
  const hasCompletedSetupFromDC = (() => {
    const dbUser = currentUserData?.users?.[0];
    if (!dbUser) return false;

    // Get first workspace membership and check hasCompletedSetup
    const memberships = dbUser.workspaceMembers_on_user || [];
    if (memberships.length === 0) return false;

    // Check if any membership has completed setup
    // The hasCompletedSetup field will be available after SDK regeneration
    const firstMembership = memberships[0] as Record<string, unknown>;
    return firstMembership?.hasCompletedSetup === true;
  })();

  // Use DataConnect value if available, fall back to localStorage
  const setupLoading = loading || (user && userDataLoading);
  const hasCompletedSetup = hasCompletedSetupFromDC || hasCompletedSetupLocal;

  const isStaff = user?.email?.endsWith('@herofy.ai') ?? false;

  const signOutFn = useCallback(async () => {
    try {
      await firebaseSignOut();
      // Clear all localStorage
      localStorage.clear();
      sessionStorage.clear();
      setHasCompletedSetupLocal(false);
      console.log('[Auth] User signed out, storage cleared');
    } catch (error) {
      console.error('[Auth] Sign out error:', error);
      throw error;
    }
  }, []);

  const completeSetupFn = useCallback(async () => {
    const authDbUser = currentUserData?.users?.[0];
    console.log('[Auth] completeSetup called', { userId: user?.uid, hasMemberships: !!(authDbUser?.workspaceMembers_on_user?.length) });
    if (!user) {
      console.log('[Auth] No user, skipping setup completion');
      return;
    }

    // Get workspace ID from current user data
    const memberships = authDbUser?.workspaceMembers_on_user || [];
    if (memberships.length > 0) {
      const workspaceId = memberships[0].workspace?.id;
      console.log('[Auth] Found workspace membership:', { workspaceId });
      if (workspaceId) {
        try {
          console.log('[Auth] Calling completeUserWorkspaceSetup mutation');
          // Call the DataConnect mutation to update per-user hasCompletedSetup
          await completeUserWorkspaceSetup.mutateAsync({
            workspaceId,
            userId: user.uid,
          });
          console.log('[Auth] Setup status saved to database (hasCompletedSetup=true)');
          // Refetch user data to update hasCompletedSetup in context
          await refetchCurrentUser();
        } catch (error) {
          console.warn('[Auth] Failed to save setup status to database:', error);
          // Fall back to localStorage on error
        }
      }
    }

    // Also save to localStorage as fallback
    const setupKey = `${SETUP_COMPLETE_KEY}_${user.uid}`;
    localStorage.setItem(setupKey, 'true');
    setHasCompletedSetupLocal(true);
    console.log('[Auth] Setup marked complete in localStorage');
  }, [user, currentUserData, completeUserWorkspaceSetup, refetchCurrentUser]);

  const value = useMemo(
    () => ({
      user,
      loading,
      isAuthenticated: !!user,
      isAnonymous: !!user?.isAnonymous,
      isStaff,
      hasCompletedSetup,
      setupLoading: setupLoading ?? false,
      completeSetup: completeSetupFn,
      signOut: signOutFn,
    }),
    [user, loading, isStaff, hasCompletedSetup, setupLoading, completeSetupFn, signOutFn]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

// Route guard component - requires authentication
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isAnonymous, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-charcoal-900">
        <div className="text-cream-100">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Redirect to login
    window.location.href = '/login';
    return null;
  }

  // Anonymous (demo) users may only exist on the demo host — bounce them out of the real app.
  if (isAnonymous && !isDemoHost()) {
    window.location.href = '/login';
    return null;
  }

  return <>{children}</>;
}

// Route guard component - requires setup completion
export function RequireSetup({ children }: { children: ReactNode }) {
  const { hasCompletedSetup, isAnonymous, loading, setupLoading } = useAuth();

  if (loading || setupLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-charcoal-900">
        <div className="text-cream-100">Loading...</div>
      </div>
    );
  }

  // Demo (anonymous) users are provisioned setup-complete server-side; skip the setup gate to
  // avoid a redirect race while their membership row loads into context.
  if (isAnonymous && isDemoHost()) {
    return <>{children}</>;
  }

  if (!hasCompletedSetup) {
    // Redirect to setup
    window.location.href = '/setup';
    return null;
  }

  return <>{children}</>;
}
