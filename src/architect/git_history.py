"""Read-only, commit-pinned Git history for Project Chronicle."""

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess


class GitHistory:
    """Committed history reachable from one resolved revision; no working-tree reads.

    Merge paths are relative to the first parent. Renames are represented as
    deletion + addition, avoiding configuration-dependent similarity detection.
    """

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).expanduser().resolve()
        top = os.fsdecode(self._git('rev-parse', '--show-toplevel').removesuffix(b'\n'))
        if Path(top).resolve() != self.root:
            raise ValueError('Git history requires the repository root')

    def _git(self, *args, allow_missing=False):
        env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        result = subprocess.run(
            ['git', '--no-replace-objects', '-C', str(self.root), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        )
        if result.returncode:
            if allow_missing and result.returncode == 1:
                return None
            raise ValueError('Git history source is unavailable or invalid')
        return result.stdout

    def _head(self, revision):
        value = self._git('rev-parse', '--verify', '--quiet', '--end-of-options',
                          revision + '^{commit}', allow_missing=True)
        if value is not None:
            return value.decode().strip()
        if revision == 'HEAD':
            branch = self._git('symbolic-ref', '-q', 'HEAD', allow_missing=True)
            if branch is not None and self._git('show-ref', '--verify', '--quiet',
                                                branch.decode().strip(), allow_missing=True) is None:
                return None  # An unborn branch has no committed history.
        raise ValueError('Unknown Git revision')

    def changes(self, revision: str = 'HEAD') -> list[dict]:
        head = self._head(revision)
        if head is None:
            return []
        records = []
        for line in self._git('rev-list', '--timestamp', '--parents', head, '--').splitlines():
            stamp, commit, *parents = line.decode().split()
            args = ['diff-tree', '--no-ext-diff', '--no-textconv', '--no-renames',
                    '--ignore-submodules=none', '--no-commit-id', '--name-status', '-r', '-z']
            args += [parents[0], commit] if parents else ['--root', commit]
            fields = self._git(*args, '--').split(b'\0')
            paths = []
            for i in range(0, len(fields) - 1, 2):
                paths.append({'status': fields[i].decode('ascii'),
                              'path': fields[i + 1].decode('utf-8', 'surrogateescape')})
            paths.sort(key=lambda item: item['path'])
            records.append({
                'kind': 'git_change', 'project_root': str(self.root),
                'commit_id': commit, 'parents': parents,
                'timestamp': datetime.fromtimestamp(int(stamp), timezone.utc).isoformat(timespec='microseconds'),
                'comparison_parent': parents[0] if parents else None,
                'changed_paths': paths,
            })
        records.sort(key=lambda record: (record['timestamp'], record['commit_id']))
        return records

    def file(self, commit_id: str, path: str) -> dict:
        """Resolve a regular file by full commit ID and exact tree path.

        Returned bytes and blob ID establish provenance even after HEAD changes.
        Symlinks/submodules are not followed or treated as decision documents.
        """
        if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit_id):
            raise ValueError('A full Git commit ID is required')
        if not path or path.startswith('/') or any(part in ('.', '..', '') for part in path.split('/')):
            raise ValueError('An exact relative Git path is required')
        rows = self._git('ls-tree', '-z', commit_id, '--', ':(literal)' + path).split(b'\0')
        for row in filter(None, rows):
            header, name = row.split(b'\t', 1)
            mode, kind, blob = header.decode().split()
            if name.decode('utf-8', 'surrogateescape') == path and kind == 'blob' and mode in ('100644', '100755'):
                return {'commit_id': commit_id, 'path': path, 'blob_id': blob,
                        'content': self._git('cat-file', 'blob', blob)}
        raise ValueError('Regular file not found at Git commit')

    def decisions(self, revision: str = 'HEAD') -> list[dict]:
        """ADR revisions, including deletion records with prior-content provenance.

        This is document history, not inferred acceptance, rationale or tool approval.
        """
        records = []
        for change in self.changes(revision):
            for item in change['changed_paths']:
                path = item['path']
                if not (path.startswith('docs/adr/') and Path(path).name.startswith('ADR-') and path.endswith('.md')):
                    continue
                source = change['comparison_parent'] if item['status'] == 'D' else change['commit_id']
                try:
                    evidence = self.file(source, path)
                except ValueError as error:
                    # A symlink or non-regular tree entry is not an ADR document.
                    if str(error) == 'Regular file not found at Git commit':
                        continue
                    raise
                records.append({
                    'kind': 'adr_revision', 'project_root': str(self.root),
                    'commit_id': change['commit_id'], 'timestamp': change['timestamp'],
                    'change_status': item['status'], 'path': path,
                    'source_commit_id': source, 'blob_id': evidence['blob_id'],
                })
        return records
