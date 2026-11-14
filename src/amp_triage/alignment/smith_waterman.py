"""Smith-Waterman local alignment with affine gap penalties, written from scratch.

Reference implementation: clear, returns the full alignment (strings, coordinates, identity)
so it can be drawn in the dashboard. A fast score-only version for large searches lives in
`fast.py`; tests check that the two always agree, and both are checked against Biopython.

Scoring
-------
* Substitutions: BLOSUM62 (see blosum62.py).
* Gaps (NCBI BLAST convention): a gap of length k costs ``gap_open + k * gap_extend``.
  Defaults 11 and 1 are the BLASTP defaults for BLOSUM62, so a single-residue gap costs 12.

Algorithm (Gotoh, 1982, applied to local alignment; Smith & Waterman, 1981)
---------------------------------------------------------------------------
Three tables over query prefix i and target prefix j:

    H[i][j]  best score of a local alignment ending at (i, j)
    E[i][j]  best score ending at (i, j) with a gap in the query (consumes target[j])
    F[i][j]  best score ending at (i, j) with a gap in the target (consumes query[i])

    E[i][j] = max(H[i][j-1] - (gap_open + gap_extend),  E[i][j-1] - gap_extend)
    F[i][j] = max(H[i-1][j] - (gap_open + gap_extend),  F[i-1][j] - gap_extend)
    H[i][j] = max(0, H[i-1][j-1] + s(q[i], t[j]), E[i][j], F[i][j])

The "0" is what makes the alignment local: a score never goes negative, so a poor region
simply starts a fresh alignment. The answer is the largest value in H, and the traceback
runs from that cell back to the first cell whose H is 0.
"""

from __future__ import annotations

from dataclasses import dataclass

from amp_triage.alignment import blosum62

DEFAULT_GAP_OPEN = 11
DEFAULT_GAP_EXTEND = 1

_NEG = float("-inf")

# Pointers for H: where the best score at (i, j) came from
_STOP, _DIAG, _FROM_E, _FROM_F = 0, 1, 2, 3


@dataclass(frozen=True)
class Alignment:
    """A local alignment. Coordinates are 0-based, half-open: query[query_start:query_end]."""

    score: float
    query_start: int
    query_end: int
    target_start: int
    target_end: int
    aligned_query: str  # '-' marks a gap
    aligned_target: str
    midline: str  # '|' identical, ':' similar (BLOSUM62 > 0), ' ' otherwise
    identities: int
    positives: int  # identical or similar columns
    gaps: int  # number of gap columns

    @property
    def length(self) -> int:
        return len(self.aligned_query)

    @property
    def identity(self) -> float:
        """Fraction of alignment columns that are identical (0 for an empty alignment)."""
        return self.identities / self.length if self.length else 0.0

    @property
    def similarity(self) -> float:
        return self.positives / self.length if self.length else 0.0

    def format(self, width: int = 60, query_name: str = "Query", target_name: str = "Sbjct") -> str:
        """Pretty text alignment in BLAST style, with 1-based coordinates."""
        if not self.length:
            return "(no alignment: score 0)"
        label = max(len(query_name), len(target_name))
        out = [
            f"Score = {self.score:g}, Identities = {self.identities}/{self.length} "
            f"({self.identity:.0%}), Positives = {self.positives}/{self.length} "
            f"({self.similarity:.0%}), Gaps = {self.gaps}/{self.length}"
        ]
        qpos, tpos = self.query_start, self.target_start
        for k in range(0, self.length, width):
            q = self.aligned_query[k : k + width]
            t = self.aligned_target[k : k + width]
            mid = self.midline[k : k + width]
            q_res = sum(c != "-" for c in q)
            t_res = sum(c != "-" for c in t)
            out.append(f"{query_name:<{label}} {qpos + 1:>4}  {q}  {qpos + q_res}")
            out.append(f"{'':<{label}} {'':>4}  {mid}")
            out.append(f"{target_name:<{label}} {tpos + 1:>4}  {t}  {tpos + t_res}")
            out.append("")
            qpos += q_res
            tpos += t_res
        return "\n".join(out).rstrip()


_EMPTY = Alignment(0, 0, 0, 0, 0, "", "", "", 0, 0, 0)


