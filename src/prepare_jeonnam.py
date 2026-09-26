"""AI허브 전남 데이터 — 기업 정보 정리 + 제조업 사업장 전력 데이터 추출"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "raw" / "aihub_jeonnam" / "_extracted"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

# AI허브 데이터 설명서 기준 코드표
CODE = {
    "indusKind": {1: "농임어업", 2: "숙박음식점업", 3: "제조업", 4: "도소매업"},
    "workNo": {1: "1~30인", 2: "30~50인", 3: "50인 이상"},
    "workHour": {1: "주간", 2: "야간", 3: "주야간"},
    "location": {1: "순천", 2: "목포", 3: "여수", 4: "광양", 5: "나주"},
}
SPLITS = {"train": ("TL_6.industry", "TS_6.industry"),
          "valid": ("VL_6.industry", "VS_6.industry")}


def read_csv(path):
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"읽기 실패: {path}")


# ─────────────────────────────────────────────
# 1. 기업 정보: 세로(4줄) → 가로(1줄)
# ─────────────────────────────────────────────
labs = []
for split, (lab_dir, _) in SPLITS.items():
    for p in (EXT / lab_dir).glob("*.csv"):
        df = read_csv(p)
        df["split"] = split
        df["file_id"] = int(p.stem)
        labs.append(df)
labs = pd.concat(labs, ignore_index=True)
labs["RSPNS_CN"] = pd.to_numeric(labs["RSPNS_CN"], errors="coerce")

mismatch = (labs["memberID"] != labs["file_id"]).sum()
print(f"[점검] 파일명과 memberID 불일치 행: {mismatch}")

biz = (labs.pivot_table(index=["memberID", "split"], columns="QITM_EN",
                        values="RSPNS_CN", aggfunc="first")
           .reset_index())
biz.columns.name = None
print(f"[점검] 사업장 수: {len(biz)}, 항목 누락: {biz[list(CODE)].isna().sum().sum()}")

for col, table in CODE.items():
    biz[col] = biz[col].astype(int)
    biz[f"{col}_name"] = biz[col].map(table)

print("\n[업종 분포]")
print(biz["indusKind_name"].value_counts().to_string())

mfg = biz[biz["indusKind"] == 3].copy()
print(f"\n[제조업 사업장 수] {len(mfg)}곳")
print("\n[제조업 × 직원 수]")
print(mfg["workNo_name"].value_counts().to_string())
print("\n[제조업 × 근무시간]")
print(mfg["workHour_name"].value_counts().to_string())
print("\n[제조업 × 지역]")
print(mfg["location_name"].value_counts().to_string())
print("\n[제조업: 직원 수 × 근무시간]")
print(pd.crosstab(mfg["workNo_name"], mfg["workHour_name"]).to_string())

biz.to_csv(OUT / "jeonnam_business.csv", index=False, encoding="utf-8-sig")

# ─────────────────────────────────────────────
# 2. 제조업 사업장 전력 데이터 합치기
# ─────────────────────────────────────────────
frames = []
for mid, split in mfg[["memberID", "split"]].itertuples(index=False):
    src_dir = SPLITS[split][1]
    df = read_csv(EXT / src_dir / f"{mid}.csv")
    frames.append(df)
power = pd.concat(frames, ignore_index=True)
power["ts"] = pd.to_datetime(power["mrdDt"], format="%Y-%m-%d %H")
power = power.rename(columns={"pwrQrt": "kwh"})[["memberID", "ts", "kwh"]]

print("\n[전력 데이터 점검]")
print(f"  행 수: {len(power):,} (기대값: {len(mfg) * 17520:,})")
print(f"  (사업장, 시각) 중복: {power.duplicated(['memberID', 'ts']).sum()}")
print(f"  결측: {power['kwh'].isna().sum()}, 음수: {(power['kwh'] < 0).sum()}")
print(f"  0인 시간 비율: {(power['kwh'] == 0).mean():.2%}")

full = pd.date_range("2020-09-01 00:00", "2022-08-31 23:00", freq="h")
gaps = power.groupby("memberID")["ts"].apply(lambda s: len(full.difference(s)))
print(f"  빠진 시각이 있는 사업장: {(gaps > 0).sum()}곳")

# ─────────────────────────────────────────────
# 3. 사업장별 규모 요약 (1시간 사용량 kWh = 그 시간 평균 kW)
# ─────────────────────────────────────────────
g = power.groupby("memberID")["kwh"]
summary = pd.DataFrame({
    "annual_mwh": g.sum() / 2 / 1000,          # 2년치 → 연평균
    "mean_kw": g.mean(),
    "max_hourly_kw": g.max(),
    "median_kw": g.median(),
    "zero_share": g.apply(lambda s: (s == 0).mean()),
})
summary["load_factor"] = summary["mean_kw"] / summary["max_hourly_kw"]
summary = summary.merge(
    mfg[["memberID", "split", "workNo_name", "workHour_name", "location_name"]],
    on="memberID")

print("\n[제조업 사업장 규모 요약]")
print(summary[["annual_mwh", "mean_kw", "max_hourly_kw", "load_factor", "zero_share"]]
      .describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]).round(2).to_string())

bins = [0, 10, 50, 100, 300, float("inf")]
labels = ["10kW 미만", "10~50kW", "50~100kW", "100~300kW", "300kW 이상"]
summary["size_band"] = pd.cut(summary["max_hourly_kw"], bins=bins, labels=labels, right=False)
print("\n[1시간 최대 전력 구간별 사업장 수]")
print(summary["size_band"].value_counts().reindex(labels).to_string())

print("\n[직원 수별 1시간 최대 전력 중앙값(kW)]")
print(summary.groupby("workNo_name")["max_hourly_kw"].median().round(1).to_string())

# ─────────────────────────────────────────────
# 4. 저장
# ─────────────────────────────────────────────
power.to_csv(OUT / "jeonnam_mfg_hourly.csv.gz", index=False, compression="gzip")
summary.to_csv(OUT / "jeonnam_mfg_summary.csv", index=False, encoding="utf-8-sig")
print("\n[저장 완료]")
print("  data/processed/jeonnam_business.csv")
print("  data/processed/jeonnam_mfg_hourly.csv.gz")
print("  data/processed/jeonnam_mfg_summary.csv")