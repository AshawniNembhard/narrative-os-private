"""One-owner upload-based migration for earlier Narrative OS SQLite databases.

Only known tables/columns are copied as data; no source SQL is executed against
our application database. Runtime flags, external credentials and OAuth tokens
are never migrated. The upload size is bounded and the temporary file is deleted.
"""
from __future__ import annotations
import os
import json
import sqlite3
import tempfile
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import Response

MAX_DB_BYTES=32*1024*1024
TABLES={
 'events': ('id','mode','occurred','created','payload'),
 'chart_imports': ('symbol','interval','uploaded','last_candle','payload'),
 'council_plans': ('id','created','payload'),
 'council_runs': ('id','plan_id','created','payload'),
 'council_bias_states': ('focus','horizon','updated','payload'),
}

def copy_rows(source_path, destination, max_rows=50000):
    """Copy only known v0.6 data tables, within an existing destination transaction."""
    old=sqlite3.connect(f'file:{Path(source_path).as_posix()}?mode=ro',uri=True)
    try:
        if old.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise ValueError('Uploaded SQLite file failed integrity check')
        names={r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'events','council_plans','chart_imports'}.intersection(names):
            raise ValueError('This does not look like a Narrative OS database')
        imported={}
        for table,cols in TABLES.items():
            if table not in names:continue
            available={r[1] for r in old.execute(f'PRAGMA table_info({table})')}
            if not set(cols).issubset(available):continue
            count=old.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            if count>max_rows:raise ValueError(f'{table} exceeds migration row limit')
            rows=old.execute(f'SELECT {",".join(cols)} FROM {table}').fetchall()
            if table=='events':
                verified=[]
                for row in rows:
                    try:
                        payload=json.loads(row[4])
                        if isinstance(payload,dict) and payload.get('id')==row[0] and isinstance(payload.get('time'),str):verified.append(row)
                    except (ValueError,TypeError):pass
                rows=verified
            if not rows:continue
            before=destination.total_changes
            placeholders=','.join('?' for _ in cols)
            # Historic chart IDs are deliberately not copied; destination ids are unique.
            destination.executemany(f'INSERT OR IGNORE INTO {table} ({",".join(cols)}) VALUES ({placeholders})',rows)
            imported[table]=destination.total_changes-before
        return imported
    finally:old.close()

async def import_db(request:Request, destination_factory, lock):
    fd, path=tempfile.mkstemp(prefix='narrative-migrate-',suffix='.db')
    size=0
    try:
        with os.fdopen(fd,'wb') as target:
            async for chunk in request.stream():
                size+=len(chunk)
                if size>MAX_DB_BYTES:raise HTTPException(413,'Legacy database must be smaller than 32MB')
                target.write(chunk)
        with open(path,'rb') as src_file:magic=src_file.read(16)
        if size<100 or magic!=b'SQLite format 3\x00':
            raise HTTPException(422,'Choose the original narrative.db SQLite file, not a ZIP or JSON export')
        try:
            with lock, destination_factory() as dest:
                data=copy_rows(path,dest)
        except (ValueError,sqlite3.Error) as exc:
            raise HTTPException(422,'Import rejected: '+str(exc)[:200]) from exc
        return {'ok':True,'imported':data,'message':'Known research tables imported. Refresh the dashboard.'}
    finally:
        try:os.unlink(path)
        except OSError:pass

def backup_db(destination_factory,lock):
    with lock, destination_factory() as src:
        target=sqlite3.connect(':memory:')
        try:
            src.backup(target)
            data=target.serialize()
        finally:target.close()
    return Response(data,media_type='application/octet-stream',headers={
        'Content-Disposition':'attachment; filename="narrative-os-backup.db"',
        'Cache-Control':'no-store'})