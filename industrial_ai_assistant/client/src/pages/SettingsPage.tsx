/**
 * SettingsPage.tsx — BYOK provider configuration + system diagnostics.
 *
 * Replaces the old static read-only settings with a full
 * provider selector, masked API key inputs, and save/test flow.
 */
import React, { useState, useEffect } from 'react';
import {
  Cpu, RefreshCw, Loader2, CheckCircle2, XCircle, Database,
  Eye, EyeOff, Save, ShieldCheck,
} from 'lucide-react';
import { userApi } from '../services/userApi';
import { useAuth } from '../context/AuthContext';

const PROVIDERS = [
  { id: 'gemini',   label: 'Google Gemini',   models: ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-pro'] },
  { id: 'openai',   label: 'OpenAI',          models: ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo'] },
  { id: 'deepseek', label: 'DeepSeek',        models: ['deepseek-chat', 'deepseek-coder'] },
  { id: 'ollama',   label: 'Ollama (Local)',   models: ['mistral', 'llama3', 'codellama'] },
];

export default function SettingsPage() {
  const { user, refreshSettings } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [showKey, setShowKey] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Form state
  const [provider, setProvider] = useState('gemini');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434');
  const [hasExistingKey, setHasExistingKey] = useState(false);
  const [keyPreview, setKeyPreview] = useState('');

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const s = await userApi.getSettings();
      if (s.llm_provider) setProvider(s.llm_provider);
      if (s.llm_model) setModel(s.llm_model);
      if (s.ollama_url) setOllamaUrl(s.ollama_url);
      setHasExistingKey(s.has_llm_key);
      setKeyPreview(s.llm_key_preview || '');
    } catch {
      // No settings yet — that's fine
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const payload: any = {
        llm_provider: provider,
        llm_model: model || undefined,
      };
      if (apiKey.trim()) payload.llm_api_key = apiKey.trim();
      if (provider === 'ollama') payload.ollama_url = ollamaUrl;

      const result = await userApi.saveSettings(payload);
      setHasExistingKey(result.has_llm_key);
      setKeyPreview(result.llm_key_preview || '');
      setApiKey(''); // Clear the input after save
      try {
        await refreshSettings();
      } catch (refreshErr) {
        console.error("Failed to refresh global settings", refreshErr);
      }
      setMessage({ type: 'success', text: 'Settings saved successfully.' });
    } catch (err: any) {
      setMessage({ type: 'error', text: err.response?.data?.detail || err.message || 'Save failed' });
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await userApi.testConnection();
      setTestResult(result);
    } catch (err: any) {
      setTestResult({ status: 'error', error: err.response?.data?.detail || err.message });
    } finally {
      setTesting(false);
    }
  };

  const selectedProviderInfo = PROVIDERS.find(p => p.id === provider);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-industrial-400" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-8 max-w-4xl pb-24">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-industrial-800">AI Provider Settings</h2>
            <p className="text-sm text-industrial-500 mt-1">
              Configure your AI provider using your own API key (BYOK).
            </p>
          </div>
          {user && (
            <div className="flex items-center gap-2 text-sm text-industrial-500">
              {user.photoURL && (
                <img src={user.photoURL} alt="" className="w-7 h-7 rounded-full" />
              )}
              <span className="font-medium">{user.displayName || user.email}</span>
            </div>
          )}
        </div>

        <div className="space-y-6">
          {/* Provider Selection Card */}
          <div className="bg-white p-6 rounded-xl border border-industrial-200 shadow-sm space-y-5">
            <h3 className="text-lg font-bold text-industrial-800 border-b border-industrial-100 pb-3 flex items-center gap-2">
              <Cpu className="w-5 h-5 text-primary-600" /> LLM Provider
            </h3>

            {/* Provider Buttons */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {PROVIDERS.map(p => (
                <button
                  key={p.id}
                  onClick={() => { setProvider(p.id); setModel(''); }}
                  className={`p-4 rounded-xl border-2 text-left transition-all ${
                    provider === p.id
                      ? 'border-primary-500 bg-primary-50 shadow-sm'
                      : 'border-industrial-200 hover:border-industrial-300'
                  }`}
                >
                  <div className="text-sm font-bold text-industrial-800">{p.label}</div>
                  <div className="text-[10px] text-industrial-400 mt-1">
                    {p.models[0]}
                  </div>
                </button>
              ))}
            </div>

            {/* Model Selector */}
            {selectedProviderInfo && (
              <div>
                <label className="text-xs font-semibold text-industrial-600 uppercase mb-1.5 block">Model</label>
                <select
                  value={model || selectedProviderInfo.models[0]}
                  onChange={e => setModel(e.target.value)}
                  className="w-full border border-industrial-200 rounded-xl px-4 py-2.5 text-sm text-industrial-800 focus:border-primary-400 focus:ring-1 focus:ring-primary-400 outline-none bg-white"
                >
                  {selectedProviderInfo.models.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
            )}

            {/* API Key Input */}
            {provider !== 'ollama' ? (
              <div>
                <label className="text-xs font-semibold text-industrial-600 uppercase mb-1.5 block">API Key</label>
                {hasExistingKey && !apiKey && (
                  <div className="flex items-center gap-2 mb-2 text-xs text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    Key saved: <span className="font-mono">{keyPreview}</span>
                    <span className="text-industrial-400 ml-1">· Enter a new key below to replace it</span>
                  </div>
                )}
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={e => setApiKey(e.target.value)}
                    placeholder={hasExistingKey ? 'Enter new key to replace…' : `Paste your ${selectedProviderInfo?.label} API key`}
                    className="w-full border border-industrial-200 rounded-xl px-4 py-2.5 pr-10 text-sm font-mono text-industrial-800 focus:border-primary-400 focus:ring-1 focus:ring-primary-400 outline-none"
                  />
                  <button
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-industrial-400 hover:text-industrial-600"
                  >
                    {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <label className="text-xs font-semibold text-industrial-600 uppercase mb-1.5 block">Ollama URL</label>
                <input
                  type="text"
                  value={ollamaUrl}
                  onChange={e => setOllamaUrl(e.target.value)}
                  placeholder="http://localhost:11434"
                  className="w-full border border-industrial-200 rounded-xl px-4 py-2.5 text-sm font-mono text-industrial-800 focus:border-primary-400 focus:ring-1 focus:ring-primary-400 outline-none"
                />
              </div>
            )}

            {/* Message */}
            {message && (
              <div className={`flex items-center gap-2 text-sm font-medium p-3 rounded-lg border ${
                message.type === 'success'
                  ? 'bg-green-50 border-green-200 text-green-700'
                  : 'bg-red-50 border-red-200 text-red-700'
              }`}>
                {message.type === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                {message.text}
              </div>
            )}

            {/* Test Connection Result */}
            {testResult && (
              <div className={`flex items-center gap-2 text-sm font-bold p-3 rounded-lg border ${
                testResult.status === 'connected'
                  ? 'bg-green-50 border-green-200 text-green-700'
                  : 'bg-red-50 border-red-200 text-red-700'
              }`}>
                {testResult.status === 'connected' ? (
                  <><CheckCircle2 className="w-4 h-4" /> Connected · {testResult.model} · {testResult.latency_ms}ms</>
                ) : (
                  <><XCircle className="w-4 h-4" /> {testResult.error || 'Connection failed'}</>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="pt-4 border-t border-industrial-100 flex items-center gap-3">
              <button
                onClick={handleSave}
                disabled={saving}
                className="bg-industrial-900 text-white px-5 py-2.5 rounded-xl text-sm font-bold hover:bg-industrial-800 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                Save Settings
              </button>
              <button
                onClick={handleTestConnection}
                disabled={testing || !hasExistingKey}
                className="bg-primary-600 text-white px-5 py-2.5 rounded-xl text-sm font-bold hover:bg-primary-700 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                Test Connection
              </button>
            </div>
          </div>

          {/* Architecture Info (read-only) */}
          <div className="bg-white p-6 rounded-xl border border-industrial-200 shadow-sm space-y-4">
            <h3 className="text-lg font-bold text-industrial-800 border-b border-industrial-100 pb-3 flex items-center gap-2">
              <Database className="w-5 h-5 text-primary-600" /> Infrastructure
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-lg border border-industrial-200 bg-industrial-50">
                <div className="text-sm font-bold text-industrial-800">Vector Database</div>
                <div className="text-xs text-industrial-500 mt-1">Qdrant Cloud</div>
              </div>
              <div className="p-4 rounded-lg border border-industrial-200 bg-industrial-50">
                <div className="text-sm font-bold text-industrial-800">Auth</div>
                <div className="text-xs text-industrial-500 mt-1">Firebase Authentication</div>
              </div>
              <div className="p-4 rounded-lg border border-industrial-200 bg-industrial-50">
                <div className="text-sm font-bold text-industrial-800">Storage</div>
                <div className="text-xs text-industrial-500 mt-1">Firestore + Cloud Storage</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
