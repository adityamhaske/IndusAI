/**
 * AuthContext.tsx — React context providing Firebase user state.
 *
 * Wrap your <App /> with <AuthProvider> to make `useAuth()` available
 * everywhere. The context also exposes `getIdToken()` for API calls.
 */
import React, { createContext, useContext, useEffect, useState } from 'react';
import { type User } from 'firebase/auth';
import { onAuthChange, signInWithGoogle, signOut, getIdToken } from '../services/auth';
import { useUserSettings } from '../hooks/useUserSettings';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  hasApiKey: boolean;
  signIn: () => Promise<void>;
  logOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
  refreshSettings: () => Promise<any>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  hasApiKey: false,
  signIn: async () => {},
  logOut: async () => {},
  getToken: async () => null,
  refreshSettings: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loadingAuth, setLoadingAuth] = useState(true);
  
  const { settings, loading: loadingSettings, refreshSettings } = useUserSettings(user?.uid);
  const hasApiKey = !!settings?.gemini_api_key || !!settings?.has_api_key;
  
  // Overall loading is true if auth is loading, or if we have a user but settings are still loading
  const loading = loadingAuth || (!!user && loadingSettings);

  useEffect(() => {
    const unsub = onAuthChange((u) => {
      setUser(u);
      setLoadingAuth(false);
    });
    return unsub;
  }, []);

  const signIn = async () => {
    await signInWithGoogle();
  };

  const logOut = async () => {
    await signOut();
  };

  const getToken = async () => {
    return getIdToken();
  };

  return (
    <AuthContext.Provider value={{ user, loading, hasApiKey, signIn, logOut, getToken, refreshSettings }}>
      {children}
    </AuthContext.Provider>
  );
}

/** Hook to access auth state and methods. */
export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
