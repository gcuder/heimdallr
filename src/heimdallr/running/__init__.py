"""Running-session detection — multi-layered.

- Layer 1: psutil process scan (most authoritative when --resume <sid> in argv)
- Layer 2: mtime activity (low-confidence "warm" signal)
- Layer 3: self-launched PID tracking (resume wrapper records $$ before exec)
- Layer 4: ~/.claude/ide/*.lock files (upgrade confidence + show IDE name)
"""

from .detector import RunningDetector, RunningSnapshot
from .pid_tracker import SpawnedRow
from .pid_tracker import live as pid_tracker_live
from .resume_wrapper_path import wrapper_path

__all__ = [
    "RunningDetector",
    "RunningSnapshot",
    "SpawnedRow",
    "pid_tracker_live",
    "wrapper_path",
]
