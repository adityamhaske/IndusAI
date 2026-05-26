const fs = require('fs');

const code = fs.readFileSync('client/src/pages/Placeholders.jsx', 'utf8');

// Find the UI Dependencies marker
const uiDepIndex = code.indexOf('// ── UI Dependencies ──────────────────────────────────────────────────────────────');
const projectPageIndex = code.indexOf('// ── Project Page ──────────────────────────────────────────────────────────────');

const importsStr = code.substring(uiDepIndex, projectPageIndex);

// Logs and History are before UI Dependencies
const historyCode = code.substring(0, uiDepIndex);

const projectCode = code.substring(projectPageIndex);

const getHeader = () => `import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
    FolderOpen, RefreshCw, Trash2, CheckCircle2, AlertTriangle,
    Loader2, Database, FileText, Cpu, Hash, Upload, FolderSearch, File, Frown, Save, ShieldCheck, XCircle, FileImage, FileBarChart
} from 'lucide-react';
import useAppStore from '../store/useAppStore';
import { getIdToken } from '../services/auth';

/**
 * Authenticated fetch wrapper
 */
async function authFetch(url, options = {}) {
    const token = await getIdToken();
    const headers = { ...(options.headers || {}) };
    if (token) headers['Authorization'] = \`Bearer \${token}\`;
    return fetch(url, { ...options, headers });
}
`;

fs.writeFileSync('client/src/pages/LogsPage.tsx', `
import React from 'react';

export const LogsPage = () => (
    <div className="p-8">
        <h2 className="text-2xl font-bold text-industrial-800 mb-4">PLC Fault Logs</h2>
        <div className="bg-white p-6 rounded-lg border border-industrial-200 shadow-sm text-center py-20">
            <p className="text-industrial-500">Use the PLC Logs tab in the sidebar.</p>
        </div>
    </div>
);
`);

fs.writeFileSync('client/src/pages/HistoryPage.tsx', `// @ts-nocheck
${getHeader()}

${historyCode.replace(/export const LogsPage[\s\S]*?(?=export const HistoryPage)/, '')}
`);

fs.writeFileSync('client/src/pages/ProjectPage.tsx', `// @ts-nocheck
${getHeader()}
import systemApi from '../services/systemApi';
import { getProjectStatus, resetProject, getProjectFiles } from '../services/knowledgeApi';
import { projectApi } from '../services/projectApi';

${importsStr.replace(/\/\/ ── UI Dependencies[\s\S]*?(?=\/\/ ── Folder Tree Component)/, '')}
${projectCode}
`);

console.log("Splitting complete");
