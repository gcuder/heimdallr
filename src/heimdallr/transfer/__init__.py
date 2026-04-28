"""Context-transfer machinery: compact a session, inject it into another."""

from .compactor import ContextBundle, Strategy, compact
from .injector import InjectPlan, build_inject_plan, execute_plan, save_transfer_row

__all__ = [
    "ContextBundle",
    "InjectPlan",
    "Strategy",
    "build_inject_plan",
    "compact",
    "execute_plan",
    "save_transfer_row",
]
