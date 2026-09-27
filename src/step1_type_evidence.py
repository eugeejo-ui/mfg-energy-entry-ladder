"""1단계 1-4 — 대상 73곳 공장 유형 증거 추출 (주요 사업 문장, 원재료 단서, 전력비)"""
from pathlib import Path
from datetime import date
import gzip
import html
import io
import os
import re
import sys
import time
import zipfile

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "raw" / "reports"
CACHE.mkdir(parents=True, exist_ok=True)
CBAM_CACHE = Path(r"C:\cbam-mfg-data-layer-entry\data\raw\reports")

load_dotenv(ROOT / ".env")
KEY = os.environ.get("DART_API_KEY", "").strip()
if not KEY:
    sys.exit("DART_API_KEY 를 찾지 못했습니다. .env 파일을 확인해 주세요.")
API = "https://opendart.fss.or.kr/api"

# 주요 사업 문장
BIZ = r"주요\s*(?:사업|영업|제품)|영위하고|제조\s*및\s*판매|생산\s*및\s*판매|제조하여"
# 원재료 단서: 용해형 쪽 / 가공형 쪽 / 시멘트 쪽
RAW_MELT = {"고철": r"고철|철\s*스크랩|스크랩", "합금괴·잉곳 원료": r"알루미늄\s*스크랩|알루미늄\s*괴|알루미늄\s*지금",
            "망간·규소광": r"망간광|규소|페로"}
RAW_PROC = {"빌렛": r"빌렛|빌레트|billet|Billet", "슬래브": r"슬래브|슬라브", "열연코일": r"열연\s*(?:강판|코일)|핫코일",
            "선재": r"선재", "잉곳 매입": r"잉곳|합금괴"}
RAW_CEM = {"석회석": r"석회석", "유연탄": r"유연탄"}
POWER = r"전력비|동력비|전기료|전기요금|수도광열비"


def xml_to_text(raw: bytes) -> str:
    for enc in ("utf-8", "cp949"):
        try:
            s = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        s = raw.decode("utf-8", errors="ignore")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s))


def get_text(rcept_no: str):
    for base in (CACHE, CBAM_CACHE):
        p = base / f"{rcept_no}.txt.gz"
        if p.exists():
            return gzip.decompress(p.read_bytes()).decode("utf-8")
    r = requests.get(f"{API}/document.xml", params={"crtfc_key": KEY, "rcept_no": rcept_no}, timeout=60)
    time.sleep(0.3)
    if r.content[:2] != b"PK":
        return None
    z = zipfile.ZipFile(io.BytesIO(r.content))
    text = " ".join(xml_to_text(z.read(n)) for n in z.namelist())
    (CACHE / f"{rcept_no}.txt.gz").write_bytes(gzip.compress(text.encode("utf-8")))
    return text


def latest_report(corp_code: str):
    best = None
    for ty in ("A", "F"):
        j = requests.get(f"{API}/list.json", params={
            "crtfc_key": KEY, "corp_code": corp_code, "bgn_de": "20250101",
            "end_de": date.today().strftime("%Y%m%d"), "pblntf_ty": ty, "page_count": 100},
            timeout=30).json()
        time.sleep(0.2)
        for x in (j.get("list", []) if j.get("status") == "000" else []):
            nm = x["report_nm"]
            if "사업보고서" not in nm and "감사보고서" not in nm:
                continue
            pri = 0 if "사업보고서" in nm else (1 if "연결" not in nm else 2)
            k = (pri, -int(x["rcept_dt"]))
            if best is None or k < best[0]:
                best = (k, x["rcept_no"], nm)
    return (best[1], best[2]) if best else (None, None)


def sentence_at(text: str, m, before=120, after=160) -> str:
    """찾은 위치를 포함한 문장을 잘라냄 (앞쪽은 '다.' 이후, 뒤쪽은 다음 '다.'까지)"""
    s0 = max(0, m.start() - before)
    head = text[s0:m.start()]
    cut = max(head.rfind("다."), head.rfind(". "))
    start = s0 + cut + 2 if cut >= 0 else s0
    tail = text[m.end(): m.end() + after]
    end_cut = tail.find("다.")
    end = m.end() + (end_cut + 2 if end_cut >= 0 else len(tail))
    return text[start:end].strip()


def is_history(s: str) -> bool:
    """연혁 문장(연도.월 나열) 제외"""
    return len(re.findall(r"(?:19|20)\d{2}\s*[.년]\s*\d{1,2}", s)) >= 2


def find_sentences(text: str, pat: str, n: int):
    out = []
    for m in re.finditer(pat, text):
        s = sentence_at(text, m)
        if is_history(s) or any(s in o or o in s for o in out):
            continue
        out.append(s)
        if len(out) >= n:
            break
    return out


# ─────────────────────────────────────────────
# 대상
# ─────────────────────────────────────────────
T = pd.read_csv(P / "step1_firm_types.csv", dtype={"corp_code": str, "rcept_no": str})
T["corp_code"] = T["corp_code"].str.zfill(8)

rows = []
for i, (_, t) in enumerate(T.iterrows(), 1):
    rno, rnm = t.get("rcept_no"), "사업보고서 (cbam)"
    if t["source"] != "상장(cbam)" or pd.isna(rno):
        rno, rnm = latest_report(t["corp_code"])
    text = get_text(rno) if rno else None
    rec = {"corp_code": t["corp_code"], "name": t["name"], "source": t["source"],
           "ksic_used": t["ksic_used"], "type_by_code": t["type_by_code"], "report": rnm}
    if text:
        biz = find_sentences(text, BIZ, 2)
        rec["biz_sentences"] = " | ".join(biz)

        def count(d):
            return {k: len(re.findall(p, text)) for k, p in d.items()}
        melt, proc, cem = count(RAW_MELT), count(RAW_PROC), count(RAW_CEM)
        rec["raw_melt"] = ", ".join(f"{k} {v}" for k, v in melt.items() if v)
        rec["raw_proc"] = ", ".join(f"{k} {v}" for k, v in proc.items() if v)
        rec["raw_cement"] = ", ".join(f"{k} {v}" for k, v in cem.items() if v)
        top = max({**melt, **proc}.items(), key=lambda kv: kv[1])
        if top[1] > 0:
            pat = {**RAW_MELT, **RAW_PROC}[top[0]]
            s = find_sentences(text, pat, 1)
            rec["raw_sentence"] = s[0] if s else ""
        rec["power_sentences"] = " | ".join(find_sentences(text, POWER, 2))
    else:
        rec["biz_sentences"] = "(보고서 없음)"
    rows.append(rec)
    if i % 10 == 0 or i == len(T):
        print(f"  {i}/{len(T)} 진행")

E = pd.DataFrame(rows).fillna("")
E.to_csv(P / "step1_type_evidence.csv", index=False, encoding="utf-8-sig")

print("\n[요약]")
print(f"  주요 사업 문장 추출: {(E['biz_sentences'].str.len() > 0).sum()}곳")
print(f"  고철 등 용해 원료 언급: {(E['raw_melt'] != '').sum()}곳")
print(f"  빌렛 등 가공 원료 언급: {(E['raw_proc'] != '').sum()}곳")
print(f"  전력비 문장 있음: {(E['power_sentences'] != '').sum()}곳")
print("\n[저장] data/processed/step1_type_evidence.csv")