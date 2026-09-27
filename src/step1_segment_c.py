"""1단계 1-8 — 세그먼트 C(비CBAM) 규모 파악
상장: cbam 중견 확정 + CBAM 1차 비대상 + GIR 에너지 자료 있음 (정확)
비상장: GIR 법인 중 cbam 상장 목록 밖의 제조사, 대기업 계열 제외 (규모 미판정 = 최대치)"""
from pathlib import Path
import json
import os
import re
import sys
import time
import warnings
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import matplotlib.pyplot as plt
import seaborn as sns
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
P = ROOT / "data" / "processed"
CBAM = ROOT / "data" / "external" / "cbam"
FIG = ROOT / "figures"
FIG.mkdir(exist_ok=True)

sns.set_theme(style="whitegrid", font="Malgun Gothic")
plt.rcParams["axes.unicode_minus"] = False

load_dotenv(ROOT / ".env")
KEY = os.environ.get("DART_API_KEY", "").strip()
if not KEY:
    sys.exit("DART_API_KEY 를 찾지 못했습니다. .env 파일을 확인해 주세요.")

LARGE_GROUP_ASSET = 12_000_000  # 백만 원 (12조), cbam과 동일
CBAM_WAVE1 = {"241": "철강", "24212": "알루미늄", "24222": "알루미늄", "23311": "시멘트",
              "2031": "비료", "2511": "구조물", "25122": "탱크·용기", "25123": "탱크·용기",
              "25991": "탱크·용기", "25941": "볼트·너트"}
CBAM_PARTIAL = {"25942": "기타 파스너(일부)", "2591": "단조·압형(일부)"}
KSIC2 = {"10": "식료품", "11": "음료", "12": "담배", "13": "섬유", "14": "의복", "15": "가죽·신발",
         "16": "목재", "17": "펄프·종이", "18": "인쇄", "19": "코크스·석유정제", "20": "화학",
         "21": "의약", "22": "고무·플라스틱", "23": "비금속광물", "24": "1차금속", "25": "금속가공",
         "26": "전자부품·컴퓨터", "27": "의료·정밀", "28": "전기장비", "29": "기타 기계",
         "30": "자동차", "31": "기타 운송장비", "32": "가구", "33": "기타 제품", "34": "산업용 기계 수리"}
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


def ksic2(code) -> str:
    c = digits(code)
    return c[:2] if len(c) >= 2 else ""


def is_mfg(code) -> bool:
    k = ksic2(code)
    return k.isdigit() and 10 <= int(k) <= 34


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


def find_one(pattern: str) -> Path:
    hits = sorted(RAW.glob(pattern))
    if not hits:
        sys.exit(f"data/raw 에서 '{pattern}' 파일을 찾지 못했습니다.")
    return hits[-1]


# DART 회사 정보 (조회 결과 저장해서 재사용)
CACHE_F = RAW / "dart" / "company_cache.json"
cache = json.loads(CACHE_F.read_text(encoding="utf-8")) if CACHE_F.exists() else {}


def company(corp_code: str) -> dict:
    if corp_code in cache:
        return cache[corp_code]
    j = requests.get("https://opendart.fss.or.kr/api/company.json",
                     params={"crtfc_key": KEY, "corp_code": corp_code}, timeout=30).json()
    time.sleep(0.15)
    cache[corp_code] = j
    return j


def save_cache():
    CACHE_F.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


# ─────────────────────────────────────────────
# 입력
# ─────────────────────────────────────────────
girw = pd.read_csv(P / "gir_2023_2025_by_firm.csv", dtype={"name_key": str})
girw["energy_tj_avg"] = pd.to_numeric(girw["energy_tj_avg"], errors="coerce")
print(f"GIR 법인: {len(girw):,}곳")

cb = pd.read_csv(CBAM / "mfg_final_reviewed.csv", dtype=str)
cb["corp_code"] = cb["corp_code"].str.zfill(8)
cb["is_holding"] = cb["is_holding"].astype(str).str.lower() == "true"
key2cb = {}
for _, r in cb.iterrows():
    key2cb[norm_name(r["corp_name"])] = r["corp_code"]
    if pd.notna(r["kets_name"]):
        key2cb[norm_name(r["kets_name"])] = r["corp_code"]
girw["cb_corp"] = girw["name_key"].map(key2cb)

T = pd.read_csv(P / "target_firms.csv", dtype=str)
un = pd.read_csv(P / "step1_unlisted_final.csv", dtype=str)
ab_keys = (set(T["name"].map(norm_name)) | set(T["kets_name"].dropna().map(norm_name))
           | set(un["kets_name"].map(norm_name)) | set(un["dart_name"].dropna().map(norm_name)))

