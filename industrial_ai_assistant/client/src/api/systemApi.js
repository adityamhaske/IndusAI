import axios from 'axios';

const BASE = '/api/system';

const systemApi = {
    /**
     * GET /api/system/health
     * Returns { status, llm_connected, rag_connected, vector_store_connected, llm_reason, ... }
     */
    health: () => axios.get(`${BASE}/health`).then(r => r.data),
};

export default systemApi;
