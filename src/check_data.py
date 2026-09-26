"""0단계 데이터 점검 — UCI Steel Industry Energy Consumption"""
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC, FIG = ROOT / "data" / "raw", ROOT / "data" / "processed", ROOT / "figures"
PROC.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", font="Malgun Gothic")
plt.rcParams["axes.unicode_minus"] = False


def section(title):
    print("\n" + "=" * 60 + f"\n[{title}]\n" + "=" * 60)


# ---------------------------------------------------------------
# 0. 파일 찾기 + 해시
# ---------------------------------------------------------------
csvs = [p for p in RAW.glob("*.csv") if "steel" in p.name.lower()]
if not csvs:
    raise FileNotFoundError("data/raw 에 steel 이 들어간 CSV가 없습니다.")
src = csvs[0]
sha = hashlib.sha256(src.read_bytes()).hexdigest()
section("0. 파일")
print("파일명:", src.name)
print("SHA-256:", sha)

df = pd.read_csv(src)

# 열 이름을 짧게 통일 (원본 이름은 출력으로 확인)
section("1. 구조")
print("원본 열 이름:", list(df.columns))
col = {}
for c in df.columns:
    lc = c.lower()
    if lc == "date": col["date"] = c
    elif "usage" in lc: col["kwh"] = c
    elif "co2" in lc: col["co2"] = c
    elif lc == "nsm": col["nsm"] = c
    elif "weekstatus" in lc: col["week_status"] = c
    elif "day_of_week" in lc: col["dow"] = c
    elif "load_type" in lc: col["load_type"] = c
print("매핑:", col)
print("행·열:", df.shape, "| 기대 행 수: 35,040 (365일 × 96구간)")
print("결측:\n", df.isna().sum().to_string())

# ---------------------------------------------------------------
# 2. 날짜 파싱 + 순서 점검
# ---------------------------------------------------------------
section("2. 날짜 파싱")
raw_date = df[col["date"]].astype(str)
print("원본 날짜 예시 (앞 3행):", raw_date.head(3).tolist())
print("원본 날짜 예시 (96~98행):", raw_date.iloc[94:98].tolist())
ts = pd.to_datetime(raw_date, format="%d/%m/%Y %H:%M", errors="coerce")
if ts.isna().any():
    ts = pd.to_datetime(raw_date, dayfirst=True, errors="coerce")
print("파싱 실패 행 수:", int(ts.isna().sum()))

diff = ts.diff()
back = diff < pd.Timedelta(0)
print("원본 순서에서 시각이 거꾸로 가는 행 수:", int(back.sum()))
if back.any():
    ex = df.index[back][:3]
    for i in ex:
        print(f"  예: {i-1}행 {ts[i-1]} → {i}행 {ts[i]}")
    # 자정(00:00) 행이 같은 날짜로 표기된 경우 → 다음날 00:00으로 보정
    fix = back & (ts.dt.hour == 0) & (ts.dt.minute == 0)
    ts = ts.where(~fix, ts + pd.Timedelta(days=1))
    print("자정 표기 보정 행 수:", int(fix.sum()))

diff = ts.diff().dropna()
print("시각 간격 분포:\n", diff.value_counts().head().to_string())
print("중복 시각 수:", int(ts.duplicated().sum()))
print("첫 시각:", ts.iloc[0], "| 마지막 시각:", ts.iloc[-1])

# 구간 표기 기준 판단
first_hm = (ts.iloc[0].hour, ts.iloc[0].minute)
ending_label = first_hm == (0, 15)
print("첫 행이 00:15 →", "구간 '끝' 시각 표기로 판단" if ending_label else "구간 '시작' 시각 표기로 판단")
start = ts - pd.Timedelta(minutes=15) if ending_label else ts

# 월별 행 수 (구간 시작 기준)
per_month = start.dt.month.value_counts().sort_index()
expected = pd.Series({m: pd.Period(f"2018-{m:02d}").days_in_month * 96 for m in range(1, 13)})
section("3. 월별 행 수 (구간 시작 기준)")
print(pd.DataFrame({"실제": per_month, "기대": expected}).to_string())

