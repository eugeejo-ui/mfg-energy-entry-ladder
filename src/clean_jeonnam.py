"""전남 제조업 데이터 정리 — 0.001(기록 없음)은 전부 결측, 급등값 제거"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"

power = pd.read_csv(P / "jeonnam_mfg_hourly.csv.gz", parse_dates=["ts"])
power = power.sort_values(["memberID", "ts"]).reset_index(drop=True)

EPS = 0.001
LONG_RUN = 24
OUTAGES = [  # 여러 사업장이 동시에 끊긴 기간 (기록용 구분)
    ("2022-02-23 10:00", "2022-03-03 13:00"),
    ("2022-03-25 21:00", "2022-03-27 09:00"),
]

power["is_eps"] = np.isclose(power["kwh"], EPS)
power["run_id"] = power.groupby("memberID")["kwh"].transform(
    lambda s: s.ne(s.shift()).cumsum())
power["run_len"] = power.groupby(["memberID", "run_id"])["kwh"].transform("size")

in_outage = pd.Series(False, index=power.index)
for s, e in OUTAGES:
    in_outage |= power["ts"].between(pd.Timestamp(s), pd.Timestamp(e))

p999 = power.groupby("memberID")["kwh"].transform(lambda s: s.quantile(0.999))

# 규칙 적용 (먼저 걸린 규칙이 우선). 결측 사유만 구분하고 처리는 모두 결측
power["flag"] = "ok"
power.loc[power["kwh"] > 5 * p999, "flag"] = "spike"
power.loc[(power["flag"] == "ok") & power["is_eps"] & in_outage, "flag"] = "outage"
power.loc[(power["flag"] == "ok") & power["is_eps"] & (power["run_len"] >= LONG_RUN),
          "flag"] = "eps_long"
power.loc[(power["flag"] == "ok") & power["is_eps"], "flag"] = "eps_short"

power["kwh_clean"] = power["kwh"].where(power["flag"] == "ok")

# ─────────────────────────────────────────────
# 결과 요약
# ─────────────────────────────────────────────
print("=" * 60)
print("1. 결측 사유별 건수")
print("=" * 60)
print(power["flag"].value_counts().to_string())
print(f"\n  전체 대비 결측 비율: {power['kwh_clean'].isna().mean():.2%}")

power["date"] = power["ts"].dt.normalize()
site = power.groupby("memberID").agg(
    missing_share=("kwh_clean", lambda s: s.isna().mean()))
site["full_days"] = (power.groupby(["memberID", "date"])["kwh_clean"]
                          .apply(lambda s: s.notna().all())
                          .groupby("memberID").sum())

print("\n" + "=" * 60)
print("2. 사업장별 결측 비율")
print("=" * 60)
print(site["missing_share"].describe(percentiles=[0.5, 0.75, 0.9]).round(4).to_string())
print("\n  [결측 5% 이상 사업장]")
print(site[site["missing_share"] >= 0.05]
          .sort_values("missing_share", ascending=False).round(3).to_string())
print("\n  [완전한 날 수 분포] (전체 730일)")
print(site["full_days"].describe().round(1).to_string())

stat = pd.read_csv(P / "jeonnam_quality_stat.csv")
big_ids = stat.loc[stat["p999"] >= 100, "memberID"]
print("\n  [100kW 이상 17곳]")
print(site.loc[site.index.isin(big_ids)]
          .sort_values("missing_share", ascending=False).round(3).to_string())

# 저장
out = power[["memberID", "ts", "kwh", "kwh_clean", "flag"]]
out.to_csv(P / "jeonnam_mfg_hourly_clean.csv.gz", index=False, compression="gzip")
site.to_csv(P / "jeonnam_site_quality.csv", encoding="utf-8-sig")
print("\n[저장] jeonnam_mfg_hourly_clean.csv.gz, jeonnam_site_quality.csv")