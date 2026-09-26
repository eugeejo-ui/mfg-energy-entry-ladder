"""전남 제조업 데이터 품질 점검 — 이상값(급등·고착)과 시각 표기 방식"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"

power = pd.read_csv(P / "jeonnam_mfg_hourly.csv.gz", parse_dates=["ts"])
biz = pd.read_csv(P / "jeonnam_business.csv")
power = power.sort_values(["memberID", "ts"]).reset_index(drop=True)

# ─────────────────────────────────────────────
# 1. 급등값 점검
# ─────────────────────────────────────────────
g = power.groupby("memberID")["kwh"]
stat = pd.DataFrame({
    "p99": g.quantile(0.99),
    "p999": g.quantile(0.999),
    "max": g.max(),
})
stat["max_to_p999"] = stat["max"] / stat["p999"]

merged = power.merge(stat[["p999"]], left_on="memberID", right_index=True)
spikes = merged[merged["kwh"] > 5 * merged["p999"]]

print("=" * 60)
print("1. 급등값 (사업장 상위 0.1% 값의 5배 초과)")
print("=" * 60)
print(f"  급등 시간 수: {len(spikes)}, 해당 사업장 수: {spikes['memberID'].nunique()}")
if len(spikes):
    print(spikes[["memberID", "ts", "kwh", "p999"]].head(30).to_string(index=False))

print("\n  [최댓값 / 상위 0.1% 값 비율 상위 10곳]")
print(stat.sort_values("max_to_p999", ascending=False).head(10).round(2).to_string())

# ─────────────────────────────────────────────
# 2. 고착값 점검 (같은 값이 연속되는 최장 시간)
# ─────────────────────────────────────────────
def longest_run(s):
    grp = s.ne(s.shift()).cumsum()
    return grp.value_counts().max()

runs = power.groupby("memberID")["kwh"].apply(longest_run)
print("\n" + "=" * 60)
print("2. 같은 값이 연속되는 최장 시간")
print("=" * 60)
print(runs.describe().round(1).to_string())
print("\n  [24시간 이상 같은 값이 이어진 사업장]")
print(runs[runs >= 24].sort_values(ascending=False).to_string())

# ─────────────────────────────────────────────
# 3. 이상값 제외 후 규모 재분류 (상위 0.1% 값 기준)
# ─────────────────────────────────────────────
bins = [0, 10, 50, 100, 300, float("inf")]
labels = ["10kW 미만", "10~50kW", "50~100kW", "100~300kW", "300kW 이상"]
stat["band_robust"] = pd.cut(stat["p999"], bins=bins, labels=labels, right=False)
stat["band_raw"] = pd.cut(stat["max"], bins=bins, labels=labels, right=False)

print("\n" + "=" * 60)
print("3. 규모 재분류 (최댓값 기준 vs 상위 0.1% 값 기준)")
print("=" * 60)
print(pd.crosstab(stat["band_raw"], stat["band_robust"]).to_string())
print("\n  [상위 0.1% 값 기준 100kW 이상 사업장]")
big = stat[stat["p999"] >= 100].sort_values("p999", ascending=False)
big = big.merge(biz[["memberID", "workNo_name", "workHour_name", "location_name"]],
                left_index=True, right_on="memberID")
print(big[["memberID", "p999", "max", "workNo_name", "workHour_name", "location_name"]]
      .round(1).to_string(index=False))

# ─────────────────────────────────────────────
# 4. 시각 표기 점검: 주간 사업장 평일 점심 하락 시각
# ─────────────────────────────────────────────
day_ids = biz.loc[(biz["indusKind"] == 3) & (biz["workHour"] == 1), "memberID"]
wk = power[power["memberID"].isin(day_ids) & (power["ts"].dt.dayofweek < 5)].copy()
wk["hour"] = wk["ts"].dt.hour

prof = wk.groupby(["memberID", "hour"])["kwh"].mean().unstack()
norm = prof.div(prof.max(axis=1), axis=0)

print("\n" + "=" * 60)
print(f"4. 주간 사업장 {len(prof)}곳의 평일 평균 부하 모양 (각 사업장 최댓값=1)")
print("=" * 60)
avg = norm.mean().round(3)
print(pd.DataFrame({"평균": avg, "전 시간 대비 변화": avg.diff().round(3)}).to_string())

# 사업장별로 11~14시 중 가장 낮은 시각
dip = norm[[11, 12, 13, 14]].idxmin(axis=1)
print("\n  [11~14시 중 사용량이 가장 낮은 시각별 사업장 수]")
print(dip.value_counts().sort_index().to_string())

# 저장
stat.to_csv(P / "jeonnam_quality_stat.csv", encoding="utf-8-sig")
spikes.to_csv(P / "jeonnam_spikes.csv", index=False, encoding="utf-8-sig")
print("\n[저장] jeonnam_quality_stat.csv, jeonnam_spikes.csv")