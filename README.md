# mfg-energy-entry-ladder (중단, 보관)

- 상태: 2026-09-29 중단. 이 레포는 읽기 전용으로 보관함
- 후속 레포: https://github.com/eugeejo-ui/carbon-data-governance-two-track

## 무엇을 했나

- 전기요금 절감을 입구로 CBAM 대상 중견 제조사에 진입하는 설계를 검토함 (계획서 v1~v6: docs/project_plan.md)
- 0단계: 전력 자료 점검 (UCI 철강 공장 15분 자료, AI허브 전남 제조업 자료)
- 1단계: CBAM 1차 업종 중견 제조사 73곳 명단, K-ETS 여부, IT 투자액, GIR 에너지 사용량, 공장 종류 판정 (docs/progress/01_target_accounts.md)

## 왜 멈췄나

- 입구로 삼은 전력 예측·설비별 계측·CBAM 데이터 층이 정부 무상 FEMS 구축 사업, 한전 무료 전력 데이터 서비스, 기존 벤더로 이미 채워져 있음
- 정부 지원 사업과 가격으로 경쟁하기 어려워 입구가 성립하지 않는다고 판단함
- 요금 엔진·예측 실험·이동 시뮬레이션(2~4단계)은 구현 전에 중단함

## 후속 레포로 가져간 것 (커밋 55524b0 기준)

- data/processed/target_firms.csv, step1_unlisted_final.csv, step1_firm_types_final.csv
- data/processed/steel_15min_clean.csv
- data/external/cbam/의 산출물 2개, data/raw/의 공개 원자료 5개

## 자료 이용 안내

- UCI Steel Industry Energy Consumption: CC BY 4.0
- AI허브 전남 전력소비패턴 데이터는 로컬에서만 처리했으며 이 레포에 포함하지 않음 (출처 문구는 docs/progress/00_setup.md)