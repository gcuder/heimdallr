"""TUI package for heimdallr."""

from .. import __version__
from .app import HeimdallrApp


def run_tui(
    query: str = "",
    agent_filter: str | None = None,
    yolo: bool = False,
) -> tuple[list[str] | None, str | None, str | None, str | None]:
    """Run the TUI; return (resume_cmd_argv, resume_directory, session_id, agent).

    Session id and agent are returned alongside the command so the CLI's wrapper
    can record them for self-PID tracking before exec.
    """
    app = HeimdallrApp(initial_query=query, agent_filter=agent_filter, yolo=yolo)
    app.run()
    return (
        app.get_resume_command(),
        app.get_resume_directory(),
        app.get_resume_session_id(),
        app.get_resume_agent(),
    )


__all__ = ["HeimdallrApp", "run_tui", "__version__"]
