"""BLOSUM62 substitution matrix (Henikoff & Henikoff, 1992).

The values are data, not algorithm: the table below is the standard NCBI BLOSUM62 file. A test
(tests/test_alignment.py) checks every one of the 24 x 24 entries against Biopython's copy, so a
typo here cannot go unnoticed.
"""

from __future__ import annotations

import numpy as np

_TABLE = """\
   A   R   N   D   C   Q   E   G   H   I   L   K   M   F   P   S   T   W   Y   V   B   Z   X   *
A  4  -1  -2  -2   0  -1  -1   0  -2  -1  -1  -1  -1  -2  -1   1   0  -3  -2   0  -2  -1   0  -4
R -1   5   0  -2  -3   1   0  -2   0  -3  -2   2  -1  -3  -2  -1  -1  -3  -2  -3  -1   0  -1  -4
N -2   0   6   1  -3   0   0   0   1  -3  -3   0  -2  -3  -2   1   0  -4  -2  -3   3   0  -1  -4
D -2  -2   1   6  -3   0   2  -1  -1  -3  -4  -1  -3  -3  -1   0  -1  -4  -3  -3   4   1  -1  -4
C  0  -3  -3  -3   9  -3  -4  -3  -3  -1  -1  -3  -1  -2  -3  -1  -1  -2  -2  -1  -3  -3  -2  -4
Q -1   1   0   0  -3   5   2  -2   0  -3  -2   1   0  -3  -1   0  -1  -2  -1  -2   0   3  -1  -4
E -1   0   0   2  -4   2   5  -2   0  -3  -3   1  -2  -3  -1   0  -1  -3  -2  -2   1   4  -1  -4
G  0  -2   0  -1  -3  -2  -2   6  -2  -4  -4  -2  -3  -3  -2   0  -2  -2  -3  -3  -1  -2  -1  -4
H -2   0   1  -1  -3   0   0  -2   8  -3  -3  -1  -2  -1  -2  -1  -2  -2   2  -3   0   0  -1  -4
I -1  -3  -3  -3  -1  -3  -3  -4  -3   4   2  -3   1   0  -3  -2  -1  -3  -1   3  -3  -3  -1  -4
L -1  -2  -3  -4  -1  -2  -3  -4  -3   2   4  -2   2   0  -3  -2  -1  -2  -1   1  -4  -3  -1  -4
K -1   2   0  -1  -3   1   1  -2  -1  -3  -2   5  -1  -3  -1   0  -1  -3  -2  -2   0   1  -1  -4
M -1  -1  -2  -3  -1   0  -2  -3  -2   1   2  -1   5   0  -2  -1  -1  -1  -1   1  -3  -1  -1  -4
F -2  -3  -3  -3  -2  -3  -3  -3  -1   0   0  -3   0   6  -4  -2  -2   1   3  -1  -3  -3  -1  -4
P -1  -2  -2  -1  -3  -1  -1  -2  -2  -3  -3  -1  -2  -4   7  -1  -1  -4  -3  -2  -2  -1  -2  -4
S  1  -1   1   0  -1   0   0   0  -1  -2  -2   0  -1  -2  -1   4   1  -3  -2  -2   0   0   0  -4
T  0  -1   0  -1  -1  -1  -1  -2  -2  -1  -1  -1  -1  -2  -1   1   5  -2  -2   0  -1  -1   0  -4
W -3  -3  -4  -4  -2  -2  -3  -2  -2  -3  -2  -3  -1   1  -4  -3  -2  11   2  -3  -4  -3  -2  -4
Y -2  -2  -2  -3  -2  -1  -2  -3   2  -1  -1  -2  -1   3  -3  -2  -2   2   7  -1  -3  -2  -1  -4
V  0  -3  -3  -3  -1  -2  -2  -3  -3   3   1  -2   1  -1  -2  -2   0  -3  -1   4  -3  -2  -1  -4
B -2  -1   3   4  -3   0   1  -1   0  -3  -4   0  -3  -3  -2   0  -1  -4  -3  -3   4   1  -1  -4
Z -1   0   0   1  -3   3   4  -2   0  -3  -3   1  -1  -3  -1   0  -1  -3  -2  -2   1   4  -1  -4
X  0  -1  -1  -1  -2  -1  -1  -1  -1  -1  -1  -1  -1  -1  -2   0   0  -2  -1  -1  -1  -1  -1  -4
* -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4  -4   1
"""


def _parse(table: str) -> tuple[str, np.ndarray]:
    rows = [line.split() for line in table.strip().splitlines()]
    alphabet = "".join(rows[0])
    body = np.array([[int(x) for x in r[1:]] for r in rows[1:]], dtype=np.int64)
    if [r[0] for r in rows[1:]] != list(alphabet):
        raise ValueError("BLOSUM62 row order does not match column order")
    if not np.array_equal(body, body.T):
        raise ValueError("BLOSUM62 must be symmetric")
    return alphabet, body


ALPHABET, MATRIX = _parse(_TABLE)
INDEX = {c: i for i, c in enumerate(ALPHABET)}


# 256-entry lookup table: byte value -> matrix index. Anything unknown maps to 'X'.
_LUT = np.full(256, INDEX["X"], dtype=np.int64)
for _c, _i in INDEX.items():
    _LUT[ord(_c)] = _i
    _LUT[ord(_c.lower())] = _i


def encode(seq: str) -> np.ndarray:
    """Map a sequence to integer indices into MATRIX. Unknown letters become 'X'."""
    return _LUT[np.frombuffer(seq.encode("ascii", errors="replace"), dtype=np.uint8)]


def score(a: str, b: str) -> int:
    """Substitution score of two residues."""
    return int(MATRIX[INDEX.get(a.upper(), INDEX["X"]), INDEX.get(b.upper(), INDEX["X"])])
