"""Shared argparse help strings reused across ``_commands`` noun modules.

Centralized here so the same literal text isn't duplicated verbatim across
every noun module's ``register()`` (SonarCloud S1192). Keep the text
identical to what each module previously inlined.
"""

from __future__ import annotations

JSON_HELP = "Emit structured JSON."
PUBLICATION_HELP = "Publication host, e.g. example.substack.com"
