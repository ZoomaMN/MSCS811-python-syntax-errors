# -*- coding: utf-8 -*-
"""
injectors.py — build a synthetic, family-matched counterpart of a natural error.

For a snippet that a human repaired (the "human fix", known to parse), each injector
applies ONE minimal edit -- or, for the print-statement family, one edit that removes a
matched pair of parentheses -- breaking parsing in a chosen error family, at a site as
close as possible to a requested relative position in the file.

Invariants enforced on every emitted injection (verified, not assumed):
    * the human fix parses
    * the injected version does NOT parse
    * the injected error, classified from its own parser diagnostic and from the edit it
      makes, belongs to the requested family

A candidate that fails any check is discarded rather than returned.

All offsets are ABSOLUTE character offsets into the source string. Token positions from
`tokenize` are (row, column) pairs and are converted with `pos_to_offset`.
"""

import ast
import io
import re
import tokenize

from error_families import assign_family

# ------------------------------------------------------------------------------- helpers

_PREFIX_RX = re.compile(r"^([rRbBuUfF]*)('''|\"\"\"|'|\")")


def line_offsets(code):
    """Absolute offset at which every line starts (index 0 == line 1)."""
    offs = [0]
    for i, ch in enumerate(code):
        if ch == "\n":
            offs.append(i + 1)
    return offs


def pos_to_offset(offs, row, col):
    """(1-based row, 0-based col) -> absolute character offset."""
    idx = row - 1
    if idx < 0:
        return 0
    if idx >= len(offs):
        return len(offs[-1:][0]) if offs else 0
    return offs[idx] + col


def tokens_of(code):
    try:
        return list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []


def parses(code):
    try:
        ast.parse(code)
        return True
    except (SyntaxError, ValueError):
        return False


def parser_message(code):
    try:
        ast.parse(code)
    except SyntaxError as e:
        return type(e).__name__, (e.msg or ""), e.lineno, e.offset
    except ValueError as e:
        return type(e).__name__, str(e), None, None
    return None, None, None, None


def _relative(line_no, total_lines):
    return (line_no - 1) / max(1, total_lines - 1)


class Patch(object):
    """A set of non-overlapping (start, end, replacement) edits plus provenance."""
    __slots__ = ("edits", "rule", "line_no")

    def __init__(self, edits, rule, line_no):
        self.edits = edits
        self.rule = rule
        self.line_no = line_no

    def apply(self, code):
        new = code
        for start, end, repl in sorted(self.edits, key=lambda e: -e[0]):
            new = new[:start] + repl + new[end:]
        return new


# ------------------------------------------------------------------------ site finders
# Each finder returns a list of Patch objects.

def sites_missing_colon(code, toks, offs):
    out = []
    for i, t in enumerate(toks):
        if t.type == tokenize.OP and t.string == ":":
            j = i + 1
            while j < len(toks) and toks[j].type in (tokenize.COMMENT, tokenize.NL):
                j += 1
            if j < len(toks) and toks[j].type == tokenize.NEWLINE:
                s = pos_to_offset(offs, t.start[0], t.start[1])
                e = pos_to_offset(offs, t.end[0], t.end[1])
                out.append(Patch([(s, e, "")], "delete a block colon", t.start[0]))
    return out


def sites_missing_comma(code, toks, offs):
    out, depth = [], 0
    for t in toks:
        if t.type == tokenize.OP:
            if t.string in "([{":
                depth += 1
            elif t.string in ")]}":
                depth -= 1
            elif t.string == "," and depth > 0:
                s = pos_to_offset(offs, t.start[0], t.start[1])
                e = pos_to_offset(offs, t.end[0], t.end[1])
                out.append(Patch([(s, e, "")], "delete a comma inside brackets",
                                 t.start[0]))
    return out


def sites_missing_closer(code, toks, offs):
    """Delete the closer of a matched pair, leaving its opener unclosed."""
    out, stack = [], []
    for t in toks:
        if t.type == tokenize.OP and t.string in "([{":
            stack.append(t)
        elif t.type == tokenize.OP and t.string in ")]}":
            if stack:
                stack.pop()
                s = pos_to_offset(offs, t.start[0], t.start[1])
                e = pos_to_offset(offs, t.end[0], t.end[1])
                out.append(Patch([(s, e, "")],
                                 "delete the '%s' that closes a bracket" % t.string,
                                 t.start[0]))
    return out


def sites_bracket_mismatch(code, toks, offs):
    swap = {")": "]", "]": "}", "}": ")"}
    out, stack = [], []
    for t in toks:
        if t.type == tokenize.OP and t.string in "([{":
            stack.append(t)
        elif t.type == tokenize.OP and t.string in ")]}":
            if stack:
                stack.pop()
                s = pos_to_offset(offs, t.start[0], t.start[1])
                e = pos_to_offset(offs, t.end[0], t.end[1])
                out.append(Patch([(s, e, swap[t.string])],
                                 "close with '%s' instead of '%s'"
                                 % (swap[t.string], t.string), t.start[0]))
    return out


def sites_quotation(code, toks, offs):
    out = []
    for t in toks:
        if t.type == tokenize.STRING:
            m = _PREFIX_RX.match(t.string)
            if not m:
                continue
            prefix, quote = m.group(1), m.group(2)
            if len(t.string) <= len(prefix) + len(quote):
                continue
            s = pos_to_offset(offs, t.start[0], t.start[1])
            e = pos_to_offset(offs, t.end[0], t.end[1])
            out.append(Patch([(s + len(prefix), s + len(prefix) + len(quote), "")],
                             "remove the opening string delimiter", t.start[0]))
            out.append(Patch([(e - len(quote), e, "")],
                             "remove the closing string delimiter", t.start[0]))
    return out


