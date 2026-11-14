from amp_triage.data.happenn import parse_supplement_text

SAMPLE = (
    "1 >lcl|2826|lcl|HAPPENN&HAPPENN-RR90&HAPPENN-hard|lcl|subdataset_9|lcl|hemolytic|lcl|cTe\r\n"
    "r\r\n"
    "2 YKLLKLLLPKLKGLLFKL\r\n"
    "3 >lcl|793|lcl|HAPPENN|lcl|subdataset_10|lcl|non-hemolytic\r\n"
    "4 GEKLKKIGKKIKNFFQKL\r\n"
)


def test_parses_wrapped_header_and_sets():
    df = parse_supplement_text(SAMPLE)
    assert len(df) == 2
    first, second = df.iloc[0], df.iloc[1]
    assert first.sequence == "YKLLKLLLPKLKGLLFKL"
    assert first.label == "hemolytic" and first.hemolytic == 1
    assert first.c_ter_flag and not first.n_ter_flag  # wrapped "cTe"+"r" rebuilt
    assert first.in_happenn and first.in_rr90 and first.in_hard
    assert second.label == "non-hemolytic" and second.hemolytic == 0
    assert second.in_happenn and not second.in_rr90 and not second.in_hard
    assert second.length == 18
