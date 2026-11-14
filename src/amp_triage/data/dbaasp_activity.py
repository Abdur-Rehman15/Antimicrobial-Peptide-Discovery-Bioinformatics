"""Turn DBAASP detail records into per-peptide activity labels.

Decisions (also written down in docs/DATA_SOURCES.md):

* Only MIC measurements (minimum inhibitory concentration) against **bacteria** are used.
  A target species counts as bacterial unless its genus is a known fungus, oomycete, parasite,
  virus, archaeon or a mammalian/other cell (see NON_BACTERIAL).
* Concentration text is parsed directly. Ranges ("0.78-1.56") use the UPPER end, which is the
  conservative choice for a "must be at most X" rule. "a ± b" uses a.
* Qualifiers matter: "MIC > 64" says the peptide did NOT work up to 64, so it can never count
  as evidence of activity. "MIC < 4" counts as definite activity at 4 or better.
* Units: µM is used as written. µg/ml is converted with the peptide's molecular weight.
  Entries with no unit carry a placeholder (1111111) and are dropped.
* A peptide is **active** if any definite bacterial MIC is <= threshold (default 32 µM),
  **inactive** if it has bacterial MIC data and every entry is definitely above the threshold,
  and **ambiguous** otherwise (such peptides are used as neither positives nor negatives).
"""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path

from Bio.SeqUtils.ProtParam import ProteinAnalysis

from amp_triage import config

MIC_THRESHOLD_UM = 32.0

# Target species whose first word is one of these are NOT bacteria. Built by reading all 239
# distinct first words in the downloaded MIC data (fungi, oomycetes, parasites, cells, virus...).
NON_BACTERIAL = {
    # yeasts and moulds
    "Candida", "Cryptococcus", "Aspergillus", "Fusarium", "Saccharomyces", "Trichosporon",
    "Trichophyton", "Botrytis", "Penicillium", "Batrachochytrium", "Rhodotorula",
    "Aureobasidium", "Neurospora", "Alternaria", "Trichoderma", "Rhizoctonia", "Pichia",
    "Cladosporium", "Colletotrichum", "Malassezia", "Microsporum", "Schizosaccharomyces",
    "Rhizopus", "Sporothrix", "Ramulariopsis", "Drechslera", "Ascochyta", "Pyricularia",
    "Mucor", "Debaryomyces", "Stachybotrys", "Paecilomyces", "Kluyveromyces",
    "Leptosphaeria", "Geotrichum", "Histoplasma", "Beauveria", "Metarhizium", "Aspicilia",
    "Lichtheimia", "Zygosaccharomyces", "Meyerozyma", "Sclerotinia", "Papiliotrema",
    "Parastagonospora", "Fulvia", "Pachysolen", "Coccidioides", "Paracoccidioides",
    "Yarrowia", "Eurotium", "Verticillium", "Gibberella", "Pestalotia", "Valsa",
    "Syspastospora", "Chaetomium", "Actinomucor", "Talaromyces", "Phomopsis", "Hypocreales",
    "Lomentospora", "Curvularia", "Bipolaris", "Neocamarosporium", "Stemphylium",
    # oomycetes, slime moulds, parasites and other protists
    "Phytophthora", "Pythium", "Arcyria", "Slime", "Trypanosoma", "Leishmania",
    "Trichomonas", "Philasterides", "Theileria", "Miamiensis",
    # archaea, virus, animal, human cells
    "Haloarcula", "Haloferax", "Enterovirus", "Galleria", "Human", "Mouse", "Murine", "Rat",
}
_NON_BACTERIAL_WORDS = ("cell", "virus", "carcinoma", "macrophage", "fibroblast", "erythrocyte")

_NUM = r"\d+(?:\.\d+)?"


def is_bacterial(species_name: str | None) -> bool:
    if not species_name or not species_name.strip():
        return False
    name = species_name.strip()
    first = name.split()[0].strip("[]()").rstrip(",")
    if first in NON_BACTERIAL:
        return False
    return not any(w in name.lower() for w in _NON_BACTERIAL_WORDS)


