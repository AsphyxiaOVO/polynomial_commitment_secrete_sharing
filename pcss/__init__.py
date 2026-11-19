"""pcss — polynomial-commitment-style verifiable secret sharing (teaching / research prototype).

Modules
-------
config      FIELD_MODULUS = 2^255 - 19, CHUNK_SIZE = 31, resource limits
errors      exception hierarchy
field       GF(p) arithmetic with Python ints
polynomial  polynomial arithmetic (low-to-high coefficients), interpolation
encoding    UTF-8 message <-> 31-byte chunks
sharing     threshold sharing (degree = k - 1) and recovery
commitment  Prover / Verifier of the thesis' batched evaluation check
fri         FRI-style folding (stand-alone research prototype)
vss         end-to-end workflow combining sharing and commitment

Not production cryptography: see README "Known limitations".
"""

from .config import CHUNK_SIZE, FIELD_MODULUS
from .commitment import Opening, Prover, PublicParameters, VerificationResult, Verifier
from .encoding import EncodedMessage, decode_message, encode_message
from .errors import (DecodingError, DuplicatePointError, FieldElementError,
                     InconsistentSharesError, InsufficientSharesError, NonInvertibleError,
                     PCSSError, ProtocolError, ValidationError)
from .sharing import (Share, SharingMetadata, SharingResult, recover_constants, recover_message,
                      split_secret)
from .vss import DealerSession

__all__ = [
    "CHUNK_SIZE", "FIELD_MODULUS",
    "Opening", "Prover", "PublicParameters", "VerificationResult", "Verifier",
    "EncodedMessage", "decode_message", "encode_message",
    "DecodingError", "DuplicatePointError", "FieldElementError", "InconsistentSharesError",
    "InsufficientSharesError", "NonInvertibleError", "PCSSError", "ProtocolError",
    "ValidationError",
    "Share", "SharingMetadata", "SharingResult", "recover_constants", "recover_message",
    "split_secret", "DealerSession",
]

__version__ = "0.2.0"
