/**
 * AuthContext.tsx — React context providing Firebase user state.
 *
 * Wrap your <App /> with <AuthProvider> to make `useAuth()` available
 * everywhere. The context also exposes `getIdToken()` for API calls.
 */
import React, { createContext, useContext, useEffect, useState } from 'react';
import { type User } from 'firebase/auth';
import { onAuthChange, signInWithGoogle, signInWithEmail, signOut, getIdToken } from '../services/auth';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  hasApiKey: boolean;
  signIn: () => Promise<void>;
  signInEmail: (email: string, password: string) => Promise<void>;
  logOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  hasApiKey: false,
  signIn: async () => {},
  signInEmail: async () => {},
  logOut: async () => {},
  getToken: async () => null,
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loadingAuth, setLoadingAuth] = useState(true);
  
  const hasApiKey = true; // Centralized API key
  
  const loading = loadingAuth;

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

  const signInEmailFn = async (email: string, password: string) => {
    await signInWithEmail(email, password);
  };

  const logOut = async () => {
    await signOut();
  };

  const getToken = async () => {
    return getIdToken();
  };

  return (
    <AuthContext.Provider value={{ user, loading, hasApiKey, signIn, signInEmail: signInEmailFn, logOut, getToken }}>
      {children}
    </AuthContext.Provider>
  );
}

/** Hook to access auth state and methods. */
export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
