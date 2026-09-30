"""Local Compose retention scheduler. Hosted deployment uses a managed cron job."""

import signal
import subprocess
import sys
from pathlib import Path
from threading import Event

stop = Event()
for signum in (signal.SIGTERM, signal.SIGINT):
    signal.signal(signum, lambda *_: stop.set())
while not stop.is_set():
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("cleanup.py"))], check=False)
    if result.returncode:
        print("Retention job failed; operator action is required.", flush=True)
    stop.wait(3600)