groups = pd.read_excel(find_one("*기업집단별*개요*.xlsx"), dtype=str)
groups["is_large"] = pd.to_numeric(groups["공정거래위원회자산총액"].str.replace(",", ""),
                                   errors="coerce") >= LARGE_GROUP_ASSET
aff = pd.read_excel(find_one("*소속회사*개요*.xlsx"), dtype=str)
aff["jurir_key"] = aff["법인등록번호"].map(digits)
aff = aff.merge(groups[["기업집단", "is_large"]], left_on="기업집단명", right_on="기업집단", how="left")
aff_map = aff.groupby("jurir_key").agg(ftc_group=("기업집단명", "first"),
                                       is_large=("is_large", "max")).to_dict("index")

# ─────────────────────────────────────────────
# 1. 상장: cbam 중견 확정 + CBAM 1차 비대상 + GIR 있음
# ─────────────────────────────────────────────
g_by_cb = (girw.dropna(subset=["cb_corp"]).groupby("cb_corp")
               .agg(energy_tj_avg=("energy_tj_avg", "max"), gir_type=("gir_type", "first"),
                    gir_industry=("gir_industry", "first")))
lc = cb[(cb["size_class"] == "중견") & ~cb["is_holding"]
        & ~cb["wave_group_reviewed"].astype(str).str.startswith("1차")]
lc = lc.merge(g_by_cb, left_on="corp_code", right_index=True, how="inner")
C_listed = pd.DataFrame({
    "source": "상장 (중견 확정)", "name": lc["corp_name"], "corp_code": lc["corp_code"],
    "induty_code": lc["induty_code"], "ksic2": lc["induty_code"].map(ksic2),
    "ftc_group": lc["ftc_group"], "cbam_wave": lc["wave_group_reviewed"],
    "gir_type": lc["gir_type"], "energy_tj_avg": lc["energy_tj_avg"],
})

ab_listed_gir = cb[(cb["size_class"] == "중견") & ~cb["is_holding"]
                   & cb["wave_group_reviewed"].astype(str).str.startswith("1차")
                   & cb["corp_code"].isin(g_by_cb.index)]
print(f"[점검] cbam 중견·1차 적용 중 GIR 있음: {len(ab_listed_gir)}곳 (1-3 결과 34곳과 같아야 함)")

# ─────────────────────────────────────────────
# 2. 비상장: cbam 상장 목록 밖 GIR 법인 → DART로 제조업 확인
# ─────────────────────────────────────────────
root = ET.parse(RAW / "dart" / "corpCode.xml").getroot()
corps = pd.DataFrame([{k: (el.findtext(k) or "").strip() for k in ("corp_code", "corp_name")}
                      for el in root.iter("list")])
corps["key"] = corps["corp_name"].map(norm_name)

rest = girw[girw["cb_corp"].isna() & ~girw["name_key"].isin(ab_keys)]
print(f"\n[비상장 조회 대상] {len(rest):,}곳 (DART 조회, 수 분 소요)")
rows = []
for i, (_, g) in enumerate(rest.iterrows(), 1):
    cands = corps[corps["key"] == g["name_key"]].head(8)
    infos = []
    for _, c in cands.iterrows():
        j = company(c["corp_code"])
        if j.get("status") == "000":
            infos.append({"corp_code": c["corp_code"], "dart_name": j.get("corp_name"),
                          "induty_code": j.get("induty_code"), "corp_cls": j.get("corp_cls"),
                          "jurir_key": digits(j.get("jurir_no"))})
    mfg = [x for x in infos if is_mfg(x["induty_code"])]
    rec = {"gir_name": g["gir_name"], "gir_type": g["gir_type"], "gir_industry": g["gir_industry"],
           "energy_tj_avg": g["energy_tj_avg"]}
    if not infos:
        rec["status"] = "DART 미매칭"
    elif not mfg:
        rec["status"] = "비제조업"
    elif len(mfg) > 1:
        rec["status"] = "동명 제조사 여러 개"
    else:
        x = mfg[0]
        a = aff_map.get(x["jurir_key"], {})
        w = ksic_match(x["induty_code"])
        rec.update({"corp_code": x["corp_code"], "dart_name": x["dart_name"],
                    "induty_code": x["induty_code"], "ksic2": ksic2(x["induty_code"]),
                    "corp_cls": x["corp_cls"], "ftc_group": a.get("ftc_group"), "cbam_wave": w})
        if x["corp_cls"] in ("Y", "K", "N"):
            rec["status"] = "상장사 (cbam 목록 밖)"
        elif a.get("is_large"):
            rec["status"] = "대기업 계열 → 제외"
        elif w == "해당":
            rec["status"] = "CBAM 업종코드 해당 → A·B 추가 검토"
        elif a.get("ftc_group"):
            rec["status"] = "C 비상장 (공시대상집단 소속 = 중견)"
        else:
            rec["status"] = "C 비상장 (규모 미판정)"
    rows.append(rec)
    if i % 100 == 0:
        save_cache()
    if i % 50 == 0 or i == len(rest):
        print(f"  {i}/{len(rest)} 진행")
