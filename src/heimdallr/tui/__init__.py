"""TUI package for heimdallr."""

from dataclasses import dataclass

from .. import __version__
from .app import HeimdallrApp


@dataclass
class TuiResult:
    """What the CLI needs to know after the TUI exits.

    The TUI normally spawns the agent in a new terminal window itself and
    stays open. The CLI only acts when window-spawning isn't available and
    the TUI exited with a fallback resume command — it then runs the agent
    in the current shell via `os.execvp`.
    """

    resume_command: list[str] | None
    resume_directory: str | None
    session_id: str | None
    agent: str | None


def run_tui(
    query: str = "",
    agent_filter: str | None = None,
    yolo: bool = False,
) -> TuiResult:
    app = HeimdallrApp(initial_query=query, agent_filter=agent_filter, yolo=yolo)
    app.run()
    return TuiResult(
        resume_command=app.get_resume_command(),
        resume_directory=app.get_resume_directory(),
        session_id=app.get_resume_session_id(),
        agent=app.get_resume_agent(),
    )


__all__ = ["HeimdallrApp", "TuiResult", "run_tui", "__version__"]
