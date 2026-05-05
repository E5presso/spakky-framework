"""Acceptance test import path setup for example modules."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2]))
