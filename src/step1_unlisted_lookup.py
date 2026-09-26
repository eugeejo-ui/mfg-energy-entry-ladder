"""1단계 1-1b (A·B) — 비상장 배출권 1차 업종 32곳: DART 회사 코드 찾기 + 기업집단 판정"""
from pathlib import Path
import io
import os
import re
import sys
import time
import warnings
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd
import requests
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CBAM = ROOT / "data" / "external" / "cbam"
OUT = ROOT / "data" / "processed"
DART_DIR = RAW / "dart"
DART_DIR.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")
KEY = os.environ.get("DART_API_KEY", "").strip()
if not KEY:
    sys.exit("DART_API_KEY 를 찾지 못했습니다. .env 파일을 확인해 주세요.")

LARGE_GROUP_ASSET = 12_000_000  # 상호출자제한 기준 12조 원 (공정위 파일 단위: 백만 원), cbam과 동일

LETTER_KO = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지",
    "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔",
    "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유",
    "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "제트",
}


def norm_name(x) -> str:
    """cbam과 같은 회사명 정리: 법인 표기·공백·괄호 제거, 영문은 한글 읽기로 변환"""
    s = str(x) if pd.notna(x) else ""
    s = re.sub(r"주식회사|유한회사|유한책임회사|합자회사|㈜|\(주\)|\(유\)|\(합\)", "", s)
    s = re.sub(r"[\s\.\,\-·&()]", "", s).upper()
    return "".join(LETTER_KO.get(ch, ch) for ch in s)


def strip_site(name: str) -> str:
    """'(주)성호금속 경주2공장' 같은 사업장 표기 제거"""
    return re.sub(r"\s+\S*(공장|사업장|사업소)$", "", str(name)).strip()


def digits(x) -> str:
    return re.sub(r"\D", "", str(x)) if pd.notna(x) else ""


def find_one(pattern: str) -> Path:
    hits = sorted(RAW.glob(pattern))
    if not hits:
        sys.exit(f"data/raw 에서 '{pattern}' 파일을 찾지 못했습니다.")
    return hits[-1]


# ─────────────────────────────────────────────
# DART
# ─────────────────────────────────────────────
def load_corp_codes() -> pd.DataFrame:
    path = DART_DIR / "corpCode.xml"
    if not path.exists():
        r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                         params={"crtfc_key": KEY}, timeout=120)
        if not r.content[:2] == b"PK":
            sys.exit(f"회사 코드 다운로드 실패: {r.text[:300]}")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            path.write_bytes(z.read(z.namelist()[0]))
    root = ET.parse(path).getroot()
    rows = [{k: (el.findtext(k) or "").strip()
             for k in ("corp_code", "corp_name", "stock_code", "modify_date")}
            for el in root.iter("list")]
    df = pd.DataFrame(rows)
    df["name_key"] = df["corp_name"].map(norm_name)
    return df


def company(corp_code: str) -> dict:
    r = requests.get("https://opendart.fss.or.kr/api/company.json",
                     params={"crtfc_key": KEY, "corp_code": corp_code}, timeout=30)
    j = r.json()
    time.sleep(0.2)
    return j


# ─────────────────────────────────────────────
# 입력
# ─────────────────────────────────────────────
un = pd.read_csv(CBAM / "kets_unmatched_wave1.csv", dtype=str)
un["kets_ksic"] = un["kets_ksic"].str.strip().str.zfill(5)
un["name_key"] = un["업체명"].map(lambda s: norm_name(strip_site(s)))
print(f"비상장·미매칭 배출권 1차 업종: {len(un)}곳")

corps = load_corp_codes()
print(f"DART 전체 회사 코드: {len(corps):,}")

cbam = pd.read_csv(CBAM / "mfg_final_reviewed.csv", dtype=str)
cbam_codes = set(cbam["corp_code"].str.zfill(8))

groups = pd.read_excel(find_one("*기업집단별*개요*.xlsx"), dtype=str)
groups["ftc_asset"] = pd.to_numeric(groups["공정거래위원회자산총액"].str.replace(",", ""),
                                    errors="coerce")