def sites_indentation(code, toks, offs):
    """Dedent the first body line of a block to column 0."""
    out = []
    lines = code.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[:1].isspace():
            continue
        j = i - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j < 0:
            continue
        if lines[j].rstrip().endswith(":"):
            indent = len(line) - len(line.lstrip())
            if indent <= 0:
                continue
            start = offs[i] if i < len(offs) else None
            if start is None:
                continue
            out.append(Patch([(start, start + indent, "")],
                             "dedent a block body to column 0", i + 1))
    return out


def sites_keyword_as_identifier(code, toks, offs):
    out = []
    for i, t in enumerate(toks):
        if t.type != tokenize.NAME:
            continue
        j = i + 1
        while j < len(toks) and toks[j].type in (tokenize.COMMENT, tokenize.NL):
            j += 1
        if j < len(toks) and toks[j].type == tokenize.OP and toks[j].string == "=":
            if t.string in ("print", "self", "cls"):
                continue
            s = pos_to_offset(offs, t.start[0], t.start[1])
            e = pos_to_offset(offs, t.end[0], t.end[1])
            out.append(Patch([(s, e, "class")],
                             "rename an assignment target to the reserved word 'class'",
                             t.start[0]))
    return out


def sites_print_statement(code, toks, offs):
    """Turn a print(...) call into the Python-2 print statement print ... ."""
    out = []
    for i, t in enumerate(toks):
        if not (t.type == tokenize.NAME and t.string == "print"):
            continue
        j = i + 1
        while j < len(toks) and toks[j].type == tokenize.NL:
            j += 1
        if j >= len(toks) or not (toks[j].type == tokenize.OP
                                  and toks[j].string == "("):
            continue
        depth, k = 0, j
        while k < len(toks):
            if toks[k].type == tokenize.OP and toks[k].string == "(":
                depth += 1
            elif toks[k].type == tokenize.OP and toks[k].string == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if k >= len(toks):
            continue
        op, cl = toks[j], toks[k]
        os_ = pos_to_offset(offs, op.start[0], op.start[1])
        oe = pos_to_offset(offs, op.end[0], op.end[1])
        cs = pos_to_offset(offs, cl.start[0], cl.start[1])
        ce = pos_to_offset(offs, cl.end[0], cl.end[1])
        out.append(Patch([(os_, oe, ""), (cs, ce, "")],
                         "drop both parentheses of a print call", t.start[0]))
    return out


SITE_FINDERS = {
    "MISSING_COLON": sites_missing_colon,
    "MISSING_COMMA": sites_missing_comma,
    "MISSING_CLOSER": sites_missing_closer,
    "BRACKET_MISMATCH": sites_bracket_mismatch,
    "QUOTATION": sites_quotation,
    "INDENTATION": sites_indentation,
    "KEYWORD_AS_IDENTIFIER": sites_keyword_as_identifier,
    "PRINT_STATEMENT": sites_print_statement,
}


# ----------------------------------------------------------------------------- injector

def inject(fix_code, family, target_rel=0.5, max_tries=40, avoid_code=None):
    """
    Try to break `fix_code` in `family`, as close as possible to `target_rel`
    (0.0 = top of file, 1.0 = bottom).

    `avoid_code` is the natural erroneous snippet of the same pair. Any candidate whose
    result equals it is rejected: such a pair would present the SAME string to both arms,
    so its paired difference is zero by construction and it carries no information. This
    matters because the closest candidate to the natural error's own position is usually
    the natural error's own site.

    Returns a dict describing a verified injection, or None.
    """
    finder = SITE_FINDERS.get(family)
    if finder is None:
        return None
    if not parses(fix_code):
        return None

    toks = tokens_of(fix_code)
    if not toks:
        return None
    offs = line_offsets(fix_code)

    patches = finder(fix_code, toks, offs)
    if not patches:
        return None

    total = fix_code.count("\n") + 1
    patches.sort(key=lambda p: abs(_relative(p.line_no, total) - target_rel))

    tried = 0
    for p in patches:
        if tried >= max_tries:
            break
        tried += 1
        try:
            new_code = p.apply(fix_code)
        except Exception:
            continue
        if new_code == fix_code or parses(new_code):
            continue
        if avoid_code is not None and new_code == avoid_code:
            continue

        etype, emsg, eline, eoff = parser_message(new_code)
        info = assign_family(new_code, fix_code, emsg, etype)
        if info["family"] != family:
            continue

        removed = "".join(fix_code[s:e] for s, e, _ in p.edits)
        added = "".join(r for _, _, r in p.edits)
        return {
            "synthetic_code": new_code,
            "injection_rule": p.rule,
            "injected_line": (eline if eline else p.line_no),
            "site_line": p.line_no,
            "synthetic_error_type": etype,
            "synthetic_error_message": emsg,
            "synthetic_family": info["family"],
            "synthetic_family_source": info["family_source"],
            "edit_size": max(len(removed), len(added)),
            "edit_removed": removed,
            "edit_added": added,
            "relative_position": _relative(eline if eline else p.line_no,
                                           new_code.count("\n") + 1),
        }
    return None
