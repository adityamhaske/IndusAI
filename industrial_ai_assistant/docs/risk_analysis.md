# PLC Fault System — Risk Analysis

## Complexity

| Operation | Complexity |
|---|---|
| Upload + parse | O(n) |
| Schema normalization | O(n) |
| Summary stats (build_stats_cache) | O(n) |
| Summary retrieval (cached) | O(1) |
| Detail retrieval | O(log n) via bisect |
| Co-occurrence | O(n log n) — sort + sliding window |
| Burst detection | O(n) — single pass sliding window |
| LLM analysis | O(log n) + network I/O |

## Failure Modes

| Failure | Detection | Mitigation |
|---|---|---|
| Corrupt / binary CSV | `FaultParsingError` | Return 400 with structured error |
| File > 50MB | `FaultTooLargeError` | Rejected before reading (size check) |
| Missing `fault_code` / `timestamp` | `FaultSchemaError` | Structured error with missing col list |
| Non-parseable timestamps | Log warning, drop rows | Warn in upload response |
| Mixed timezones | Per-row UTC conversion | Warning included in response |
| Memory spike (large upload) | MAX_ROWS = 250k | Hard reject above limit |
| Two simultaneous uploads | `threading.RLock` | Second upload blocks until first completes |
| LLM timeout | 8s guard | Returns partial structured error |
| Stale dataset reference | `DatasetHashMismatchError` | Reject with 409 |
| Row ID not found | `FaultRowNotFoundError` | 404 response |

## Scaling Risks

- **Single-server design**: In-memory store is not shared across multiple uvicorn workers. Use `--workers 1` in production or migrate to Redis/shared DB for multi-worker.
- **Memory ceiling**: 200k rows × 6 cols ≈ 200MB. Acceptable for single-engineer workstation. Monitor via `/api/fault/metrics`.
- **LLM bottleneck**: LLM calls are synchronous per request. Use `asyncio`/background workers for concurrent analysis in v2.

## Security Considerations

- CSV files are processed in-memory, never written to disk.
- No external LLM APIs — fully local (Ollama).
- No authentication in v1 — add API key middleware before any shared deployment.
- File type validated server-side (Content-Type + pandas parse attempt).

## Improvement Roadmap

| Version | Feature |
|---|---|
| v1.1 | Chunked pandas reading for files near 50MB limit |
| v1.2 | Export filtered results to CSV |
| v2.0 | Multi-project support + persistent dataset store |
| v2.1 | Background async LLM analysis with WebSocket streaming |
| v3.0 | Time-series anomaly detection (statistical, no LLM) |
