"""1단계 1-1b (C) — 비상장 후보의 매출·자산 확보
사업보고서가 있으면 API로 자동 수집, 감사보고서만 있으면 수기 입력용 목록 작성"""
from pathlib import Path
from datetime import date
import os
import re
import sys
import time

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"

load_dotenv(ROOT / ".env")
KEY = os.environ.get("DART_API_KEY", "").strip()
if not KEY:
    sys.exit("DART_API_KEY 를 찾지 못했습니다. .env 파일을 확인해 주세요.")

API = "https://opendart.fss.or.kr/api"
EOK = 100_000_000
SME_REV_LIMIT = {"24": 1800, "23": 800, "25": 1200, "20": 1200}  # cbam과 동일 (억 원)
SME_ASSET_CAP = 5_000 * EOK

HOLD = {
    "주식회사 피엔알": "대기업 추정 (포스코 계열 후보) → 제외",
    "(주)동남": "보류 (동명 회사 8곳, 업종 일치 후보 없음)",
}


def call(endpoint: str, **params) -> dict:
    r = requests.get(f"{API}/{endpoint}", params={"crtfc_key": KEY, **params}, timeout=30)
    time.sleep(0.2)
    return r.json()


def filings(corp_code: str) -> pd.DataFrame:
    """2023년 이후 정기공시(A) + 외부감사관련(F) 목록"""
    out = []
    for ty in ("A", "F"):
        j = call("list.json", corp_code=corp_code, bgn_de="20230101",
                 end_de=date.today().strftime("%Y%m%d"), pblntf_ty=ty, page_count=100)
        if j.get("status") == "000":
            out += j.get("list", [])
    return pd.DataFrame(out)


def to_num(x):
    s = re.sub(r"[^\d\-]", "", str(x))
    return float(s) if s not in ("", "-") else None


REV_NAMES = re.compile(r"^(매출액|수익\(매출액\)|영업수익|매출|수익)$")


def fin_from_api(corp_code: str, year: int):
    """사업보고서 전체 재무제표(별도)에서 매출·자산"""
    j = call("fnlttSinglAcntAll.json", corp_code=corp_code, bsns_year=str(year),
             reprt_code="11011", fs_div="OFS")
    if j.get("status") != "000":
        return None
    d = pd.DataFrame(j["list"])
    d["nm"] = d["account_nm"].astype(str).str.replace(r"\s", "", regex=True)
    rev = d[((d["account_id"] == "ifrs-full_Revenue") | d["nm"].str.match(REV_NAMES))
            & d["sj_div"].isin(["IS", "CIS"])]
    ast = d[((d["account_id"] == "ifrs-full_Assets") | (d["nm"] == "자산총계"))
            & (d["sj_div"] == "BS")]
    if rev.empty:
        return None
    r0 = rev.iloc[0]
    return {
        "fin_year": year,
        "rev_t": to_num(r0.get("thstrm_amount")),
        "rev_t1": to_num(r0.get("frmtrm_amount")),
        "rev_t2": to_num(r0.get("bfefrmtrm_amount")),
        "assets_t": to_num(ast.iloc[0]["thstrm_amount"]) if not ast.empty else None,
        "fin_source": "DART 사업보고서(API)",
    }


# ─────────────────────────────────────────────
# 대상
# ─────────────────────────────────────────────
lk = pd.read_csv(P / "step1_unlisted_lookup.csv", dtype=str)
tgt = lk[lk["verdict"].isin(["매출·자산 확인 필요 (C단계)", "후보 여러 개 (수동 확인)"])
         & ~lk["kets_name"].isin(HOLD)].copy()
tgt["corp_code"] = tgt["corp_code"].str.zfill(8)
print(f"조회 대상: {tgt['kets_code'].nunique()}개 업체, 후보 {len(tgt)}건")
for k, v in HOLD.items():
    print(f"  제외·보류: {k} — {v}")

