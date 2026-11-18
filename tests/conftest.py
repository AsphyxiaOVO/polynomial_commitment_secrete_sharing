import random

import pytest

from pcss.config import FIELD_MODULUS


@pytest.fixture
def rng():
    """Deterministic random source so failures are reproducible."""
    return random.Random(20250318)


@pytest.fixture
def randbelow(rng):
    """Drop-in replacement for secrets.randbelow driven by the seeded rng."""
    return rng.randrange


@pytest.fixture
def p():
    return FIELD_MODULUS
