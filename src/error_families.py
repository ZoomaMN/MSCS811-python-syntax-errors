# -*- coding: utf-8 -*-
"""
error_families.py — deterministic taxonomy for the syntax-study pipeline.

Two independent signals are derived for every natural error, and both are stored:

  1. MESSAGE family  — from the parser diagnostic regenerated under the pinned
     interpreter (Python 3.12 gives far more specific messages than the Python 3.6
     messages shipped with the corpus).
  2. EDIT family     — from the minimal character edit the human applied to turn the
     erroneous snippet into the accepted fix. This is the robust signal: it does not
     depend on how expressive the parser message happens to be.

`assign_family` prefers the MESSAGE family when it is specific, falls back to the EDIT
family otherwise, and records whether the two agree. The taxonomy is aligned with the
error families used by Aloufi & Aljuhani (2025) so results can be related to that study,
with two additions the natural corpus requires: INDENTATION and PRINT_STATEMENT.
"""

import difflib
import re

# ----------------------------------------------------------------------------- families

FAMILIES = [
    "MISSING_COLON",
    "MISSING_COMMA",
    "MISSING_CLOSER",
    "QUOTATION",
    "BRACKET_MISMATCH",
    "INDENTATION",
    "KEYWORD_AS_IDENTIFIER",
    "PRINT_STATEMENT",
    "OTHER",
]

FAMILY_NOTE = {
    "MISSING_COLON": "a ':' was absent (Aloufi & Aljuhani: MC)",
    "MISSING_COMMA": "a ',' was absent (MCo)",
    "MISSING_CLOSER": "an opening bracket was never closed (MP)",
    "QUOTATION": "a string delimiter was missing or mismatched (MQ)",
    "BRACKET_MISMATCH": "a closing bracket did not match its opener (MB)",
    "INDENTATION": "block indentation was wrong (no counterpart in the 2025 taxonomy)",
    "KEYWORD_AS_IDENTIFIER": "a reserved word was used as a name (KID)",
    "PRINT_STATEMENT": "Python-2 print statement without parentheses (no counterpart)",
    "OTHER": "no rule matched; excluded from family-level matching",
}

# Message rules, most specific first.
MESSAGE_RULES = [
    ("BRACKET_MISMATCH", re.compile(r"does not match opening (parenthesis|bracket|brace)")),
    ("PRINT_STATEMENT", re.compile(r"Missing parentheses in call to 'print'")),
    ("QUOTATION", re.compile(r"unterminated (triple-quoted )?string literal"
                             r"|EOL while scanning string literal"
                             r"|EOF while scanning triple-quoted string literal")),
    ("MISSING_CLOSER", re.compile(r"was never closed|unmatched [\)\]\}]")),
    ("MISSING_COLON", re.compile(r"expected ':'")),
    ("MISSING_COMMA", re.compile(r"forgot a comma")),
    ("INDENTATION", re.compile(r"expected an indented block|unexpected indent"
                               r"|unindent does not match|unexpected unindent"
                               r"|inconsistent use of tabs and spaces")),
]


def normalize_message(message, error_type=None):
    """Map a parser message to a family, or None when no rule is specific enough."""
    if not message:
        return None
    for family, rx in MESSAGE_RULES:
        if rx.search(message):
            return family
    return None


# ------------------------------------------------------------------------- edit analysis

OPENERS = "([{"
CLOSERS = ")]}"
MATCH = {"(": ")", "[": "]", "{": "}"}
REVERSE_MATCH = {")": "(", "]": "[", "}": "{"}
QUOTES = "'\""
KEYWORDS = {
    "False", "None", "True", "and", "as", "assert", "async", "await", "break",
    "class", "continue", "def", "del", "elif", "else", "except", "finally",
    "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
    "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
}


def _trim_common(a, b):
    """Strip the common head and tail so the sequence diff stays tiny."""
    n = min(len(a), len(b))
    head = 0
    while head < n and a[head] == b[head]:
        head += 1
    tail = 0
    while tail < (n - head) and a[len(a) - 1 - tail] == b[len(b) - 1 - tail]:
        tail += 1
    a_mid = a[head:len(a) - tail] if tail else a[head:]
    b_mid = b[head:len(b) - tail] if tail else b[head:]
    return head, a_mid, b_mid


def _line_diff(a_lines, b_lines):
    """Return (inserted_lines, deleted_lines, inserted_indexes, deleted_indexes)."""
    head, a_mid, b_mid = _trim_common(a_lines, b_lines)
    sm = difflib.SequenceMatcher(a=a_mid, b=b_mid, autojunk=True)
    ins, dele = [], []
    ins_idx, del_idx = set(), set()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            for i in range(i1, i2):
                dele.append(a_mid[i])
                del_idx.add(head + i)
        if tag in ("replace", "insert"):
            for j in range(j1, j2):
                ins.append(b_mid[j])
                ins_idx.add(head + j)
    return ins, dele, ins_idx, del_idx


