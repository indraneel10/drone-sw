"""One local CLI process owns each survey database at a time."""
import os
from pathlib import Path


class DatabaseLease:
    def __init__(self, database):
        self.path = Path(str(Path(database).resolve()) + '.lock')
        self.handle = None

    def __enter__(self):
        self.handle = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.handle.seek(0, os.SEEK_END)
                if self.handle.tell() == 0:
                    self.handle.write(b'0')
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close()
            self.handle = None
            raise OSError('Cannot acquire database lock; another monitor may already be using this database') from error
        return self

    def __exit__(self, *args):
        if self.handle is not None:
            try:
                if os.name == 'nt':
                    import msvcrt
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None
        # Keep the lock file: removing it can allow separate inode owners to race.
