"""Command-line walkthrough of the whole workflow (no GUI needed).

    python examples/demo.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from pcss import (FIELD_MODULUS, DealerSession, InsufficientSharesError, Verifier,  # noqa: E402
                  recover_message)
from pcss.fri import reduce_degree  # noqa: E402


def main() -> None:
    message = "多项式承诺 × 秘密分享 / 多項式コミットメント 🔐"
    session = DealerSession.create(message, threshold=3, share_count=5, point_sets=[[0, 7, 9]])
    meta = session.metadata
    print("metadata:", meta.to_dict())
    print("T =", session.public_parameters().evaluation_set,
          "| share x =", [s.x for s in session.shares])

    verifier = Verifier(session.public_parameters())
    for share in session.shares:
        _, opening = session.open_share(share.x)            # random challenge y
        result = verifier.verify_opening(opening)
        print(f"share x={share.x}: verification {'OK' if result else 'FAILED'}")

    _, opening = session.open_share(1, y=12345)
    bad = verifier.verify(1, 12345, opening.commitments, (opening.witness + 1) % FIELD_MODULUS)
    print("tampered witness accepted?", bad.valid)

    print("recovered from shares x=1,3,5:", recover_message(session.shares[::2], meta))
    try:
        recover_message(session.shares[:2], meta)
    except InsufficientSharesError as exc:
        print("2 shares:", exc)

    red = reduce_degree(list(range(1, 31)), alpha=6, max_degree=5)
    print("FRI prototype (independent of sharing): degrees", red.degrees)


if __name__ == "__main__":
    main()
