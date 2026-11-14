import numpy as np

from amp_triage.candidates.stage1 import Stage1Model
from amp_triage.data.negatives import (
    kmer_set,
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
