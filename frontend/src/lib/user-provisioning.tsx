import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useAuth } from './auth';
import { useWorkspace } from './workspace';
import {
  useGetUserById,
  useCreateUserWithId,
  useCreateWorkspaceWithId,
  useAddWorkspaceMember,
  useGetWorkspaceByDomain,
} from '@/dataconnect-generated/react';
import { WorkspaceRole } from '@/dataconnect-generated';
import { v4 as uuidv4 } from 'uuid';
import { seedWorkspaceDefaults } from './seed-workspace-defaults';
import { syncWorkspaceClaims } from './claims';

// Public email domains that shouldn't be used for team matching
const PUBLIC_DOMAINS = new Set([
  'gmail.com',
  'googlemail.com',
  'outlook.com',
  'hotmail.com',
  'live.com',
  'msn.com',
  'yahoo.com',
  'ymail.com',
  'icloud.com',
  'me.com',
  'mac.com',
  'aol.com',
  'protonmail.com',
  'proton.me',
  'fastmail.com',
  'zoho.com',
  'mail.com',
  'gmx.com',
  'gmx.net',
  'tutanota.com',
  'hey.com',
]);

/**
 * Extracts the domain from an email address.
 * Returns null for public domains that shouldn't be used for team matching.
 */
function getTeamDomain(email: string): string | null {
  const domain = email.split('@')[1]?.toLowerCase();
  if (!domain || PUBLIC_DOMAINS.has(domain)) {
    return null;
  }
  return domain;
}

/**
 * Extracts a workspace name placeholder from an email address.
 * e.g., "john.doe@example.com" -> "John's Workspace"
 */
function getWorkspaceNameFromEmail(email: string): string {
  const localPart = email.split('@')[0];
  const firstName = localPart.split(/[.+_-]/)[0];
  const capitalized = firstName.charAt(0).toUpperCase() + firstName.slice(1).toLowerCase();
  return `${capitalized}'s Workspace`;
}

/**
 * Creates a unique slug from a workspace name.
 * Adds a random suffix to avoid collisions.
 */
function createSlug(name: string): string {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
  const suffix = Math.random().toString(36).substring(2, 6);
  return `${base}-${suffix}`;
}

type ProvisioningState =
  | 'loading'
  | 'checking_domain'
  | 'creating_workspace'
  | 'redirect_to_join'
  | 'ready'
  | 'error';

interface Props {
  children: ReactNode;
}

/**
 * UserProvisioner Component
 *
 * Handles the workspace provisioning flow:
 * 1. Check if user already has a workspace -> use it
 * 2. Check if user's email domain has an existing workspace -> request to join
 * 3. Otherwise -> create new workspace with domain set
 *
 * This runs after Firebase auth and before the rest of the app.
 */
