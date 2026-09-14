"""Local deterministic context indexing; source content stays in the repository."""

import ast
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
from typing import Protocol

from architect.git_history import GitHistory


class KnowledgeProvider(Protocol):
    def search(self, query: str, *, limit: int = 5) -> list[dict]: ...
    def read(self, path: str, *, start: int = 1, end: int | None = None) -> dict: ...


class LocalContext:
    MAX_FILE_BYTES = 1024 * 1024

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.git = GitHistory(self.root)
        self.cache = self.root / '.architect/context-index.json'

    def _source(self, path):
        file = self.root / path
        if file.is_symlink() or any(parent.is_symlink() for parent in file.parents if parent != self.root.parent):
            raise ValueError('Symlink sources are excluded')
        if not file.resolve().is_relative_to(self.root) or not file.is_file():
            raise ValueError('Source is missing or outside the project')
        if file.stat().st_size > self.MAX_FILE_BYTES:
            raise ValueError('Source exceeds the context file limit')
        data = file.read_bytes()
        if len(data) > self.MAX_FILE_BYTES or b'\0' in data:
            raise ValueError('Binary or oversized source is excluded')
        return data, data.decode('utf-8')

    def _load(self):
        if not self.cache.exists():
            return {'version': 1, 'files': {}}
        if self.cache.is_symlink() or self.cache.parent.is_symlink():
            raise ValueError('Context cache cannot be a symlink')
        data = json.loads(self.cache.read_text())
        if data.get('version') != 1 or not isinstance(data.get('files'), dict):
            raise ValueError('Unsupported context cache')
        return data

    def refresh(self) -> dict:
        old = self._load()
        files, skipped = {}, {}
        parsed = reused = 0
        # Git's tracked index includes newly staged files, but never ignored/untracked files.
        entries = self.git._git('ls-files', '--stage', '-z').split(b'\0')
        for entry in filter(None, entries):
            header, raw_path = entry.split(b'\t', 1)
            mode, blob, stage = header.decode().split()
            path = raw_path.decode('utf-8', 'surrogateescape')
            if path.startswith('.architect/'):
                continue
            if stage != '0':
                raise ValueError('Resolve index conflicts before compiling context')
            if mode not in ('100644', '100755'):
                skipped[path] = 'non-regular tracked entry'
                continue
            try:
                data, text = self._source(path)
            except (OSError, ValueError, UnicodeError) as error:
                skipped[path] = str(error)
                continue
            digest = sha256(data).hexdigest()
            previous = old['files'].get(path)
            if previous and previous['sha256'] == digest:
                files[path] = previous
                reused += 1
                continue
            symbols = []
            parse_error = False
            if path.endswith('.py'):
                try:
                    tree = ast.parse(text)
                    symbols = [{'name': node.name, 'line': node.lineno, 'kind': type(node).__name__}
                               for node in ast.walk(tree)
                               if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
                    symbols.sort(key=lambda item: (item['line'], item['name']))
                except (SyntaxError, ValueError):
                    parse_error = True
            files[path] = {'sha256': digest, 'bytes': len(data), 'lines': len(text.splitlines()),
                           'symbols': symbols, 'parse_error': parse_error}
            parsed += 1
        index = {'version': 1, 'head': self.git._head('HEAD'),
                 'files': dict(sorted(files.items())), 'skipped': dict(sorted(skipped.items()))}
        self.cache.parent.mkdir(exist_ok=True)
        if self.cache.parent.is_symlink() or self.cache.is_symlink():
            raise ValueError('Context cache cannot be a symlink')
        encoded = json.dumps(index, sort_keys=True, ensure_ascii=True, separators=(',', ':'))
        with tempfile.NamedTemporaryFile(mode='w', dir=self.cache.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
        try:
            temporary.replace(self.cache)
        finally:
            temporary.unlink(missing_ok=True)
        return {'head': index['head'], 'indexed': len(files), 'parsed': parsed, 'reused': reused,
                'removed': len(set(old['files']) - set(files)), 'skipped': index['skipped']}

    def repo_map(self) -> dict:
        self.refresh()
        return self._load()

    def search(self, query: str, *, limit: int = 5) -> list[dict]:
        if limit < 1:
            raise ValueError('limit must be positive')
        terms = sorted(set(re.findall(r'\w+', query.casefold())))
        self.refresh()
        hits = []
        for path, info in self._load()['files'].items():
            haystack = path.casefold() + ' ' + ' '.join(s['name'].casefold() for s in info['symbols'])
            score = sum(term in haystack for term in terms)
            if score:
                hits.append({'path': path, 'score': score, **info})
        hits.sort(key=lambda item: (-item['score'], item['path']))
        return hits[:limit]

    def read(self, path: str, *, start: int = 1, end: int | None = None) -> dict:
        info = self._load()['files'].get(path)
        if info is None:
            raise ValueError('Path is not indexed; refresh first')
        tracked = self.git._git('ls-files', '--stage', '-z', '--', ':(literal)' + path)
        entries = [entry for entry in tracked.split(b'\0') if entry]
        if len(entries) != 1:
            raise ValueError('Source is no longer a regular tracked stage-0 file')
        header, current_path = entries[0].split(b'\t', 1)
        mode, _, stage = header.decode().split()
        if stage != '0' or mode not in ('100644', '100755') or current_path.decode('utf-8', 'surrogateescape') != path:
            raise ValueError('Source is no longer a regular tracked stage-0 file')
        data, text = self._source(path)
        if sha256(data).hexdigest() != info['sha256']:
            raise ValueError('Indexed source changed; refresh before reading')
        lines = text.splitlines(keepends=True)
        last = len(lines) if end is None else end
        if start < 1 or last < start or last > len(lines):
            raise ValueError('Invalid source line range')
        return {'path': path, 'start': start, 'end': last, 'sha256': info['sha256'],
                'content': ''.join(lines[start-1:last])}

    def bootstrap(self, query: str, *, max_chars: int = 12000, limit: int = 5) -> dict:
        if max_chars < 1:
            raise ValueError('max_chars must be positive')
        hits = self.search(query, limit=limit)
        index = self._load()
        candidates = list(dict.fromkeys(['AGENTS.md', 'docs/STATUS.md', 'docs/ROADMAP.md']
                                       + [hit['path'] for hit in hits]))
        snippets, omitted = [], []
        used = 0
        for path in candidates:
            info = index['files'].get(path)
            if info is None or info['lines'] == 0:
                omitted.append({'path': path, 'reason': 'not indexed or empty'})
                continue
            snippet = self.read(path)
            if used + len(snippet['content']) > max_chars:
                omitted.append({'path': path, 'reason': 'character budget'})
                continue
            snippets.append(snippet)
            used += len(snippet['content'])
        return {'head': index['head'], 'snippets': snippets, 'omitted': omitted,
                'metrics': {'characters': used, 'max_characters': max_chars,
                            'estimated_tokens': (used + 3)//4, 'token_estimator': 'ceil(characters/4); not model tokenization'},
                'indexed_files': len(index['files']), 'skipped': index['skipped'],
                'coverage': 'tracked working-tree regular UTF-8 files up to 1 MiB; no untracked files'}
