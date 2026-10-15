"""Immutable, private upload objects. SQLite owns references and permissions."""
import os
import re
import uuid
import fcntl
import stat
from contextlib import contextmanager
from pathlib import Path

CHUNK_SIZE=1024*1024
MAX_FILE_BYTES=250*1024**3


class UploadTooLarge(Exception):
    pass


class FileStorage:
    def __init__(self,data):
        self.root=Path(data)/'file-objects'
        self.root.mkdir(mode=0o700,exist_ok=True)
        self.lock_path=Path(data)/'file-objects.lock'

    @contextmanager
    def writing(self):
        """Protect all staged objects through the database commit, across workers."""
        with self.lock_path.open('a+b') as lock:
            os.chmod(self.lock_path,0o600)
            fcntl.flock(lock,fcntl.LOCK_SH)
            try:yield
            finally:fcntl.flock(lock,fcntl.LOCK_UN)

    def collect_unused(self,connection):
        """Recover interrupted uploads; skip a sweep if any upload is active.

        Hold the file lease before taking the database writer lock, matching
        upload commit order. A fresh reference snapshot covers all owners,
        copied files and recycled files. Unrecognized filesystem entries stay.
        """
        with self.lock_path.open('a+b') as lock:
            os.chmod(self.lock_path,0o600)
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return {'skipped':'active-upload','removed':0,'bytes':0}
            except PermissionError:
                # Sandboxes may deny advisory locks. Never sweep without a lease;
                # existing files remain readable and protected writes still require locking.
                return {'skipped':'advisory-lock-unavailable','removed':0,'bytes':0}
            try:
                connection.execute('BEGIN IMMEDIATE')
                try:
                    referenced={r[0] for r in connection.execute('SELECT DISTINCT blob_key FROM drive_file_blobs')}
                    removed=freed=0
                    for path in self.root.iterdir():
                        if not re.fullmatch('[a-f0-9]{32}',path.name) or path.name in referenced:continue
                        try:info=path.lstat()
                        except FileNotFoundError:continue
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:continue
                        path.unlink();removed+=1;freed+=info.st_size
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
                return {'skipped':None,'removed':removed,'bytes':freed}
            finally:fcntl.flock(lock,fcntl.LOCK_UN)

    def path(self,key):
        if not isinstance(key,str) or not re.fullmatch('[a-f0-9]{32}',key):
            raise ValueError('Invalid storage key')
        path=self.root/key
        if path.is_symlink():raise ValueError('Storage object must not be a symlink')
        return path

    async def stage(self,upload,limit):
        key=uuid.uuid4().hex;path=self.path(key);size=0
        try:
            with path.open('xb') as output:
                os.chmod(path,0o600)
                while True:
                    chunk=await upload.read(CHUNK_SIZE)
                    if not chunk:break
                    size+=len(chunk)
                    if size>min(limit,MAX_FILE_BYTES):raise UploadTooLarge()
                    output.write(chunk)
                output.flush();os.fsync(output.fileno())
            return key,size
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def discard(self,key):
        self.path(key).unlink(missing_ok=True)
