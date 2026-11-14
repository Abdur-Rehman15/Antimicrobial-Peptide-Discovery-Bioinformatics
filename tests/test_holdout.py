from amp_triage.data.holdout import find_in_proteins

FASTA = """>sp|P00001|ONE_HUMAN first
MKTAYIAKQR
>sp|P00002|TWO_HUMAN second
QISFVKSHFSRQ
"""


def test_finds_exact_substrings_and_reports_owner(tmp_path):
    f = tmp_path / "p.fasta"
    f.write_text(FASTA)
    hits = find_in_proteins(["AYIAK", "SFVKS", "NOTTHERE"], f)
    assert hits == {"AYIAK": "P00001", "SFVKS": "P00002"}


def test_match_cannot_span_two_proteins(tmp_path):
    f = tmp_path / "p.fasta"
    f.write_text(FASTA)
    # "...KQR" ends protein one and "QIS..." starts protein two: joined it would read KQRQIS
    assert find_in_proteins(["KQRQIS"], f) == {}


def test_empty_sequence_is_ignored(tmp_path):
    f = tmp_path / "p.fasta"
    f.write_text(FASTA)
    assert find_in_proteins(["", "MKT"], f) == {"MKT": "P00001"}
