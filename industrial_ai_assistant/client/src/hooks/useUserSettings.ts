import { useState, useEffect } from 'react';
import api from '../services/apiClient';

export interface UserSettings {
  llm_provider?: string | null;
  llm_model?: string | null;
  embedding_provider?: string | null;
  ollama_url?: string | null;
  has_llm_key?: boolean;
  has_embedding_key?: boolean;
  llm_key_preview?: string | null;
  embedding_key_preview?: string | null;
  gemini_api_key?: string;
  has_api_key?: boolean;
}

export function useUserSettings(uid: string | undefined) {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!uid) {
      setSettings(null);
      setLoading(false);
      return;
    }

    let isMounted = true;
    
    const fetchSettings = async () => {
      try {
        setLoading(true);
        const res = await api.get('/api/user/settings');
        if (isMounted) {
          setSettings(res.data);
          setError(null);
        }
      } catch (err: any) {
        if (isMounted) {
          console.error("Failed to fetch user settings", err);
          setError(err);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchSettings();

    return () => { isMounted = false; };
  }, [uid]);

  const refreshSettings = async () => {
    try {
      const res = await api.get('/api/user/settings');
      setSettings(res.data);
      return res.data;
    } catch (err: any) {
      console.error("Failed to refresh user settings", err);
      throw err;
    }
  };

  return { settings, loading, error, refreshSettings };
}
