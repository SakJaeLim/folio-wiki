"""Find explicit qualifications inside the policy block containing a saved sentence.

A match asks a reviewer to inspect evidence. It never chooses a new rule.
"""

import re


def plain(text):
    # Keep the visible subject/action; URL paths and Markdown reference labels
    # are not assertions about eligibility.
    text = re.sub(r"\[([^\]\n]+)\](?:\([^)\n]*\)|\[[^\]\n]*\])?", r"\1", text)
    return " ".join(text.replace("*", "").casefold().split())


# Pair context vocabulary with operative wording. Merely mentioning votes,
# applications or an exception form should not invalidate a decision.
ACTIONS = (
    (
        r"\b(?:vot(?:e|es|ers?|ing)|ballots?)\b|투표|선거권",
        r"\b(?:eligible|ineligible|allowed|permitted|entitled|prohibited) (?:to |from )vot(?:e|ing)\b|\b(?:may|can|cannot|must not) vote\b|투표(?:할|하실) 수 (?:있|없)|투표(?:가|를)? (?:가능|허용|금지)|투표권을 (?:부여|인정|제한)",
    ),
    (
        r"\b(?:apply|applications?|applicants?)\b|신청|지원\s*자격",
        r"\b(?:eligible|ineligible|allowed|permitted) to apply\b|\b(?:may|can|cannot) apply\b|신청(?:할|하실) 수 (?:있|없)|신청(?:이|을)? (?:가능|허용|금지)",
    ),
    (
        r"\b(?:submit|submission|submissions)\b|제출",
        r"\b(?:eligible|allowed|permitted) to submit\b|\b(?:may|can|cannot) submit\b|제출(?:할|하실) 수 (?:있|없)|제출(?:이|을)? (?:가능|허용|금지)",
    ),
)
SCOPE = re.compile(
    r"\b(?:all|any|every|only|except|unless|regardless|however|instead|exempt|waived|without|even if|no longer)\b|누구나|모든|모두|단[, ]|다만|예외|관계없이|무관하게|없이|않아도|제외|면제"
)
WAIVER = re.compile(
    r"\b(?:regardless of|exempt from|waiv(?:ed|er)|does not apply|no longer required|not required)\b|관계없이|무관하게|면제|적용하지 않|적용되지 않"
)
CONDITIONS = (
    r"\bcontributions?\b|기여",
    r"\bdeadlines?\b|기한|마감",
    r"\bfees?\b|수수료|참가비",
    r"\bmembership\b|회원\s*자격",
)
RULE = re.compile(
    r"\b(?:at least|at most|minimum|maximum|must|may|only|eligible|eligibility|required|requirement|deadline|no later than)\b|이상|이하|요건|자격|해야|하여야|할 수|마감|까지|필수|투표권"
)
BACK_REFERENCE = re.compile(
    r"\b(?:this|that|the above) (?:requirement|condition|threshold|rule)\b|(?:이|위|해당|앞의)\s*(?:요건|조건|기준|규정)"
)
CONTINUATION = re.compile(
    r"^(?:however\b|except(?:ion)?\b|unless\b|(?:eligibility|policy) update\s*:|다만|단[, ]|예외)"
)
BULLET = re.compile(r"^\s*(?:[*+-] |\d+[.)] )")


def qualifies(anchor, context, clause):
    rule, sentence = plain(anchor), plain(clause)
    if not RULE.search(rule):
        return False
    # A subordinate description of already-eligible people does not grant
    # eligibility (e.g. "members who are eligible to vote can order lunch").
    sentence = re.sub(
        r"\bwho (?:are|were) (?:already )?(?:in)?eligible to \w+", "", sentence
    )
    if not SCOPE.search(sentence) and not WAIVER.search(sentence):
        return False
    for waiver in WAIVER.finditer(sentence):
        target = (
            re.split(
                r"[,;:!?]|\b(?:but|because)\b", sentence[waiver.end() :], maxsplit=1
            )[0]
            if waiver[0] in ("regardless of", "exempt from")
            else re.split(r"[,;:!?]|\b(?:but|because)\b", sentence[: waiver.end()])[-1]
        )
        if BACK_REFERENCE.search(target) or any(
            re.search(key, rule) and re.search(key, target) for key in CONDITIONS
        ):
            return True
    # Where a policy explicitly names a linked audience, an unrelated
    # group's permission to perform the same action is not enough.
    audiences = [
        plain(label)
        for label in re.findall(r"\[([^]\n]+)\]", anchor)
        if re.search(
            r"\b(?:members?|voters?|applicants?|contributors?|employees?)\b|회원|신청자|직원",
            label,
            re.I,
        )
    ]
    if audiences and not any(name in sentence for name in audiences):
        return False
    explicit = [operative for subject, operative in ACTIONS if re.search(subject, rule)]
    if not explicit:
        explicit = [
            operative for subject, operative in ACTIONS if re.search(subject, context)
        ]
    return any(re.search(operative, sentence) for operative in explicit)


def following_qualifiers(item, parts, index):
    anchor = parts[index]
    intro = next(
        (
            p["quote"]
            for p in reversed(parts[:index])
            if p["quote"].rstrip().endswith(":")
        ),
        "",
    )
    context = plain(item["topic"] + " " + intro)
    result = []
    for part in parts[index + 1 :]:
        text = part["quote"]
        # A sibling list rule starts a new subject. Prose notes and line
        # breaks can move without changing which exception modifies a rule.
        if BULLET.match(text) and not CONTINUATION.match(plain(BULLET.sub("", text))):
            break
        if text.lstrip().startswith((">", "<!--", "\x60\x60\x60", "~~~")):
            break
        if qualifies(anchor["quote"], context, text):
            result.append(part)
        elif re.search(
            r"\b(?:must|required to|at least)\b|해야 (?:한다|합니다)|하여야|이상이어야",
            plain(text),
        ):
            break
    return result
