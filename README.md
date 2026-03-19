# jungle_week1

크래프톤 정글 12기 Week 1 미니 프로젝트 `정품타`입니다.  
학습 시간을 기록하고, 랭킹을 비교하고, 친구와 상호작용할 수 있는 Flask 기반 웹 서비스입니다.

배포 도메인: https://jungpumta.site

## 프로젝트 개요

정품타는 공부 시간 측정 기능을 중심으로 랭킹, 친구 관리, 실시간 접속 확인, 방명록 기능을 결합한 서비스입니다.

핵심 기능:

- 회원가입 / 로그인 / 로그아웃
- 공부 시작 / 일시정지 / 종료 타이머
- 전체 랭킹 및 친구 랭킹
- 실시간 접속자 조회
- 마이페이지 / 친구 프로필
- 방명록 댓글 작성 / 삭제
- 친구 추가 / 삭제, 차단 기능

## 기술 스택

- Backend: `Python`, `Flask`, `Flask-APScheduler`
- Database: `MongoDB`
- Frontend: `Jinja2`, `HTML`, `Tailwind CSS`, `jQuery`
- Auth: `JWT`, cookie-based session flow

## 실행 방법

1. 가상환경 활성화

```powershell
.venv\Scripts\Activate.ps1
```

2. 패키지 설치

```powershell
pip install -r requirements.txt
```

3. 환경 변수 설정

```powershell
$env:MONGO_URI="mongodb://test:test@localhost:27017"
$env:DB_NAME="jungle"
$env:JWT_SECRET="dev-only-secret"
```

4. 더미 데이터 생성

```powershell
python dummy.py
```

5. 서버 실행

```powershell
python mergetest.py
```

로컬 접속 주소: `http://localhost:5000`

## 프로젝트 구조

```text
.
|-- mergetest.py
|-- dummy.py
|-- changeId.py
|-- requirements.txt
|-- templates/
|-- static/js/
|-- static/img/
```

주요 파일:

- `mergetest.py`: Flask 엔트리 파일, 인증/타이머/랭킹/친구/댓글 기능 포함
- `dummy.py`: 시연용 더미 데이터 생성 스크립트
- `changeId.py`: 사용자 ID 마이그레이션 스크립트
- `static/js/main.js`: 타이머 UI 및 세션 복원 로직
- `static/js/auth.js`: 로그인 처리 로직

## 접근 방법

구현 방향:

- 서버가 공부 시작/종료 시각과 누적 시간을 관리
- 클라이언트는 `sessionStorage`로 새로고침 이후 UI 상태를 복원
- JWT 인증에 DB 세션과 heartbeat를 결합해 로그인 상태 유지
- 랭킹, 친구, 실시간 접속 기능은 MongoDB 조회 결과를 기반으로 구성
- 매일 오전 4시 기준 초기화를 스케줄러로 처리

## 커밋 기반 트러블슈팅

### 1. 시간대와 타이머 오차

관련 커밋:

- `Update: Timer UTC`
- `Fix: Time Format Bug`

문제:

- 서버 시간과 화면 표시 시간이 어긋나거나 세션 시간이 잘못 계산되는 문제가 있었습니다.

해결:

- `Asia/Seoul` 타임존을 명시
- 시간 포맷을 통일
- 오전 4시 기준 초기화 로직을 별도 스케줄러 작업으로 분리

### 2. 새로고침 후 타이머 상태 유실

관련 커밋:

- `Update Session`
- `fixed stopwatch and resume features`
- `added auth.js and fixed stopwatch logic`

문제:

- 새로고침, 페이지 이동, 토큰 만료 상황에서 공부 중인 상태가 끊기기 쉬웠습니다.

해결:

- `sessionStorage`에 시작 시각과 누적 시간을 저장
- `heartbeat` API로 세션 상태를 확인
- `refresh token`으로 access token을 재발급
- 비정상 종료 시 서버에서 시간을 강제 정산

### 3. 사용자 식별자 불일치

관련 커밋:

- `Update: Friends Id`
- `Mod: Comment id -> Nickname`
- `Create changeId.py`
- `Update changeId.py`

문제:

- 친구 목록, 방명록, 프로필에서 ID 형식이 섞이거나 작성자 표시가 직관적이지 않았습니다.

해결:

- 사용자 ID를 `01`, `02` 형식으로 정리하는 스크립트 추가
- 댓글 작성자 닉네임 표시 반영
- 친구/차단 참조 데이터도 함께 보정

### 4. 병합 후 구조 정리

관련 커밋:

- `Merge pull request #19`
- `Mod: Delete Files`

문제:

- 병렬 개발 과정에서 중복 파일과 임시 파일이 누적되었습니다.

해결:

- 불필요한 테스트/중복 파일 삭제
- 실제 실행 기준을 `mergetest.py` 중심으로 통합

## 역할 분배

### 이시원 [@NearthYou](https://github.com/NearthYou)

- 세션/JWT 인증 흐름
- 타이머 시간 계산 및 오전 4시 리셋
- `dummy.py`, `changeId.py` 등 보조 스크립트 작성

### 이원재 [@Wish-Upon-A-Star](https://github.com/Wish-Upon-A-Star)

- 메인 화면 및 타이머 UX
- `main.js` 기반 스톱워치/재개 로직
- `index`, `result`, `realTimeUser` 화면 연동

### 염태선 [@liamyoum](https://github.com/liamyoum)

- 저장소 운영
- 로그인/회원가입/헤더 등 공통 화면 구성
- 초기 템플릿 구조와 프론트 연결

### 송영진 [@cad8798-cmd](https://github.com/cad8798-cmd)

- 친구 페이지, 친구 프로필, 마이페이지 UI
- 댓글이 포함된 프로필 화면 개선

## 개선 포인트

- `mergetest.py` 기능 분리 필요
- 테스트 코드와 배포 설정 정리 필요
- 문자 인코딩 흔적 정리 필요
- `requirements.txt`는 현재 import 기준이라 추후 버전 고정이 필요
