"""Text <-> data helpers shared by the Tkinter front-ends.

No Tkinter import here, so the parsing rules are unit-tested on headless
machines (``tests/test_gui_parsing.py``).  All errors are ValidationError.
"""

from __future__ import annotations

import json
from typing import List, Optional, Sequence, Tuple

from pcss.errors import ValidationError
from pcss.sharing import Share, SharingMetadata


def parse_int(text: str, name: str) -> int:
    text = text.strip()
    if not text:
        raise ValidationError(f"{name} must not be empty")
    try:
        return int(text, 10)
    except ValueError:
        raise ValidationError(f"{name} must be an integer, got {text!r}") from None


def parse_optional_int(text: str, name: str) -> Optional[int]:
    return None if not text.strip() else parse_int(text, name)


def parse_int_list(text: str, name: str) -> List[int]:
    """Parse ``"1, 2,3"`` (commas and/or whitespace) into ``[1, 2, 3]``."""
    parts = [p for p in text.replace(",", " ").split() if p]
    if not parts:
        raise ValidationError(f"{name} must contain at least one integer")
    return [parse_int(p, f"{name}[{i}]") for i, p in enumerate(parts)]


def parse_point_sets(text: str) -> List[List[int]]:
    """One point set S_i per non-empty line, e.g. ``"0,3\\n0,3,8"``.

    A single line is broadcast to every chunk polynomial by ``DealerSession``.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValidationError("at least one point set S_i is required")
    return [parse_int_list(ln, f"S_{i}") for i, ln in enumerate(lines)]


def bundle_to_json(metadata: SharingMetadata, shares: Sequence[Share]) -> str:
    """Serialise metadata + shares for the recovery tool (ints stay exact in JSON)."""
    return json.dumps({"metadata": metadata.to_dict(),
                       "shares": [s.to_dict() for s in shares]}, indent=2)


def bundle_from_json(text: str) -> Tuple[SharingMetadata, List[Share]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON: {exc.msg} (line {exc.lineno})") from exc
    if not isinstance(data, dict) or "metadata" not in data or "shares" not in data:
        raise ValidationError('JSON must be an object with "metadata" and "shares"')
    if not isinstance(data["shares"], list):
        raise ValidationError('"shares" must be a list')
    metadata = SharingMetadata.from_dict(data["metadata"])
    shares = []
    for i, item in enumerate(data["shares"]):
        if not isinstance(item, dict) or not isinstance(item.get("values"), list):
            raise ValidationError(f"shares[{i}] must be an object with x and values")
        shares.append(Share.from_dict(item))
    return metadata, shares
