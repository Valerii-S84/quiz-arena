from __future__ import annotations

from app.db.repo.processed_updates_repo_metrics import ProcessedUpdatesRepoMetricsMixin
from app.db.repo.processed_updates_repo_slots import ProcessedUpdatesRepoSlotsMixin


class ProcessedUpdatesRepo(ProcessedUpdatesRepoSlotsMixin, ProcessedUpdatesRepoMetricsMixin):
    pass
