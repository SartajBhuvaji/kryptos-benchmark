"""Hill cipher over Z/26 — linear algebra on blocks of letters.

A block of ``n`` plaintext letters becomes a column vector over Z/26 and is multiplied by
an ``n x n`` key matrix::

    c = K p  (mod 26)

Decryption multiplies by ``K^-1 (mod 26)``, which exists only when ``det K`` is a unit
modulo 26 — that is, when ``gcd(det K, 26) == 1``. Since 26 = 2 x 13, a determinant that
is merely non-zero is not enough: any even determinant, or any multiple of 13, has no
inverse. This is the trap that makes randomly generated key matrices fail, and
:func:`is_invertible` exists so generators can screen for it.

Why this is in the project
--------------------------
The Hill conjecture for K4, formalised by Bauer, Link and Molle, rests on an anomalous
extra ``L`` carved into the sculpture's Vigenère tableau, which produces a vertical
``H-I-L-L``. Nothing here bears on whether that conjecture is right. The cipher is
implemented because Phase 3 needs it for the composite K4 *proxies* — a Vigenère stage
followed by a Hill stage is a genuine multi-layer capability probe, regardless of what K4
actually is.

Blocks, not passthrough
-----------------------
Unlike the Quagmire and route ciphers, this one is block-structured: a stray ``?`` would
shift every subsequent letter into a different block. Only A-Z is accepted, and the text
length must be a multiple of the block size. Callers pad deliberately rather than having
padding applied behind their back.

Known-plaintext attack
----------------------
Hill is linear, so it falls to a known-plaintext attack outright. Given ``n`` plaintext
blocks whose matrix is invertible mod 26, ``K = C P^-1``. :func:`recover_key` does this,
which is what a Tier 4 solver would need to run against the ``BERLIN``/``CLOCK`` cribs
under the Hill conjecture.
"""

from __future__ import annotations

import math
import string
from itertools import combinations

ALPHABET = string.ascii_uppercase
MODULUS = 26

#: Row-major square matrix over Z/26.
Matrix = tuple[tuple[int, ...], ...]

_FOLD = str.maketrans(string.ascii_lowercase, ALPHABET)


# --- matrix arithmetic over Z/26 --------------------------------------------------


def determinant(matrix: Matrix) -> int:
    """Determinant reduced mod 26, by cofactor expansion.

    >>> determinant(((3, 3), (2, 5)))
    9
    """
    rows = _validate_matrix(matrix)
    return _det(rows) % MODULUS


def is_invertible(matrix: Matrix) -> bool:
    """Whether the matrix has an inverse mod 26.

    Requires ``gcd(det, 26) == 1``. A non-zero determinant is *not* sufficient — 26 is
    composite, so even determinants and multiples of 13 are singular here.

    >>> is_invertible(((3, 3), (2, 5)))
    True
    >>> is_invertible(((2, 4), (6, 8)))
    False
    """
    return math.gcd(determinant(matrix), MODULUS) == 1


def inverse(matrix: Matrix) -> Matrix:
    """Matrix inverse mod 26, via the adjugate.

    ``K^-1 = det(K)^-1 * adj(K)  (mod 26)``.

    >>> inverse(((3, 3), (2, 5)))
    ((15, 17), (20, 9))
    """
    rows = _validate_matrix(matrix)
    det = _det(rows) % MODULUS
    if math.gcd(det, MODULUS) != 1:
        raise ValueError(
            f"matrix is not invertible mod {MODULUS}: determinant {det} shares a factor "
            f"with {MODULUS} (needs gcd == 1, and {MODULUS} = 2 x 13)"
        )
    det_inv = pow(det, -1, MODULUS)
    adj = _adjugate(rows)
    return tuple(tuple(det_inv * value % MODULUS for value in row) for row in adj)


def multiply(a: Matrix, b: Matrix) -> Matrix:
    """Matrix product mod 26."""
    left, right = _validate_matrix(a), _validate_matrix(b)
    if len(left[0]) != len(right):
        raise ValueError(f"shape mismatch: {len(left)}x{len(left[0])} times {len(right)}x{len(right[0])}")
    return tuple(
        tuple(
            sum(left[i][k] * right[k][j] for k in range(len(right))) % MODULUS
            for j in range(len(right[0]))
        )
        for i in range(len(left))
    )


# --- the cipher -------------------------------------------------------------------


def encrypt(plaintext: str, matrix: Matrix) -> str:
    """Encipher ``plaintext`` in blocks of ``len(matrix)``.

    >>> encrypt("HELP", ((3, 3), (2, 5)))
    'HIAT'
    """
    return _apply(plaintext, _validate_matrix(matrix))


def decrypt(ciphertext: str, matrix: Matrix) -> str:
    """Decipher ``ciphertext``. Inverse of :func:`encrypt`.

    >>> decrypt("HIAT", ((3, 3), (2, 5)))
    'HELP'
    """
    return _apply(ciphertext, inverse(matrix))


