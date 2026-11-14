from amp_triage.data.apd import load_apd_fasta
from amp_triage.data.dramp import load_dramp


def test_apd_skips_search_header(tmp_path):
    f = tmp_path / "apd.fasta"
    f.write_text(">Your search led to 2 peptides\n\n>AP00001\nGLWSKIK\n\n>AP00002\nYVPLPNV\n")
    df = load_apd_fasta(f)
    assert df.apd_id.tolist() == ["AP00001", "AP00002"]
    assert df.length.tolist() == [7, 7]


def test_dramp_general_layout_with_multiline_field(tmp_path):
    f = tmp_path / "general.txt"
    f.write_text(
        "DRAMP_ID\tSequence\tSequence_Length\tComments\n"
        'DRAMP00001\tgl wskik\t7\t"line one\nline two"\n'
        "DRAMP00002\tYVPLPNV\t7\tplain\n"
    )
    df = load_dramp(f)
    assert len(df) == 2  # the quoted multi-line field must not split the row
    assert df.length.tolist() == [7, 7]
    assert df.Sequence.iloc[1] == "YVPLPNV"


def test_dramp_subset_layout_uses_length_column(tmp_path):
    f = tmp_path / "subset.txt"
    f.write_text("DRAMP_ID\tSequence\tName\tDataset\tLength\nDRAMP00001\tGLWSKIK\tx\tPatent\t7\n")
    df = load_dramp(f)
    assert df.length.iloc[0] == 7
    assert df.Dataset.iloc[0] == "Patent"
