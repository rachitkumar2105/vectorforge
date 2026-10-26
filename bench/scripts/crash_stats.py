"""How often does a hard kill leave a torn WAL tail? Evidence that the recovery path is exercised.

Run from engine/: python ../bench/scripts/crash_stats.py
"""

import random
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine" / "tests"))

from test_crash_recovery import run_and_kill  # noqa: E402

from vectorforge.collection import Collection  # noqa: E402


def main(kills: int = 30) -> None:
    reasons: Counter[str] = Counter()
    torn_bytes = 0
    rng = random.Random(0)
    for n in range(kills):
        with tempfile.TemporaryDirectory() as tmp:
            run_and_kill(
                Path(tmp), ["hnsw", "flat", "ivf"][n % 3], 0, rng.randint(5, 60), "chunked"
            )
            c = Collection.open(Path(tmp) / "crash")
            report = c.replay_report
            reasons[report.reason or "clean tail"] += 1
            torn_bytes += report.truncated_bytes
            c.close()
    print(f"{kills} kills: {dict(reasons)}; total torn bytes discarded {torn_bytes}")


if __name__ == "__main__":
    main()
