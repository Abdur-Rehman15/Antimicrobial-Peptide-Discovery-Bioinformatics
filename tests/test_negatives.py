import numpy as np

from amp_triage.candidates.stage1 import Stage1Model
from amp_triage.data.negatives import (
    kmer_set,
    load_mixed_pool,
    protein_split,
    sample_windows,
    shares_kmer,
)
from amp_triage.features import descriptors as D


def proteins(n, seed):
    rng = np.random.default_rng(seed)
    accs = [f"Q{i:05d}" for i in range(n)]
    seqs = ["".join(rng.choice(list(D.AA), size=rng.integers(60, 200))) for _ in range(n)]
    return accs, seqs


def test_protein_split_is_stable_and_roughly_70_15_15():
    accs = [f"P{i:06d}" for i in range(20000)]
    first = [protein_split(a) for a in accs]
    assert first == [protein_split(a) for a in accs]  # deterministic
    for name, share in (("train", 0.70), ("val", 0.15), ("test", 0.15)):
        assert abs(first.count(name) / len(accs) - share) < 0.01


def test_kmer_helpers():
    kmers = kmer_set(["ACDEFGHIK"], k=7)
    assert kmers == {"ACDEFGH", "CDEFGHI", "DEFGHIK"}
    assert shares_kmer("XXXCDEFGHIXXX", kmers)
    assert not shares_kmer("ACDEFGXXXXXX", kmers)


def test_sampled_windows_come_only_from_proteins_of_that_split():
    accs, seqs = proteins(600, 1)
    lengths = np.array([10, 15, 20, 25])
    df = sample_windows(accs, seqs, lengths, n=200, split="val", banned_kmers=set(), seed=1)
    assert len(df) == 200 and set(df.split) == {"val"}
    assert all(protein_split(a) == "val" for a in df.accession)
    lookup = dict(zip(accs, seqs, strict=True))
    for r in df.itertuples():  # every window really is that slice of that protein
        assert lookup[r.accession][r.start : r.start + r.length] == r.sequence


def test_lengths_follow_the_given_pool():
    accs, seqs = proteins(600, 2)
    df = sample_windows(accs, seqs, np.array([12, 12, 12, 30]), 400, "train", set(), seed=2)
    share12 = (df.length == 12).mean()
    assert 0.65 < share12 < 0.85  # pool is 75% length 12


def test_windows_sharing_a_kmer_with_a_known_amp_are_removed():
    accs, seqs = proteins(400, 3)
    banned = kmer_set([seqs[0][10:40]])  # pretend a stretch of protein 0 is a known AMP
    df = sample_windows(accs, seqs, np.array([20, 30]), 300, "train", banned, seed=3)
    assert not df.sequence.apply(lambda s: shares_kmer(s, banned)).any()


def test_stage1_filter_keeps_only_windows_that_pass():
    accs, seqs = proteins(600, 4)
    # a screen that only passes windows rich in lysine
    w = [0.0] * 20
    w[D.AA.index("K")] = 20.0
    model = Stage1Model(aac_weights=w, length_weight=0.0, charge_weight=0.0, intercept=0.0,
                        threshold=2.0)
    df = sample_windows(accs, seqs, np.array([12, 16]), 40, "train", set(), stage1=model, seed=4)
    assert len(df) > 0
    assert (model.scores(df.sequence.tolist()) >= 2.0).all()


def write_fasta(path, records):
    """records: (accession, organism id, sequence)"""
    lines = []
    for acc, ox, seq in records:
        lines += [f">sp|{acc}|X_{acc} protein OS=Some organism OX={ox} GN=g PE=1 SV=1", seq]
    path.write_text("\n".join(lines) + "\n")


def test_mixed_pool_takes_the_asked_mammal_share_and_never_human(tmp_path):
    rng = np.random.default_rng(0)

    def seq():
        return "".join(rng.choice(list(D.AA), size=80))

    records = (
        [(f"M{i}", "10090", seq()) for i in range(70)]  # mouse
        + [(f"B{i}", "83333", seq()) for i in range(70)]  # E. coli
        + [(f"H{i}", "9606", seq()) for i in range(30)]  # human: must never appear
        + [("EXCL", "10116", seq())]  # a rat protein on the exclude list
    )
    path = tmp_path / "pool.fasta"
    write_fasta(path, records)
    accs, seqs, n_mammal = load_mixed_pool(path, {"EXCL"}, 50, 0.7, seed=1)
    assert len(accs) == len(seqs) == 50 and n_mammal == 35
    assert sum(a.startswith("M") for a in accs) == 35 and sum(a.startswith("B") for a in accs) == 15
    assert not any(a.startswith("H") or a == "EXCL" for a in accs)
    assert (accs, seqs) == load_mixed_pool(path, {"EXCL"}, 50, 0.7, seed=1)[:2]  # reproducible


def test_mixed_pool_fills_up_with_other_organisms_when_mammals_run_out(tmp_path):
    rng = np.random.default_rng(1)
    records = [(f"M{i}", "10090", "".join(rng.choice(list(D.AA), 60))) for i in range(5)]
    records += [(f"B{i}", "83333", "".join(rng.choice(list(D.AA), 60))) for i in range(40)]
    path = tmp_path / "pool.fasta"
    write_fasta(path, records)
    accs, _, n_mammal = load_mixed_pool(path, set(), 30, 0.7, seed=2)
    assert n_mammal == 5 and len(accs) == 30  # all 5 mammals, 25 others


def test_even_length_pool_gives_every_length_about_equally_often():
    accs, seqs = proteins(300, 7)
    lengths = np.arange(8, 51)
    df = sample_windows(accs, seqs, lengths, n=4300, split="train", banned_kmers=set(), seed=3)
    counts = df.length.value_counts()
    assert set(counts.index) == set(range(8, 51))
    assert counts.max() < 2.0 * counts.min() + 20  # roughly 100 per length
