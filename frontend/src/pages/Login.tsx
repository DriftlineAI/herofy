import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { signInWithGoogle, signInWithEmail, signUpWithEmail } from '@/lib/firebase';
import { useAuth } from '@/lib/auth';

export default function Login() {
  const navigate = useNavigate();
  const { isAuthenticated, hasCompletedSetup, signOut, user } = useAuth();
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showLogoutPrompt, setShowLogoutPrompt] = useState(false);

  // Check if already logged in, show logout option instead of auto-redirect
  useEffect(() => {
    if (isAuthenticated) {
      setShowLogoutPrompt(true);
    }
  }, [isAuthenticated]);

  const handleSignOut = async () => {
    try {
      await signOut();
      setShowLogoutPrompt(false);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to sign out');
    }
  };

  const handleGoogleSignIn = async () => {
    setError(null);
    setLoading(true);
    try {
      await signInWithGoogle();
      // Navigation handled by useEffect watching isAuthenticated
    } catch (err: any) {
      setError(err.message || 'Failed to sign in with Google');
      setLoading(false);
    }
  };

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isSignUp) {
        await signUpWithEmail(email, password);
      } else {
        await signInWithEmail(email, password);
      }
      // Navigation handled by useEffect watching isAuthenticated
    } catch (err: any) {
      // Firebase error messages are user-friendly
      setError(err.message || 'Authentication failed');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-charcoal-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-cream-100">Herofy</h1>
          <p className="text-cream-400 mt-2">AI-powered Customer Success</p>
        </div>

        {/* Already Logged In */}
        {showLogoutPrompt ? (
          <div className="bg-charcoal-800 rounded-xl p-8 border border-charcoal-700">
            <h2 className="text-xl font-semibold text-cream-100 mb-4">
              Already signed in
            </h2>
            <p className="text-cream-400 mb-6">
              You're currently signed in as <span className="text-cream-100">{user?.email}</span>
            </p>

            <div className="space-y-3">
              <button
                onClick={() => navigate(hasCompletedSetup ? '/app' : '/setup')}
                className="w-full bg-rust-600 hover:bg-rust-500 text-cream-100 rounded-lg px-4 py-3 font-medium transition-colors"
              >
                Continue to {hasCompletedSetup ? 'Dashboard' : 'Setup'}
              </button>

              <button
                onClick={handleSignOut}
                className="w-full bg-charcoal-700 hover:bg-charcoal-600 text-cream-100 rounded-lg px-4 py-3 font-medium transition-colors border border-charcoal-600"
              >
                Sign out and log in as different user
              </button>
            </div>

            {error && (
              <div className="mt-4 text-red-400 text-sm bg-red-900/20 border border-red-900/50 rounded-lg px-4 py-2">
                {error}
              </div>
            )}
          </div>
        ) : (
          /* Card */
          <div className="bg-charcoal-800 rounded-xl p-8 border border-charcoal-700">
            <h2 className="text-xl font-semibold text-cream-100 mb-6">
              {isSignUp ? 'Create your account' : 'Welcome back'}
            </h2>

          {/* Google Sign In */}
          <button
            onClick={handleGoogleSignIn}
            disabled={loading}
            className="w-full flex items-center justify-center gap-3 bg-white text-charcoal-900 rounded-lg px-4 py-3 font-medium hover:bg-cream-100 transition-colors disabled:opacity-50"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Continue with Google
          </button>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-charcoal-600" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-charcoal-800 text-cream-500">or</span>
            </div>
          </div>

          {/* Email Form */}
          <form onSubmit={handleEmailSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-cream-300 mb-1">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="w-full bg-charcoal-700 border border-charcoal-600 rounded-lg px-4 py-2 text-cream-100 placeholder-cream-600 focus:outline-none focus:ring-2 focus:ring-rust-500 focus:border-transparent"
                placeholder="you@company.com"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-cream-300 mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                autoComplete={isSignUp ? 'new-password' : 'current-password'}
                className="w-full bg-charcoal-700 border border-charcoal-600 rounded-lg px-4 py-2 text-cream-100 placeholder-cream-600 focus:outline-none focus:ring-2 focus:ring-rust-500 focus:border-transparent"
                placeholder="At least 6 characters"
              />
            </div>

            {error && (
              <div className="text-red-400 text-sm bg-red-900/20 border border-red-900/50 rounded-lg px-4 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-rust-600 hover:bg-rust-500 text-cream-100 rounded-lg px-4 py-3 font-medium transition-colors disabled:opacity-50"
            >
              {loading ? 'Please wait...' : isSignUp ? 'Create account' : 'Sign in'}
            </button>
          </form>

          <div className="mt-6 text-center">
            <button
              onClick={() => setIsSignUp(!isSignUp)}
              className="text-cream-400 hover:text-cream-200 text-sm"
            >
              {isSignUp ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
            </button>
          </div>
        </div>
        )}

        {/* Demo note */}
        {!showLogoutPrompt && (
          <p className="text-cream-600 text-sm text-center mt-6">
            For demo, sign up with any email or use Google
          </p>
        )}
      </div>
    </div>
  );
}
