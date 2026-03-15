import json
import os
import sqlite3
from datetime import date, datetime
from threading import Lock
from typing import Any, Dict, List, Optional

from models.task import Task
from services.task_store_memory_backup import TaskStoreMemoryBackup


class _SQLiteTaskStore:
    """Persistent task store backed by SQLite."""

    def __init__(self) -> None:
        default_db = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "task_store.db"))
        self._db_path = os.environ.get("TASK_STORE_DB_PATH", default_db)
        self._lock = Lock()
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    company_name TEXT,
                    report_type TEXT,
                    analysis_type TEXT,
                    status TEXT,
                    progress INTEGER,
                    start_time TEXT,
                    end_time TEXT,
                    results_json TEXT,
                    error TEXT,
                    user_data_json TEXT,
                    message TEXT,
                    report_path TEXT,
                    detected_type TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def _task_to_payload(self, task: Task) -> Dict[str, Any]:
        def _json_default(value: Any) -> Any:
            # Handle datetime-like objects produced by pandas/numpy without hard dependency.
            if isinstance(value, (datetime, date)):
                return value.isoformat()

            isoformat = getattr(value, "isoformat", None)
            if callable(isoformat):
                try:
                    return isoformat()
                except Exception:
                    pass

            tolist = getattr(value, "tolist", None)
            if callable(tolist):
                try:
                    return tolist()
                except Exception:
                    pass

            return str(value)

        return {
            "id": task.id,
            "filename": task.filename,
            "filepath": task.filepath,
            "company_name": task.company_name,
            "report_type": task.report_type,
            "analysis_type": task.analysis_type,
            "status": task.status,
            "progress": task.progress,
            "start_time": task.start_time,
            "end_time": task.end_time,
            "results_json": (
                json.dumps(task.results, ensure_ascii=False, default=_json_default)
                if task.results is not None
                else None
            ),
            "error": task.error,
            "user_data_json": json.dumps(task.user_data or {}, ensure_ascii=False, default=_json_default),
            "message": task.message,
            "report_path": task.report_path,
            "detected_type": task.detected_type,
        }

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        results = None
        user_data = {}
        if row["results_json"]:
            try:
                results = json.loads(row["results_json"])
            except Exception:
                results = None
        if row["user_data_json"]:
            try:
                user_data = json.loads(row["user_data_json"])
            except Exception:
                user_data = {}

        return Task(
            id=row["id"],
            filename=row["filename"],
            filepath=row["filepath"],
            company_name=row["company_name"] or row["filename"],
            report_type=row["report_type"] or "auto",
            analysis_type=row["analysis_type"] or "comprehensive",
            status=row["status"] or "pending",
            progress=int(row["progress"] or 0),
            start_time=row["start_time"] or "",
            end_time=row["end_time"],
            results=results,
            error=row["error"],
            user_data=user_data,
            message=row["message"],
            report_path=row["report_path"],
            detected_type=row["detected_type"],
        )

    def create(self, task: Task) -> Task:
        payload = self._task_to_payload(task)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tasks (
                        id, filename, filepath, company_name, report_type, analysis_type,
                        status, progress, start_time, end_time, results_json, error,
                        user_data_json, message, report_path, detected_type, updated_at
                    ) VALUES (
                        :id, :filename, :filepath, :company_name, :report_type, :analysis_type,
                        :status, :progress, :start_time, :end_time, :results_json, :error,
                        :user_data_json, :message, :report_path, :detected_type, CURRENT_TIMESTAMP
                    )
                    """,
                    payload,
                )
                conn.commit()
        return task

    def get(self, task_id: str) -> Optional[Task]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def update(self, task_id: str, **kwargs) -> Optional[Task]:
        task = self.get(task_id)
        if not task:
            return None

        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)

        payload = self._task_to_payload(task)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE tasks SET
                        filename = :filename,
                        filepath = :filepath,
                        company_name = :company_name,
                        report_type = :report_type,
                        analysis_type = :analysis_type,
                        status = :status,
                        progress = :progress,
                        start_time = :start_time,
                        end_time = :end_time,
                        results_json = :results_json,
                        error = :error,
                        user_data_json = :user_data_json,
                        message = :message,
                        report_path = :report_path,
                        detected_type = :detected_type,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """,
                    payload,
                )
                conn.commit()
        return task

    def recent(self, limit: int = 10) -> List[Task]:
        if limit <= 0:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def all(self) -> Dict[str, Task]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tasks").fetchall()
            tasks = [self._row_to_task(r) for r in rows]
            return {t.id: t for t in tasks}

    def delete(self, task_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
                return cursor.rowcount > 0


class TaskStore:
    """Facade: default SQLite persistence; optional memory backend for backup mode."""

    def __init__(self) -> None:
        backend = os.environ.get("TASK_STORE_BACKEND", "sqlite").strip().lower()
        if backend == "memory":
            self._impl = TaskStoreMemoryBackup()
        else:
            self._impl = _SQLiteTaskStore()

    def create(self, task: Task) -> Task:
        return self._impl.create(task)

    def get(self, task_id: str) -> Optional[Task]:
        return self._impl.get(task_id)

    def update(self, task_id: str, **kwargs) -> Optional[Task]:
        return self._impl.update(task_id, **kwargs)

    def recent(self, limit: int = 10) -> List[Task]:
        return self._impl.recent(limit)

    def all(self) -> Dict[str, Task]:
        return self._impl.all()

    def delete(self, task_id: str) -> bool:
        return self._impl.delete(task_id)
