"""AI허브 전남 전력소비패턴 데이터 — 기업(industry) 파일 내용 확인"""
from pathlib import Path
import hashlib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "raw" / "aihub_jeonnam" / "_extracted"

if not EXT.exists():
    raise FileNotFoundError(f"폴더가 없습니다: {EXT}")


def read_csv(path, **kw):
    """인코딩을 바꿔가며 읽기"""
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc, **kw)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"읽기 실패: {path}")


def show_time_columns(df, label):
    """날짜·시각으로 읽히는 열을 찾아 기간과 간격 출력"""
    for c in df.columns:
        if df[c].dtype != object:
            continue
        parsed = pd.to_datetime(df[c], errors="coerce")
        if parsed.notna().mean() < 0.9:
            continue
        gaps = parsed.sort_values().diff().dropna()
        print(f"  [{label}] 시각 열 후보: {c}")
        print(f"    기간: {parsed.min()} ~ {parsed.max()}")
        print(f"    가장 흔한 간격: {gaps.mode().iloc[0] if len(gaps) else '없음'}")
        print(f"    행 수: {len(parsed):,}, 중복 시각: {parsed.duplicated().sum():,}")


folders = {
    "TL": EXT / "TL_6.industry",
    "VL": EXT / "VL_6.industry",
    "TS": EXT / "TS_6.industry",
    "VS": EXT / "VS_6.industry",
}

# 1. 파일 수와 ID 대조
print("=" * 60)
print("1. 파일 수와 ID 대조")
print("=" * 60)
ids = {k: {p.stem for p in v.glob("*.csv")} for k, v in folders.items()}
for k, s in ids.items():
    print(f"  [{k}] 파일 수: {len(s)}")
print("  TL과 TS의 ID가 같은가:", ids["TL"] == ids["TS"])
print("  VL과 VS의 ID가 같은가:", ids["VL"] == ids["VS"])
train_ids = ids["TL"] | ids["TS"]
valid_ids = ids["VL"] | ids["VS"]
print("  Training·Validation 겹치는 ID 수:", len(train_ids & valid_ids))

# 2. 라벨 파일 1개
print("\n" + "=" * 60)
print("2. 라벨(기업 정보) 파일 예시")
print("=" * 60)
lab_path = sorted(folders["TL"].glob("*.csv"))[0]
lab = read_csv(lab_path)
print(f"  파일: {lab_path.name}  shape: {lab.shape}")
print(lab.head(10).to_string())

# 3. 라벨 전체를 합쳐서 값 분포 보기
print("\n" + "=" * 60)
print("3. 라벨 전체 값 분포 (값 종류 12개 이하인 열만)")
print("=" * 60)
labs = pd.concat(
    [read_csv(p).assign(_id=p.stem, _split=k)
     for k in ("TL", "VL") for p in folders[k].glob("*.csv")],
    ignore_index=True,
)
print(f"  합친 shape: {labs.shape}")
print(f"  열: {list(labs.columns)}")
for c in labs.columns:
    if c.startswith("_"):
        continue
    vc = labs[c].value_counts(dropna=False)
    if len(vc) <= 12:
        print(f"\n  <{c}>")
        print(vc.to_string())

# 4. 원천(전력) 파일 1개
print("\n" + "=" * 60)
print("4. 원천(전력) 파일 예시")
print("=" * 60)
src_path = sorted(folders["TS"].glob("*.csv"))[0]
src = read_csv(src_path)
print(f"  파일: {src_path.name}  shape: {src.shape}")
print(src.head(5).to_string())
print("  ...")
print(src.tail(3).to_string())
print("\n  [열 형식]")
print(src.dtypes.to_string())
print("\n  [결측 수]")
print(src.isna().sum().to_string())
show_time_columns(src, src_path.name)

# 5. 원천 파일 전체의 행 수 분포 (기간이 사업장마다 같은지)
print("\n" + "=" * 60)
print("5. 원천 파일별 행 수 분포")
print("=" * 60)
rows = pd.Series(
    {p.stem: sum(1 for _ in open(p, encoding="utf-8", errors="ignore")) - 1
     for k in ("TS", "VS") for p in folders[k].glob("*.csv")}
)
print(rows.describe().to_string())
print("\n  가장 흔한 행 수 상위 5개:")
print(rows.value_counts().head(5).to_string())

# 6. 날씨 파일
print("\n" + "=" * 60)
print("6. 날씨 파일")
print("=" * 60)
for k in ("TS_weatherdata", "VS_weatherdata"):
    names = sorted(p.name for p in (EXT / k).glob("*.csv"))
    print(f"  [{k}] {names}")


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


same = all(
    md5(EXT / "TS_weatherdata" / n) == md5(EXT / "VS_weatherdata" / n)
    for n in names
    if (EXT / "TS_weatherdata" / n).exists()
)
print("  TS와 VS 날씨 파일이 완전히 같은가:", same)

w_path = sorted((EXT / "TS_weatherdata").glob("*.csv"))[0]
w = read_csv(w_path)
print(f"\n  파일: {w_path.name}  shape: {w.shape}")
print(w.head(3).to_string())
show_time_columns(w, w_path.name)