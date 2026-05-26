/**
 * auth.ts — Firebase Authentication helpers.
 *
 * Provides sign-in (Google), sign-out, and token retrieval.
 * Microsoft sign-in is stubbed for future use.
 */
import {
  GoogleAuthProvider,
  signInWithPopup,
  signOut as fbSignOut,
  onAuthStateChanged,
  type User,
} from 'firebase/auth';
import { firebaseAuth } from '../config/firebase';

const googleProvider = new GoogleAuthProvider();

/** Sign in with Google popup. Returns the Firebase User. */
export async function signInWithGoogle(): Promise<User> {
  const result = await signInWithPopup(firebaseAuth, googleProvider);
  return result.user;
}

/** Sign out the current user. */
export async function signOut(): Promise<void> {
  await fbSignOut(firebaseAuth);
}

/** Get the current user (null if not signed in). */
export function getCurrentUser(): User | null {
  return firebaseAuth.currentUser;
}

/** Get a fresh ID token for API calls. Returns null if not signed in. */
export async function getIdToken(): Promise<string | null> {
  const user = firebaseAuth.currentUser;
  if (!user) return null;
  return user.getIdToken();
}

/** Subscribe to auth state changes. Returns an unsubscribe function. */
export function onAuthChange(callback: (user: User | null) => void): () => void {
  return onAuthStateChanged(firebaseAuth, callback);
}
