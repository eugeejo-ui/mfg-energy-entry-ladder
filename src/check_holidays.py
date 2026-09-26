"""0단계 보완 — 데이터가 공휴일로 처리한 날과 공휴일 목록 대조"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_csv(ROOT / "data" / "processed" / "steel_15min_clean.csv",
                 parse_dates=["interval_start"])
hol = pd.read_csv(ROOT / "data" / "processed" / "holidays_2018.csv",
                  parse_dates=["date"])

df["date"] = df["interval_start"].dt.normalize()
df["hour"] = df["interval_start"].dt.hour

# 평일 9~22시가 전부 경부하로 찍힌 날 = 데이터가 공휴일로 처리한 평일
wk = df[(df["weekday"] < 5) & df["hour"].between(9, 22)]
is_light = wk.groupby("date")["load_type_raw"].apply(lambda s: (s == "Light_Load").all())
data_hol = set(is_light[is_light].index)

our_hol = set(hol.loc[hol["date"].dt.dayofweek < 5, "date"])
name = dict(zip(hol["date"], hol["holiday_name"]))

print("[데이터가 공휴일로 처리한 평일]", len(data_hol))
for d in sorted(data_hol):
    print(" ", d.date(), name.get(d, "(목록에 없음)"))

print("\n[목록에는 있는데 데이터는 평일로 처리한 날]")
for d in sorted(our_hol - data_hol):
    print(" ", d.date(), name[d])

print("\n[데이터만 공휴일로 처리한 날]")
for d in sorted(data_hol - our_hol):
    print(" ", d.date())

# 토요일 시간대 처리 확인 (한전 규정: 토요일 최대부하는 중간부하로 계량)
sat = df[df["weekday"] == 5]
print("\n[토요일 시각대별 Load_Type]")
print(pd.crosstab(sat["hour"], sat["load_type_raw"]).to_string())