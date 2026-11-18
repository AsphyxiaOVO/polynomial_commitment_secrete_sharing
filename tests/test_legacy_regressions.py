"""Regression tests against the original (legacy) implementation.

* "bug" tests reproduce problems of the legacy code that the refactoring fixes;
* "equivalence" tests show that the refactored algebra gives the same numbers
  as the legacy Prover/Verifier/FRI wherever the legacy code was correct.

The legacy modules import NumPy/SymPy and Tkinter; Tkinter is stubbed so the
tests also run on headless machines.  Skipped if NumPy/SymPy are missing.
"""

import importlib
import io
import os
import sys
import types
from contextlib import redirect_stdout

import pytest

pytest.importorskip("numpy")
pytest.importorskip("sympy")

from pcss import fri, polynomial  # noqa: E402
from pcss.commitment import Prover, Verifier  # noqa: E402
from pcss.config import FIELD_MODULUS  # noqa: E402
from pcss.encoding import decode_message, encode_message  # noqa: E402
from pcss.errors import DuplicatePointError  # noqa: E402

P = FIELD_MODULUS
LEGACY_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "legacy")


@pytest.fixture(scope="module")
def legacy():
    if "tkinter" not in sys.modules:
        try:
            import tkinter  # noqa: F401
        except ImportError:  # headless CI: provide a minimal stub
            tk = types.ModuleType("tkinter")
            tk.Tk = object
            sys.modules["tkinter"] = tk
            sys.modules["tkinter.messagebox"] = types.ModuleType("tkinter.messagebox")
            sys.modules["tkinter.scrolledtext"] = types.ModuleType("tkinter.scrolledtext")
            tk.messagebox = sys.modules["tkinter.messagebox"]
            tk.scrolledtext = sys.modules["tkinter.scrolledtext"]
    sys.path.insert(0, os.path.abspath(LEGACY_DIR))
    try:
        mods = {name: importlib.import_module(name) for name in
                ("rxi", "message_coding", "FRI", "polynomial_division",
                 "main_withui_finally", "secret_clipswithui")}
    finally:
        sys.path.pop(0)
    return types.SimpleNamespace(**mods)


# --------------------------------------------------------------------------- #
# Bugs fixed by the refactoring
# --------------------------------------------------------------------------- #

def test_bug_numpy_interpolation_overflows_for_255_bit_field(legacy):
    points = [(0, P - 5), (1, P - 7), (2, 3)]
    with pytest.raises(OverflowError):
        legacy.rxi.fit_polynomial(points, P)
    coeffs = polynomial.interpolate(points)
    assert [polynomial.evaluate(coeffs, x) for x, _ in points] == [y for _, y in points]


def test_bug_leading_nul_bytes_lost(legacy):
    msg = "\x00abc"
    n = legacy.message_coding.encode_message_to_constant(msg)
    assert legacy.message_coding.decode_constant_to_message(n) == "abc"   # data loss
    enc = encode_message(msg)
    assert decode_message(enc.chunks, enc.original_length) == msg


def test_bug_decimal_chunks_can_exceed_small_field(legacy):
    n = legacy.message_coding.encode_message_to_constant("Hello")
    parts, _ = legacy.message_coding.split_integer_to_polynomials(n, 2)
    assert any(part >= 13 for part in parts)  # irrecoverable after "mod 13"


def test_bug_duplicate_x_silently_accepted(legacy):
    # mod_inverse(0) returned 0, so a duplicate x produced a number instead of an error.
    value = legacy.secret_clipswithui.lagrange([(1, 5), (1, 5), (2, 7)], 13)
    assert isinstance(value, int)
    with pytest.raises(DuplicatePointError):
        polynomial.lagrange_evaluate([(1, 5), (1, 5), (2, 7)])


def test_bug_degree_detection_skips_degree_6(legacy):
    prover = legacy.main_withui_finally.Prover()
    prover.coefficients = [[1, 2, 3, 4, 5, 6] + [0]]   # GUI appends constant 0 -> degree 6
    with redirect_stdout(io.StringIO()):
        prover.reduce_high_degree_polynomials()
    assert prover.coefficients[0] == [1, 2, 3, 4, 5, 6, 0]  # not folded although 6 > 5
    assert len(fri.reduce_degree(polynomial.from_high_to_low([1, 2, 3, 4, 5, 6, 0])).rounds) == 1


def test_bug_empty_complement_crashes(legacy):
    verifier = legacy.main_withui_finally.Verifier(10, 3)
    with pytest.raises(IndexError):
        verifier.compute_zi([0, 1, 2], [[0, 1, 2]], P)          # S_0 == T
    prover = Prover([[5, 6, 7, 8]], [[0, 1, 2]], [0, 1, 2])
    assert Verifier(prover.public_parameters()).verify_opening(prover.open(10, 3)).valid


def test_bug_x_in_T_accepts_any_witness(legacy):
    m = legacy.main_withui_finally
    verifier = m.Verifier(8, 5)                    # x = 8 ∈ T \ S_0
    T, S = [0, 3, 8], [[0, 3]]
    verifier.verify_equality(T, P)
    zi = verifier.compute_zi(T, S, P)              # Z_{T\S_0}(8) = 0
    right = verifier.compute_f_right(1, 5, [42], [17], zi, P)   # arbitrary cm, r(x)
    assert verifier.compute_f_left(123456789, P) == right == 0


# --------------------------------------------------------------------------- #
# Equivalence with the legacy algebra
# --------------------------------------------------------------------------- #

def test_equivalence_prover_and_verifier(legacy, rng):
    m = legacy.main_withui_finally
    polys = [[rng.randrange(P) for _ in range(5)], [rng.randrange(P) for _ in range(3)]]
    S, T = [[0, 3], [0, 3, 8]], [0, 3, 8, 11]
    x, y = 1000, 77

    old = m.Prover()
    old.field, old.S, old.points, old.T = P, S, S, T
    old.coefficients = [polynomial.to_high_to_low(f) for f in polys]
    # legacy rxi.fit_polynomial cannot handle this field; feed it the correct r_i (high-to-low)
    old.rx = [polynomial.to_high_to_low(polynomial.interpolate(
        [(s, polynomial.evaluate(f, s)) for s in Si])) for f, Si in zip(polys, S)]
    old.initialized = True

    new = Prover(polys, S, T)
    assert list(new.commitments(x)) == old.compute_commitments(x)
    assert new.witness(x, y) == old.compute_proof_w(y, x)

    v_old = m.Verifier(x, y)
    v_old.verify_equality(T, P)
    zi = v_old.compute_zi(T, S, P)
    ri = [m.Prover.evaluate_polynomial(r, x, P) for r in old.rx]
    right_old = v_old.compute_f_right(2, y, list(new.commitments(x)), ri, zi, P)
    left_old = v_old.compute_f_left(new.witness(x, y), P)
    res = Verifier(new.public_parameters()).verify_opening(new.open(x, y))
    assert (res.left, res.right) == (left_old, right_old) and res.valid


@pytest.mark.parametrize("coeffs", [[1, 2, 3, 4, 5], [7, 0, 3, 9, 1, 4], [1, 2, 3, 4, 5, 6, 7, 8]])
def test_equivalence_fri_single_round(legacy, coeffs):
    with redirect_stdout(io.StringIO()):
        even, odd = legacy.FRI.split_polynomial(coeffs)
        old = legacy.FRI.transform_to_y_polynomial(even, odd, 6)
    assert polynomial.trim([c % P for c in old]) == fri.fold(coeffs, 6)
