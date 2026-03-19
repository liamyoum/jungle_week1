# jungle_week1

Krafton Jungle 12기 Week 1 미니 프로젝트 `정품타`의 README입니다.  
이 문서는 현재 코드베이스 구조와 `git` 커밋 히스토리를 함께 분석해 정리했습니다.

## 1. 프로젝트 소개

`정품타`는 학습 시간을 측정하고, 사용자 간 랭킹을 비교하고, 친구와 상호작용할 수 있도록 만든 웹 서비스입니다.

- 학습 시작/일시정지/종료 타이머 제공
- 전체 랭킹 및 친구 랭킹 확인
- 실시간 접속자 확인
- 마이페이지/친구 프로필 조회
- 친구 추가 및 차단 기능
- 방명록(댓글) 작성/삭제
- JWT + 세션 기반 로그인 유지

접속 가능 도메인: `https://jungpumta.site`

## 2. 주요 기능

### 인증

- 회원가입, 로그인, 로그아웃
- `access token` + `refresh token` 쿠키 기반 인증
- heartbeat로 세션 활성 상태 주기적 갱신
- 중복 로그인/세션 만료 시 강제 로그아웃 처리

### 학습 타이머

- 학습 시작 시 서버 기준 시작 시각 기록
- 일시정지 시 세션 시간 누적
- 종료 시 전체 공부 시간과 이번 세션 시간 반영
- 새로고침 이후에도 `sessionStorage`를 이용해 화면 상태 복원
- 매일 오전 4시 기준으로 일일 기록 초기화

### 커뮤니티

- 전체 리더보드 TOP 30
- 친구 목록 및 친구 프로필 조회
- 실시간 접속 중인 사용자 조회
- 방명록 댓글 작성/삭제
- 차단 목록 관리

## 3. 기술 스택

- Backend: `Python`, `Flask`, `APScheduler`
- Database: `MongoDB`
- Frontend: `Jinja2`, `HTML`, `Tailwind CSS`, `jQuery`
- Auth: `JWT`, `Werkzeug Password Hash`
- Deploy domain: `jungpumta.site`

## 4. 프로젝트 구조

```text
.
|-- mergetest.py          # 현재 메인 Flask 애플리케이션
|-- dummy.py              # 더미 데이터 생성 스크립트
|-- changeId.py           # 사용자 ID 마이그레이션 스크립트
|-- templates/            # Jinja2 템플릿
|-- static/js/            # 프론트엔드 로직
|-- static/img/           # 배경 이미지 등 정적 리소스
```

핵심 파일 설명:

- `mergetest.py`: 라우팅, 인증, 타이머, 랭킹, 친구/댓글 기능, 스케줄러를 한 곳에서 관리
- `static/js/main.js`: 타이머 시작/일시정지/종료, 복원 로직 담당
- `static/js/auth.js`: 로그인 처리 담당
- `dummy.py`: 초기 시연용 사용자/댓글/친구/명언 데이터 생성
- `changeId.py`: 기존 사용자 ID를 `01`, `02` 형식으로 변환하는 보정 스크립트

## 5. 접근 방법

커밋 흐름과 브랜치 구성을 보면 이 프로젝트는 기능 단위로 빠르게 구현한 뒤 `main`에 병합하면서 안정화한 방식으로 진행됐습니다.

### 개발 흐름

- 초기에는 `front`, `back` 브랜치 중심으로 화면과 서버 기능을 병렬 개발
- 이후 `main` 기준으로 병합하며 라우트, 세션, 타이머 로직을 통합
- 중간에 사용하지 않는 파일(`app.py`, `mtest.py`, `test.py`)을 정리하고 `mergetest.py` 중심 구조로 수렴
- 더미 데이터 생성기와 ID 마이그레이션 스크립트를 추가해 시연성과 데이터 정합성을 보완

### 구현 관점

- 서버가 공부 시작/종료 시각과 누적 시간을 관리
- 클라이언트는 `sessionStorage`로 현재 타이머 UI 상태를 유지
- 인증은 JWT를 쓰되, 단순 토큰 저장이 아니라 DB 세션과 heartbeat를 함께 사용
- 리더보드/친구/실시간 접속 기능은 MongoDB 조회 결과를 필터링해 구성
- 오전 4시 리셋 규칙을 별도 스케줄러 작업으로 처리

## 6. 커밋 내역으로 본 트러블슈팅

커밋 메시지 기준으로 실제로 많이 다뤘던 문제는 아래 네 가지였습니다.

### 1. 시간대 및 타이머 오차 문제

관련 커밋:

- `Update: Timer UTC`
- `Fix: Time Format Bug`

문제:

- 서버 시간과 클라이언트 표시 시간이 어긋나거나
- 타이머 종료 후 세션 시간이 비정상적으로 계산되는 이슈가 있었음

해결:

