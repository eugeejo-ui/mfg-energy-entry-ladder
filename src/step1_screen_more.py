"""1단계 보완 — GIR 미판정 72곳 1차 선별: CBAM 1차 업종 + 대기업 계열 아님"""
from pathlib import Path
import os
import re
import sys
import time
import warnings
import xml.etree.ElementTree as ET

import pandas as pd
import requests
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
P = ROOT / "data" / "processed"
CBAM = ROOT / "data" / "external" / "cbam"

load_dotenv(ROOT / ".env")
KEY = os.environ.get("DART_API_KEY", "").strip()
if not KEY:
    sys.exit("DART_API_KEY 를 찾지 못했습니다. .env 파일을 확인해 주세요.")

LARGE_GROUP_ASSET = 12_000_000  # 백만 원 (12조), cbam과 동일

# cbam과 동일한 CBAM 1차 업종 규칙
CBAM_WAVE1 = {"241": "철강", "24212": "알루미늄", "24222": "알루미늄", "23311": "시멘트",
              "2031": "비료", "2511": "구조물", "25122": "탱크·용기", "25123": "탱크·용기",
              "25991": "탱크·용기", "25941": "볼트·너트"}
CBAM_PARTIAL = {"25942": "기타 파스너(일부)", "2591": "단조·압형(일부)"}

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


def digits(x) -> str:
    return re.sub(r"\D", "", str(x)) if pd.notna(x) else ""


def ksic_match(code) -> str:
    c = str(code or "").strip()
    if not c or c == "nan":
        return "비해당"
    if any(c.startswith(k) for k in CBAM_PARTIAL):
        return "일부해당"
    if any(c.startswith(k) for k in CBAM_WAVE1):
        return "해당"
    if any(k.startswith(c) for k in CBAM_WAVE1):
        return "일부해당"
    return "비해당"


def company(corp_code: str) -> dict:
    r = requests.get("https://opendart.fss.or.kr/api/company.json",
                     params={"crtfc_key": KEY, "corp_code": corp_code}, timeout=30)
    time.sleep(0.2)
    return r.json()


def find_one(pattern: str) -> Path:
    hits = sorted(RAW.glob(pattern))
    if not hits:
        sys.exit(f"data/raw 에서 '{pattern}' 파일을 찾지 못했습니다.")
    return hits[-1]


# ─────────────────────────────────────────────
# 입력
# ─────────────────────────────────────────────
G = pd.read_csv(P / "step1_gir_not_judged.csv", dtype=str)
G["energy_tj_avg"] = pd.to_numeric(G["energy_tj_avg"], errors="coerce")
print(f"GIR 미판정: {len(G)}곳")

root = ET.parse(RAW / "dart" / "corpCode.xml").getroot()
corps = pd.DataFrame([{k: (el.findtext(k) or "").strip() for k in ("corp_code", "corp_name", "stock_code")}
                      for el in root.iter("list")])
corps["key"] = corps["corp_name"].map(norm_name)

cb = pd.read_csv(CBAM / "mfg_final_reviewed.csv", dtype=str)
cb["corp_code"] = cb["corp_code"].str.zfill(8)
cb_map = cb.set_index("corp_code")[["size_class", "wave_group_reviewed"]].to_dict("index")

groups = pd.read_excel(find_one("*기업집단별*개요*.xlsx"), dtype=str)
groups["is_large"] = pd.to_numeric(groups["공정거래위원회자산총액"].str.replace(",", ""),
                                   errors="coerce") >= LARGE_GROUP_ASSET
aff = pd.read_excel(find_one("*소속회사*개요*.xlsx"), dtype=str)
aff["jurir_key"] = aff["법인등록번호"].map(digits)
aff = aff.merge(groups[["기업집단", "is_large"]], left_on="기업집단명", right_on="기업집단", how="left")
aff_map = aff.groupby("jurir_key").agg(ftc_group=("기업집단명", "first"),
                                       is_large=("is_large", "max")).to_dict("index")

# ─────────────────────────────────────────────
# 선별
# ─────────────────────────────────────────────
rows = []
for i, (_, g) in enumerate(G.iterrows(), 1):
    cands = corps[corps["key"] == norm_name(g["gir_name"])].head(8)
    infos = []
    for _, c in cands.iterrows():
        j = company(c["corp_code"])
        if j.get("status") == "000":
            infos.append({"corp_code": c["corp_code"], "dart_name": j.get("corp_name"),
                          "induty_code": j.get("induty_code"), "corp_cls": j.get("corp_cls"),
                          "jurir_key": digits(j.get("jurir_no")),
                          "wave": ksic_match(j.get("induty_code"))})
    hit = [x for x in infos if x["wave"] == "해당"]
    pick = hit if hit else infos
    rec = {"gir_name": g["gir_name"], "gir_type": g["gir_type"], "gir_industry": g["gir_industry"],
           "energy_tj_avg": g["energy_tj_avg"], "n_cand": len(infos)}

    if not infos:
        rec["verdict"] = "DART 미매칭"
    elif len(pick) > 1:
        rec["verdict"] = "후보 여러 개 (수동 확인)"
        rec["dart_name"] = " / ".join(f"{x['dart_name']}({x['induty_code']})" for x in pick)
    else:
        x = pick[0]
        a = aff_map.get(x["jurir_key"], {})
        rec.update({k: x[k] for k in ("corp_code", "dart_name", "induty_code", "corp_cls", "wave")})
        rec["ftc_group"] = a.get("ftc_group")
        if x["corp_code"] in cb_map:
            c = cb_map[x["corp_code"]]
            rec["verdict"] = f"상장사, cbam에서 이미 판정 ({c['size_class']}, {c['wave_group_reviewed']})"
        elif x["wave"] != "해당":
            rec["verdict"] = f"CBAM {x['wave']} → 제외"
        elif a.get("is_large"):
            rec["verdict"] = "대기업 계열 → 제외"
        elif a.get("ftc_group"):
            rec["verdict"] = "추가 후보 (공시대상집단 소속 = 중견)"
        else:
            rec["verdict"] = "추가 후보 (매출 판정 필요)"
    rows.append(rec)
    if i % 10 == 0 or i == len(G):
        print(f"  {i}/{len(G)} 진행")

R = pd.DataFrame(rows)
print("\n[선별 결과]")
print(R["verdict"].value_counts().to_string())

add = R[R["verdict"].str.startswith("추가 후보")].sort_values("energy_tj_avg", ascending=False)
print(f"\n[추가 후보] {len(add)}곳")
print(add[["gir_name", "dart_name", "induty_code", "gir_type", "energy_tj_avg", "ftc_group", "verdict"]]
      .round(0).to_string(index=False))

multi = R[R["verdict"].str.startswith("후보 여러 개")]
if len(multi):
    print("\n[후보 여러 개]")
    print(multi[["gir_name", "dart_name", "energy_tj_avg"]].round(0).to_string(index=False))

R.to_csv(P / "step1_screen_more.csv", index=False, encoding="utf-8-sig")
print("\n[저장] data/processed/step1_screen_more.csv")