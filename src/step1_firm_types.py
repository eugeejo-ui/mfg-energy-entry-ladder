"""1단계 1-4 — 대상 73곳 공장 유형 구분 (업종코드 + 보고서 원문 검색) + 야간 조업 보도·모자회사 표시"""
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
CBAM = ROOT / "data" / "external" / "cbam"
CACHE = ROOT / "data" / "raw" / "reports"
CACHE.mkdir(parents=True, exist_ok=True)
CBAM_CACHE = Path(r"C:\cbam-mfg-data-layer-entry\data\raw\reports")  # cbam에서 받아둔 사업보고서 원문

load_dotenv(ROOT / ".env")
KEY = os.environ.get("DART_API_KEY", "").strip()
if not KEY:
    sys.exit("DART_API_KEY 를 찾지 못했습니다. .env 파일을 확인해 주세요.")
API = "https://opendart.fss.or.kr/api"

# 보도로 확인된 야간·주말 조업 (6단계 표시용)
NIGHT_REPORTED = {
    "동국제강": "머니S 2024-06-06, 메트로신문 2025-10-29",
    "대한제강": "한국경제 2025-03-30, 메트로신문 2025-10-29",
    "한국철강": "한국경제 2025-03-30",
    "환영철강공업": "한국경제 2025-03-30",
}
# 기업집단 밖의 모회사·자회사 관계 (기업집단 소속은 ftc_group 열로 표시됨)
PARENT = {
    "와이케이스틸": "대한제강 자회사 (2020년 지분 51% 인수)",
    "한라시멘트": "아세아시멘트 자회사로 알려짐",
}

KW = {
    "전기로": r"전기로(?!\s*(?:인해|인한|부터|써))|전기\s*아크\s*로|EAF",
    "유도로": r"유도\s*로(?!\s*(?:인해|인한))|유도\s*용해",
    "용해로": r"용해\s*로|용해\s*설비",
    "합금철": r"합금철",
    "소성로": r"소성\s*로|킬른|[Kk]iln",
    "가열로": r"가열\s*로",
    "가공": r"압연|인발|압출|냉연|도금|조관",
}
SNIP_KEYS = ("전기로", "유도로", "용해로", "소성로")


def norm(x) -> str:
    s = str(x) if pd.notna(x) else ""
    s = re.sub(r"주식회사|㈜|\(주\)", "", s)
    return re.sub(r"\s", "", s)


def ksic_type(code) -> str:
    c = re.sub(r"\D", "", str(code or ""))
    if not c:
        return "코드 없음"
    if c.startswith("2331"):
        return "시멘트"
    if c.startswith("20"):
        return "비료·화학"
    if c.startswith("2411"):
        return "용해형(제철·제강·합금철)"
    if c.startswith("243"):
        return "용해형(주조)"
    if c.startswith("2421"):
        return "용해형(비철 제련·합금)"
    if c.startswith(("2412", "2413", "2419", "2422", "2429")):
        return "가공형"
    if c.startswith("25"):
        return "가공형(금속가공)"
    return "코드 불충분"


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
        print(f"  ! 원문 없음 {rcept_no}")
        return None
    z = zipfile.ZipFile(io.BytesIO(r.content))
    text = " ".join(xml_to_text(z.read(n)) for n in z.namelist())
    (CACHE / f"{rcept_no}.txt.gz").write_bytes(gzip.compress(text.encode("utf-8")))
    return text


def latest_report(corp_code: str):
    """비상장사: 2025년 이후 사업보고서 우선, 없으면 감사보고서(별도 우선)"""
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


# ─────────────────────────────────────────────
# 대상 + 업종코드
# ─────────────────────────────────────────────
T = pd.read_csv(P / "target_firms.csv", dtype=str)
cb = pd.read_csv(CBAM / "mfg_final_reviewed.csv", dtype=str)
cb["corp_code"] = cb["corp_code"].str.zfill(8)
T["corp_code"] = T["corp_code"].str.zfill(8)
T = T.merge(cb[["corp_code", "rcept_no", "kets_ksic"]], on="corp_code", how="left")

# 상장사: 5자리 배출권 업종코드 우선, 없으면 DART 업종코드 / 비상장: 배출권 업종코드
T["ksic_used"] = T["kets_ksic"].where(T["kets_ksic"].notna(), T["ksic"])
T.loc[T["source"] != "상장(cbam)", "ksic_used"] = T["ksic"]
T["type_by_code"] = T["ksic_used"].map(ksic_type)

