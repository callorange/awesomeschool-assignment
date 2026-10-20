# 개발 규약

이 문서는 개발 절차, 검증 기준과 Git 정책의 원본입니다. 구조·기술 선택은 [아키텍처](architecture.md), 실제 실행 명령과 현재 구현 범위는 [프로젝트 README](../README.md)를 따릅니다.

## 검증과 코드 문서화

README의 명령으로 Django check, migration 변경 누락 검사, `test education`, Ruff lint·format 검사를 수행합니다. 테스트는 PostgreSQL의 별도 테스트 DB를 사용합니다. 실제 `.env`와 격리한 파일 로딩·환경 변수 우선순위·설정 오류·파싱, 실제 DB 쿼리, 관리자 로그인 화면을 확인하고, 정적 파일은 실제 개발 서버에서 별도로 확인합니다. 실패를 코드 오류와 환경 문제로 구분하며 미검증 항목을 성공으로 기록하지 않습니다.

Ruff는 Python 3.14를 대상으로 프로젝트 소유 코드만 검사합니다. 에이전트 스킬·template managed 파일과 도구 캐시는 검사·자동 수정하지 않습니다. 주석과 docstring은 프로젝트의 한국어 정책을 따르되 Django가 생성한 기존 설명은 유지합니다.

## Git Workflow

GitHub Flow의 기준 브랜치는 `main`, 작업 브랜치는 `feature/<change-name>`입니다. 계획과 구현은 같은 브랜치에서 별도 커밋으로 관리하고 검증 후 PR로 검토합니다. `feature/*`를 `main`에 병합할 때는 `git merge --no-ff <feature-branch>`로 merge commit을 남깁니다. GitHub PR에서는 `Create a merge commit`을 사용합니다. Conventional Commits의 영어 type과 한국어 제목을 사용합니다.

작업 브랜치는 `main`에서 생성하며 OpenSpec change가 있으면 해당 kebab-case 이름을 사용합니다. 확정한 계획을 먼저 커밋하고 구현·검증 결과는 별도 커밋으로 남깁니다. 커밋 type은 브랜치 접두사와 관계없이 변경 목적에 맞게 선택합니다. 병합을 확인한 뒤 작업 브랜치를 정리합니다.

이 정책만으로 commit·push·PR 생성·병합·브랜치 삭제를 자동 승인하지 않습니다. 해당 작업은 사용자의 직접 요청 또는 이미 승인된 범위에서 수행합니다.

## OpenSpec 기록

OpenSpec change 문서는 해당 변경의 제안·설계·작업 및 결정 당시의 기록입니다. 완료된 archive는 이후 공통 정책이 바뀌어도 일괄 수정하지 않습니다. 현재 공통 규약은 [문서 안내](README.md)가 연결한 주제별 문서를 따릅니다. 별도 constitution이나 custom schema는 만들지 않습니다.
