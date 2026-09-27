"""1단계 1-4 확정 — 문장 검토 결과(판정표)를 유형표에 반영"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
M = ROOT / "data" / "manual"

T = pd.read_csv(P / "step1_firm_types_final.csv", dtype={"corp_code": str})
D = pd.read_csv(M / "step1_type_decisions.csv", dtype={"corp_code": str})
T["corp_code"] = T["corp_code"].str.zfill(8)
D["corp_code"] = D["corp_code"].str.zfill(8)

T = T.drop(columns=[c for c in ("category_final", "confidence", "evidence") if c in T.columns])
T = T.merge(D[["corp_code", "category_final", "confidence", "evidence"]], on="corp_code", how="left")
print(f"판정 누락: {T['category_final'].isna().sum()}곳")

print("\n[최종 유형 × 확신도]")
print(pd.crosstab(T["category_final"], T["confidence"], margins=True).to_string())

has = T["energy_tj_avg"].notna()
print("\n[GIR 에너지 자료 있는 49곳의 유형]")
print(T[has]["category_final"].value_counts().to_string())

T.to_csv(P / "step1_firm_types_final.csv", index=False, encoding="utf-8-sig")
print("\n[저장] data/processed/step1_firm_types_final.csv")