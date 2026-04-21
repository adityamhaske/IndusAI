# IndusAI — Comprehensive Evaluation & Amazon PE Interview Guide

## 1. System Architecture Highlights (The "Elevator Pitch")

IndusAI is not a standard LangChain wrapper. It is a **deterministic, 9-stage knowledge retrieval engine** built for safety-critical PLC (Programmable Logic Controller) environments.

1. **Rule-Based Routing**: 6 query intent classifications (e.g., `TAG_LOOKUP`, `SYSTEM_FLOW`) using instantaneous regex evaluation—zero LLM token cost.
2. **Hybrid RRF Search**: Merges in-process TF-IDF (BM25) for exact tag/port matches with Qdrant cosine vector search, fused via Reciprocal Rank Fusion ($k=60$).
3. **Pydantic Validation**: Enforces strict JSON output schemas (Summary, Root Causes, Remediation, Confidence) with a 3-layer parsing fallback.
4. **Post-Gen Hallucination Guard**: Uses `SequenceMatcher` ($threshold \ge 0.85$) to validate tag extraction against the actual indexed project DB, redacting fabrications before the user sees them.

---

## 2. Evaluation Methodology & Target Metrics

When interviewing with a Principal Engineer, you need to prove you measure **Retrieval Quality** entirely separately from **Generation Quality**. 

### A. Retrieval Quality (The "R" in RAG)
You evaluate this by feeding the system a "Golden Dataset" of 50-100 known PLC questions and checking if the correct source files appear in the top $K$ chunks *before* the LLM sees them.

| Metric | Formula | IndusAI Target | Why it Matters for PLC |
|--------|---------|----------------|------------------------|
| **Recall@5** | $\frac{|Relevant \cap Retrieved|}{Relevant}$ | **> 85%** | Missing a troubleshooting step in a manual can cause hours of downtime. |
| **Precision@5** | $\frac{|Relevant \cap Retrieved|}{5}$ | **> 60%** | We want high recall, so lower precision is acceptable (it's okay to fetch extra context). |
| **MRR** | $\frac{1}{Rank_{first\_relevant}}$ | **> 0.75** | The most relevant chunk should ideally be in position 1 or 2. |
| **Hit Rate** | % of queries where $Recall > 0$ | **> 95%** | If Hit Rate is low, your embeddings model (`all-MiniLM-L6-v2`) is failing to capture the domain vocabulary. |

**Interview Talking Point:** 
> *"By implementing Reciprocal Rank Fusion combining BM25 and Vector Search, I boosted Recall@5 by an estimated 15-20% over pure cosine similarity. Pure vector search notoriously fails at finding exact string matches like 'ALM_1045' or 'Drive.Speed', which BM25 excels at."*

### B. Generation Quality (The "G" in RAG)
Evaluated manually or via an LLM-as-a-judge (like GPT-4) against the generated JSON.

| Metric | Target | IndusAI Implementation |
|--------|--------|------------------------|
| **Faithfulness** | **> 90%** | The output must not contain claims not present in the fetched Qdrant chunks. |
| **Hallucination Rate** | **< 3%** | Your `_detect_hallucinated_tags` function explicitly enforces this by redacting fake tag names. |
| **Schema Completion** | **> 98%** | Pydantic ensures the `FaultAnalysisResponseModel` always returns `root_causes` and `recommended_actions`. |

---

## 3. System Latency & Performance Benchmarks

In industrial environments, time-to-resolution is critical. Here is how IndusAI breaks down:

| Component | Target Latency / Throughput | Notes |
|-----------|-----------------------------|-------|
| Intent Classification | **< 2ms** | Pure Python regex. |
| Hybrid Retrieval | **< 150ms** | Qdrant lookup + local BM25 scoring. |
| Prompt Assembly | **< 10ms** | In-memory string concatenation (max 24k chars). |
| E2E with Cloud LLM (Gemini) | **2.5s - 5.0s** | P90 response time. |
| E2E with Local Edge LLM (Llama 3) | **15s - 45s** | Hardware dependent, but ensures 100% data privacy. |
| Ingestion & Indexing | **~25 chunks / sec** | Local embedding models are lightweight but highly parallelizable. |

---

## 4. How to Impress an Amazon Principal Engineer

Amazon PEs evaluate on **Operational Excellence**, **Scalability**, and **Deep Dive**. Here is how to map IndusAI features to Amazon Leadership Principles.

### 1. Project-Scoping & Multi-Tenancy (Scalability)
**Feature:** The system uses strict `project_id` scoping inside Qdrant filters rather than creating separate vector collections per project.
**The Pitch:** 
> *"I designed the vector database around a multi-tenant single-collection architecture. Instead of spinning up a new Qdrant collection for every PLC project—which consumes massive RAM overhead—I index everything into one collection and use Qdrant Payload Filters (`FieldCondition(project_id)`) to hard-isolate environments. This allows the system to scale to thousands of facilities with constant memory overhead."*

### 2. The Hallucination Guard (Customer Obsession / Dive Deep)
**Feature:** The `_fuzzy_match` function prevents the LLM from inventing PLC hardware tags.
**The Pitch:** 
> *"GenAI in industrial automation has a massive trust deficit: an LLM hallucinating a generic SQL query is annoying, but hallucinating a PLC actuator tag like `VALVE_OPEN_FORCE` could be physically dangerous. I built a deterministic post-generation safeguard. It uses regex to identify PLC-style tokens in the LLM's output, does an $O(N)$ fuzzy lookup against the known project tag database, and actively redacts any token that doesn't physically exist in the facility. I don't trust the LLM; I verify it."*

### 3. Graceful Fallback & Fast Paths (Operational Excellence)
**Feature:** The STRICT mode fast-path (`is_fast_path`) for single file explanations.
**The Pitch:**
> *"When an engineer asks to 'explain this file' and selects a single script in STRICT mode, executing a vector search is a waste of compute and introduces chunk-boundary loss. I implemented a fast-path circuit breaker: if the query intent is `FILE_EXPLANATION` and exactly one file $< 32KB$ is selected, it bypasses Qdrant entirely, loads the exact file content into syntax bounds, and feeds it directly to the prompt builder. It reduces retrieval latency from 150ms to 2ms and guarantees 100% context inclusion."*

### 4. Zero-Cost Intent Routing (Frugality / Bias for Action)
**Feature:** `QueryClassifier._RULES`
**The Pitch:**
> *"Many modern RAG applications use an LLM agent just to figure out what the user is asking. That adds $1.5+$ seconds of latency and API costs. I profiled standard industrial queries and built a deterministic, multi-label regex classifier that runs in less than a millisecond. It dictates whether the orchestrator needs to query the semantic index, the structured SQL index, or both, ensuring strict routing efficiency."*
