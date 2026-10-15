from __future__ import annotations

import os
import time
import uuid
from pathlib import Path


class LockHeldError(RuntimeError):
    pass


class RunLock:
    """Exclusive O_EXCL lock file with age-based stale-lock recovery."""

    def __init__(self, output_dir: Path, stale_after_seconds: float):
        self.path = output_dir / ".tenderscrape.lock"
        self.stale_after_seconds = stale_after_seconds
        self.token = f"{os.getpid()}:{uuid.uuid4().hex}"
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age <= self.stale_after_seconds:
                    raise LockHeldError(f"another scraper run holds {self.path.name}")
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    continue
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
                    lock_file.write(self.token)
                    lock_file.flush()
                    os.fsync(lock_file.fileno())
                self.acquired = True
                return
        raise LockHeldError("could not acquire scraper lock after stale-lock check")

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            if self.path.read_text(encoding="utf-8") == self.token:
                self.path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_exc):
        self.release()
