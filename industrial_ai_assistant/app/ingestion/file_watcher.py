import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from app.ingestion.ingestion_manager import IngestionManager

class IngestionHandler(FileSystemEventHandler):
    def __init__(self, manager: IngestionManager):
        self.manager = manager

    def on_created(self, event):
        if not event.is_directory:
            print(f"New file detected: {event.src_path}")
            self.manager.ingest_file(event.src_path)

class FileWatcher:
    def __init__(self, watch_dir: str, manager: IngestionManager):
        self.observer = Observer()
        self.watch_dir = watch_dir
        self.handler = IngestionHandler(manager)

    def start(self):
        self.observer.schedule(self.handler, self.watch_dir, recursive=True)
        self.observer.start()
        print(f"Watching {self.watch_dir} for new files...")

    def stop(self):
        self.observer.stop()
        self.observer.join()