# ---------------------------------------------------------------
# 4. 요일·NSM 일관성
# ---------------------------------------------------------------
section("4. 요일·NSM 일관성")
dow = df[col["dow"]].astype(str)
print("Day_of_week 일치율 (표기 시각 기준):", round((dow == ts.dt.day_name()).mean(), 4))
print("Day_of_week 일치율 (구간 시작 기준):", round((dow == start.dt.day_name()).mean(), 4))
nsm_calc = ts.dt.hour * 3600 + ts.dt.minute * 60
print("NSM 일치율 (표기 시각 기준):", round((df[col["nsm"]] == nsm_calc).mean(), 4))

# ---------------------------------------------------------------
# 5. 사용량·kW 변환
# ---------------------------------------------------------------
section("5. 사용량")
kwh = df[col["kwh"]].astype(float)
kw = kwh * 4  # 15분 사용량(kWh) → 평균 전력(kW)
print("kWh 요약:\n", kwh.describe().round(2).to_string())
print("최대 15분 평균 전력(kW):", round(kw.max(), 1))
print("사용량 0 구간 수:", int((kwh == 0).sum()))
print("연간 총 사용량(MWh):", round(kwh.sum() / 1000, 1))

# ---------------------------------------------------------------
# 6. CO2 열 점검
# ---------------------------------------------------------------
section("6. CO2 열")
co2 = df[col["co2"]].astype(float)
print("CO2 고유값 개수:", co2.nunique(), "| 0 비율:", round((co2 == 0).mean(), 4))
mask = kwh > 0
ratio = (co2[mask] / kwh[mask]) * 1000  # tCO2/MWh 로 환산
print("CO2 ÷ 사용량 비율(tCO2/MWh) 요약:\n", ratio.describe().round(4).to_string())
big = kwh > kwh.quantile(0.5)
print("사용량 상위 50% 구간만 본 비율 요약:\n", ((co2[big] / kwh[big]) * 1000).describe().round(4).to_string())

# ---------------------------------------------------------------
# 7. Load_Type 이 시각만으로 결정되는지
# ---------------------------------------------------------------
section("7. Load_Type")
lt = df[col["load_type"]].astype(str)
key = pd.DataFrame({
    "hm": start.dt.strftime("%H:%M"),
    "weekend": start.dt.dayofweek >= 5,
    "month": start.dt.month,
    "lt": lt,
})
nuniq = key.groupby(["hm", "weekend", "month"])["lt"].nunique()
print("(시각, 주말여부, 월) 조합 수:", len(nuniq))
print("조합 안에서 Load_Type 이 하나로 고정된 비율:", round((nuniq == 1).mean(), 4))
print("시각대별 Load_Type 분포(평일):")
wk = key[~key["weekend"]].copy()
wk["hour"] = wk["hm"].str[:2]
print(pd.crosstab(wk["hour"], wk["lt"]).to_string())

# ---------------------------------------------------------------
# 8. 공휴일 표 (2018, 원문 대조 필요)
# ---------------------------------------------------------------
holidays = {
    "2018-01-01": "신정",
    "2018-02-15": "설날연휴", "2018-02-16": "설날", "2018-02-17": "설날연휴",
    "2018-03-01": "삼일절",
    "2018-05-05": "어린이날", "2018-05-07": "대체공휴일",
    "2018-05-22": "부처님오신날",
    "2018-06-06": "현충일",
    "2018-06-13": "지방선거일",
    "2018-08-15": "광복절",
    "2018-09-23": "추석연휴", "2018-09-24": "추석", "2018-09-25": "추석연휴",
    "2018-09-26": "대체공휴일",
    "2018-10-03": "개천절",
    "2018-10-09": "한글날",
    "2018-12-25": "성탄절",
}
hol = pd.Series(holidays, name="holiday_name")
hol.index = pd.to_datetime(hol.index)
hol.to_frame().to_csv(PROC / "holidays_2018.csv", encoding="utf-8-sig", index_label="date")

