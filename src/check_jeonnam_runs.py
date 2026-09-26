"""전남 제조업 데이터 — 고착(같은 값 연속) 구간 정체 확인"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"

power = pd.read_csv(P / "jeonnam_mfg_hourly.csv.gz", parse_dates=["ts"])
power = power.sort_values(["memberID", "ts"]).reset_index(drop=True)

# 같은 값이 이어지는 구간(run) 번호 매기기
power["run_id"] = power.groupby("memberID")["kwh"].transform(
    lambda s: s.ne(s.shift()).cumsum())
runs = (power.groupby(["memberID", "run_id"])
             .agg(start=("ts", "min"), end=("ts", "max"),
                  hours=("kwh", "size"), value=("kwh", "first"))
             .reset_index())
long = runs[runs["hours"] >= 24].copy()

# ─────────────────────────────────────────────
# 1. 24시간 이상 고착 구간 요약
# ─────────────────────────────────────────────
print("=" * 60)
print("1. 24시간 이상 고착 구간")
print("=" * 60)
print(f"  구간 수: {len(long)}, 사업장 수: {long['memberID'].nunique()}, "
      f"총 시간: {long['hours'].sum():,}")
print("\n  [길이별 구간 수 상위 10]")
print(long["hours"].value_counts().head(10).to_string())

# ─────────────────────────────────────────────
# 2. 같은 길이 구간이 같은 날짜인지
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("2. 자주 나오는 길이의 구간이 같은 날짜인지")
print("=" * 60)
for h in long["hours"].value_counts().head(3).index:
    sub = long[long["hours"] == h]
    print(f"\n  [{h}시간 구간 {len(sub)}개] 시작~끝 조합 상위 5")
    print(sub.groupby(["start", "end"]).size()
             .sort_values(ascending=False).head(5).to_string())
    print(f"  채워진 값 분포(상위 5): {sub['value'].round(3).value_counts().head(5).to_dict()}")

# ─────────────────────────────────────────────
# 3. 가장 긴 구간 10개
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("3. 가장 긴 고착 구간 10개")
print("=" * 60)
print(long.sort_values("hours", ascending=False)
          [["memberID", "start", "end", "hours", "value"]]
          .head(10).to_string(index=False))

# ─────────────────────────────────────────────
# 4. 날짜별로 몇 곳이 동시에 고착 상태인지
# ─────────────────────────────────────────────
power = power.merge(runs[["memberID", "run_id", "hours"]],
                    on=["memberID", "run_id"], how="left")
power["stuck"] = power["hours"] >= 24
by_ts = power.groupby("ts")["stuck"].sum()

print("\n" + "=" * 60)
print("4. 동시에 고착된 사업장 수 (20곳 이상인 기간)")
print("=" * 60)
hot = by_ts[by_ts >= 20]
if len(hot):
    block = (hot.index.to_series().diff() != pd.Timedelta(hours=1)).cumsum()
    periods = hot.groupby(block.values).agg(["size", "max"])
    periods["start"] = hot.index.to_series().groupby(block.values).min().values
    periods["end"] = hot.index.to_series().groupby(block.values).max().values
    print(periods[["start", "end", "size", "max"]]
          .rename(columns={"size": "시간 수", "max": "최대 동시 사업장"})
          .to_string(index=False))
else:
    print("  없음")

# ─────────────────────────────────────────────
# 5. 가장 흔한 길이 구간 하나의 앞뒤 모습
# ─────────────────────────────────────────────
sample = long[long["hours"] == long["hours"].value_counts().idxmax()].iloc[0]
win = power[(power["memberID"] == sample["memberID"])
            & (power["ts"] >= sample["start"] - pd.Timedelta(hours=6))
            & (power["ts"] <= sample["start"] + pd.Timedelta(hours=6))]
print("\n" + "=" * 60)
print(f"5. 예시 구간 시작 전후 (사업장 {sample['memberID']})")
print("=" * 60)
print(win[["ts", "kwh"]].to_string(index=False))

win2 = power[(power["memberID"] == sample["memberID"])
             & (power["ts"] >= sample["end"] - pd.Timedelta(hours=3))
             & (power["ts"] <= sample["end"] + pd.Timedelta(hours=6))]
print("\n  [구간 끝 전후]")
print(win2[["ts", "kwh"]].to_string(index=False))

long.to_csv(P / "jeonnam_stuck_runs.csv", index=False, encoding="utf-8-sig")
print("\n[저장] jeonnam_stuck_runs.csv")