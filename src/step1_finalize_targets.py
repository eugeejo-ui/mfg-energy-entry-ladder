"""1단계 1-1b 마무리 — 비상장 32곳 판정 확정 + 대상 기업 명단(target_firms.csv) 작성"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "data" / "processed"
CBAM = ROOT / "data" / "external" / "cbam"
EOK = 100_000_000

# ─────────────────────────────────────────────
# 감사보고서에서 직접 확인한 값 (단위: 원, DART 전자공시 육안 확인, 2026-09-26)
# 3년치 값이 있는 곳은 기준선 근처라 전전기 보고서까지 확인한 경우
# ─────────────────────────────────────────────
MANUAL = [
    # (배출권 명단 업체명, 보고서, 결산일, 매출 당기, 매출 전기, 매출 전전기, 자산총계 당기, 판정, 비고)
    ("와이케이스틸(주)", "감사보고서 (2025.12)", "2025-12-31", 318459093588, 462547661923, None, 414323341885,
     "중견", "대한제강 자회사(2020년 지분 51% 인수)"),
    ("대한시멘트주식회사", "감사보고서 (2025.12)", "2025-12-31", 179042325023, 206863199979, None, 212410132781, "중견", ""),
    ("한라시멘트주식회사", "감사보고서 (2025.12)", "2025-12-31", 534324987650, 585702462566, None, 1103489056266,
     "중견", "아세아시멘트 자회사로 알려짐"),
    ("한국씨엔티(주)", "감사보고서 (2025.12)", "2025-12-31", 134534480427, 136360416860, None, 209698194049, "중견", ""),
    ("광진산업(주)", "감사보고서 (2025.12)", "2025-12-31", 22702480606, 20243728229, None, 22758247012,
     "중소", "동명 회사 2곳 중 한울회계법인 감사분"),
    ("한국제강 주식회사", "감사보고서 (2025.12)", "2025-12-31", 524468864432, 570985465192, None, 477074449981, "중견", ""),
    ("홍덕산업(주)", "감사보고서 (2025.12)", "2025-12-31", 263714140386, 302148472782, None, 882239404446, "중견", ""),
    ("디케이동신(주)", "감사보고서 (2025.12)", "2025-12-31", 231825721143, 250909647795, None, 135927105763, "중견", ""),
    ("진양특수강(주)", "감사보고서 (2025.12)", "2025-12-31", 222257979759, 234919953219, None, 128715744780, "중견", ""),
    ("고려강선(주)", "감사보고서 (2025.12)", "2025-12-31", 146109016979, 162942556936, 180466492750, 332684646000,
     "중소", "3년 평균 판정, 고려제강 계열"),
    ("일진제강(주)", "감사보고서 (2025.12)", "2025-12-31", 289692656357, 229884309095, None, 329786655785, "중견", ""),
    ("주식회사 심팩인더스트리", "감사보고서 (2025.12)", "2025-12-31", 101603942065, 74980967139, None, 166324231124, "중소", ""),
    ("노벨리스코리아 주식회사", "감사보고서 (2026.03)", "2026-03-31", 4364920434673, 3694034171308, None, 2475491049446,
     "외국계 대기업 계열", "Novelis Inc.(Hindalco) 특수목적회사 3곳이 99.999% 보유"),
    ("성훈엔지니어링주식회사", "감사보고서 (2025.12)", "2025-12-31", 140184059037, 121519280108, None, 59073119282,
     "중소", "배출권 업종 24212 기준 판정. DART 업종 23999와 불일치"),
    ("주식회사 세진메탈", "감사보고서 (2025.12)", "2025-12-31", 213857391199, 181990796051, 234589470462, 116373835349,
     "중견", "3년 평균 판정"),
    ("하이호경금속 주식회사", "감사보고서 (2025.12)", "2025-12-31", 480338813527, 416078130408, None, 110844699310, "중견", ""),
    ("울산알루미늄 주식회사", "감사보고서 (2026.03)", "2026-03-31", 1649002542742, 1364702846183, None, 1182450154127,
     "외국계 대기업 계열", "노벨리스코리아 50% + Kobe Steel 50% 합작"),
    ("한일제관(주)", "감사보고서 (2025.12)", "2025-12-31", 490002696897, 472212023188, None, 411738945538, "중견", ""),
    ("현대아이에프씨 주식회사", "감사보고서 (2025.12)", "2025-12-31", 482905176435, 527368920370, None, 567850524557,
     "중견", "2026-02-27 현대제철 지분 100% 매각(우리베일리국민성장(유)), 현대자동차 집단 이탈"),
]
man = pd.DataFrame(MANUAL, columns=["kets_name", "report", "fiscal_end", "rev_t", "rev_t1", "rev_t2",
                                    "assets_t", "verdict", "note"])
man["basis"] = "감사보고서 육안 확인"

# ─────────────────────────────────────────────
# 사후 확인으로 제외 (2026-09-26 보도·GIR 확인)
# ─────────────────────────────────────────────
EVENT_EXCLUDE = {
    "한일현대시멘트 주식회사": ("합병 소멸",
        "2025-11-01 한일시멘트에 흡수합병. 존속법인 한일시멘트는 상장 대상에 포함"),
    "주식회사 디비메탈": ("대기업 계열",
        "DB그룹 계열, DB월드와 합병 보도, 2026-06 합금철 생산 전면 중단 보도"),
}

# ─────────────────────────────────────────────
# 비상장 32곳 최종 판정
# ─────────────────────────────────────────────
lk = pd.read_csv(P / "step1_unlisted_lookup.csv", dtype=str).drop_duplicates("kets_code")
fin = pd.read_csv(P / "step1_unlisted_financials.csv", dtype=str)

api = fin[fin["fin_source"] == "DART 사업보고서(API)"][
    ["kets_name", "rev_t", "rev_t1", "rev_t2", "assets_t", "size_class"]].copy()
api = api.rename(columns={"size_class": "verdict"})
api["basis"] = "DART 사업보고서(API)"
api["note"] = ""
api.loc[api["kets_name"].str.contains("쌍용씨앤이"), "note"] = \
    "API 매출값 이상(1,116억/0원). 자산 3.8조로 매출과 무관하게 중견"

decided = pd.concat([man, api], ignore_index=True)
for c in ("rev_t", "rev_t1", "rev_t2", "assets_t"):
    decided[c] = pd.to_numeric(decided[c], errors="coerce")
decided["rev_avg_eok"] = (decided[["rev_t", "rev_t1", "rev_t2"]].mean(axis=1) / EOK).round(0)
decided["assets_eok"] = (decided["assets_t"] / EOK).round(0)

un = lk[["kets_code", "kets_name", "kets_ksic", "verdict"]].rename(columns={"verdict": "auto_verdict"})
un = un.merge(fin[["kets_code", "corp_code", "dart_name"]], on="kets_code", how="left")
un = un.merge(decided, on="kets_name", how="left")

# 자동 판정분: 상호출자제한 소속
is_large = un["auto_verdict"].astype(str).str.startswith("대기업")
un.loc[is_large, ["verdict", "basis"]] = ["대기업 계열", "공정위 소속회사 명단(법인등록번호)"]

# 수동 판정분
un.loc[un["kets_name"] == "주식회사 피엔알", ["verdict", "basis", "note"]] = \
    ["대기업 계열", "수동 판정", "동명 2곳 중 포스코 집단 소속 후보가 철강 관련"]
un.loc[un["kets_name"] == "(주)동남", ["verdict", "basis", "note"]] = \
    ["보류", "", "동명 회사 8곳, GIR상 1차 비철금속 사업장"]

# 사후 제외
for name, (v, n) in EVENT_EXCLUDE.items():
    un.loc[un["kets_name"] == name, ["verdict", "basis", "note"]] = [v, "사후 확인(보도·GIR)", n]

un = un.drop(columns="auto_verdict")
print("[비상장 32곳 최종 판정]")
print(un["verdict"].value_counts().to_string())
un.to_csv(P / "step1_unlisted_final.csv", index=False, encoding="utf-8-sig")

# ─────────────────────────────────────────────
# 대상 기업 명단 = 상장 58곳(cbam) + 비상장 중견
# ─────────────────────────────────────────────
cb = pd.read_csv(CBAM / "mfg_final_reviewed.csv", dtype=str)
it = pd.read_csv(CBAM / "it_spend_matched.csv", dtype=str)
cb["is_holding"] = cb["is_holding"].astype(str).str.lower() == "true"
listed = cb[(cb["size_class"] == "중견") & ~cb["is_holding"]
            & cb["wave_group_reviewed"].astype(str).str.startswith("1차")].copy()
listed = listed.merge(it[["stock_code", "it_spend", "it_year"]], on="stock_code", how="left")

t_listed = pd.DataFrame({
    "source": "상장(cbam)",
    "corp_code": listed["corp_code"].str.zfill(8),
    "name": listed["corp_name"],
    "kets_name": listed["kets_name"],
    "ksic": listed["induty_code"],
    "kets_member": listed["kets_member"].astype(str).str.lower() == "true",
    "ftc_group": listed["ftc_group"],
    "rev_avg_eok": (pd.to_numeric(listed["ofs_rev_3y_avg"], errors="coerce") / EOK).round(0),
    "it_spend_eok": (pd.to_numeric(listed["it_spend"], errors="coerce") / EOK).round(1),
    "note": "",
})
mid_un = un[un["verdict"] == "중견"]
t_unlisted = pd.DataFrame({
    "source": "비상장(배출권)",
    "corp_code": mid_un["corp_code"].str.zfill(8),
    "name": mid_un["dart_name"],
    "kets_name": mid_un["kets_name"],
    "ksic": mid_un["kets_ksic"],
    "kets_member": True,
    "ftc_group": None,
    "rev_avg_eok": mid_un["rev_avg_eok"],
    "it_spend_eok": None,
    "note": mid_un["note"],
})
targets = pd.concat([t_listed, t_unlisted], ignore_index=True)
targets.to_csv(P / "target_firms.csv", index=False, encoding="utf-8-sig")

print(f"\n[대상 기업] 상장 {len(t_listed)} + 비상장 {len(t_unlisted)} = {len(targets)}")
print(f"  배출권 대상: {int(targets['kets_member'].sum())}")
print(f"  IT 투자 공시값 있음: {int(targets['it_spend_eok'].notna().sum())}")
print("\n[저장] data/processed/step1_unlisted_final.csv, data/processed/target_firms.csv")