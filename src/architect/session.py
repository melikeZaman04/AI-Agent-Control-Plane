"""Deterministic session reports over existing historical evidence."""

from collections import Counter
from datetime import date, datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from architect.chronicle import ProjectChronicle
from architect.git_history import GitHistory


class SessionIntelligence:
    def __init__(self, db_path: str | Path, project_id: int):
        self.chronicle = ProjectChronicle(db_path)
        self.project_id = project_id

    def status(self) -> dict:
        episodes = self.chronicle.query(self.project_id)
        return {
            'report': 'status', 'project_id': self.project_id,
            'recorded_status_counts': dict(sorted(Counter(e.run_status for e in episodes).items())),
            'recorded_active_run_ids': [e.run_id for e in episodes if e.run_status in ('PENDING', 'RUNNING')],
            'runs': [json.loads(e.to_json()) for e in episodes],
            'live_process_state': None,
        }

    def _run(self, run_id):
        episodes = self.chronicle.query(self.project_id, run_id=run_id)
        if run_id is not None and not episodes:
            raise ValueError(f'Unknown run: {run_id}')
        if not episodes:
            return None
        return max(episodes, key=lambda episode: (episode.began_at or '', episode.run_id))

    def resume(self, run_id: str | None = None) -> dict:
        episode = self._run(run_id)
        return {
            'report': 'resume', 'project_id': self.project_id,
            'selection': 'explicit run' if run_id is not None else 'latest recorded start; unknown starts first; full ID tie',
            'run': json.loads(episode.to_json()) if episode else None,
            'next_actions': [], 'provider_resume_command': None,
        }

    def explain(self, run_id: str, *, event_id: str | None = None) -> dict:
        if event_id is not None:
            source = self.chronicle.evidence(self.project_id, run_id=run_id, event_id=event_id)
            evidence = json.loads(source.to_json())
            scope = 'recorded event'
        else:
            source = self._run(run_id)
            evidence = json.loads(source.to_json())
            scope = 'recorded run and normalized observations'
        return {'report': 'explain', 'scope': scope, 'project_id': self.project_id,
                'run_id': run_id, 'evidence': evidence, 'cause': None, 'recommendations': []}

    @staticmethod
    def changes(project_root: str | Path, *, revision='HEAD', since: str | None = None) -> dict:
        history = GitHistory(project_root)
        records = history.changes(revision)
        base = None
        if since is not None:
            base = history._head(since)
            if base is None or base not in {record['commit_id'] for record in records}:
                raise ValueError('Baseline must be reachable from the selected revision')
            excluded = {record['commit_id'] for record in history.changes(base)}
            records = [record for record in records if record['commit_id'] not in excluded]
        return {'report': 'changes', 'baseline_commit_id': base, 'commits': records,
                'run_attribution': None, 'scope': 'committed history; baseline ancestry excluded'}

    def day(self, project_root: str | Path, day: str, *, timezone='UTC', revision='HEAD') -> dict:
        selected = date.fromisoformat(day)
        if selected.isoformat() != day:
            raise ValueError('Date must be YYYY-MM-DD')
        zone = ZoneInfo(timezone)
        def on_day(timestamp):
            return timestamp is not None and datetime.fromisoformat(timestamp).astimezone(zone).date() == selected
        work = []
        for receipt in self.chronicle.receipts(self.project_id):
            observations = [item for item in receipt['observations'] if on_day(item['timestamp'])]
            boundaries = {key: receipt[key] for key in ('began_at', 'ended_at') if on_day(receipt[key])}
            if observations or boundaries:
                work.append({'run_source': receipt['run_source'], 'run_id': receipt['run_id'],
                             'boundaries_on_day': boundaries, 'observations': observations})
        commits = [record for record in GitHistory(project_root).changes(revision) if on_day(record['timestamp'])]
        return {'report': 'day', 'date': day, 'timezone': timezone, 'project_id': self.project_id,
                'work': work, 'commits': commits,
                'scope': 'observed event and receipt-boundary occurrences; independent Git/SQLite snapshots'}