export function UserProvisioner({ children }: Props) {
  const { user, loading: authLoading, isAuthenticated } = useAuth();
  const { setWorkspaceId } = useWorkspace();
  const [state, setState] = useState<ProvisioningState>('loading');
  const [error, setError] = useState<string | null>(null);
  // Ensures we mint the `ws` claim at most once per mount on the existing-user fast path.
  const claimSyncStartedRef = useRef(false);

  // Query current user from database using explicit userId
  // (useGetCurrentUser uses auth.uid which doesn't work with real Firebase Auth + DataConnect emulator)
  const { data: currentUserData, isLoading: userLoading, refetch: refetchUser } = useGetUserById(
    { userId: user?.uid || '' },
    { enabled: !!user?.uid && isAuthenticated }
  );

  // Get user's email domain for workspace matching
  const userDomain = user?.email ? getTeamDomain(user.email) : null;

  // Query for existing workspace by domain (only if user has a business domain)
  const { data: domainWorkspaceData, isLoading: domainLoading, isError: domainError } = useGetWorkspaceByDomain(
    { domain: userDomain || '' },
    { enabled: !!userDomain && isAuthenticated }
  );

  // Mutations for provisioning
  const createUser = useCreateUserWithId();
  const createWorkspace = useCreateWorkspaceWithId();
  const addWorkspaceMember = useAddWorkspaceMember();

  useEffect(() => {
    console.log('[UserProvisioner] useEffect running:', {
      authLoading,
      userLoading,
      domainLoading,
      isAuthenticated,
      userId: user?.uid,
      hasUserData: !!currentUserData?.users?.[0],
      membershipsCount: currentUserData?.users?.[0]?.workspaceMembers_on_user?.length || 0,
      state,
    });

    // Wait for all data to load
    if (authLoading || userLoading || (userDomain && domainLoading)) {
      console.log('[UserProvisioner] Still loading, waiting...');
      setState('loading');
      return;
    }

    // Not authenticated - no provisioning needed
    if (!isAuthenticated || !user) {
      console.log('[UserProvisioner] Not authenticated, setting ready');
      setState('ready');
      return;
    }

    // Check if user exists in database and has a workspace
    // Note: GetUserById now returns users[] array, not user object
    const dbUser = currentUserData?.users?.[0];
    console.log('[UserProvisioner] Checking user data:', {
      hasDbUser: !!dbUser,
      dbUserId: dbUser?.id,
      memberships: dbUser?.workspaceMembers_on_user,
    });

    if (dbUser) {
      const memberships = dbUser.workspaceMembers_on_user || [];
      if (memberships.length > 0) {
        // User has a workspace - set it and we're done
        const primaryWorkspace = memberships[0].workspace;
        console.log('[UserProvisioner] ✓ Found existing workspace:', primaryWorkspace.id);
        setWorkspaceId(primaryWorkspace.id);
        // Existing users skip the provisioning path that mints the `ws` custom claim, so without
        // this their Firestore tenant-isolated realtime reads (notifications/agent_status) 403.
        // Sync + refresh the token BEFORE the app renders so subscriptions get a claim-bearing
        // token. Runs once per mount; keep the spinner up until it resolves (state stays non-ready).
        if (!claimSyncStartedRef.current) {
          claimSyncStartedRef.current = true;
          syncWorkspaceClaims().finally(() => setState('ready'));
        }
        return;
      }
    }

    // User has no workspace - check if their domain has an existing workspace
    // Note: If domain query failed, we proceed to create a new workspace (safe fallback)
    if (userDomain && !domainError && domainWorkspaceData?.workspaces?.length) {
      const existingWorkspace = domainWorkspaceData.workspaces[0];
      // Check if user is already a member of this workspace
      const isMember = existingWorkspace.workspaceMembers_on_workspace?.some(
        m => m.user?.id === user.uid
      );

      if (!isMember) {
        // Domain has workspace but user is not a member - redirect to /join
        console.log('Domain workspace found, redirecting to /join:', {
          domain: userDomain,
          workspaceId: existingWorkspace.id,
          workspaceName: existingWorkspace.name,
        });
        setState('redirect_to_join');
        window.location.href = '/join';
        return;
      }
    }

    // Log if domain query failed (for debugging)
    if (domainError) {
      console.warn('[UserProvisioner] Domain query failed, proceeding to create workspace:', { userDomain });
    }

    // User has no workspace and no domain match - create one
    console.log('[UserProvisioner] No existing workspace found, will provision new one');
    if (state !== 'creating_workspace' && state !== 'checking_domain' && state !== 'redirect_to_join') {
      provisionUser();
    }
  }, [authLoading, userLoading, domainLoading, domainError, isAuthenticated, user, currentUserData, domainWorkspaceData, userDomain]);

  async function provisionUser() {
    if (!user?.email || !user?.uid) return;

    setState('creating_workspace');
    setError(null);

    try {
      const workspaceId = uuidv4();
      const workspaceName = getWorkspaceNameFromEmail(user.email);
      const workspaceSlug = createSlug(workspaceName);
      const domain = getTeamDomain(user.email);

      console.log('Provisioning new user:', {
        userId: user.uid,
        email: user.email,
        workspaceId,
        workspaceName,
        domain,
      });

      // Check if user already exists (might have been created by another tab)
      const checkResult = await refetchUser();
      const checkUser = checkResult.data?.users?.[0];
      if (checkUser) {
        const memberships = checkUser.workspaceMembers_on_user || [];
        if (memberships.length > 0) {
          setWorkspaceId(memberships[0].workspace.id);
          setState('ready');
          return;
        }
      }

      // Create user record if doesn't exist (ignore if already exists)
      if (!checkUser) {
        console.log('[UserProvisioner] No user record found, attempting to create...');
        try {
          await createUser.mutateAsync({
            id: user.uid,
            email: user.email,
            displayName: user.displayName || user.email.split('@')[0],
          });
          console.log('[UserProvisioner] ✓ User record created successfully');
        } catch (err) {
          console.log('[UserProvisioner] User creation error:', err);
          // Ignore "already exists" errors - user may have been created in a previous session
          const errorMsg = err instanceof Error ? err.message : String(err);
          const isAlreadyExists = errorMsg.includes('ALREADY_EXISTS') || errorMsg.includes('duplicate') || errorMsg.includes('unique');
          if (!isAlreadyExists) {
            console.error('[UserProvisioner] ✗ User creation failed (non-duplicate error):', errorMsg);
            throw err;
          }
          console.log('[UserProvisioner] User already exists, continuing...');
        }

        // IMPORTANT: After creating user record, refetch to check for existing memberships
        // This handles the case where WorkspaceMember exists but User didn't (e.g., from seeding)
        console.log('[UserProvisioner] Refetching user data after user creation...');
        const recheckAfterUserCreate = await refetchUser();
        const recheckUser = recheckAfterUserCreate.data?.users?.[0];
        console.log('[UserProvisioner] Refetch result:', {
          hasUser: !!recheckUser,
          membershipsCount: recheckUser?.workspaceMembers_on_user?.length || 0
        });

        if (recheckUser) {
          const existingMemberships = recheckUser.workspaceMembers_on_user || [];
          if (existingMemberships.length > 0) {
            console.log('[UserProvisioner] ✓ Found existing workspace membership, using workspace:', existingMemberships[0].workspace.id);
            setWorkspaceId(existingMemberships[0].workspace.id);
            // Ensure the auth token carries the `ws` membership claim (Firestore tenant isolation),
            // e.g. for users provisioned before claims existed. Best-effort, non-blocking.
            void syncWorkspaceClaims();
            setState('ready');
            return;
          }
        }
        console.log('[UserProvisioner] No existing memberships found, will create new workspace');
      }

      // No existing membership - create workspace with domain (ignore if already exists)
      try {
        await createWorkspace.mutateAsync({
          id: workspaceId,
          name: workspaceName,
          slug: workspaceSlug,
          domain: domain || undefined,
          setupCompleted: false, // New workspaces need setup
        });

        // Add user as workspace owner with hasCompletedSetup: false
        await addWorkspaceMember.mutateAsync({
          workspaceId,
          userId: user.uid,
          role: WorkspaceRole.owner,
          hasCompletedSetup: false, // New users need to complete setup
        });

        // Publish the new membership to the auth token (`ws` claim) so Firestore tenant-isolation
        // rules let this user read their workspace's notifications/setup_progress.
        await syncWorkspaceClaims();

        // Seed default content (playbooks, handbook docs, voice docs)
        // This runs in the background - we don't block on it
        seedWorkspaceDefaults(workspaceId).catch((err) => {
          console.error('[UserProvisioner] Failed to seed workspace defaults:', err);
          // Don't throw - workspace is still usable without defaults
        });
      } catch (err) {
        // If workspace creation fails, check if user now has a workspace (race condition)
        const recheck = await refetchUser();
        const recheckUser2 = recheck.data?.users?.[0];
        const memberships = recheckUser2?.workspaceMembers_on_user || [];
        if (memberships.length > 0) {
          setWorkspaceId(memberships[0].workspace.id);
          setState('ready');
          return;
        }
        throw err;
      }

      // Set workspace in context
      setWorkspaceId(workspaceId);
      setState('ready');

      console.log('User provisioning complete');
    } catch (err) {
      console.error('Failed to provision user:', err);
      setError(err instanceof Error ? err.message : 'Failed to create account');
      setState('error');
    }
  }

  // Anonymous (demo) users are provisioned by the /demo landing, not here — they have no email and
  // would otherwise hang on the "Setting up your account" spinner. Bypass the email-based flow.
  if (user?.isAnonymous) {
    return <>{children}</>;
  }

  // Show loading ONLY when authenticated and provisioning
  // Don't block the landing page for unauthenticated users
  if (isAuthenticated && (state === 'loading' || state === 'creating_workspace' || state === 'checking_domain' || state === 'redirect_to_join')) {
    let message = 'Setting up your account...';
    if (state === 'creating_workspace') {
      message = 'Creating your workspace...';
    } else if (state === 'checking_domain') {
      message = 'Checking for existing team workspace...';
    } else if (state === 'redirect_to_join') {
      message = 'Found your team, redirecting...';
    }

    return (
      <div className="min-h-screen flex items-center justify-center bg-charcoal-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-rust-500 mx-auto mb-4" />
          <p className="text-cream-400">{message}</p>
        </div>
      </div>
    );
  }

  // Show error if provisioning failed
  if (state === 'error' || error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-charcoal-900">
        <div className="text-center max-w-md px-6">
          <div className="w-12 h-12 rounded-full bg-rust-500/20 flex items-center justify-center mx-auto mb-4">
            <svg className="w-6 h-6 text-rust-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-cream-100 mb-2">Account Setup Error</h1>
          <p className="text-cream-400 mb-4">{error || 'Something went wrong'}</p>
          <button
            onClick={() => window.location.reload()}
            className="text-sm font-mono uppercase tracking-widest bg-rust-500 text-charcoal-900 px-4 py-2 hover:bg-rust-400 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
