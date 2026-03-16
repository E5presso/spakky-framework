"""Pytest configuration for spakky-celery tests."""

import nest_asyncio

# Allow nested asyncio.run() calls in tests with existing event loops (pytest-asyncio)
nest_asyncio.apply()
