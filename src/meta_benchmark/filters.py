from __future__ import annotations

import re


def build_filter_regex_for_cases(cases: list[str]) -> str | None:
    if not cases:
        return None
    escaped = [re.escape(c) for c in cases]
    union = "|".join(escaped)
    # Avoid non-capturing groups for ECMAScript regex; use capturing groups instead.
    return f"^({union})$"