def parse_concentration(text: str | None) -> tuple[str, float] | None:
    """Return (relation, value) or None if unusable.

    relation is "=" (a measured value), "<" (value or lower), ">" (strictly higher) or ">="
    (value or higher). ">" and ">=" are no evidence of activity. For ranges the upper end is
    returned. Examples:
        "16" -> ("=", 16)   "0.78-1.56" -> ("=", 1.56)   ">64" -> (">", 64)   "<=4" -> ("<", 4)
        ">=32" -> (">=", 32)   "16->64" -> (">", 64)
    """
    if not text:
        return None
    t = text.strip().replace("–", "-").replace("≥", ">=").replace("≤", "<=").replace(" ", "")
    if t.upper() == "NA":
        return None
    if t.startswith(">"):
        m = re.search(_NUM, t)
        if not m:
            return None
        return (">=" if t.startswith(">=") else ">", float(m.group()))
    if t.startswith("<"):
        m = re.search(_NUM, t)
        return ("<", float(m.group())) if m else None
    if "±" in t:
        m = re.match(_NUM, t)
        return ("=", float(m.group())) if m else None
    nums = re.findall(_NUM, t)
    if not nums:
        return None
    if "->" in t:  # "N->N": a range whose top end is open, so the MIC is above the last number
        return (">", float(nums[-1]))
    return ("=", max(float(n) for n in nums))  # plain value, or range -> upper end


def molecular_weight(sequence: str) -> float:
    return ProteinAnalysis(sequence).molecular_weight()


def mic_in_um(relation_value: tuple[str, float], unit: str | None, mw: float) -> float | None:
    """Convert a parsed concentration to µM. Returns None for an unusable unit."""
    value = relation_value[1]
    if unit == "µM":
        return value
    if unit == "µg/ml":
        return value / mw * 1000.0
    return None


@dataclass
class MicSummary:
    status: str  # "active" | "inactive" | "ambiguous" | "no_data"
    min_mic_um: float | None  # smallest definite MIC (relation "=" or "<"), in µM
    n_bacterial_mic: int  # usable bacterial MIC entries
    best_species: str | None


def summarize_peptide(
    record: dict, sequence: str, threshold_um: float = MIC_THRESHOLD_UM
) -> MicSummary:
    mw = molecular_weight(sequence)
    definite: list[tuple[float, str]] = []  # (µM, species) with relation = or <
    n_total = 0
    all_clearly_inactive = True
    for entry in record.get("targetActivities") or []:
        if (entry.get("activityMeasureGroup") or {}).get("name") != "MIC":
            continue
        species = (entry.get("targetSpecies") or {}).get("name")
        if not is_bacterial(species):
            continue
        parsed = parse_concentration(entry.get("concentration"))
        um = mic_in_um(parsed, (entry.get("unit") or {}).get("name"), mw) if parsed else None
        if um is None or (entry.get("activity") or 0) >= 1e6:  # placeholder / unusable
            continue
        n_total += 1
        rel = parsed[0]
        if rel in ("=", "<"):
            definite.append((um, species))
            if um <= threshold_um:
                all_clearly_inactive = False
            elif rel == "<":
                all_clearly_inactive = False  # "<v" with v > threshold says nothing useful
        else:  # ">" or ">=": the MIC is above (or at) the value
            # Clearly inactive only if the value already reaches the threshold:
            # MIC > v with v >= threshold, or MIC >= v with v > threshold.
            clear = um >= threshold_um if rel == ">" else um > threshold_um
            if not clear:
                all_clearly_inactive = False
    if n_total == 0:
        return MicSummary("no_data", None, 0, None)
    best = min(definite) if definite else None
    if best and best[0] <= threshold_um:
        return MicSummary("active", best[0], n_total, best[1])
    status = "inactive" if all_clearly_inactive else "ambiguous"
    return MicSummary(status, best[0] if best else None, n_total, best[1] if best else None)


def load_details(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def details_dir() -> Path:
    return config.RAW_DIR / "dbaasp" / "details"
