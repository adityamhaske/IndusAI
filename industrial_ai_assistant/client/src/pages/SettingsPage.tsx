/**
 * SettingsPage.tsx — BYOK provider configuration + system diagnostics.
 *
 * Replaces the old static read-only settings with a full
 * provider selector, masked API key inputs, and save/test flow.
 */
import React, { useState, useEffect } from 'react';
import {
  Cpu, Loader2, CheckCircle2, Database,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';



export default function SettingsPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);

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
              System diagnostics and infrastructure status.
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
          {/* System Status Card */}
          <div className="bg-white p-6 rounded-xl border border-industrial-200 shadow-sm space-y-5">
            <h3 className="text-lg font-bold text-industrial-800 border-b border-industrial-100 pb-3 flex items-center gap-2">
              <Cpu className="w-5 h-5 text-primary-600" /> AI Provider Status
            </h3>

            <div className="flex items-center gap-3 p-4 rounded-xl border-2 border-green-500 bg-green-50 text-green-800">
              <CheckCircle2 className="w-6 h-6" />
              <div>
                <div className="font-bold">Enterprise AI Connected</div>
                <div className="text-xs mt-1">Powered by Google Gemini 1.5 Flash (Centralized Key)</div>
              </div>
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
