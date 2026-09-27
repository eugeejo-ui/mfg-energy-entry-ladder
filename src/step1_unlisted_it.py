"""1단계 보완 — 비상장 15곳 IT 예산 추정
② 상장사(기업집단 비소속) 매출 대비 IT 투자 비율을 비상장사 매출에 적용
① 감사보고서에서 IT 관련 항목 문맥 추출 (육안 확인용)"""
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

load_dotenv(ROOT / ".env")
KEY = os.environ.get("DART_API_KEY", "").strip()
if not KEY:
    sys.exit("DART_API_KEY 를 찾지 못했습니다. .env 파일을 확인해 주세요.")
API = "https://opendart.fss.or.kr/api"


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
    p = CACHE / f"{rcept_no}.txt.gz"
    if p.exists():
        return gzip.decompress(p.read_bytes()).decode("utf-8")
    r = requests.get(f"{API}/document.xml", params={"crtfc_key": KEY, "rcept_no": rcept_no}, timeout=60)
    time.sleep(0.3)
    if r.content[:2] != b"PK":
        return None
    z = zipfile.ZipFile(io.BytesIO(r.content))
    text = " ".join(xml_to_text(z.read(n)) for n in z.namelist())
    p.write_bytes(gzip.compress(text.encode("utf-8")))
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


T = pd.read_csv(P / "step1_energy_it.csv", dtype={"corp_code": str})
T["corp_code"] = T["corp_code"].str.zfill(8)

# ─────────────────────────────────────────────
# ② 상장사 매출 대비 IT 투자 비율
# ─────────────────────────────────────────────
L = T[(T["source"] == "상장(cbam)") & T["it_spend_kisa_eok"].notna()].copy()
L["it_ratio_pct"] = L["it_spend_kisa_eok"] / L["rev_avg_eok"] * 100
L["group"] = L["ftc_group"].notna().map({True: "기업집단 소속", False: "비소속"})
print("[상장사 매출 대비 IT 투자 비율 (%)]")
print(L.groupby("group")["it_ratio_pct"]
       .describe(percentiles=[0.25, 0.5, 0.75])[["count", "25%", "50%", "75%"]]
       .round(3).to_string())

# 비상장 15곳은 모두 기업집단 비소속 → 비소속 상장사 비율을 적용
q = L.loc[L["group"] == "비소속", "it_ratio_pct"].quantile([0.25, 0.5, 0.75])
U = T[T["source"] != "상장(cbam)"].copy()
U["it_est_low"] = (U["rev_avg_eok"] * q[0.25] / 100).round(1)
U["it_est_mid"] = (U["rev_avg_eok"] * q[0.5] / 100).round(1)
U["it_est_high"] = (U["rev_avg_eok"] * q[0.75] / 100).round(1)

print(f"\n[비상장 15곳 IT 투자 추정 (억 원)] 적용 비율: 하위25% {q[0.25]:.3f}%, "
      f"중앙 {q[0.5]:.3f}%, 상위25% {q[0.75]:.3f}%")
print(U[["name", "category_final", "rev_avg_eok", "energy_tj_avg",
         "it_est_low", "it_est_mid", "it_est_high"]]
      .sort_values("energy_tj_avg", ascending=False).to_string(index=False))

# ─────────────────────────────────────────────
# ① 감사보고서 IT 관련 항목 문맥
# ─────────────────────────────────────────────
IT_PAT = r"전산비|전산유지비|전산용역비?|전산장비|전산기기|전산비품|소프트웨어|정보시스템|정보화|IT\s*(?:비용|투자)"
UNIT_PAT = r"\(\s*단위\s*[:：]\s*([^)]{1,10})\)"
rows = []
for _, u in U.iterrows():
    rno, rnm = latest_report(u["corp_code"])
    text = get_text(rno) if rno else None
    hits = []
    if text:
        for m in re.finditer(IT_PAT, text):
            ctx = text[max(0, m.start() - 30): m.end() + 90]
            if any(ctx == h["context"] for h in hits):
                continue
            units = re.findall(UNIT_PAT, text[max(0, m.start() - 3000): m.start()])
            hits.append({"name": u["name"], "report": rnm, "keyword": m.group(0),
                         "unit": units[-1].strip() if units else "?", "context": ctx})
            if len(hits) >= 6:
                break
    rows += hits or [{"name": u["name"], "report": rnm, "keyword": "(없음)", "unit": "", "context": ""}]

S = pd.DataFrame(rows)
print("\n[감사보고서 IT 관련 문장 수]")
print(S.assign(found=S["keyword"] != "(없음)").groupby("name")["found"].sum()
        .astype(int).to_string())

U.to_csv(P / "step1_unlisted_it_est.csv", index=False, encoding="utf-8-sig")
S.to_csv(P / "step1_unlisted_it_snippets.csv", index=False, encoding="utf-8-sig")
print("\n[저장] step1_unlisted_it_est.csv, step1_unlisted_it_snippets.csv")