# ---------------------------------------------------------------
# 9. 정제 데이터 저장
# ---------------------------------------------------------------
out = pd.DataFrame({
    "interval_start": start,
    "kwh": kwh,
    "kw": kw,
    "co2": co2,
    "load_type_raw": lt,
})
d = out["interval_start"].dt.normalize()
out["weekday"] = out["interval_start"].dt.dayofweek  # 0=월 ... 6=일
out["is_saturday"] = out["weekday"] == 5
out["is_sunday"] = out["weekday"] == 6
out["is_holiday"] = d.isin(hol.index)
out["is_zero"] = out["kwh"] == 0
out = out.sort_values("interval_start").reset_index(drop=True)
out.to_csv(PROC / "steel_15min_clean.csv", index=False, encoding="utf-8-sig")
section("9. 저장")
print("저장:", PROC / "steel_15min_clean.csv", out.shape)

# ---------------------------------------------------------------
# 10. 탐색 그래프 (seaborn)
# ---------------------------------------------------------------
out["hour"] = out["interval_start"].dt.hour
out["tod"] = out["hour"] + out["interval_start"].dt.minute / 60
out["month"] = out["interval_start"].dt.month
names = ["월", "화", "수", "목", "금", "토", "일"]
out["요일"] = pd.Categorical(out["weekday"].map(dict(enumerate(names))), categories=names, ordered=True)
out["구분"] = np.where(out["is_sunday"] | out["is_holiday"], "일요일·공휴일",
                     np.where(out["is_saturday"], "토요일", "평일"))

# (1) 시각 × 요일 히트맵
pv = out.pivot_table(index="hour", columns="요일", values="kw", aggfunc="mean", observed=False)
plt.figure(figsize=(8, 7))
sns.heatmap(pv, cmap="YlOrRd", cbar_kws={"label": "평균 kW"})
plt.title("시각 × 요일 평균 전력")
plt.tight_layout(); plt.savefig(FIG / "00_heatmap_hour_weekday.png", dpi=150); plt.close()

# (2) 월별 최대 15분 수요
mp = out.groupby("month")["kw"].max().reset_index()
mp["계절"] = mp["month"].map(lambda m: "하계(7~9월)" if m in (7, 8, 9)
                             else ("동계(12~2월)" if m in (12, 1, 2) else "기타"))
plt.figure(figsize=(9, 4.5))
sns.barplot(data=mp, x="month", y="kw", hue="계절", dodge=False)
plt.title("월별 최대 15분 수요 (래칫 기준 계절 표시)"); plt.xlabel("월"); plt.ylabel("kW")
plt.tight_layout(); plt.savefig(FIG / "00_monthly_peak.png", dpi=150); plt.close()

# (3) 평일·토요일·일요일/공휴일 일간 부하 곡선
prof = out.groupby(["구분", "tod"])["kw"].mean().reset_index()
plt.figure(figsize=(9, 4.5))
sns.lineplot(data=prof, x="tod", y="kw", hue="구분")
plt.title("일간 평균 부하 곡선"); plt.xlabel("시각"); plt.ylabel("평균 kW")
plt.xticks(range(0, 25, 3))
plt.tight_layout(); plt.savefig(FIG / "00_daily_profile.png", dpi=150); plt.close()

# (4) 하루 최저 부하 분포 (기본 부하 사전 확인)
dmin = out.groupby([out["interval_start"].dt.date, "구분"])["kw"].min().reset_index()
plt.figure(figsize=(7, 4.5))
sns.boxplot(data=dmin, x="구분", y="kw")
plt.title("하루 최저 15분 전력 분포"); plt.xlabel(""); plt.ylabel("kW")
plt.tight_layout(); plt.savefig(FIG / "00_base_load.png", dpi=150); plt.close()

section("10. 그래프 저장 완료")
print([p.name for p in FIG.glob("00_*.png")])
print("\n기본 부하 참고 — 하루 최저 kW 중앙값:")
print(dmin.groupby("구분")["kw"].median().round(1).to_string())