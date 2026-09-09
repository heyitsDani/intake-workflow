"""
config.py - environment and model configuration for the triage pipeline.

Loads ANTHROPIC_API_KEY from .env (or the shell environment). One model
constant, used for every call in the pipeline - see docs/DECISIONS.md
("Model choice: use the strongest available model for every call").
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-5"