# ─────────────────────────────────────────────
# 공시 조회 + 재무 수집
# ─────────────────────────────────────────────
rows = []
for _, t in tgt.iterrows():
    f = filings(t["corp_code"])
    biz = f[f["report_nm"].str.contains("사업보고서")] if len(f) else f
    aud = f[f["report_nm"].str.contains("감사보고서")] if len(f) else f
    rec = {
        "kets_code": t["kets_code"], "kets_name": t["kets_name"], "kets_ksic": t["kets_ksic"],
        "corp_code": t["corp_code"], "dart_name": t["dart_name"],
        "last_filing": f["rcept_dt"].max() if len(f) else "",
        "n_biz_report": len(biz), "n_audit_report": len(aud),
    }
    fin = None
    if len(biz):
        for y in (2025, 2024):
            fin = fin_from_api(t["corp_code"], y)
            if fin:
                break
    if fin:
        rec.update(fin)
    elif len(aud):
        latest = aud.sort_values("rcept_dt").iloc[-1]
        rec.update({
            "fin_source": "감사보고서 수기 입력 필요",
            "audit_report_nm": latest["report_nm"],
            "audit_rcept_dt": latest["rcept_dt"],
            "audit_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={latest['rcept_no']}",
        })
    else:
        rec["fin_source"] = "2023년 이후 공시 없음"
    rows.append(rec)

res = pd.DataFrame(rows)

# 같은 이름 후보가 여러 개면 최근 공시가 있는 쪽만 남김
res = res.sort_values(["kets_code", "last_filing"], ascending=[True, False])
res["dup_rank"] = res.groupby("kets_code").cumcount()
dropped = res[res["dup_rank"] > 0]
res = res[res["dup_rank"] == 0].drop(columns="dup_rank")
if len(dropped):
    print("\n[같은 이름 후보 중 제외한 쪽 (공시가 더 오래됨)]")
    print(dropped[["kets_name", "corp_code", "last_filing"]].to_string(index=False))

# ─────────────────────────────────────────────
# API로 받은 곳은 바로 중견 판정
# ─────────────────────────────────────────────
def judge(r):
    if r.get("fin_source") != "DART 사업보고서(API)":
        return ""
    revs = [v for v in (r.get("rev_t"), r.get("rev_t1"), r.get("rev_t2")) if pd.notna(v)]
    if not revs:
        return "판정불가"
    avg = sum(revs) / len(revs)
    limit = SME_REV_LIMIT.get(str(r["kets_ksic"])[:2])
    over_rev = limit is not None and avg > limit * EOK
    over_ast = pd.notna(r.get("assets_t")) and r["assets_t"] >= SME_ASSET_CAP
    return "중견" if (over_rev or over_ast) else "중소"


res["size_class"] = res.apply(judge, axis=1)
for c in ("rev_t", "rev_t1", "rev_t2", "assets_t"):
    if c in res:
        res[c + "_eok"] = (pd.to_numeric(res[c], errors="coerce") / EOK).round(0)

print("\n[재무 확보 방법별 업체 수]")
print(res["fin_source"].value_counts().to_string())

api_done = res[res["fin_source"] == "DART 사업보고서(API)"]
if len(api_done):
    print("\n[API로 받은 곳]")
    cols = ["kets_name", "fin_year", "rev_t_eok", "rev_t1_eok", "rev_t2_eok", "assets_t_eok", "size_class"]
    print(api_done[[c for c in cols if c in api_done]].to_string(index=False))

manual = res[res["fin_source"] == "감사보고서 수기 입력 필요"]
if len(manual):
    print("\n[감사보고서 수기 입력 필요]")
    print(manual[["kets_name", "audit_report_nm", "audit_rcept_dt"]].to_string(index=False))
    tmpl = manual[["kets_code", "kets_name", "kets_ksic", "corp_code", "dart_name",
                   "audit_report_nm", "audit_url"]].copy()
    for c in ("보고서_사업연도", "매출_당기_억", "매출_전기_억", "자산총계_당기_억", "최대주주", "메모"):
        tmpl[c] = ""
    tmpl.to_csv(P / "step1_manual_financials.csv", index=False, encoding="utf-8-sig")
    print("\n[저장] 수기 입력용: data/processed/step1_manual_financials.csv")

none = res[res["fin_source"] == "2023년 이후 공시 없음"]
if len(none):
    print("\n[2023년 이후 공시 없음]")
    print(none[["kets_name", "corp_code"]].to_string(index=False))

res.to_csv(P / "step1_unlisted_financials.csv", index=False, encoding="utf-8-sig")
print("\n[저장] data/processed/step1_unlisted_financials.csv")