def _char_delta(a_text, b_text):
    """Character multiset difference between two strings."""
    _, a_mid, b_mid = _trim_common(a_text, b_text)
    sm = difflib.SequenceMatcher(a=a_mid, b=b_mid, autojunk=True)
    added, removed = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed.append(a_mid[i1:i2])
        if tag in ("replace", "insert"):
            added.append(b_mid[j1:j2])
    return "".join(added), "".join(removed)


def classify_edit(natural, fix):
    """
    Classify the human repair action.

    Returns dict with: family, added_chars, removed_chars, edit_size,
    changed_lines, relative_line.
    """
    a = natural.splitlines()
    b = fix.splitlines()
    ins_lines, del_lines, ins_idx, del_idx = _line_diff(a, b)

    if ins_idx:
        relative_line = min(ins_idx) / max(1, len(b))
    elif del_idx:
        relative_line = min(del_idx) / max(1, len(a))
    else:
        relative_line = 0.0

    added, removed = _char_delta("\n".join(ins_lines), "\n".join(del_lines))
    edit_size = max(len(added), len(removed))

    changed = [ln for ln in ins_lines]
    left = [ln for ln in del_lines]

    # Leading-whitespace-only change -> indentation.
    def strip_indent(lines):
        return [ln.lstrip() for ln in lines]

    if left and changed and strip_indent(left) == strip_indent(changed):
        if [len(ln) - len(ln.lstrip()) for ln in left] != \
           [len(ln) - len(ln.lstrip()) for ln in changed]:
            return dict(family="INDENTATION", added_chars=added,
                        removed_chars=removed, edit_size=edit_size,
                        changed_lines=len(left), relative_line=relative_line)

    added_set = set(added)
    removed_set = set(removed)

    # Bracket-kind substitution.
    for ch in removed_set & set(CLOSERS):
        for ch2 in added_set & set(CLOSERS):
            if ch != ch2:
                return dict(family="BRACKET_MISMATCH", added_chars=added,
                            removed_chars=removed, edit_size=edit_size,
                            changed_lines=len(left), relative_line=relative_line)

    if ":" in added_set and ":" not in removed_set:
        return dict(family="MISSING_COLON", added_chars=added, removed_chars=removed,
                    edit_size=edit_size, changed_lines=len(left),
                    relative_line=relative_line)

    if any(c in added_set for c in QUOTES):
        return dict(family="QUOTATION", added_chars=added, removed_chars=removed,
                    edit_size=edit_size, changed_lines=len(left),
                    relative_line=relative_line)

    if (added_set & set(CLOSERS)) and not (added_set & set(OPENERS)):
        return dict(family="MISSING_CLOSER", added_chars=added, removed_chars=removed,
                    edit_size=edit_size, changed_lines=len(left),
                    relative_line=relative_line)

    if "," in added_set:
        return dict(family="MISSING_COMMA", added_chars=added, removed_chars=removed,
                    edit_size=edit_size, changed_lines=len(left),
                    relative_line=relative_line)

    if "print" in "\n".join(changed) and "(" in added_set:
        return dict(family="PRINT_STATEMENT", added_chars=added, removed_chars=removed,
                    edit_size=edit_size, changed_lines=len(left),
                    relative_line=relative_line)

    # Identifier renamed to or from a reserved word.
    names_added = set(re.findall(r"\b[A-Za-z_]\w*\b", " ".join(changed)))
    names_removed = set(re.findall(r"\b[A-Za-z_]\w*\b", " ".join(left)))
    if (names_added & KEYWORDS) or (names_removed & KEYWORDS):
        return dict(family="KEYWORD_AS_IDENTIFIER", added_chars=added,
                    removed_chars=removed, edit_size=edit_size,
                    changed_lines=len(left), relative_line=relative_line)

    return dict(family="OTHER", added_chars=added, removed_chars=removed,
                edit_size=edit_size, changed_lines=len(left),
                relative_line=relative_line)


def assign_family(natural, fix, regenerated_message, regenerated_type=None):
    """
    Combine both signals. Returns dict with message_family, edit_family,
    family (the one used), and family_source.
    """
    msg_family = normalize_message(regenerated_message, regenerated_type)
    edit = classify_edit(natural, fix)
    edit_family = edit["family"]

    if msg_family:
        family, source = msg_family, "message"
    elif edit_family != "OTHER":
        family, source = edit_family, "edit"
    else:
        family, source = "OTHER", "none"

    return {
        "message_family": msg_family,
        "edit_family": edit_family,
        "family": family,
        "family_source": source,
        "families_agree": (msg_family == edit_family) if msg_family else None,
        "edit_size": edit["edit_size"],
        "changed_lines": edit["changed_lines"],
        "edit_added": edit["added_chars"],
        "edit_removed": edit["removed_chars"],
        "relative_line": edit["relative_line"],
    }
