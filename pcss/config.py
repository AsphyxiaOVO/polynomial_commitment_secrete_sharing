"""Global constants and resource limits.

All finite-field arithmetic in the package uses the single prime modulus
``FIELD_MODULUS``.  It is defined here only; other modules import it.

Note: using the prime 2**255 - 19 does NOT make the protocol production-grade
cryptography.  This project is a teaching / research prototype.
"""

from __future__ import annotations

#: The prime p = 2^255 - 19.  Every value handled by the core is an element of GF(p).
FIELD_MODULUS: int = 2**255 - 19

#: Number of message bytes stored in one secret chunk (one polynomial constant term).
#: 256**31 == 2**248 < FIELD_MODULUS, so every chunk integer is a valid field element.
CHUNK_SIZE: int = 31

# --------------------------------------------------------------------------- #
# Resource limits (protect against accidental / malicious huge inputs).
# --------------------------------------------------------------------------- #

#: Smallest allowed recovery threshold k.
MIN_THRESHOLD: int = 2
#: Largest allowed recovery threshold k (polynomial degree is k - 1).
MAX_THRESHOLD: int = 32
#: Largest allowed number of participants / shares n.
MAX_SHARE_COUNT: int = 100
#: Largest accepted message length in UTF-8 bytes.
MAX_MESSAGE_BYTES: int = 2048
#: Largest number of chunks a message may produce (derived from MAX_MESSAGE_BYTES).
MAX_CHUNK_COUNT: int = -(-MAX_MESSAGE_BYTES // CHUNK_SIZE)

#: Largest |S_i| (the original GUI limited each point set to at most 6 points).
MAX_POINT_SET_SIZE: int = 6
#: Largest |T| (the union evaluation set used by the commitment/verification step).
MAX_EVALUATION_SET_SIZE: int = 64

#: Largest number of coefficients accepted by generic polynomial helpers / the FRI prototype.
MAX_POLYNOMIAL_LENGTH: int = 1024
#: Default "fold until degree <= this" bound used by the FRI-style prototype.
FRI_DEFAULT_MAX_DEGREE: int = 5
#: Folding challenge used by the original FRI.py (``reduce_power`` hard-coded a = 6).
FRI_DEFAULT_ALPHA: int = 6

if 256**CHUNK_SIZE >= FIELD_MODULUS:  # pragma: no cover - static sanity check
    raise RuntimeError("CHUNK_SIZE too large for FIELD_MODULUS")
