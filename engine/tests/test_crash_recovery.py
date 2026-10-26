"""Kill a writer process mid-stream and check that recovery loses no acknowledged write.

The writer prints "ACK <i>" only after ``Collection.upsert`` returns, which is after the WAL
fsync. The parent hard-kills it (SIGKILL on POSIX, TerminateProcess on Windows: neither lets the
child run any cleanup) at a random point, often in the middle of a WAL append or a checkpoint.
"""

import random
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

from vectorforge.collection import Collection

DIM = 16

WRITER = textwrap.dedent("""
    import sys
    from pathlib import Path
    import numpy as np
    from vectorforge.collection import Collection, UpsertItem

    root, index_type, start = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
    if sys.argv[4] == "chunked":
        # Fault injection (test process only): write each batch in 7-byte flushed chunks, like a
        # slow disk. A kill then often lands inside a record and leaves a torn tail on disk.
        import os
        from vectorforge.storage import wal as wal_mod

        def chunked_append(self, records):
            data = b"".join(r.encode() for r in records)
            for pos in range(0, len(data), 7):
                self._file.write(data[pos : pos + 7])
                self._file.flush()
            os.fsync(self._file.fileno())

        wal_mod.WriteAheadLog.append = chunked_append
    path = root / "crash"
    if path.exists():
        c = Collection.open(path, checkpoint_every=40)
    else:
        params = {{"hnsw": {{"M": 8, "ef_construction": 32}}, "ivf": {{"nlist": 4}}, "flat": {{}}}}
        c = Collection.create(root, "crash", dim={dim}, metric="l2", index_type=index_type,
                              index_params=params[index_type], checkpoint_every=40)
    print("READY", flush=True)
    i = start
    while True:
        batch = [UpsertItem(f"v{{j}}", np.random.default_rng(j).standard_normal({dim})
                 .astype(np.float32), {{"j": j}}) for j in range(i, i + 3)]
        c.upsert(batch)
        deleted = -1
        if i % 9 == 0:
            c.delete(f"v{{i}}")
            deleted = i
        # One line, printed only after both the upsert and the delete are durable, so the parent
        # never sees an ACK without also knowing about that batch's delete.
        print("ACK", i + 2, deleted, flush=True)
        i += 3
    """).format(dim=DIM)


def expected(j: int) -> np.ndarray:
    return np.random.default_rng(j).standard_normal(DIM).astype(np.float32)


def run_and_kill(
    root: Path, index_type: str, start: int, acks_before_kill: int, mode: str = "normal"
) -> tuple[int, set[int]]:
    proc = subprocess.Popen(
        [sys.executable, "-c", WRITER, str(root), index_type, str(start), mode],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    acked, deleted = -1, set()
    seen = 0
    for line in proc.stdout:
        kind, *values = line.split()
        if kind == "ACK":
            acked = int(values[0])
            if int(values[1]) >= 0:
                deleted.add(int(values[1]))
            seen += 1
        if seen >= acks_before_kill:
            break
    proc.kill()
    proc.wait(timeout=30)
    return acked, deleted


@pytest.mark.slow
@pytest.mark.parametrize("run", range(10))
def test_no_acknowledged_write_is_lost_after_kill(tmp_path: Path, run: int) -> None:
    rng = random.Random(run)
    index_type = ["hnsw", "flat", "ivf"][run % 3]
    acked_total, deleted_total = -1, set()
    # Two kill/reopen cycles per run: the second one recovers on top of a recovered collection.
    for _ in range(2):
        # The second writer continues after the last acknowledged id; ids in between may or may
        # not have been committed by the first writer, and either outcome is correct.
        start = acked_total + 1
        start += (-start) % 3
        mode = "chunked" if run % 2 else "normal"
        acked, deleted = run_and_kill(tmp_path, index_type, start, rng.randint(5, 60), mode)
        acked_total = max(acked_total, acked)
        deleted_total |= deleted
        c = Collection.open(tmp_path / "crash")
        for j in range(acked_total + 1):
            if j in deleted_total:
                continue
            vector, meta = c.get(f"v{j}")
            np.testing.assert_array_equal(vector, expected(j))
            assert meta == {"j": j}
        for j in deleted_total:
            with pytest.raises(KeyError):
                c.get(f"v{j}")
        # Every surviving vector is findable through the index, not just the id map.
        probe = max(j for j in range(acked_total + 1) if j not in deleted_total)
        assert c.search(expected(probe), k=1, ef_search=64, nprobe=64).hits[0].id == f"v{probe}"
        c.close()
