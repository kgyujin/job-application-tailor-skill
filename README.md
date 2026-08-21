# job-application-tailor-skill

![License](https://img.shields.io/github/license/kgyujin/job-application-tailor-skill)
![Last Commit](https://img.shields.io/github/last-commit/kgyujin/job-application-tailor-skill)
![Claude Code](https://img.shields.io/badge/Claude%20Code-compatible-6b46c1?logo=anthropic&logoColor=white)
![Codex](https://img.shields.io/badge/Codex-compatible-10a37f?logo=openai&logoColor=white)
![Skill Format](https://img.shields.io/badge/format-SKILL.md-blue)

채용공고를 분석해서 **이력서 · 자기소개서 · 포트폴리오**를 그 공고에 맞게
다시 써주는 에이전트 스킬입니다. Claude Code와 Codex 양쪽에서 동일한
`SKILL.md` 하나로 동작합니다.

## 이 스킬이 하는 일

1. 채용공고 원문에서 필수 자격요건 · 우대사항 · 주요 업무 · 기술 키워드를 추출합니다.
2. 기존 이력서/자소서/포트폴리오와 대조해 매칭되는 부분과 부족한 부분(gap)을 분류합니다.
3. **사실을 지어내지 않고** 기존 서류에 있는 내용만 재배열·재서술해서 공고에 맞춥니다.
4. 원본 파일은 건드리지 않고, `이력서_회사명_직무명.md`처럼 새 버전 파일로 저장합니다.
5. 매칭이 안 되는 항목(gap)은 숨기지 않고 별도로 보고합니다.

자세한 절차는 [`SKILL.md`](./SKILL.md)를, 꼼꼼한 점검이 필요할 때는
[`reference/checklist.md`](./reference/checklist.md)를 참고하세요.

## 설치

두 도구 모두 `~/도구별-홈/skills/<스킬이름>/SKILL.md` 형식을 그대로 읽는
**같은 방식**으로 동작합니다. 저장소를 클론(또는 심볼릭 링크)해 넣기만 하면 됩니다.

### Claude Code

```bash
git clone https://github.com/kgyujin/job-application-tailor-skill.git ~/.claude/skills/job-application-tailor-skill
```

Claude Code를 재시작하면 스킬 목록에 `job-application-tailor`가 자동으로
표시됩니다. 대화 중 "이 채용공고에 맞게 이력서 수정해줘"처럼 요청하면
Claude가 자동으로 이 스킬을 불러옵니다.

### Codex

**방법 1 — 네이티브 스킬 폴더 (권장)**

Codex 앱/클라이언트가 스킬 마켓플레이스(`~/.codex/skills/`)를 지원하는
버전이라면, Claude Code와 완전히 동일한 방식으로 동작합니다.

```bash
git clone https://github.com/kgyujin/job-application-tailor-skill.git ~/.codex/skills/job-application-tailor-skill
```

이후 별도 설정 없이 "이 채용공고에 맞게 서류 다듬어줘"라고 요청하면
Codex가 `SKILL.md`를 자동으로 찾아 따릅니다.

**방법 2 — 순수 codex-cli / 스킬 폴더 미지원 환경**

스킬 자동 인식 기능이 없는 codex-cli 환경이라면, 아래 중 하나로 사용합니다.

```bash
git clone https://github.com/kgyujin/job-application-tailor-skill.git ~/.codex/skills/job-application-tailor-skill
```

- 대화에서 파일을 직접 지정:

  ```text
  ~/.codex/skills/job-application-tailor-skill/SKILL.md 의 절차를 따라서
  [채용공고]에 맞게 [이력서/자소서/포트폴리오]를 수정해줘.
  ```

- 또는 `AGENTS.md`(프로젝트 루트 또는 `~/.codex/AGENTS.md`)에 한 줄 참조를
  추가해두면 이후 "이 공고에 맞춰서 서류 다듬어줘"라고만 해도 절차를 찾아 따릅니다.

  ```markdown
  ## 채용공고 맞춤형 서류 작성
  채용공고에 맞춰 이력서/자소서/포트폴리오를 수정해야 하면
  ~/.codex/skills/job-application-tailor-skill/SKILL.md 의 절차를 따른다.
  ```

## 사용 예시

```text
[채용공고 원문 붙여넣기 또는 URL]

내 이력서: ./이력서.md
내 자기소개서: ./자기소개서.md
내 포트폴리오: ./포트폴리오.md

이 공고에 맞게 위 서류들을 수정해줘.
```

스킬은 다음을 순서대로 진행합니다.

1. 공고 요구사항 요약표 제시
2. 기존 서류와의 매칭/갭 분석 제시
3. 이력서 → 자소서 → 포트폴리오 순으로 수정본 생성 (새 파일로 저장, 원본 보존)
4. 변경 포인트 요약과 사용자 확인이 필요한 항목(gap) 보고

## 핵심 원칙

- **사실 왜곡 금지**: 없는 경력·기술·수치를 만들어내지 않습니다.
- **원본 보존**: 항상 새 파일로 저장하고 원본을 덮어쓰지 않습니다.
- **정직한 gap 보고**: 매칭되지 않는 요구사항은 숨기지 않고 사용자에게 알립니다.

## 폴더 구조

```text
job-application-tailor-skill/
├── SKILL.md                 # 메인 절차 (Claude Code / Codex 공용)
├── reference/
│   └── checklist.md          # 단계별 상세 점검 목록
├── README.md
└── LICENSE
```

## 라이선스

[MIT](./LICENSE)
