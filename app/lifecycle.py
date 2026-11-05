"""User deletion with durable cleanup and minimal cancellation tombstones."""
import json
import re
import sqlite3

from sqlalchemy import Column, MetaData, String, Table, Text, delete, insert, select

from app.jobs import job_rows
from app.store import Conflict, NotFound, annotations, resumes, versions

metadata = MetaData()
cleanup_rows = Table('deletion_cleanup', metadata, Column('id', String, primary_key=True), Column('data', Text, nullable=False))


class Lifecycle:
    def __init__(self, store, jobs, data_dir):
        self.store, self.jobs, self.root = store, jobs, data_dir.resolve()
        metadata.create_all(store.engine)

    @staticmethod
    def _id(value):
        if not re.fullmatch(r'[0-9a-f]{32}', value):
            raise NotFound('记录不存在')

    def _references(self, connection):
        result = set()
        for text in connection.execute(select(annotations.c.info)).scalars():
            info = json.loads(text)
            result.update(value for value in (info.get('job_id'), info.get('review_job_id')) if value)
        return result

    def _queue(self, connection, key, data):
        if connection.execute(select(cleanup_rows.c.id).where(cleanup_rows.c.id == key)).first() is None:
            connection.execute(insert(cleanup_rows).values(id=key, data=json.dumps(data)))

    def _erase_job(self, connection, job, retained):
        keep = {k: job[k] for k in ('id', 'stage', 'revisions', 'calls', 'elapsed_ms', 'engine', 'engine_version', 'budget_policy', 'mode', 'created_at') if k in job}
        source = {k: v for k, v in job.get('input', {}).items()
                  if k in ('target_role', 'jd', 'career_stage', 'has_career_gap', 'execution_mode', 'allow_questions')}
        evidence = job.get('evidence', []) if retained else []
        job.clear()
        job.update(keep, input=source if retained else {}, evidence=evidence, draft=None, review=None, issues=[], adopted_resume_id=None)
        job.update(deleted=True, state='cancelled', run_token='', request_started=None, error='记录已删除')
        self.jobs._write(connection, job)
        self._queue(connection, 'job:'+job['id'], {'job_id': job['id']})

    def delete_job(self, job_id):
        self._id(job_id)
        with self.store.engine.begin() as connection:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            job = self.jobs._get(connection, job_id)
            retained = job_id in self._references(connection)
            self._erase_job(connection, job, retained)
        pending = self.retry_cleanup()
        return {'deleted': True, 'retained_for_resume': retained, 'cleanup_pending': pending}

    def related_jobs(self, resume_id):
        with self.store.engine.connect() as connection:
            info = [json.loads(text) for text in connection.execute(select(annotations.c.info).where(annotations.c.resume_id == resume_id)).scalars()]
            refs = {value for row in info for value in (row.get('job_id'), row.get('review_job_id')) if value}
            jobs = [json.loads(text) for text in connection.execute(select(job_rows.c.data)).scalars()]
            return [job['id'] for job in jobs if job['id'] in refs or job.get('adopted_resume_id') == resume_id
                    or job.get('input', {}).get('review_resume_id') == resume_id]

    def delete_resume(self, resume_id, revision):
        self._id(resume_id)
        related = self.related_jobs(resume_id)
        with self.store.engine.begin() as connection:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                record = self.store._read(connection, resume_id)
            except NotFound:
                record = None
            if record and record.revision != revision:
                raise Conflict('简历版本已变化，请刷新后再删除')
            connection.execute(delete(annotations).where(annotations.c.resume_id == resume_id))
            connection.execute(delete(versions).where(versions.c.resume_id == resume_id))
            connection.execute(delete(resumes).where(resumes.c.id == resume_id))
            remaining = self._references(connection)
            for job_id in related:
                self._erase_job(connection, self.jobs._get(connection, job_id), job_id in remaining)
            self._queue(connection, 'resume:'+resume_id, {'resume_id': resume_id})
        return {'deleted': True, 'retained_for_resume': False, 'cleanup_pending': self.retry_cleanup()}

    def _cleanup(self, item):
        if 'job_id' in item:
            self._id(item['job_id'])
            path = self.root / 'workflow-checkpoints.sqlite3'
            if path.is_symlink() or path.resolve().parent != self.root:
                raise OSError('检查点目录异常')
            if path.exists():
                with sqlite3.connect(path, timeout=2) as db:
                    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    for name in ('writes', 'checkpoints'):
                        if name in tables:
                            db.execute(f'DELETE FROM {name} WHERE thread_id=?', (item['job_id'],))
        if 'resume_id' in item:
            rid = item['resume_id']
            self._id(rid)
            folder = self.root / 'exports'
            if folder.is_symlink() or folder.is_junction() or folder.resolve().parent != self.root:
                raise OSError('导出目录异常')
            if not folder.exists():
                return
            for manifest in folder.glob(f'resume-{rid[:8]}-*.json'):
                if manifest.is_symlink():
                    raise OSError('导出清单异常')
                data = json.loads(manifest.read_text(encoding='utf-8'))
                if data.get('resume_id') != rid:
                    continue
                artifact = manifest.with_suffix('')
                if artifact.suffix not in ('.pdf', '.docx') or artifact.resolve().parent != folder.resolve():
                    raise OSError('导出路径异常')
                artifact.unlink(missing_ok=True)
                manifest.unlink(missing_ok=True)

    def retry_cleanup(self):
        with self.store.engine.connect() as connection:
            pending = list(connection.execute(select(cleanup_rows)).mappings())
        failed = False
        for row in pending:
            try:
                self._cleanup(json.loads(row['data']))
            except (OSError, ValueError, sqlite3.Error):
                failed = True
                continue
            with self.store.engine.begin() as connection:
                connection.execute(delete(cleanup_rows).where(cleanup_rows.c.id == row['id']))
        return failed