groups["is_large"] = groups["ftc_asset"] >= LARGE_GROUP_ASSET

aff = pd.read_excel(find_one("*소속회사*개요*.xlsx"), dtype=str)
aff["jurir_key"] = aff["법인등록번호"].map(digits)
aff = aff.merge(groups[["기업집단", "is_large"]],
                left_on="기업집단명", right_on="기업집단", how="left")
aff_agg = (aff.groupby("jurir_key")
              .agg(ftc_group=("기업집단명", lambda s: "/".join(sorted(set(s)))),
                   ftc_is_large=("is_large", "max"))
              .reset_index())
print(f"기업집단 {len(groups)}개 (상호출자제한 {int(groups['is_large'].sum())}), "
      f"소속회사 {aff['jurir_key'].nunique():,}곳")

# ─────────────────────────────────────────────
# A. DART 회사 코드 찾기
# ─────────────────────────────────────────────
rows = []
for _, u in un.iterrows():
    base = {"kets_code": u["업체코드"], "kets_name": u["업체명"], "kets_ksic": u["kets_ksic"]}
    cands = corps[corps["name_key"] == u["name_key"]]
    if cands.empty:
        rows.append({**base, "n_cand": 0})
        continue
    for _, c in cands.iterrows():
        info = company(c["corp_code"])
        ok = info.get("status") == "000"
        rows.append({
            **base,
            "n_cand": len(cands),
            "corp_code": c["corp_code"],
            "dart_name": info.get("corp_name") if ok else c["corp_name"],
            "corp_cls": info.get("corp_cls") if ok else "",
            "stock_code": (info.get("stock_code") or "").strip() if ok else c["stock_code"],
            "jurir_no": info.get("jurir_no") if ok else "",
            "induty_code": info.get("induty_code") if ok else "",
            "adres": info.get("adres") if ok else "",
            "api_status": info.get("status"),
        })

res = pd.DataFrame(rows)
res["same_div"] = res["induty_code"].astype(str).str[:2] == res["kets_ksic"].str[:2]

# 후보가 여러 개인데 업종이 맞는 후보가 딱 1개면 그것만 남김 (그 외에는 모두 남김)
n_same = res.groupby("kets_code")["same_div"].transform("sum")
keep = (res["n_cand"] <= 1) | (n_same != 1) | res["same_div"]
res = res[keep].copy()
res["n_kept"] = res.groupby("kets_code")["corp_code"].transform("count")

# ─────────────────────────────────────────────
# B. 기업집단 판정
# ─────────────────────────────────────────────
res["jurir_key"] = res["jurir_no"].map(digits)
res = res.merge(aff_agg, on="jurir_key", how="left")
res["ftc_is_large"] = res["ftc_is_large"].fillna(False).astype(bool)
res["in_cbam"] = res["corp_code"].fillna("").str.zfill(8).isin(cbam_codes)


def verdict(r) -> str:
    if r["n_cand"] == 0:
        return "DART 미매칭 (수동 확인)"
    if r["n_kept"] > 1:
        return "후보 여러 개 (수동 확인)"
    if r["in_cbam"]:
        return "cbam 명단에 이미 있음 (중복 제외)"
    if r["ftc_is_large"]:
        return "대기업 (상호출자제한 소속, 제외)"
    if pd.notna(r["ftc_group"]):
        return "중견 (공시대상기업집단 소속)"
    return "매출·자산 확인 필요 (C단계)"


res["verdict"] = res.apply(verdict, axis=1)

# ─────────────────────────────────────────────
# 결과
# ─────────────────────────────────────────────
print("\n[판정 결과] (업체 기준)")
print(res.drop_duplicates("kets_code")["verdict"].value_counts().to_string())

show = ["kets_name", "kets_ksic", "dart_name", "corp_cls", "stock_code",
        "induty_code", "ftc_group", "verdict"]
print("\n[회사별]")
print(res[show].to_string(index=False))

res.to_csv(OUT / "step1_unlisted_lookup.csv", index=False, encoding="utf-8-sig")
print("\n[저장] data/processed/step1_unlisted_lookup.csv")