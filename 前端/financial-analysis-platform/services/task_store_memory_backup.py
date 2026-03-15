from typing import Dict, List, Optional

from models.task import Task


class TaskStoreMemoryBackup:
    """Original in-memory task store kept as backup/fallback."""

    def __init__(self) -> None:
        self._tasks: Dict[str, Task] = {}

    def create(self, task: Task) -> Task:
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs) -> Optional[Task]:
        task = self._tasks.get(task_id)
        if not task:
            return None
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        return task

    def recent(self, limit: int = 10) -> List[Task]:
        if limit <= 0:
            return []
        return list(self._tasks.values())[-limit:]

    def all(self) -> Dict[str, Task]:
        return self._tasks

    def delete(self, task_id: str) -> bool:
        if task_id not in self._tasks:
            return False
        del self._tasks[task_id]
        return True
