#!/usr/bin/env python3
"""지원서류 문장 자동 점검.

가운뎃점, 분량, 반복 핵심어, 동의어 반복, 반복 구절, 중복 문장, 문체 신호,
남은 자리표시자, 다른 회사명, 참고 자료(합격 자기소개서 등) 문장 차용을 검사한다.

Markdown 제목(#) 줄은 문항 질문으로 보고, 코드 블록과 HTML 주석과 함께 집계에서 뺀다. 제목 사이의 본문이 한 문항이다.
표준 라이브러리만 사용한다. 차단 항목이 하나라도 있으면 종료 코드 1을 돌려준다.

사용 예:
  python3 scripts/check_text.py 자기소개서_회사_직무_v01.md --limit 700,1000 --unit chars
  python3 scripts/check_text.py 자기소개서.md --forbid "다른회사,옛회사" --ref 합격자소서1.md
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

MIDDLE_DOTS = "\u00b7\u318d\u30fb\u2027\u2219\uff65\u22c5"  # 가운뎃점과 비슷한 점 문자들
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#]*(?:[.\-][A-Za-z0-9+#]+)*|[가-힣]+")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

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
    "이를 바탕으로/이를 통해": r"이를\s(?:바탕으로|통해)",
    "~하고자 합니다": r"고자\s?합니다",
}

CLICHES = [
    "어릴 때부터", "어렸을 때부터", "어려서부터", "누구보다", "최선을 다하", "귀사", "일원이 되",
    "밑거름", "초석", "시너지", "뼈저리게", "남다른", "끊임없이", "인재가 되겠습니다",
]

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


def split_sections(text):
    """Markdown 제목을 경계로 (제목, 본문, 시작 줄 번호) 목록을 만든다."""
    blank = lambda m: "\n" * m.group(0).count("\n")
    text = re.sub(r"<!--.*?-->", blank, text, flags=re.S)
    text = re.sub(r"^```.*?^```[^\n]*", blank, text, flags=re.S | re.M)  # 코드 블록 제외
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":  # YAML 머리말 건너뛰기
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines[: i + 1] = [""] * (i + 1)
                break
    sections, title, body, start = [], "(제목 없음)", [], 1
    for no, line in enumerate(lines, 1):
        if re.match(r"\s{0,3}#{1,6}\s", line):
            if any(b.strip() for b in body):
                sections.append((title, "\n".join(body).strip("\n"), start))
            title, body, start = line.strip().lstrip("#").strip(), [], no + 1
        else:
            body.append(line)
    if any(b.strip() for b in body):
        sections.append((title, "\n".join(body).strip("\n"), start))
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
    return [s.strip() for s in SENT_SPLIT_RE.split(text) if s and s.strip()]


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
    return re.escape(term)


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


def check(path, limits, unit, forbid, refs):
    raw = read_text(path)
    findings = []  # (등급, 위치, 내용)

    def add(level, where, msg):
        findings.append({"level": level, "where": where, "message": msg})

    for no, line in enumerate(raw.split("\n"), 1):
        for col, ch in enumerate(line, 1):
            if ch in MIDDLE_DOTS:
                add("차단", f"{no}행 {col}열", f"가운뎃점 '{ch}' 사용: {line.strip()[:60]}")
        for m in PLACEHOLDER_RE.finditer(line):
            add("차단", f"{no}행", f"자리표시자 또는 확인 표시가 남음: '{m.group(0)}'")
        for name in forbid:
            if name and name in line:
                add("차단", f"{no}행", f"금지 문자열(다른 회사명 등) '{name}' 포함")

    sections = split_sections(raw)
    lengths = []
    all_sents = []
    ref_words = [(r, eojeols(read_text(r))) for r in refs]

    for idx, (title, body, start) in enumerate(sections):
        where = f"[{idx + 1}] {title[:30]}"
        m = measure(body)
        lengths.append({"section": where, **m})
        if limits:
            lim = limits[idx] if idx < len(limits) else limits[-1]
            if m[unit] > lim:
                add("차단", where, f"분량 초과: {m[unit]} / {lim} ({unit})")

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
            add("차단", where, f"같은 문장 중복({seen[key]}): '{s[:50]}'")
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
    ap.add_argument("--limit", help="문항별 분량 제한. 쉼표로 여러 개를 주면 문항 순서대로 적용, 하나면 전체 적용")
    ap.add_argument("--unit", default="chars", choices=["chars", "nospace", "utf8", "cp949"],
                    help="chars=공백 포함, nospace=공백 제외, utf8/cp949=바이트")
    ap.add_argument("--forbid", default="", help="나오면 안 되는 문자열(다른 회사명 등), 쉼표로 구분")
    ap.add_argument("--ref", nargs="*", default=[], help="문장을 베끼면 안 되는 참고 자료(합격 자기소개서 등)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    limits = [int(x) for x in args.limit.split(",")] if args.limit else []
    forbid = [x.strip() for x in args.forbid.split(",") if x.strip()]
    reports = [check(f, limits, args.unit, forbid, args.ref) for f in args.files]

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
