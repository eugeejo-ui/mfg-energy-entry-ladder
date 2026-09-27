"""1단계 보완 — 에너지 규모 구간별 후보 분포 (세그먼트 × 확정/잠재)"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"

BANDS = [0, 500, 2000, 10000, float("inf")]
LABELS = ["소형 (500TJ 미만)", "중형 (500~2,000TJ)", "대형 (2,000~10,000TJ)", "초대형 (10,000TJ 이상)"]
NO_DATA = "신고 기준 미만 (GIR 없음)"
SEG_A, SEG_B, SEG_C = "A (시멘트·비료)", "B (철강·알루미늄·가공)", "C (비CBAM)"

# ─────────────────────────────────────────────
# A·B 확정 (대상 73곳)
# ─────────────────────────────────────────────
F = pd.read_csv(P / "step1_firm_types_final.csv", dtype={"corp_code": str})
ab = pd.DataFrame({
    "name": F["name"],
    "segment": F["category_final"].str.startswith(("시멘트", "비료")).map({True: SEG_A, False: SEG_B}),
    "tier": "확정",
    "energy_tj_avg": pd.to_numeric(F["energy_tj_avg"], errors="coerce"),
})

# ─────────────────────────────────────────────
# A·B 잠재 (GIR 업종명과 달리 업종코드상 CBAM 해당, 규모 미판정)
# ─────────────────────────────────────────────
S = pd.read_csv(P / "step1_segment_c_scan.csv", dtype=str)
abp = S[S["status"].str.startswith("CBAM 업종코드 해당")].copy()
abp = pd.DataFrame({
    "name": abp["gir_name"],
    "segment": abp["induty_code"].astype(str).str.startswith(("23311", "2031")).map({True: SEG_A, False: SEG_B}),
    "tier": "잠재",
    "energy_tj_avg": pd.to_numeric(abp["energy_tj_avg"], errors="coerce"),
})

# ─────────────────────────────────────────────
# C: 상장(중견 확정) + 공시대상집단 소속 비상장 = 확정 / 나머지 비상장 = 잠재
# ─────────────────────────────────────────────
C = pd.read_csv(P / "step1_segment_c.csv", dtype=str)
c = pd.DataFrame({
    "name": C["name"],
    "segment": SEG_C,
    "tier": (C["source"].str.startswith("상장") | C["ftc_group"].notna()).map({True: "확정", False: "잠재"}),
    "energy_tj_avg": pd.to_numeric(C["energy_tj_avg"], errors="coerce"),
})

ALL = pd.concat([ab, abp, c], ignore_index=True)
ALL["band"] = pd.cut(ALL["energy_tj_avg"], BANDS, labels=LABELS, right=False).astype(str)
ALL.loc[ALL["energy_tj_avg"].isna(), "band"] = NO_DATA
order = LABELS[::-1] + [NO_DATA]

# ─────────────────────────────────────────────
# 결과
# ─────────────────────────────────────────────
print("[회사 수: 세그먼트 × 확정/잠재 × 에너지 구간]")
tab = pd.crosstab([ALL["segment"], ALL["tier"]], ALL["band"], margins=True, margins_name="합계")
print(tab.reindex(columns=[b for b in order if b in tab.columns] + ["합계"]).to_string())

print("\n[확정 후보의 에너지 합계 비중 (%) — 어느 구간에 에너지가 몰려 있나]")
conf = ALL[(ALL["tier"] == "확정") & ALL["energy_tj_avg"].notna()]
share = (conf.groupby(["segment", "band"])["energy_tj_avg"].sum()
             / conf.groupby("segment")["energy_tj_avg"].sum() * 100).unstack()
print(share.reindex(columns=[b for b in LABELS[::-1] if b in share.columns]).round(1).to_string())

ALL.to_csv(P / "step1_energy_bands.csv", index=False, encoding="utf-8-sig")
print("\n[저장] data/processed/step1_energy_bands.csv")