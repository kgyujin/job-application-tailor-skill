#!/usr/bin/env python3
"""지원서류 문장 자동 점검.

가운뎃점, 분량, 반복 핵심어, 동의어 반복, 반복 구절, 중복 문장, 문체 신호,
남은 자리표시자, 다른 회사명, 참고 자료(합격 자기소개서 등) 문장 차용을 검사한다.
넘겨준 파일 전체를 묶어 용어 통일(표기, 띄어쓰기, 한영 혼용, 외래어 표기, 공고 표기)도 검사한다.

Markdown 제목 줄은 집계에서 뺀다. ## 이하 제목 아래 본문이 한 문항이며(# 는 문서 제목), 본문이 빈
문항도 --limit 순서에 포함한다. YAML 머리말, HTML 주석, 코드 블록은 가운뎃점 검사 말고는 모두 뺀다. 인라인 코드와 URL은
자리표시자와 용어 검사에서 뺀다.
표준 라이브러리만 사용한다. 차단 항목이 하나라도 있으면 종료 코드 1을 돌려준다.

사용 예:
  python3 check_text.py 자기소개서_회사_직무_v01.md --limit 700,1000 --unit chars
  python3 check_text.py 자기소개서.md --forbid "다른회사,옛회사" --ref 합격자소서1.md --ref 합격자소서2.md
  python3 check_text.py 기업분석_회사_v01.md --report
  python3 check_text.py 이력서_v01.md 자기소개서_v01.md --limit 자기소개서_v01.md=700,1000 --canon "React,Node.js"
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

MIDDLE_DOTS = "\u00b7\u0387\u318d\u30fb\u2027\u2219\uff65\u22c5"  # 가운뎃점과 비슷한 점 문자들
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#]*(?:[.\-][A-Za-z0-9+#]+)*|[가-힣]+")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n\s*\n")
MASK = "\x00"  # 집계에서 뺀 영역 표시

# 하다, 되다, 시키다 활용형. 긴 것부터 맞춘다.
VERB_ENDINGS = sorted("""
하였습니다 했습니다 합니다 하였으며 했으며 하였고 했고 하였던 했던 하였다 했다 한다 하다
하면서 하도록 하려고 하려는 하기로 하는데 했지만 하지만 하며 하고 하여 해서 하던 하는
하기 하면 하게 하자 하지 한 할 함 해
되었습니다 됐습니다 됩니다 되었으며 되었고 되었다 되어 되는 되던 되고 된 될 됨
시켰습니다 시킵니다 시켰고 시켜 시키는 시킨
""".split(), key=len, reverse=True)

PARTICLES = sorted("""
으로써 으로서 에서는 에서도 에게는 으로는 으로도 이라는 이라고 에서의 이었습니다 였습니다 입니다
에서 에게 으로 까지 부터 처럼 보다 만큼 이나 이며 이고 이다 과의 와의 라는 라고 로서 로써 로는
에는 에도 와 과 을 를 이 가 은 는 의 에 로 도 만 랑
""".split(), key=len, reverse=True)

STOPWORDS = set("""
저희 제가 저의 것 수 등 및 또한 그리고 하지만 그러나 따라서 그래서 이를 이러 그러 어떠 이런 그런
통해 위해 위한 대한 대해 같은 같이 하는 했습니다 합니다 하였습니다 됩니다 되었습니다 했던 하고 하며
때문 당시 가장 매우 모든 다시 바로 이후 이전 동안 이번 해당 또 더 각 그 이 저 우리 이것 그것
""".split())

# 한 묶음 안의 항목은 같은 뜻의 다른 말이다. "만들|만든"처럼 |로 묶은 것은 한 낱말의 활용형이다.
SYNONYM_GROUPS = [
    ("개선", "향상", "증대", "제고", "고도화", "최적화"),
    ("협업", "협력", "공동 작업"),
    ("소통", "의사소통", "커뮤니케이션"),
    ("역량", "능력", "실력", "자질"),
    ("경험", "경력"),
    ("기여", "공헌", "이바지"),
    ("성장", "발전", "성숙"),
    ("노력", "힘쓰|힘썼", "애쓰|애썼"),
    ("효율", "생산성"),
    ("구축", "구현", "개발", "제작", "만들|만든"),
    ("분석", "파악", "검토", "조사"),
    ("도전", "시도"),
    ("주도", "이끌|이끈", "리드", "총괄", "주관"),
    ("책임감", "책임", "사명감"),
    ("열정", "열의", "의지"),
    ("AI", "인공지능"),
    ("고객", "사용자", "이용자", "유저", "소비자"),
    ("성과", "결과", "실적", "성취"),
    ("중요", "핵심", "필수", "중대"),
    ("다양한", "여러", "많은", "다수"),
    ("적극적", "능동적", "주도적", "자발적"),
    ("바탕", "기반", "토대", "밑거름", "발판"),
    ("통해|통하여", "거쳐"),
    ("문제", "이슈", "어려움"),
    ("해결", "극복", "해소"),
    ("목표", "목적"),
    ("배우|배운|배웠", "학습", "습득", "익히|익힌|익혔"),
    ("고민", "숙고", "고심"),
    ("향후", "앞으로", "입사 후"),
]

PHRASE_PATTERNS = {
    "~을/를 통해": r"[을를]\s?통해",
    "~할 수 있었습니다": r"수\s?있었습니다",
    "~게 되었습니다": r"게\s?되었습니다",
    "~라고 생각합니다": r"[라다]고\s?생각합니다",
    "~뿐만 아니라": r"뿐만\s?아니라",
    "A가 아니라 B 대구": r"(?:[이가]|것이)\s아니라",
    "이를 바탕으로": r"이를\s바탕으로",
    "~하고자 합니다": r"고자\s?합니다",
}

CLICHES = [
    "어릴 때부터", "어렸을 때부터", "어려서부터", "누구보다", "최선을 다하", "귀사", "일원이 되",
    "밑거름", "초석", "시너지", "뼈저리게", "남다른", "끊임없이", "인재가 되겠습니다",
]

# 동의어 묶음에서 세지 않을 더 긴 낱말(예: 여러분, 목적지, 주도적)
SYNONYM_EXCEPT_NEXT = {"여러": "분", "목적": "지", "주도": "적", "자바": "스크립트"}

# 같은 대상을 가리키는 한글, 영문, 약어 표기. 한 문서 묶음 안에서는 하나만 쓴다.
TERM_GROUPS = [
    ("AI", "인공지능"),
    ("ML", "머신러닝", "기계학습"),
    ("LLM", "대규모 언어 모델", "거대 언어 모델"),
    ("DB", "데이터베이스"),
    ("UX", "사용자 경험"),
    ("UI", "사용자 인터페이스"),
    ("QA", "품질 보증"),
    ("프론트엔드", "프런트엔드", "frontend", "front-end"),
    ("백엔드", "backend", "back-end"),
    ("React", "리액트"),
    ("JavaScript", "자바스크립트"),
    ("TypeScript", "타입스크립트"),
    ("Python", "파이썬"),
    ("Java", "자바"),
    ("Spring", "스프링"),
    ("Docker", "도커"),
    ("Kubernetes", "쿠버네티스", "k8s"),
    ("GitHub", "깃허브"),
    ("애플리케이션", "어플리케이션", "앱", "어플"),
    ("웹사이트", "웹 사이트"),
    ("콘텐츠", "컨텐츠"),
    ("메시지", "메세지"),
    ("리더십", "리더쉽"),
    ("비즈니스", "비지니스"),
    ("아키텍처", "아키텍쳐"),
    ("콘퍼런스", "컨퍼런스"),
    ("론칭", "런칭"),
]

# 국립국어원 외래어 표기와 다른 흔한 표기. 공고나 회사 공식 표기면 그대로 둔다.
NONSTANDARD = {
    "컨텐츠": "콘텐츠", "메세지": "메시지", "리더쉽": "리더십", "비지니스": "비즈니스",
    "아키텍쳐": "아키텍처", "셋팅": "세팅", "스케쥴": "스케줄", "워크샵": "워크숍", "플렛폼": "플랫폼",
    "매니져": "매니저", "쥬니어": "주니어", "어플리케이션": "애플리케이션", "데이타": "데이터",
}

# 공식 대소문자 표기
OFFICIAL = {k.lower().replace(".", "").replace("-", ""): k for k in """
GitHub GitLab JavaScript TypeScript Node.js Next.js Vue.js NestJS React Python Java Kotlin Swift
MySQL PostgreSQL MongoDB Redis Kafka Elasticsearch GraphQL Docker Kubernetes AWS GCP Azure
TensorFlow PyTorch FastAPI Django Flask Spring iOS macOS Android LinkedIn YouTube Figma Jira
Notion Slack Jenkins Terraform Linux Git HTML CSS SQL API REST JSON
""".split()}

PLACEHOLDER_RE = re.compile(
    r"\{[^}\n]*\}|TODO|TBD|\[확인[^\]]*\]|본인 확인 필요|○○|(?<![A-Za-z])(?:OO|XX)(?![A-Za-z])|\?\?\?"
)
CONNECTIVE_COMMA_RE = re.compile(r"[가-힣](?:고|며|지만|면서|아서|어서|여서|해서|는데|니까),")
JEOK_CHAIN_RE = re.compile(r"[가-힣]{2,}적\s[가-힣]")


def read_text(path):
    data = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc).replace("\r\n", "\n")
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def mask_markup(text):
    """YAML 머리말, HTML 주석, 코드 블록을 MASK로 바꾼다. 줄 번호는 유지한다."""
    def blank(m):
        return "\n".join([MASK] * (m.group(0).count("\n") + 1))

    text = re.sub(r"<!--.*?-->", blank, text, flags=re.S)
    text = re.sub(r"^[ \t]*```.*?^[ \t]*```[^\n]*", blank, text, flags=re.S | re.M)
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines[: i + 1] = [MASK] * (i + 1)
                break
    return lines


def strip_inline(line):
    """인라인 코드, URL, 링크 주소를 지운다. 자리표시자와 용어 검사에만 쓴다."""
    line = re.sub(r"`[^`]*`", " ", line)
    line = re.sub(r"\]\([^)]*\)", "]", line)
    return re.sub(r"https?://\S+", " ", line)


def split_sections(lines):
    """Markdown 제목을 경계로 (제목, 본문, 제목 여부) 목록을 만든다. 빈 문항도 남긴다."""
    sections, title, body, is_heading = [], "(제목 없음)", [], False

    def close():
        text = "\n".join(body).strip("\n")
        if is_heading or text.strip():
            sections.append((title, text, is_heading))

    for line in lines:
        if line.strip() == MASK:
            continue
        line = line.replace(MASK, "")
        m = re.match(r"\s{0,3}(#{1,6})\s", line)
        if m:
            close()
            # 문서 제목(#)은 문항이 아니다. 문항은 ## 이하 제목이다.
            title, body, is_heading = line.strip().lstrip("#").strip(), [], len(m.group(1)) >= 2
        else:
            body.append(line)
    close()
    return sections


def measure(text):
    try:
        cp949 = len(text.encode("cp949"))
    except UnicodeEncodeError:
        cp949 = sum(1 if ord(c) < 128 else 2 for c in text)
    return {
        "chars": len(text),
        "nospace": len(re.sub(r"\s", "", text)),
        "utf8": len(text.encode("utf-8")),
        "cp949": cp949,
    }


def stem(tok):
    if tok[0].isascii():
        return tok.lower()
    for end in VERB_ENDINGS + PARTICLES:
        if tok.endswith(end) and len(tok) - len(end) >= 2:
            return tok[: -len(end)]
    return tok


def key_stems(text):
    out = []
    for tok in TOKEN_RE.findall(text):
        s = stem(tok)
        if len(s) < 2 or s in STOPWORDS or s[0] in "있없않":
            continue
        out.append(s)
    return out


def sentences(text):
    return [" ".join(s.split()) for s in SENT_SPLIT_RE.split(text) if s and s.strip()]


def norm(s):
    return re.sub(r"[\s\W_]+", "", s)


def bigrams(s):
    s = norm(s)
    return {s[i : i + 2] for i in range(len(s) - 1)}


def eojeols(text):
    return [w for w in (re.sub(r"[^\w+#]", "", w) for w in text.split()) if w]


def ngrams(words, n):
    return [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]


def term_re(term):
    if term.isascii():
        return r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])"
    if term in SYNONYM_EXCEPT_NEXT:
        return re.escape(term) + "(?!" + SYNONYM_EXCEPT_NEXT[term] + ")"
    return re.escape(term)


def forbid_hits(line, name):
    """금지 문자열이 낱말로 나오면 차단, 더 긴 낱말의 일부면 재검토."""
    if " " in name or not name:
        return ["차단"] if name and name in line else []
    hits = []
    for tok in TOKEN_RE.findall(line):
        if name not in tok:
            continue
        hits.append("차단" if tok == name or stem(tok) == name else "재검토")
    return hits


def shared_runs(words, ref_words, min_len):
    """참고 자료와 연속으로 겹치는 어절 구간(min_len 이상)을 찾는다."""
    ref_set = set(ngrams(ref_words, min_len))
    runs, i = [], 0
    while i <= len(words) - min_len:
        if tuple(words[i : i + min_len]) in ref_set:
            j = i + min_len
            while j < len(words) and tuple(words[j - min_len + 1 : j + 1]) in ref_set:
                j += 1
            runs.append(" ".join(words[i:j]))
            i = j
        else:
            i += 1
    return runs


def key_of(text):
    return re.sub(r"[\s.\-_]", "", text.lower())


def term_lines(paths):
    """용어 검사용 (위치, 줄) 목록. 제목, 머리말, 주석, 코드 블록은 뺀다."""
    out = []
    for path in paths:
        for no, line in enumerate(mask_markup(read_text(path)), 1):
            if line.strip() == MASK or re.match(r"\s{0,3}#{1,6}\s", line):
                continue
            out.append((f"{Path(path).name}:{no}", strip_inline(line.replace(MASK, ""))))
    return out


def summarize(counter):
    return ", ".join(f"'{k}' {v}회" for k, v in counter.most_common())


def check_terms(paths, canon):
    findings = []

    def add(level, where, msg):
        findings.append({"level": level, "where": where, "message": msg})

    lines = term_lines(paths)
    canon_keys = {key_of(c): c for c in canon}
    canon_group = {}
    for c in canon:
        for group in TERM_GROUPS:
            if any(key_of(f) == key_of(c) for f in group):
                canon_group[group] = c

    # 영문 표기(대소문자, 점, 하이픈) 혼용과 공식 표기, 공고 표기
    forms, first_at = {}, {}
    for where, line in lines:
        for tok in TOKEN_RE.findall(line):
            if tok[0].isascii() and len(tok) >= 2:
                k = key_of(tok)
                forms.setdefault(k, Counter())[tok] += 1
                first_at.setdefault((k, tok), where)
    for k, cnt in forms.items():
        if k in canon_keys:
            wrong = {f: n for f, n in cnt.items() if f != canon_keys[k]}
            for f in wrong:
                add("차단", first_at[(k, f)], f"공고 표기 '{canon_keys[k]}'와 다름: '{f}'")
            continue
        hint = f" (공식 표기 '{OFFICIAL[k]}')" if k in OFFICIAL else ""
        if len(cnt) >= 2:
            add("차단", first_at[(k, cnt.most_common(1)[0][0])], f"표기 혼용: {summarize(cnt)}{hint}")
        elif k in OFFICIAL and OFFICIAL[k] not in cnt:
            f = next(iter(cnt))
            add("재검토", first_at[(k, f)], f"공식 표기는 '{OFFICIAL[k]}': '{f}' {cnt[f]}회")

    # 띄어쓰기 혼용(데이터 베이스 / 데이터베이스, Type Script / TypeScript)
    single = {}
    for where, line in lines:
        for tok in TOKEN_RE.findall(line):
            single.setdefault(key_of(stem(tok)), tok)
    for c in canon:
        single.setdefault(key_of(c), c)
    reported = set()
    for where, line in lines:
        toks = list(TOKEN_RE.finditer(line))
        for a, b in zip(toks, toks[1:]):
            if line[a.end():b.start()] != " ":
                continue
            joined = key_of(a.group(0) + stem(b.group(0)))
            if joined in single and joined not in reported and len(joined) >= 3:
                reported.add(joined)
                level = "차단" if joined in canon_keys else "재검토"
                add(level, where, f"띄어쓰기 혼용: '{a.group(0)} {b.group(0)}' / '{single[joined]}'")

    # 같은 대상의 한글, 영문, 약어 혼용. '사용자 경험(UX)'처럼 처음에 괄호로 병기하면
    # 앞의 풀어 쓴 말은 세지 않고 괄호 속 표기를 쓰는 것으로 본다.
    text_all = "\n".join(line for _, line in lines)
    for group in TERM_GROUPS:
        pattern = "|".join(term_re(f) for f in sorted(group, key=len, reverse=True))
        cnt, prev_end, prev_form = Counter(), -10, None
        for m in re.finditer(pattern, text_all, flags=re.I):
            form = next(f for f in group if key_of(f) == key_of(m.group(0)))
            if prev_form and prev_form != form and text_all[prev_end:m.start()].strip() == "(":
                cnt[prev_form] -= 1
            cnt[form] += 1
            prev_end, prev_form = m.end(), form
        cnt = +cnt
        if group in canon_group:
            others = {f: n for f, n in cnt.items() if f != canon_group[group]}
            if others:
                add("차단", "전체", f"공고 표기 '{canon_group[group]}'로 통일 필요: {summarize(Counter(others))}")
        elif len(cnt) >= 2:
            add("재검토", "전체", f"같은 대상을 다른 용어로 씀: {summarize(cnt)}")

    # 외래어 표기
    for where, line in lines:
        for wrong, right in NONSTANDARD.items():
            if wrong in line and key_of(wrong) not in canon_keys:
                add("재검토", where, f"외래어 표기 '{wrong}' → 표준 '{right}'(공고나 회사 공식 표기면 유지)")

    return {"file": "(용어 통일: 넘겨준 파일 전체)", "lengths": [], "findings": findings}


def check(path, limits, unit, forbid, refs, report_mode):
    raw = read_text(path)
    findings = []  # (등급, 위치, 내용)

    def add(level, where, msg):
        findings.append({"level": level, "where": where, "message": msg})

    for no, line in enumerate(raw.split("\n"), 1):
        for col, ch in enumerate(line, 1):
            if ch in MIDDLE_DOTS:
                add("차단", f"{no}행 {col}열", f"가운뎃점 U+{ord(ch):04X} 사용: {line.strip()[:60]}")
    lines = mask_markup(raw)
    for no, line in enumerate(lines, 1):
        line = line.replace(MASK, "")
        for m in PLACEHOLDER_RE.finditer(strip_inline(line)):
            add("차단", f"{no}행", f"자리표시자 또는 확인 표시가 남음: '{m.group(0)}'")
        for name in forbid:
            for level in forbid_hits(line, name):
                add(level, f"{no}행", f"금지 문자열(다른 회사명 등) '{name}' 포함")

    sections = split_sections(lines)
    has_heading = any(h for _, _, h in sections)
    lengths = []
    all_sents = []
    ref_words = [(r, eojeols(read_text(r))) for r in refs]
    q_no = 0

    for idx, (title, body, is_heading) in enumerate(sections):
        where = f"[{idx + 1}] {title[:30]}"
        m = measure(body)
        lengths.append({"section": where, **m})
        if limits and (is_heading or not has_heading):
            lim = limits[q_no] if q_no < len(limits) else limits[-1]
            q_no += 1
            if m[unit] > lim:
                add("차단", where, f"분량 초과: {m[unit]} / {lim} ({unit})")
        if not body.strip():
            continue

        stems = key_stems(body)
        for s, c in Counter(stems).most_common():
            if c >= 5:
                add("재검토", where, f"핵심어 '{s}' {c}회 (5회 이상)")
            elif c >= 3:
                add("참고", where, f"핵심어 '{s}' {c}회")

        sents = sentences(body)
        for a, b in zip(sents, sents[1:]):
            common = sorted(set(key_stems(a)) & set(key_stems(b)))
            if common:
                add("참고", where, f"인접 문장 반복: {', '.join(common)} / '{b[:40]}'")

        for group in SYNONYM_GROUPS:
            lemma = {form.lower(): member.split("|")[0] for member in group for form in member.split("|")}
            pattern = "|".join(term_re(t) for t in sorted(lemma, key=len, reverse=True))
            hits = Counter(lemma[x.lower()] for x in re.findall(pattern, body, flags=re.I))
            if len(hits) >= 2 and sum(hits.values()) >= 3:
                detail = ", ".join(f"{k} {v}" for k, v in hits.items())
                add("재검토", where, f"동의어로 감춘 반복 의심: {detail}")

        for label, pat in PHRASE_PATTERNS.items():
            c = len(re.findall(pat, body))
            if c >= 2:
                add("재검토", where, f"구절 '{label}' {c}회")
        for phrase in CLICHES:
            if phrase in body:
                add("참고", where, f"상투 표현 '{phrase}'")

        words = eojeols(body)
        for gram, c in Counter(ngrams(words, 3)).items():
            if c >= 2:
                add("재검토", where, f"같은 어절 3개 연속 반복 {c}회: '{' '.join(gram)}'")

        for mm in CONNECTIVE_COMMA_RE.finditer(body):
            add("참고", where, f"연결어미 뒤 쉼표: '{body[max(0, mm.start() - 8): mm.end()]}'")
        jeok = JEOK_CHAIN_RE.findall(body)
        if len(jeok) >= 3:
            add("참고", where, f"'~적 명사' 추상 표현 {len(jeok)}회")
        endings = [norm(s)[-4:] for s in sents if len(norm(s)) >= 4]
        run = 1
        for i in range(1, len(endings)):
            run = run + 1 if endings[i] == endings[i - 1] else 1
            if run == 4:
                add("참고", where, f"같은 종결 '{endings[i]}' 4문장 이상 연속")
        for s in sents:
            if len(s) > 150:
                add("참고", where, f"150자 넘는 문장({len(s)}자): '{s[:40]}...'")

        for ref, rw in ref_words:
            for run_text in shared_runs(words, rw, 5):
                add("차단", where, f"참고 자료 {Path(ref).name}와 5어절 이상 일치: '{run_text[:80]}'")

        all_sents += [(where, s) for s in sents if len(norm(s)) >= 8]

    seen = {}
    for where, s in all_sents:
        key = norm(s)
        if key in seen:
            add("참고" if report_mode else "차단", where, f"같은 문장 중복({seen[key]}): '{s[:50]}'")
        else:
            seen[key] = where
    for i in range(len(all_sents)):
        bi = bigrams(all_sents[i][1])
        for j in range(i + 1, len(all_sents)):
            if norm(all_sents[i][1]) == norm(all_sents[j][1]):
                continue
            bj = bigrams(all_sents[j][1])
            sim = len(bi & bj) / max(1, len(bi | bj))
            if sim >= 0.6:
                add("재검토", all_sents[j][0], f"비슷한 문장({all_sents[i][0]}, 유사도 {sim:.2f}): '{all_sents[j][1][:50]}'")

    return {"file": str(path), "lengths": lengths, "findings": findings}


def main():
    ap = argparse.ArgumentParser(description="지원서류 문장 자동 점검")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--limit", action="append", default=[],
                    help="문항별 분량 제한. 쉼표로 여러 개를 주면 문항 순서대로, 하나면 모든 문항에 적용. "
                         "'파일=700,1000'처럼 쓰면 그 파일에만 적용(파일을 여러 개 넘길 때)")
    ap.add_argument("--unit", default="chars", choices=["chars", "nospace", "utf8", "cp949"],
                    help="chars=공백 포함, nospace=공백 제외, utf8/cp949=바이트")
    ap.add_argument("--forbid", default="", help="나오면 안 되는 문자열(다른 회사명 등), 쉼표로 구분")
    ap.add_argument("--ref", action="append", default=[], help="문장을 베끼면 안 되는 참고 자료(합격 자기소개서 등). 파일마다 한 번씩")
    ap.add_argument("--report", action="store_true", help="분석 보고서 모드: 같은 문장(출처 줄 등) 중복을 참고로만 표시")
    ap.add_argument("--canon", default="", help="공고나 회사 공식 표기로 고정할 용어, 쉼표로 구분(예: React,Node.js,프론트엔드)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    limit_all, limit_by_file = [], {}
    for spec in args.limit:
        target, _, values = spec.rpartition("=")
        nums = [int(x) for x in values.split(",") if x.strip()]
        if target:
            limit_by_file[Path(target).resolve()] = nums
        else:
            limit_all = nums
    forbid = [x.strip() for x in args.forbid.split(",") if x.strip()]
    reports = [check(f, limit_by_file.get(Path(f).resolve(), limit_all), args.unit, forbid, args.ref, args.report)
               for f in args.files]
    canon = [x.strip() for x in args.canon.split(",") if x.strip()]
    reports.append(check_terms(args.files, canon))

    blocked = sum(1 for r in reports for f in r["findings"] if f["level"] == "차단")
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        for r in reports:
            print(f"# {r['file']}")
            for ln in r["lengths"]:
                print(f"  분량 {ln['section']}: 공백 포함 {ln['chars']}, 공백 제외 {ln['nospace']}, "
                      f"UTF-8 {ln['utf8']}B, CP949 {ln['cp949']}B")
            for level in ("차단", "재검토", "참고"):
                items = [f for f in r["findings"] if f["level"] == level]
                print(f"  {level} {len(items)}건")
                for f in items:
                    print(f"    - {f['where']}: {f['message']}")
        print(f"결과: {'통과' if blocked == 0 else f'차단 {blocked}건'}")
    sys.exit(1 if blocked else 0)


if __name__ == "__main__":
    main()
