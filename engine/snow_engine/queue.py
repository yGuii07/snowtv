from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from .pipeline import Pipeline
from .store import JobStore


class JobQueue:
    def __init__(self, store: JobStore, pipeline: Pipeline, workers: int = 1):
        self.store = store
        self.pipeline = pipeline
        self.executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="snow-worker")
        self._active: dict[str, Future[Any]] = {}
        self._lock = threading.Lock()

    def submit(self, job_id: str) -> None:
        with self._lock:
            active = self._active.get(job_id)
            if active is not None and not active.done():
                return
            self.store.update(
                job_id, status="queued", stage="queued", progress=0,
                error=None, cancel_requested=0,
            )
            future = self.executor.submit(self.pipeline.process, job_id)
            self._active[job_id] = future
        # A Future que termina imediatamente executa o callback de forma
        # síncrona. Registre-o fora do lock para evitar deadlock ao recuperar
        # jobs pequenos (ou mocks usados pelo health check/testes).
        future.add_done_callback(lambda _: self._forget(job_id))

    def recover(self) -> int:
        jobs = self.store.recoverable()
        for job in jobs:
            self.store.append_log(job["job_id"], "Fila recuperada após reinício do Snow Engine.")
            self.submit(job["job_id"])
        return len(jobs)

    def cancel(self, job_id: str) -> bool:
        job = self.store.get(job_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return False
        self.store.update(
            job_id,
            status="cancelled",
            stage="cancelled",
            progress=100,
            error="Processamento cancelado pelo usuário.",
            cancel_requested=1,
        )
        self.store.append_log(
            job_id,
            "Cancelamento solicitado. A operação externa atual será encerrada no próximo ponto seguro.",
            level="warning",
        )
        with self._lock:
            future = self._active.get(job_id)
            if future is not None:
                future.cancel()
        return True

    def resume(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job["status"] not in {"cancelled", "failed"}:
            raise ValueError("Somente jobs cancelados ou com falha podem ser retomados.")
        with self._lock:
            active = self._active.get(job_id)
            if active is not None and not active.done():
                raise ValueError("O cancelamento ainda está finalizando. Aguarde alguns segundos e tente retomar novamente.")
        self.store.append_log(job_id, "Retomada solicitada; caches e artefatos válidos serão reutilizados.")
        self.submit(job_id)

    def _forget(self, job_id: str) -> None:
        with self._lock:
            self._active.pop(job_id, None)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)
