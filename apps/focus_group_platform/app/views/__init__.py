"""The views. Each renders service output; none computes anything."""
from __future__ import annotations

from . import frozen_benchmark, generate, home, new_evaluation

__all__ = ["home", "frozen_benchmark", "new_evaluation", "generate"]
