"""Multi-provider LLM adapter plugin for Spakky Agent."""

from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-llm")
"""Plugin identifier for the multi-provider LLM adapter package."""

__all__ = ["PLUGIN_NAME"]
