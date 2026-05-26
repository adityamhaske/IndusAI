/**
 * Firebase client-side initialization.
 *
 * Uses the public web-app config for indus-ai-cloud-101.
 * Only imports auth — keeps bundle small.
 */
import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';

const firebaseConfig = {
  apiKey:            import.meta.env.VITE_FIREBASE_API_KEY            || '',
  authDomain:        import.meta.env.VITE_FIREBASE_AUTH_DOMAIN        || 'indus-ai-cloud-101.firebaseapp.com',
  projectId:         import.meta.env.VITE_FIREBASE_PROJECT_ID         || 'indus-ai-cloud-101',
  storageBucket:     import.meta.env.VITE_FIREBASE_STORAGE_BUCKET     || 'indus-ai-cloud-101.firebasestorage.app',
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER   || '',
  appId:             import.meta.env.VITE_FIREBASE_APP_ID             || '',
};

export const firebaseApp = initializeApp(firebaseConfig);
export const firebaseAuth = getAuth(firebaseApp);