def recover_key(plaintext: str, ciphertext: str, block_size: int) -> Matrix:
    """Recover the key matrix from known plaintext — the standard break.

    Needs ``block_size`` plaintext blocks that together form an invertible matrix; it
    searches combinations of the available blocks until it finds such a set, so extra
    known text helps when the first blocks happen to be singular.

    >>> recover_key("HELP", "HIAT", 2)
    ((3, 3), (2, 5))
    """
    plain = _normalize(plaintext)
    cipher = _normalize(ciphertext)
    if len(plain) != len(cipher):
        raise ValueError(f"lengths differ: {len(plain)} plaintext vs {len(cipher)} ciphertext")
    # bool subclasses int, so True would silently mean a block size of 1.
    if isinstance(block_size, bool) or not isinstance(block_size, int) or block_size < 1:
        raise ValueError(f"block_size must be a positive integer, got {block_size!r}")
    if len(plain) % block_size:
        raise ValueError(f"text length {len(plain)} is not a multiple of block size {block_size}")

    count = len(plain) // block_size
    if count < block_size:
        raise ValueError(
            f"need at least {block_size} blocks to solve for a {block_size}x{block_size} "
            f"key, got {count}"
        )

    p_blocks = [_block(plain, i, block_size) for i in range(count)]
    c_blocks = [_block(cipher, i, block_size) for i in range(count)]

    for chosen in combinations(range(count), block_size):
        # Columns are blocks, so P and C are block_size x block_size.
        p_matrix = tuple(tuple(p_blocks[j][r] for j in chosen) for r in range(block_size))
        if not is_invertible(p_matrix):
            continue
        c_matrix = tuple(tuple(c_blocks[j][r] for j in chosen) for r in range(block_size))
        return multiply(c_matrix, inverse(p_matrix))

    raise ValueError(
        f"no {block_size} of the {count} known blocks form an invertible matrix mod "
        f"{MODULUS}; more known plaintext is needed"
    )


# --- internals --------------------------------------------------------------------


def _apply(text: str, matrix: Matrix) -> str:
    letters = _normalize(text)
    size = len(matrix)
    if len(letters) % size:
        raise ValueError(
            f"text length {len(letters)} is not a multiple of block size {size}; "
            f"pad deliberately rather than relying on the cipher to do it"
        )
    out: list[str] = []
    for start in range(0, len(letters), size):
        block = [ALPHABET.index(ch) for ch in letters[start : start + size]]
        for row in matrix:
            out.append(ALPHABET[sum(a * b for a, b in zip(row, block)) % MODULUS])
    return "".join(out)


def _block(text: str, index: int, size: int) -> list[int]:
    return [ALPHABET.index(ch) for ch in text[index * size : (index + 1) * size]]


def _det(rows: tuple[tuple[int, ...], ...]) -> int:
    n = len(rows)
    if n == 1:
        return rows[0][0]
    if n == 2:
        return rows[0][0] * rows[1][1] - rows[0][1] * rows[1][0]
    total = 0
    for column in range(n):
        minor = tuple(
            tuple(value for j, value in enumerate(row) if j != column) for row in rows[1:]
        )
        total += (-1) ** column * rows[0][column] * _det(minor)
    return total


def _adjugate(rows: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, ...], ...]:
    n = len(rows)
    if n == 1:
        return ((1,),)
    cofactors = []
    for i in range(n):
        row = []
        for j in range(n):
            minor = tuple(
                tuple(v for jj, v in enumerate(r) if jj != j)
                for ii, r in enumerate(rows)
                if ii != i
            )
            row.append((-1) ** (i + j) * _det(minor) % MODULUS)
        cofactors.append(row)
    # adjugate is the transpose of the cofactor matrix
    return tuple(tuple(cofactors[i][j] for i in range(n)) for j in range(n))


def _validate_matrix(matrix: Matrix) -> tuple[tuple[int, ...], ...]:
    if not isinstance(matrix, (tuple, list)) or not matrix:
        raise ValueError(f"matrix must be a non-empty sequence of rows, got {matrix!r}")
    rows = tuple(tuple(row) for row in matrix)
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("matrix rows must all be the same length")
    if not width:
        raise ValueError("matrix rows must not be empty")
    for row in rows:
        for value in row:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"matrix entries must be integers, got {value!r}")
    return rows


def _normalize(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError(f"text must be a string, got {type(text).__name__}")
    folded = text.translate(_FOLD)
    for position, ch in enumerate(folded):
        if ch not in ALPHABET:
            raise ValueError(
                f"character {text[position]!r} at position {position} is not a letter; "
                f"the Hill cipher is block-structured and admits no passthrough characters"
            )
    return folded
