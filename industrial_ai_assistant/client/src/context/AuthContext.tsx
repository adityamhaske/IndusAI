/**
 * AuthContext.tsx — React context providing Firebase user state.
 *
 * Wrap your <App /> with <AuthProvider> to make `useAuth()` available
 * everywhere. The context also exposes `getIdToken()` for API calls.
 */
import React, { createContext, useContext, useEffect, useState } from 'react';
import { type User } from 'firebase/auth';
import { onAuthChange, signInWithGoogle, signOut, getIdToken } from '../services/auth';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  signIn: () => Promise<void>;
  logOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  signIn: async () => {},
  logOut: async () => {},
  getToken: async () => null,
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsub = onAuthChange((u) => {
      setUser(u);
      setLoading(false);
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
    <AuthContext.Provider value={{ user, loading, signIn, logOut, getToken }}>
      {children}
    </AuthContext.Provider>
  );
}

/** Hook to access auth state and methods. */
export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
