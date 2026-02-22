import axios from 'axios';

const BASE = '/api/system';

const systemApi = {
    /**
     * GET /api/system/health
     * Returns { status, llm_connected, rag_connected, vector_store_connected, llm_reason, ... }
     */
    health: () => axios.get(`${BASE}/health`).then(r => r.data),

    /**
     * GET /api/system/config
     * Returns the persistent AI gateway fallback configurations and active providers.
     */
    getConfig: () => axios.get(`${BASE}/config`).then(r => r.data),

    /**
     * POST /api/system/config
     * Updates AI gateway telemetry SLAs, timeouts, and API keys securely.
     */
    updateConfig: (payload) => axios.post(`${BASE}/config`, payload).then(r => r.data),
};

export default systemApi;
