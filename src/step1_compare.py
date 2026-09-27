"""1단계 1-5 — 에너지 사용량 vs IT 투자·인력 기초 비교
주의: 정보보호 공시의 '공시연도'는 투자 연도보다 1년 뒤임 (예: 2025년 투자액 → 2026년 공시)"""
from pathlib import Path
import re
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
CBAM = ROOT / "data" / "external" / "cbam"
RAW = ROOT / "data" / "raw"
FIG = ROOT / "figures"
FIG.mkdir(exist_ok=True)

sns.set_theme(style="whitegrid", font="Malgun Gothic")
plt.rcParams["axes.unicode_minus"] = False


def norm(x) -> str:
    s = str(x) if pd.notna(x) else ""
    s = re.sub(r"주식회사|㈜|\(주\)|\(유\)", "", s)
    return re.sub(r"[\s\.\,\-·&()]", "", s).upper()


# ─────────────────────────────────────────────
# 1. 대상 + cbam의 공시 매칭 정보
# ─────────────────────────────────────────────
T = pd.read_csv(P / "step1_firm_types_final.csv", dtype={"corp_code": str})
T["corp_code"] = T["corp_code"].str.zfill(8)
cb = pd.read_csv(CBAM / "mfg_final_reviewed.csv", dtype=str)
cb["corp_code"] = cb["corp_code"].str.zfill(8)
it = pd.read_csv(CBAM / "it_spend_matched.csv", dtype=str)
T = T.merge(cb[["corp_code", "stock_code"]], on="corp_code", how="left")
T = T.merge(it[["stock_code", "kisa_name", "it_year"]], on="stock_code", how="left")

# cbam의 it_year는 '투자 연도' → 공시 파일 연도는 +1
inv_year = pd.to_numeric(T["it_year"], errors="coerce")
T["disclosure_year"] = (inv_year + 1).astype("Int64").astype(str).replace("<NA>", "")

# ─────────────────────────────────────────────
# 2. 정보보호 공시 원본 (2026, 2025)
# ─────────────────────────────────────────────
def load_kisa(y: int) -> pd.DataFrame:
    f = next(RAW.glob(f"{y}_정보보호*공시*.xlsx"))
    d = pd.read_excel(f, dtype={"기업명": str})
    d = d.rename(columns={"투자현황_정보기술부문 투자액(A)": "it_spend_won",
                          "인력현황_정보기술부문 인력(C)": "it_staff",
                          "인력현황_총임직원": "employees"})
    d["year"] = str(y)
    d["key"] = d["기업명"].map(norm)
    return d[["key", "기업명", "year", "it_spend_won", "it_staff", "employees"]]


K = pd.concat([load_kisa(2026), load_kisa(2025)], ignore_index=True)

# cbam이 매칭한 공시 이름이 있으면 그 이름·연도로, 없으면 회사명으로 최신 공시 매칭 (비상장 포함)
T["k_key"] = np.where(T["kisa_name"].notna(), T["kisa_name"].map(norm), T["name"].map(norm))
rows = []
for _, t in T.iterrows():
    cand = K[K["key"] == t["k_key"]]
    if t["disclosure_year"]:
        same = cand[cand["year"] == t["disclosure_year"]]
        cand = same if len(same) else cand
    if len(cand):
        c = cand.sort_values("year", ascending=False).iloc[0]
        rows.append({"corp_code": t["corp_code"], "kisa_year": c["year"],
                     "invest_year": int(c["year"]) - 1,
                     "it_spend_kisa_eok": c["it_spend_won"] / 1e8,
                     "it_staff": c["it_staff"], "employees": c["employees"]})
    else:
        rows.append({"corp_code": t["corp_code"]})
T = T.merge(pd.DataFrame(rows), on="corp_code", how="left")

# ─────────────────────────────────────────────
# 3. 점검: cbam IT 투자액 vs 공시 원본
# ─────────────────────────────────────────────
print("[IT 자료 확보]")
print(f"  공시 매칭: {T['it_spend_kisa_eok'].notna().sum()}곳 "
      f"(상장 {((T['source'] == '상장(cbam)') & T['it_spend_kisa_eok'].notna()).sum()}, "
      f"비상장 {((T['source'] != '상장(cbam)') & T['it_spend_kisa_eok'].notna()).sum()})")
print(f"  투자 연도 분포: {T['invest_year'].value_counts().to_dict()}")
both = T[T["it_spend_eok"].notna() & T["it_spend_kisa_eok"].notna()]
diff = both[(both["it_spend_eok"] - both["it_spend_kisa_eok"]).abs() > 0.2]
print(f"  cbam 값과 공시 원본 차이(0.2억 초과): {len(diff)}곳")
if len(diff):
    print(diff[["name", "it_spend_eok", "it_spend_kisa_eok", "kisa_year"]].round(1).to_string(index=False))

# ─────────────────────────────────────────────
# 4. 요약
# ─────────────────────────────────────────────
has_it = T["it_spend_kisa_eok"].notna()
has_en = T["energy_tj_avg"].notna()
print("\n[IT 투자·인력 중앙값 (공시 있는 곳)]")
print(f"  IT 투자: {T.loc[has_it, 'it_spend_kisa_eok'].median():.1f}억 원")
print(f"  IT 인력: {T.loc[has_it, 'it_staff'].median():.1f}명")
print(f"  총 임직원: {T.loc[has_it, 'employees'].median():.0f}명")

print("\n[공장 종류별]")
g = T.groupby("category_final").agg(
    회사수=("name", "size"),
    에너지자료=("energy_tj_avg", "count"),
    에너지_중앙값TJ=("energy_tj_avg", "median"),
    IT자료=("it_spend_kisa_eok", "count"),
    IT투자_중앙값억=("it_spend_kisa_eok", "median"),
    IT인력_중앙값=("it_staff", "median"),
)
print(g.round(1).to_string())

ov = T[has_it & has_en].copy()
rho = ov["energy_tj_avg"].corr(ov["it_spend_kisa_eok"], method="spearman")
print(f"\n[에너지와 IT 투자가 둘 다 있는 회사] {len(ov)}곳, 순위 상관 {rho:.2f}")
print(ov.sort_values("energy_tj_avg", ascending=False)
        [["name", "category_final", "energy_tj_avg", "it_spend_kisa_eok", "it_staff", "employees"]]
        .round(1).to_string(index=False))

# ─────────────────────────────────────────────
# 5. 그래프
# ─────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 5.5))
sns.scatterplot(data=ov, x="energy_tj_avg", y="it_spend_kisa_eok",
                hue="category_final", s=70, ax=ax)
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("에너지 사용량 (TJ, 2023~2025 평균, 로그)")
ax.set_ylabel("정보기술부문 투자액 (억 원, 2025년, 로그)")
ax.set_title(f"에너지 사용량 vs IT 투자 ({len(ov)}곳, 순위 상관 {rho:.2f})")
ax.legend(title="공장 종류", fontsize=8, title_fontsize=9, loc="best")
fig.tight_layout()
fig.savefig(FIG / "01_energy_vs_it.png", dpi=150)

T.to_csv(P / "step1_energy_it.csv", index=False, encoding="utf-8-sig")
print("\n[저장] data/processed/step1_energy_it.csv, figures/01_energy_vs_it.png")