def smith_waterman(
    query: str,
    target: str,
    gap_open: float = DEFAULT_GAP_OPEN,
    gap_extend: float = DEFAULT_GAP_EXTEND,
) -> Alignment:
    """Best local alignment of `query` against `target` under BLOSUM62 with affine gaps."""
    m, n = len(query), len(target)
    if m == 0 or n == 0:
        return _EMPTY
    a = blosum62.encode(query)
    b = blosum62.encode(target)
    sub = blosum62.MATRIX
    open_ext = gap_open + gap_extend

    H = [[0] * (n + 1) for _ in range(m + 1)]
    E = [[_NEG] * (n + 1) for _ in range(m + 1)]
    F = [[_NEG] * (n + 1) for _ in range(m + 1)]
    h_ptr = [[_STOP] * (n + 1) for _ in range(m + 1)]
    # e_open[i][j] is True if E[i][j] started a new gap from H, False if it extended E[i][j-1]
    e_open = [[False] * (n + 1) for _ in range(m + 1)]
    f_open = [[False] * (n + 1) for _ in range(m + 1)]

    best, best_i, best_j = 0, 0, 0
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            open_e = H[i][j - 1] - open_ext
            extend_e = E[i][j - 1] - gap_extend
            if open_e >= extend_e:
                E[i][j], e_open[i][j] = open_e, True
            else:
                E[i][j], e_open[i][j] = extend_e, False

            open_f = H[i - 1][j] - open_ext
            extend_f = F[i - 1][j] - gap_extend
            if open_f >= extend_f:
                F[i][j], f_open[i][j] = open_f, True
            else:
                F[i][j], f_open[i][j] = extend_f, False

            value, ptr = H[i - 1][j - 1] + int(sub[a[i - 1], b[j - 1]]), _DIAG
            if E[i][j] > value:
                value, ptr = E[i][j], _FROM_E
            if F[i][j] > value:
                value, ptr = F[i][j], _FROM_F
            if value <= 0:
                value, ptr = 0, _STOP
            H[i][j], h_ptr[i][j] = value, ptr

            if value > best:  # strict: the first (top-left-most) maximum wins ties
                best, best_i, best_j = value, i, j

    if best == 0:
        return _EMPTY

    # Traceback from the best cell, following the saved pointers.
    i, j = best_i, best_j
    state = "H"
    q_out: list[str] = []
    t_out: list[str] = []
    while True:
        if state == "H":
            ptr = h_ptr[i][j]
            if ptr == _STOP:
                break
            if ptr == _DIAG:
                q_out.append(query[i - 1])
                t_out.append(target[j - 1])
                i, j = i - 1, j - 1
            elif ptr == _FROM_E:
                state = "E"
            else:
                state = "F"
        elif state == "E":  # gap in query: consume a target residue
            q_out.append("-")
            t_out.append(target[j - 1])
            state = "H" if e_open[i][j] else "E"
            j -= 1
        else:  # state == "F", gap in target: consume a query residue
            q_out.append(query[i - 1])
            t_out.append("-")
            state = "H" if f_open[i][j] else "F"
            i -= 1

    aligned_q = "".join(reversed(q_out))
    aligned_t = "".join(reversed(t_out))
    mid, identities, positives, gaps = [], 0, 0, 0
    for x, y in zip(aligned_q, aligned_t, strict=True):
        if x == "-" or y == "-":
            mid.append(" ")
            gaps += 1
        elif x.upper() == y.upper():
            mid.append("|")
            identities += 1
            positives += 1
        elif blosum62.score(x, y) > 0:
            mid.append(":")
            positives += 1
        else:
            mid.append(" ")
    return Alignment(
        score=best,
        query_start=i,
        query_end=best_i,
        target_start=j,
        target_end=best_j,
        aligned_query=aligned_q,
        aligned_target=aligned_t,
        midline="".join(mid),
        identities=identities,
        positives=positives,
        gaps=gaps,
    )


def rescore(
    aligned_query: str,
    aligned_target: str,
    gap_open: float = DEFAULT_GAP_OPEN,
    gap_extend: float = DEFAULT_GAP_EXTEND,
) -> float:
    """Score an existing alignment from scratch. Used to check that a returned alignment's
    strings really add up to its reported score (independent of the dynamic programming)."""
    total = 0.0
    in_gap = None  # None, "q" (gap in query) or "t" (gap in target)
    for x, y in zip(aligned_query, aligned_target, strict=True):
        if x == "-":
            total -= gap_extend + (gap_open if in_gap != "q" else 0)
            in_gap = "q"
        elif y == "-":
            total -= gap_extend + (gap_open if in_gap != "t" else 0)
            in_gap = "t"
        else:
            total += blosum62.score(x, y)
            in_gap = None
    return total
