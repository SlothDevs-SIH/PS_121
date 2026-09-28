"""Unit conversions — the single source of conversion factors (master plan Appendix D).

Canonical internal units: m, SG, m³, kPa, kN, kN·m, L/min. Convert at the edges
(extraction and display), never ad hoc inside business logic.
"""

FT_TO_M = 0.3048
PPG_PER_SG = 8.345  # 1 SG of mud weight = 8.345 ppg
PSI_PER_FT_PER_PPG = 0.052  # hydrostatic gradient: psi/ft = 0.052 * ppg
KPA_PER_M_PER_SG = 9.80665  # hydrostatic gradient: kPa/m = 9.80665 * SG
BBL_TO_M3 = 0.158987
PSI_TO_KPA = 6.894757
KLBF_TO_KN = 4.448222
KFTLBF_TO_KNM = 1.355818
USGPM_TO_LPM = 3.785412


def ft_to_m(ft: float) -> float:
    return ft * FT_TO_M


def m_to_ft(m: float) -> float:
    return m / FT_TO_M


def ppg_to_sg(ppg: float) -> float:
    return ppg / PPG_PER_SG


def sg_to_ppg(sg: float) -> float:
    return sg * PPG_PER_SG


def ppg_to_psi_per_ft(ppg: float) -> float:
    return ppg * PSI_PER_FT_PER_PPG


def sg_to_kpa_per_m(sg: float) -> float:
    return sg * KPA_PER_M_PER_SG


def bbl_to_m3(bbl: float) -> float:
    return bbl * BBL_TO_M3


def m3_to_bbl(m3: float) -> float:
    return m3 / BBL_TO_M3


def psi_to_kpa(psi: float) -> float:
    return psi * PSI_TO_KPA


def kpa_to_psi(kpa: float) -> float:
    return kpa / PSI_TO_KPA


def klbf_to_kn(klbf: float) -> float:
    return klbf * KLBF_TO_KN


def kftlbf_to_knm(kftlbf: float) -> float:
    return kftlbf * KFTLBF_TO_KNM


def usgpm_to_lpm(gpm: float) -> float:
    return gpm * USGPM_TO_LPM
