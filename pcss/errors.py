"""Exception hierarchy.

Every error raised deliberately by the package derives from :class:`PCSSError`.
Input problems additionally derive from :class:`ValueError`, so callers that
only know the standard library can still catch them.
"""

from __future__ import annotations


class PCSSError(Exception):
    """Base class for all errors raised by the pcss package."""


class ValidationError(PCSSError, ValueError):
    """An argument is malformed, out of range or inconsistent with other arguments."""


class FieldElementError(ValidationError):
    """A value is not an integer in the range [0, FIELD_MODULUS)."""


class NonInvertibleError(PCSSError, ZeroDivisionError):
    """A field element has no multiplicative inverse (it is 0 modulo p)."""


class DuplicatePointError(ValidationError):
    """Two interpolation / share x-coordinates coincide in the field."""


class InsufficientSharesError(ValidationError):
    """Fewer shares than the recovery threshold were supplied."""


class InconsistentSharesError(ValidationError):
    """Redundant shares do not lie on a single polynomial of degree threshold - 1."""


class DecodingError(ValidationError):
    """Recovered chunks cannot be turned back into the original message."""


class ProtocolError(PCSSError):
    """An internal algebraic invariant was violated (indicates a bug or corrupted state)."""
