from __future__ import annotations

import argparse
from dataclasses import dataclass
from time import perf_counter


def _stable_index(seed: str, size: int) -> int:
    import hashlib

    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size


def _old_select_question_id(
    pool_ids: tuple[str, ...],
    *,
    recent_question_ids: tuple[str, ...],
    selection_seed: str,
) -> str | None:
    if not pool_ids:
        return None
    filtered_ids = [question_id for question_id in pool_ids if question_id not in set(recent_question_ids)]
    candidate_ids = filtered_ids if filtered_ids else list(pool_ids)
    return candidate_ids[_stable_index(selection_seed, len(candidate_ids))]


def _new_select_question_id(
    pool_ids: tuple[str, ...],
    *,
    recent_question_ids: tuple[str, ...],
    selection_seed: str,
) -> str | None:
    if not pool_ids:
        return None
    excluded = set(recent_question_ids)
    if len(excluded) >= len(pool_ids):
        excluded = set()
    start_index = _stable_index(selection_seed, len(pool_ids))
    for offset in range(len(pool_ids)):
        question_id = pool_ids[(start_index + offset) % len(pool_ids)]
        if question_id not in excluded:
            return question_id
    return None


@dataclass(frozen=True)
class BenchmarkResult:
    variant: str
    iterations: int
    elapsed_ms: float
    avg_ms: float


def _run_variant(
    *,
    variant: str,
    pool_ids: tuple[str, ...],
    recent_question_ids: tuple[str, ...],
    iterations: int,
) -> BenchmarkResult:
    selector = _old_select_question_id if variant == "old" else _new_select_question_id
    started_at = perf_counter()
    for idx in range(iterations):
        seed = f"bench-seed-{idx}"
        selected = selector(
            pool_ids,
            recent_question_ids=recent_question_ids,
            selection_seed=seed,
        )
        if selected is None:
            raise RuntimeError("selector returned None with non-empty pool")
        if len(recent_question_ids) < len(pool_ids) and selected in set(recent_question_ids):
            raise RuntimeError("anti-repeat invariant broken")
    elapsed_ms = (perf_counter() - started_at) * 1000
    return BenchmarkResult(
        variant=variant,
        iterations=iterations,
        elapsed_ms=elapsed_ms,
        avg_ms=elapsed_ms / iterations,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark old/new question-selection hot path.")
    parser.add_argument("--pool-size", type=int, default=40000)
    parser.add_argument("--recent-size", type=int, default=12)
    parser.add_argument("--iterations", type=int, default=5000)
    args = parser.parse_args()

    pool_size = max(1, int(args.pool_size))
    recent_size = max(0, min(pool_size, int(args.recent_size)))
    iterations = max(1, int(args.iterations))

    pool_ids = tuple(f"q_{idx:06d}" for idx in range(pool_size))
    recent_question_ids = tuple(pool_ids[idx] for idx in range(recent_size))

    old_result = _run_variant(
        variant="old",
        pool_ids=pool_ids,
        recent_question_ids=recent_question_ids,
        iterations=iterations,
    )
    new_result = _run_variant(
        variant="new",
        pool_ids=pool_ids,
        recent_question_ids=recent_question_ids,
        iterations=iterations,
    )

    speedup = old_result.elapsed_ms / new_result.elapsed_ms if new_result.elapsed_ms > 0 else 0.0
    print("Question Selection Hot Path Benchmark")
    print(f"pool_size={pool_size} recent_size={recent_size} iterations={iterations}")
    print(
        f"old: total_ms={old_result.elapsed_ms:.2f} avg_ms={old_result.avg_ms:.6f}"
    )
    print(
        f"new: total_ms={new_result.elapsed_ms:.2f} avg_ms={new_result.avg_ms:.6f}"
    )
    print(f"speedup_x={speedup:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
