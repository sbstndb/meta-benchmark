import re
from typing import List, Optional


def build_filter_regex_for_cases(cases: List[str]) -> Optional[str]:
    if not cases:
        return None
    escaped = [re.escape(c) for c in cases]
    union = "|".join(escaped)
    # Avoid non-capturing groups for ECMAScript regex; use capturing groups instead.
    return f"^({union})$"


