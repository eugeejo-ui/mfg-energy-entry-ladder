"""1단계 1-2 점검 — GIR 명세서 엑셀 3개년 구조 확인 (.xls 대응)"""
from pathlib import Path
import warnings
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
GIR = ROOT / "data" / "raw" / "gir"


def read_any(p: Path):
    """진짜 .xls면 xlrd로, 속이 HTML이면 read_html로 읽음 (제목행 없이 원시 그대로)"""
    try:
        return pd.read_excel(p, header=None, dtype=str, engine="xlrd"), "xlrd(.xls)"
    except Exception as e1:
        for enc in ("utf-8", "cp949"):
            try:
                tables = pd.read_html(p, header=None, encoding=enc)
                t = max(tables, key=len).astype(str)
                return t, f"HTML 표({enc})"
            except Exception:
                continue
        raise RuntimeError(f"읽기 실패: {p.name} / {e1}")


def find_col(cols, *keys):
    return next((c for c in cols if all(k in c for k in keys)), None)


for y in (2023, 2024, 2025):
    p = GIR / f"gir_{y}.xls"
    print("=" * 60)
    if not p.exists():
        print("파일 없음:", p)
        continue

    raw, how = read_any(p)
    raw = raw.replace({"nan": None})
    hdr = next((i for i in range(min(15, len(raw)))
                if raw.iloc[i].astype(str).str.contains("법인명").any()), None)
    print(f"{p.name} | 읽은 방식: {how} | 제목행 위치: {hdr} | 원시 행 수: {len(raw)}")
    if hdr is None:
        print(raw.head(10).to_string())
        continue

    df = raw.iloc[hdr + 1:].copy()
    df.columns = [str(c).replace("\n", " ").strip() for c in raw.iloc[hdr]]
    df = df.dropna(how="all")
    print("열:", list(df.columns))
    print("데이터 행 수:", len(df))

    ycol = find_col(df.columns, "대상")
    kcol = find_col(df.columns, "지정구분")
    ncol = find_col(df.columns, "법인명")
    icol = find_col(df.columns, "업종")
    gcol = find_col(df.columns, "배출량")
    ecol = find_col(df.columns, "에너지")

    if ycol:
        print("대상년도:", df[ycol].value_counts().to_dict())
    if kcol:
        print("지정구분:", df[kcol].value_counts().to_dict())

    for col in (gcol, ecol):
        if col:
            num = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
            bad = df.loc[num.isna(), col]
            print(f"[{col}] 숫자가 아닌 값: {len(bad)}건, 예시: {bad.unique()[:5].tolist()}")

    if ncol:
        print("같은 법인명이 여러 행인 경우:", int(df[ncol].duplicated(keep=False).sum()), "행")

    if icol:
        sub = df[df[icol].astype(str).str.contains("철강|비철|금속|시멘트|비료")]
        print(f"철강·비철·금속·시멘트·비료 업종 행: {len(sub)}")
        show = [c for c in (ncol, kcol, icol, gcol, ecol) if c]
        print(sub[show].head(8).to_string(index=False))