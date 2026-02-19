# PLC Fault System — Evaluation Checklist
*Amazon-style engineering review*

## Hallucination & Data Integrity

| Check | Status |
|---|---|
| Does system send raw CSV to LLM? | ✅ NO — only pre-computed stats are sent |
| Does LLM decide confidence? | ✅ NO — `fault_confidence.py` uses deterministic thresholds |
| Is fault analysis reproducible? | ✅ YES — `analysis_version` + `dataset_hash` in every response |
| Are required columns enforced? | ✅ YES — `FaultSchemaError` raised on missing cols |

## Memory & Scalability

| Check | Status |
|---|---|
| Can system handle 100k rows? | ✅ YES — tested up to 200k (sampling limit) |
| Hard limit enforced? | ✅ YES — MAX_ROWS = 250,000 |
| Single dataset constraint enforced? | ✅ YES — MAX_DATASETS = 1 |
| GC called on new upload? | ✅ YES — `gc.collect()` after del previous df |
| Memory reported via metrics? | ✅ YES — `/api/fault/metrics` endpoint |

## Correctness

| Check | Status |
|---|---|
| Schema normalization handles synonyms? | ✅ YES — 40+ aliases |
| Mixed timezone CSVs handled? | ✅ YES — per-record UTC conversion with warning |
| Timestamps sorted before row_id assignment? | ✅ YES — enforced in `schema_normalizer.py` |
| Co-occurrence uses O(n log n) algorithm? | ✅ YES — sorted + sliding window pointers |
| Burst detection implemented? | ✅ YES — sliding window, O(n) |

## Concurrency

| Check | Status |
|---|---|
| Dataset mutations thread-safe? | ✅ YES — `threading.RLock()` on all mutations |
| Race condition on analyze + upload? | ✅ PROTECTED — lock wraps store mutations |

## API Contracts

| Check | Status |
|---|---|
| All endpoints use Pydantic response models? | ✅ YES |
| Loose dict returns? | ✅ NONE |
| Typed error responses? | ✅ YES — `ErrorResponse` model |

## Performance Benchmarks (Expected)

| Operation | Target | Design |
|---|---|---|
| 50k row upload | < 3s | pandas chunked read + index |
| Summary (cached) | < 50ms | `stats_cache` — no recompute |
| Detail retrieval | < 200ms | bisect O(log n) |
| LLM analysis | < 5s | 8s timeout guard |
| UI scroll (10k rows) | 60fps | react-virtual |

## Open Items

- [ ] Chunked read for files close to 50MB limit
- [ ] Multi-project support (v2)
- [ ] Time-series cache invalidation on filter