# ─────────────────────────────────────────────
# 보고서 원문 검색
# ─────────────────────────────────────────────
print(f"[보고서 원문 검색] 대상 {len(T)}곳")
rows, snips = [], []
for i, (_, t) in enumerate(T.iterrows(), 1):
    rno, rnm = t.get("rcept_no"), "사업보고서 (cbam)"
    if t["source"] != "상장(cbam)" or pd.isna(rno):
        rno, rnm = latest_report(t["corp_code"])
    text = get_text(rno) if rno else None
    rec = {"corp_code": t["corp_code"], "report_used": rnm, "report_ok": text is not None}
    if text:
        for k, pat in KW.items():
            hits = list(re.finditer(pat, text))
            rec[f"kw_{k}"] = len(hits)
            if k in SNIP_KEYS:
                for m in hits[:2]:
                    snips.append({"corp_code": t["corp_code"], "name": t["name"], "keyword": k,
                                  "context": text[max(0, m.start() - 50): m.end() + 50]})
    rows.append(rec)
    if i % 10 == 0 or i == len(T):
        print(f"  {i}/{len(T)} 진행")

K = pd.DataFrame(rows)
T = T.merge(K, on="corp_code", how="left")
for k in KW:
    T[f"kw_{k}"] = pd.to_numeric(T.get(f"kw_{k}"), errors="coerce").fillna(0).astype(int)
T["report_ok"] = T["report_ok"].fillna(False).astype(bool)

melt_kw = T["kw_전기로"] + T["kw_유도로"] + T["kw_용해로"] + T["kw_합금철"]


def check(r, mk) -> str:
    ty = r["type_by_code"]
    if not r["report_ok"]:
        return "보고서 없음"
    if ty.startswith("가공형") and (r["kw_전기로"] >= 3 or r["kw_유도로"] >= 3):
        return "가공형인데 용해 설비 언급 많음 (확인)"
    if ty.startswith("용해형") and mk == 0:
        return "용해형인데 용해 설비 언급 없음 (확인)"
    if ty == "코드 불충분":
        if r["kw_전기로"] >= 3 or r["kw_합금철"] >= 3:
            return "용해형 추정 (확인)"
        if r["kw_가공"] >= 5:
            return "가공형 추정 (확인)"
        return "판단 불가 (확인)"
    return ""


T["check"] = [check(r, mk) for (_, r), mk in zip(T.iterrows(), melt_kw)]
T["night_reported"] = T["name"].map(
    lambda n: next((v for k, v in NIGHT_REPORTED.items() if k in norm(n)), ""))
T["parent_note"] = T["name"].map(
    lambda n: next((v for k, v in PARENT.items() if k in norm(n)), ""))

# GIR 에너지 참고용
G = pd.read_csv(P / "step1_gir_matched.csv", dtype=str)[["name", "energy_tj_avg"]]
T = T.merge(G, on="name", how="left")
T["energy_tj_avg"] = pd.to_numeric(T["energy_tj_avg"], errors="coerce").round(0)

# ─────────────────────────────────────────────
# 결과
# ─────────────────────────────────────────────
print("\n[업종코드 기준 유형]")
print(T["type_by_code"].value_counts().to_string())

show = ["name", "ksic_used", "type_by_code", "kw_전기로", "kw_유도로", "kw_용해로",
        "kw_합금철", "kw_소성로", "kw_가열로", "energy_tj_avg", "check"]
flag = T[T["check"] != ""]
print(f"\n[확인이 필요한 회사] {len(flag)}곳")
print(flag[show].to_string(index=False))

# 확인이 필요한 회사의 설비 단어 앞뒤 문장 (회사당 단어별 최대 2개)
S = pd.DataFrame(snips)
if len(flag) and len(S):
    print("\n[확인용 문맥]")
    for _, f in flag.iterrows():
        sub = S[S["corp_code"] == f["corp_code"]]
        print(f"\n■ {f['name']} ({f['type_by_code']}, {f['check']})")
        if sub.empty:
            print("  (설비 단어 없음)")
        for _, s in sub.iterrows():
            print(f"  [{s['keyword']}] …{s['context']}…")

print("\n[야간 조업 보도 / 모자회사 / 기업집단]")
print(T[(T["night_reported"] != "") | (T["parent_note"] != "") | T["ftc_group"].notna()]
      [["name", "ftc_group", "night_reported", "parent_note"]].to_string(index=False))

T.to_csv(P / "step1_firm_types.csv", index=False, encoding="utf-8-sig")
S.to_csv(P / "step1_firm_types_snippets.csv", index=False, encoding="utf-8-sig")
print("\n[저장] step1_firm_types.csv, step1_firm_types_snippets.csv")