save_cache()

R = pd.DataFrame(rows)
print("\n[비상장 조회 결과]")
print(R["status"].value_counts().to_string())

C_un = R[R["status"].str.startswith("C 비상장")].copy()
C_un["source"] = "비상장 (규모 미판정)"
C_un = C_un.rename(columns={"dart_name": "name"})

add_ab = R[R["status"].str.startswith("CBAM 업종코드 해당")]
if len(add_ab):
    print(f"\n[A·B 추가 검토] {len(add_ab)}곳 (GIR 업종명과 달리 업종코드상 CBAM 해당)")
    print(add_ab[["gir_name", "induty_code", "gir_industry", "energy_tj_avg"]]
          .round(0).to_string(index=False))

# ─────────────────────────────────────────────
# 3. 가설 확인
# ─────────────────────────────────────────────
M = pd.read_csv(P / "step1_gir_matched.csv", dtype=str)
M["energy_tj_avg"] = pd.to_numeric(M["energy_tj_avg"], errors="coerce")
AB = M[(M["source"] != "비상장(보류)") & M["energy_tj_avg"].notna()].copy()
AB["segment"] = "A·B (CBAM, 판정 완료)"

C_all = pd.concat([C_listed, C_un[["source", "name", "corp_code", "induty_code", "ksic2",
                                   "ftc_group", "cbam_wave", "gir_type", "energy_tj_avg"]]],
                  ignore_index=True)
C_all["segment"] = "C " + C_all["source"]


def summary(df, label, n_total=None):
    e = df["energy_tj_avg"].dropna()
    return {"세그먼트": label, "회사 수": n_total if n_total is not None else len(df),
            "에너지 자료": len(e), "에너지 중앙값(TJ)": round(e.median(), 0),
            "하위25%": round(e.quantile(0.25), 0), "상위25%": round(e.quantile(0.75), 0),
            "에너지 합계(TJ)": round(e.sum(), 0)}


H = pd.DataFrame([
    summary(AB, "A·B (CBAM, 판정 완료)", n_total=len(T)),
    summary(C_listed, "C 상장 (중견 확정)"),
    summary(C_un, "C 비상장 (규모 미판정)"),
])
print("\n[H1·H2: 회사 수와 에너지 규모]")
print(H.to_string(index=False))
print("  * A·B 회사 수는 대상 73곳 (에너지 자료는 49곳), 추가 후보 15곳은 미포함")

print("\n[H3: 세그먼트 C 업종 구성 (한국표준산업분류 대분류 2자리)]")
C_all["업종"] = C_all["ksic2"].map(KSIC2).fillna("미상")
ind = (C_all.groupby("업종")
            .agg(회사수=("name", "size"),
                 상장=("source", lambda s: (s.str.startswith("상장")).sum()),
                 에너지_중앙값TJ=("energy_tj_avg", "median"),
                 에너지_합계TJ=("energy_tj_avg", "sum"))
            .sort_values("회사수", ascending=False))
print(ind.round(0).to_string())

# ─────────────────────────────────────────────
# 4. 그래프
# ─────────────────────────────────────────────
plot = pd.concat([AB[["segment", "energy_tj_avg"]], C_all[["segment", "energy_tj_avg"]]])
fig, ax = plt.subplots(figsize=(8, 4.8))
sns.boxplot(data=plot, x="segment", y="energy_tj_avg", ax=ax, showfliers=False, color="#dddddd")
sns.stripplot(data=plot, x="segment", y="energy_tj_avg", ax=ax, size=3, alpha=0.6)
ax.set_yscale("log")
ax.set_xlabel("")
ax.set_ylabel("에너지 사용량 (TJ, 2023~2025 평균, 로그)")
ax.set_title("세그먼트별 에너지 사용량 (GIR 명세서)")
fig.tight_layout()
fig.savefig(FIG / "01_segment_energy.png", dpi=150)

C_all.to_csv(P / "step1_segment_c.csv", index=False, encoding="utf-8-sig")
R.to_csv(P / "step1_segment_c_scan.csv", index=False, encoding="utf-8-sig")
print("\n[저장] step1_segment_c.csv, step1_segment_c_scan.csv, figures/01_segment_energy.png")