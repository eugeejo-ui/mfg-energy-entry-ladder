"""1단계 1-4 마무리 — 유형 확정 + 에너지 집약도(TJ/매출 억 원)로 교차 확인"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"

T = pd.read_csv(P / "step1_firm_types.csv", dtype={"corp_code": str})
G = pd.read_csv(P / "step1_gir_matched.csv", dtype=str)[["name", "gir_type"]]
T = T.merge(G, on="name", how="left")

# ─────────────────────────────────────────────
# 1. 확인 결과 반영 (2026-09-27 문맥 검토)
# ─────────────────────────────────────────────
NOTES = {
    "KG스틸": "보고서의 전기로 언급은 연혁(2007 진출, 2009 시운전)뿐, 현재 가동 여부 미확인 → 업종코드대로 가공형",
    "신스틸": "업종코드 3자리(241), 설비 단어 없고 가공 단어 다수 → 가공형",
    "삼보산업": "사업보고서에 설비 단어 없음, 반대 근거도 없음 → 업종코드대로 분류",
    "한주라이트메탈": "사업보고서에 설비 단어 없음, 반대 근거도 없음 → 업종코드대로 분류",
    "한국제강": "감사보고서라 설비 설명 없음 → 업종코드대로 분류",
    "현대아이에프씨": "감사보고서라 설비 설명 없음 → 업종코드대로 분류",
    "세진메탈": "감사보고서라 설비 설명 없음 → 업종코드대로 분류",
    "하이호경금속": "감사보고서라 설비 설명 없음 → 업종코드대로 분류",
}


def group(t: str) -> str:
    if t.startswith("용해형"):
        return "용해형"
    if t.startswith("가공형") or t == "코드 불충분":
        return "가공형"
    return t  # 시멘트, 비료·화학


T["type_final"] = T["type_by_code"].map(group)
T["type_note"] = T["name"].map(
    lambda n: next((v for k, v in NOTES.items() if k in str(n).replace(" ", "")), ""))

# ─────────────────────────────────────────────
# 2. 에너지 집약도 = GIR 에너지(TJ, 3년 평균) / 매출(억 원)
# ─────────────────────────────────────────────
T["rev_avg_eok"] = pd.to_numeric(T["rev_avg_eok"], errors="coerce")
T["tj_per_eok"] = (T["energy_tj_avg"] / T["rev_avg_eok"]).round(3)
has = T["tj_per_eok"].notna()

print("[유형별 에너지 집약도 (TJ / 매출 억 원)]")
summ = (T[has].groupby("type_final")["tj_per_eok"]
          .describe(percentiles=[0.25, 0.5, 0.75])[["count", "25%", "50%", "75%", "min", "max"]])
print(summ.round(3).to_string())

melt_q25 = T.loc[has & (T["type_final"] == "용해형"), "tj_per_eok"].quantile(0.25)
proc_q75 = T.loc[has & (T["type_final"] == "가공형"), "tj_per_eok"].quantile(0.75)
print(f"\n  기준: 용해형 하위 25% = {melt_q25:.3f}, 가공형 상위 25% = {proc_q75:.3f}")

T["intensity_check"] = ""
T.loc[has & (T["type_final"] == "가공형") & (T["tj_per_eok"] >= melt_q25),
      "intensity_check"] = "가공형인데 집약도가 용해형 수준 (확인)"
T.loc[has & (T["type_final"] == "용해형") & (T["tj_per_eok"] <= proc_q75),
      "intensity_check"] = "용해형인데 집약도가 가공형 수준 (확인)"

cols = ["name", "source", "ksic_used", "type_final", "energy_tj_avg", "rev_avg_eok",
        "tj_per_eok", "gir_type", "intensity_check"]
print("\n[집약도 확인 필요]")
print(T[T["intensity_check"] != ""][cols].sort_values("tj_per_eok", ascending=False)
      .to_string(index=False))

print("\n[참고: 용해형 전체]")
print(T[has & (T["type_final"] == "용해형")][cols[:-1]]
      .sort_values("tj_per_eok", ascending=False).to_string(index=False))

print("\n[최종 유형 분포 (전체 73곳 / GIR 자료 있는 곳)]")
print(pd.concat([T["type_final"].value_counts().rename("전체"),
                 T[has]["type_final"].value_counts().rename("GIR 있음")], axis=1)
      .fillna(0).astype(int).to_string())

T.to_csv(P / "step1_firm_types_final.csv", index=False, encoding="utf-8-sig")
print("\n[저장] data/processed/step1_firm_types_final.csv")