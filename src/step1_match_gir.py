"""1단계 1-3 — GIR 명세서(2023~2025)와 대상 기업 75곳 매칭"""
from pathlib import Path
import re
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CBAM = ROOT / "data" / "external" / "cbam"
P = ROOT / "data" / "processed"
YEARS = (2023, 2024, 2025)

LETTER_KO = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지",
    "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔",
    "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유",
    "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "제트",
}


def norm_name(x) -> str:
    s = str(x) if pd.notna(x) else ""
    s = re.sub(r"주식회사|유한회사|유한책임회사|합자회사|㈜|\(주\)|\(유\)|\(합\)", "", s)
    s = re.sub(r"\s+\S*(공장|사업장|사업소)$", "", s)
    s = re.sub(r"[\s\.\,\-·&()]", "", s).upper()
    return "".join(LETTER_KO.get(ch, ch) for ch in s)


# ─────────────────────────────────────────────
# 1. GIR 읽기 + 정리
# ─────────────────────────────────────────────
def load_gir(y: int) -> pd.DataFrame:
    raw = pd.read_excel(RAW / "gir" / f"gir_{y}.xls", header=None, dtype=str, engine="xlrd")
    df = raw.iloc[1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[0]]
    ren = {}
    for c in df.columns:
        if "업종" in c:
            ren[c] = "업종"
        elif "배출량" in c:
            ren[c] = "배출량"
        elif "에너지" in c:
            ren[c] = "에너지"
    df = df.rename(columns=ren)
    n0 = len(df)
    df = df.drop(columns=["번호"]).drop_duplicates()
    print(f"  {y}: {n0:,}행 → 완전 중복 제거 후 {len(df):,}행")
    df["hidden"] = df["에너지"].astype(str).str.contains(r"\*")
    for c in ("배출량", "에너지"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    df["year"] = y
    df["name_key"] = df["법인명"].map(norm_name)
    return df


print("[GIR 읽기]")
gir = pd.concat([load_gir(y) for y in YEARS], ignore_index=True)

# 업체 행이 있으면 업체 행만, 없으면 사업장 행 합산
gir["is_up"] = gir["지정구분"] == "업체"
has_up = gir.groupby(["name_key", "year"])["is_up"].transform("any")
use = gir[~has_up | gir["is_up"]]
fy = (use.groupby(["name_key", "year"])
         .agg(gir_name=("법인명", "first"),
              gir_type=("지정구분", lambda s: "업체" if (s == "업체").any() else f"사업장 {len(s)}곳"),
              gir_industry=("업종", "first"),
              emis=("배출량", lambda s: s.sum(min_count=1)),
              energy_tj=("에너지", lambda s: s.sum(min_count=1)),
              hidden=("hidden", "any"))
         .reset_index())

e_w = fy.pivot(index="name_key", columns="year", values="energy_tj")
e_w.columns = [f"energy_tj_{c}" for c in e_w.columns]
g_w = fy.pivot(index="name_key", columns="year", values="emis")
g_w.columns = [f"emis_{c}" for c in g_w.columns]
meta = (fy.sort_values("year").groupby("name_key")
          .agg(gir_name=("gir_name", "last"), gir_type=("gir_type", "last"),
               gir_industry=("gir_industry", "last"), hidden_any=("hidden", "any")))
girw = meta.join(e_w).join(g_w).reset_index()
ecols = [f"energy_tj_{y}" for y in YEARS]
girw["energy_tj_avg"] = girw[ecols].mean(axis=1, skipna=True)
girw["n_years"] = girw[ecols].notna().sum(axis=1)
print(f"  GIR 법인(이름 기준): {len(girw):,}곳")

# ─────────────────────────────────────────────
# 2. 대상 기업 75곳 + 보류 1곳(동남, 식별용)
# ─────────────────────────────────────────────
T = pd.read_csv(P / "target_firms.csv", dtype=str)
T["kets_member"] = T["kets_member"].astype(str).str.lower() == "true"
T = pd.concat([T, pd.DataFrame([{"source": "비상장(보류)", "name": "(주)동남",
                                 "kets_name": "(주)동남", "ksic": "24212", "kets_member": True}])],
              ignore_index=True)
print(f"\n[대상] {len(T) - 1}곳 + 보류 1곳")

# ─────────────────────────────────────────────
# 3. 매칭: 배출권 명단 이름 → DART 회사명 순
# ─────────────────────────────────────────────
keys = set(girw["name_key"]) - {""}
T["k1"] = T["kets_name"].map(norm_name)
T["k2"] = T["name"].map(norm_name)
T["gir_key"] = np.where(T["k1"].isin(keys), T["k1"],
                        np.where(T["k2"].isin(keys), T["k2"], None))
T["match_by"] = np.where(T["k1"].isin(keys), "배출권 명단 이름",
                         np.where(T["k2"].isin(keys), "DART 회사명", "미매칭"))
M = T.merge(girw, left_on="gir_key", right_on="name_key", how="left")

ok_words = "철강|비철|금속|시멘트|석회|비료|화학|질소|주조|강관|알루미늄"
M["industry_check"] = np.where(
    M["gir_industry"].isna(), "",
    np.where(M["gir_industry"].astype(str).str.contains(ok_words), "", "업종 확인 필요"))

# ─────────────────────────────────────────────
# 4. 결과
# ─────────────────────────────────────────────
print("\n[매칭 결과]")
print(pd.crosstab([M["source"], M["kets_member"]], M["match_by"]).to_string())

show = ["source", "name", "gir_type", "gir_industry",
        "energy_tj_2023", "energy_tj_2024", "energy_tj_2025", "industry_check"]
print("\n[매칭된 회사]")
print(M[M["match_by"] != "미매칭"][show].round(0).to_string(index=False))

print("\n[미매칭]")
print(M[M["match_by"] == "미매칭"][["source", "name", "kets_name", "kets_member"]]
      .to_string(index=False))

# GIR 철강·비철·시멘트·비료 업종인데, 이미 판정한 어떤 회사에도 해당하지 않는 곳
cb = pd.read_csv(CBAM / "mfg_final_reviewed.csv", dtype=str)
un = pd.read_csv(P / "step1_unlisted_final.csv", dtype=str)
known = set(cb["corp_name"].map(norm_name)) | set(cb["kets_name"].dropna().map(norm_name)) \
    | set(un["kets_name"].map(norm_name)) | set(un["dart_name"].dropna().map(norm_name))
rest = girw[~girw["name_key"].isin(known)
            & girw["gir_industry"].astype(str).str.contains("철강|비철|시멘트|비료|질소")]
print(f"\n[참고] GIR 철강·비철·시멘트·비료 업종 중 한 번도 판정하지 않은 법인: {len(rest)}곳")
print(rest[["gir_name", "gir_type", "gir_industry", "energy_tj_avg"]]
      .sort_values("energy_tj_avg", ascending=False).head(20).round(0).to_string(index=False))

M.to_csv(P / "step1_gir_matched.csv", index=False, encoding="utf-8-sig")
rest.to_csv(P / "step1_gir_not_judged.csv", index=False, encoding="utf-8-sig")
girw.to_csv(P / "gir_2023_2025_by_firm.csv", index=False, encoding="utf-8-sig")
print("\n[저장] step1_gir_matched.csv, step1_gir_not_judged.csv, gir_2023_2025_by_firm.csv")