import pytest

from amp_triage.data.dbaasp_activity import (
    is_bacterial,
    mic_in_um,
    molecular_weight,
    parse_concentration,
    summarize_peptide,
)

SEQ = "GIGKFLHSAKKFGKAFVGEIMNS"  # magainin 2, MW about 2466 Da


@pytest.mark.parametrize(
    "text,expected",
    [
        ("16", ("=", 16.0)),
        ("0.78-1.56", ("=", 1.56)),  # range -> upper end
        ("0.5–2", ("=", 2.0)),  # en dash
        ("3.2 ± 0.4", ("=", 3.2)),
        (">64", (">", 64.0)),
        (">>64", (">", 64.0)),
        (">=32", (">=", 32.0)),
        ("≥ 32", (">=", 32.0)),
        ("<4", ("<", 4.0)),
        ("<=4", ("<", 4.0)),
        ("16->64", (">", 64.0)),
        ("NA", None),
        ("", None),
        (None, None),
        ("abc", None),
    ],
)
def test_parse_concentration(text, expected):
    assert parse_concentration(text) == expected


def test_is_bacterial():
    assert is_bacterial("Escherichia coli ATCC 25922")
    assert is_bacterial("Staphylococcus aureus")
    assert not is_bacterial("Candida albicans ATCC 10231")
    assert not is_bacterial("Murine macrophage cells RAW 264.7")
    assert not is_bacterial("Human lung carcinoma A549")
    assert not is_bacterial("Trypanosoma brucei")
    assert not is_bacterial("")
    assert not is_bacterial(None)


def test_unit_conversion():
    mw = molecular_weight(SEQ)
    assert 2400 < mw < 2500
    assert mic_in_um(("=", 8.0), "µM", mw) == 8.0
    assert mic_in_um(("=", mw / 1000), "µg/ml", mw) == pytest.approx(1.0)  # 1 µM
    assert mic_in_um(("=", 5.0), None, mw) is None
    assert mic_in_um(("=", 5.0), "nmol/g", mw) is None


def entry(conc, unit="µM", species="Escherichia coli ATCC 25922", measure="MIC", activity=1.0):
    return {
        "activityMeasureGroup": {"name": measure},
        "concentration": conc,
        "unit": {"name": unit} if unit else None,
        "targetSpecies": {"name": species},
        "activity": activity,
    }


def summary(*entries, threshold=32.0):
    return summarize_peptide({"targetActivities": list(entries)}, SEQ, threshold)


def test_active_when_any_bacterium_is_inhibited_at_or_below_threshold():
    s = summary(entry("100"), entry("32"), entry("64"))
    assert s.status == "active" and s.min_mic_um == 32.0


def test_inactive_when_every_result_is_clearly_above_threshold():
    assert summary(entry("100"), entry(">64")).status == "inactive"
    assert summary(entry(">32")).status == "inactive"  # MIC > 32 is above the threshold


def test_greater_than_a_small_value_is_ambiguous_not_inactive():
    assert summary(entry(">8")).status == "ambiguous"  # MIC may still be below 32


def test_greater_or_equal_threshold_is_ambiguous():
    assert summary(entry(">=32")).status == "ambiguous"  # MIC could be exactly 32


def test_less_than_a_value_above_threshold_is_ambiguous():
    assert summary(entry("<64")).status == "ambiguous"


def test_greater_than_never_counts_as_active():
    assert summary(entry(">2")).status != "active"


def test_non_bacterial_and_non_mic_and_unitless_entries_are_ignored():
    assert summary(entry("1", species="Candida albicans")).status == "no_data"
    assert summary(entry("1", measure="MBC")).status == "no_data"
    assert summary(entry("1", unit=None, activity=1111111.0)).status == "no_data"
    assert summary().status == "no_data"
    # a fungal hit does not rescue a peptide that fails against bacteria
    s = summary(entry("1", species="Candida albicans"), entry("100"))
    assert s.status == "inactive"


def test_ug_per_ml_is_converted_before_thresholding():
    mw = molecular_weight(SEQ)
    low = summary(entry(str(0.5 * mw / 1000 * 10), unit="µg/ml"))  # 5 µM
    high = summary(entry(str(100 * mw / 1000), unit="µg/ml"))  # 100 µM
    assert low.status == "active" and high.status == "inactive"


def test_threshold_is_configurable():
    assert summary(entry("16"), threshold=8.0).status == "inactive"
    assert summary(entry("16"), threshold=32.0).status == "active"