- `Asia/Seoul` 기준 타임존을 명시
- 포맷 문자열을 통일해 시작/종료 시간을 같은 기준으로 계산
- 오전 4시 기준 일일 누적 리셋 로직을 별도로 분리

### 2. 새로고침/재접속 시 타이머 상태 유실

관련 커밋:

- `Update Session`
- `fixed stopwatch and resume features`
- `added auth.js and fixed stopwatch logic`

문제:

- 새로고침, 페이지 이동, 토큰 만료 상황에서 사용자가 공부 중이던 상태가 끊기기 쉬웠음

해결:

- `sessionStorage`에 시작 시각과 누적 시간을 저장
- `heartbeat` API로 세션 유효성 주기적 확인
- `refresh token`으로 access token을 재발급
- 세션이 비정상 종료되면 서버에서 강제 정산 처리

### 3. 친구/댓글의 식별자 불일치

관련 커밋:

- `Update: Friends Id`
- `Mod: Comment id -> Nickname`
- `Create changeId.py`
- `Update changeId.py`

문제:

- 사용자 식별자 형식이 혼재되어 친구 목록, 방명록, 프로필 표시에서 혼선이 발생
- 댓글 작성자 표시가 ID 중심이라 가독성이 떨어졌음

해결:

- 사용자 ID를 `01`, `02` 형태로 일괄 정리하는 마이그레이션 스크립트 작성
- 댓글/프로필 화면에서 작성자 닉네임을 함께 매핑해 표시
- 친구 및 차단 목록 참조 데이터도 함께 정리

### 4. 병합 과정에서의 구조 정리

관련 커밋:

- `Merge pull request #19 ...`
- `Mod: Delete Files`

문제:

- 병렬 작업 중 임시 파일과 중복 엔트리 파일이 누적되어 유지보수성이 떨어졌음

해결:

- 사용하지 않는 테스트 파일과 중복 앱 파일 제거
- 실제 서비스 기준 엔트리 포인트를 `mergetest.py`로 집중
- 브랜치 병합 후 템플릿과 API 연결 상태를 다시 정리

## 7. 역할 분배

정확한 공식 역할표는 저장소에 없어서, 아래 내용은 커밋 작성자와 수정 파일을 기준으로 정리한 추정 역할 분배입니다.

### 시원

- 백엔드 핵심 로직 주도
- 세션/JWT 인증 흐름 정리
- 타이머 시간 계산, 오전 4시 리셋, 실시간 사용자 관련 로직 보완
- `dummy.py`, `changeId.py` 등 운영/시연 보조 스크립트 작성

### Wish-Upon-A-Star

- 메인 페이지와 타이머 UX 개선
- `main.js` 기반 스톱워치 및 재개 로직 강화
- `index`, `result`, `realTimeUser` 등 주요 화면과 서버 연동

### liamyoum

- 저장소 운영 및 화면 전반 구성
- 로그인/회원가입/헤더/기본 레이아웃 정리
- 초기 템플릿 구조와 프론트 연결 작업 진행

### cad8798-cmd

- 친구 페이지, 친구 프로필, 마이페이지 중심 UI 작업
- 댓글 기능이 보이는 프로필 화면과 관련 템플릿 개선

## 8. 로컬 실행 방법

### 1. 가상환경 활성화

```powershell
.venv\Scripts\Activate.ps1
```

### 2. 필요한 패키지 설치

저장소에 `requirements.txt`는 없으므로 현재 코드 import 기준으로 직접 설치해야 합니다.

```powershell
pip install flask pymongo flask-apscheduler pyjwt werkzeug pytz
```

### 3. MongoDB 환경 변수 설정

기본값:

```powershell
$env:MONGO_URI="mongodb://test:test@localhost:27017"
$env:DB_NAME="jungle"
$env:JWT_SECRET="dev-only-secret"
```

### 4. 더미 데이터 생성

```powershell
python dummy.py
```

### 5. 서버 실행

```powershell
python mergetest.py
```

브라우저에서 `http://localhost:5000`으로 접속할 수 있습니다.

## 9. 아쉬운 점과 개선 포인트

- `requirements.txt` 및 배포 설정 파일 부재
- 한 파일(`mergetest.py`)에 기능이 집중되어 있어 모듈 분리가 필요
- 테스트 코드가 현재 정리된 상태라 회귀 검증 체계가 약함
- 일부 문자열 인코딩 흔적이 남아 있어 문자셋 정리가 필요

## 10. 요약

`정품타`는 공부 시간 측정과 랭킹, 친구 상호작용을 결합한 Flask 기반 웹 프로젝트입니다.  
커밋 히스토리를 보면 단순 기능 구현보다도 시간 계산 정확성, 세션 유지, 데이터 식별자 정합성, 브랜치 병합 안정화에 많은 공을 들인 프로젝트라는 점이 분명하게 드러납니다.
