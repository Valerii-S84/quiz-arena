# P2-2 Question Selection Hot Path Report

Date: `2026-02-22`

## Scope
- Replace O(N) candidate selection path in runtime question picking.
- Keep anti-repeat behavior and deterministic seed-based selection.
- Add simple before/after benchmark.

## Implemented Changes
1. Runtime pool caching + fast pick:
   - `app/game/questions/runtime_bank.py`
   - Added in-process cache for question ID pools (`mode + level`) with TTL.
   - Replaced per-request full candidate-list materialization with deterministic circular pick from cached ordered pool.
   - Added stale-cache self-heal: if selected `question_id` is missing, cache is cleared and selection retries once.
2. Config knobs:
   - `app/core/config.py`
   - `.env.example`
   - `.env.production.example`
   - Added `QUIZ_QUESTION_POOL_CACHE_TTL_SECONDS` (default `300`).
3. Tests:
   - `tests/game/test_runtime_bank.py`
   - Added cache reuse test and stale-cache refresh test.
4. Benchmark script:
   - `scripts/benchmark_question_selection_hotpath.py`

## Benchmark (Before/After)
Command:
```bash
TMPDIR=/tmp .venv/bin/python -m scripts.benchmark_question_selection_hotpath --pool-size 40000 --recent-size 12 --iterations 5000
```

Result:
```text
Question Selection Hot Path Benchmark
pool_size=40000 recent_size=12 iterations=5000
old: total_ms=63085.87 avg_ms=12.617174
new: total_ms=13.91 avg_ms=0.002781
speedup_x=4536.46
```

Notes:
- This benchmark is synthetic (algorithm-level), not full DB end-to-end.
- It validates expected complexity reduction from repeated full-pool filtering to cached deterministic pick with anti-repeat skip.

## Validation
- `ruff check app tests scripts` -> passed.
- `mypy app/game/questions/runtime_bank.py app/workers/tasks/retention_cleanup.py tests/game/test_runtime_bank.py` -> passed.
- `pytest -q tests/game/test_runtime_bank.py tests/game/test_question_selection.py tests/bot/test_gameplay_handler_flow.py` -> passed.
- `pytest -q -s tests/integration/test_artikel_sprint_progress_integration.py tests/integration/test_retention_cleanup_integration.py` -> passed.
