"""0단계 보완 — UCI Load_Type 휴무 표시가 실제 사용량과 맞는지 확인"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_csv(ROOT / "data" / "processed" / "steel_15min_clean.csv",
                 parse_dates=["interval_start"])
df["date"] = df["interval_start"].dt.normalize()
daily = df.groupby("date")["kwh"].sum()

weekdays = daily[daily.index.dayofweek < 5]
print("평일 하루 사용량 중앙값(kWh):", round(weekdays.median(), 1))
print("평일 하루 사용량 하위 10%(kWh):", round(weekdays.quantile(0.1), 1))

check = {
    "데이터만 휴무로 표시": ["2018-02-14", "2018-05-01", "2018-08-01",
                       "2018-08-02", "2018-08-03", "2018-12-31"],
    "법정 공휴일인데 데이터는 평소대로": ["2018-03-01", "2018-05-07", "2018-05-22",
                             "2018-06-06", "2018-06-13", "2018-08-15",
                             "2018-10-03", "2018-10-09"],
    "둘 다 휴일": ["2018-01-01", "2018-02-15", "2018-02-16", "2018-09-24",
               "2018-09-25", "2018-09-26", "2018-12-25"],
}
for label, dates in check.items():
    print(f"\n[{label}]")
    for d in dates:
        print(f"  {d}  {daily[pd.Timestamp(d)]:>8.1f} kWh")