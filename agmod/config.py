"""Central configuration. Every tunable is env-var overridable.

The point is a single place for paths/settings so the rest of the code never
hardcodes machine-specific values.
"""
from __future__ import annotations

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where structure dumps + caches live.
CACHE_ROOT = os.environ.get("AGMOD_CACHE_ROOT", os.path.join(PROJECT_ROOT, "mods"))

# Optional explicit path to the `rea` CLI (morluto/rea). Defaults to PATH lookup.
REA_PATH = os.environ.get("REA_PATH", "")
