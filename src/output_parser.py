# -*- coding: utf-8 -*-
"""
output_parser.py — parse the frozen text template.

Frozen template (prompt.txt):

    ERROR_LINE: <integer>
    ERROR_FAMILY: <label>
    REPAIRED_CODE_BEGIN
    <complete corrected snippet>
    REPAIRED_CODE_END

Policy, fixed before any model call:

  * A response that does not yield `REPAIRED_CODE` is a FAILURE for repair
    (intention-to-treat). It is never repaired by hand or normalised, so markdown
    fences left inside the code block make `ast.parse` fail, as they should.
  * A missing or out-of-vocabulary `ERROR_FAMILY` fails the DETECTION measure only.
    Repair is still evaluated independently, because the point of the study is to
    measure the detection-to-repair gap, not to let a diagnosis error erase the
    repair outcome.
  * Same for an invalid `ERROR_LINE`: localisation fails, repair continues.
"""

import re

FAMILIES = [
    "MISSING_COLON",
    "MISSING_COMMA",
    "MISSING_CLOSER",
    "QUOTATION",
    "BRACKET_MISMATCH",
    "KEYWORD_AS_IDENTIFIER",
    "PRINT_STATEMENT",
]

_RX_FAMILY = re.compile(r"^[ \t]*ERROR_FAMILY[ \t]*:[ \t]*(.*?)[ \t]*$",
                        re.MULTILINE | re.IGNORECASE)
_RX_LINE = re.compile(r"^[ \t]*ERROR_LINE[ \t]*:[ \t]*(.*?)[ \t]*$",
                      re.MULTILINE | re.IGNORECASE)


def _extract_code(text):
    """Return the text between the BEGIN/END markers, or None."""
    begin = text.find("REPAIRED_CODE_BEGIN")
    if begin < 0:
        return None
    start = begin + len("REPAIRED_CODE_BEGIN")
    end = text.find("REPAIRED_CODE_END", start)
    if end < 0:
        return None
    code = text[start:end]
    if code.startswith("\r\n"):
        code = code[2:]
    elif code.startswith("\n"):
        code = code[1:]
    if code.endswith("\r\n"):
        code = code[:-2]
    elif code.endswith("\n"):
        code = code[:-1]
    return code


def parse_output(text):
    """
    Returns a dict describing one raw model response. Every field is recorded so a
    later reader can see exactly which rule fired.
    """
    out = {
        "raw_length": len(text or ""),
        "family_raw": None,
        "family_value": None,
        "family_valid": False,
        "line_raw": None,
        "line_value": None,
        "line_valid": False,
        "repaired_code": None,
        "repair_available": False,
        "parse_status": "",
    }

    if not text or not text.strip():
        out["parse_status"] = "empty_response"
        return out

    m = _RX_FAMILY.search(text)
    if m:
        raw = m.group(1).strip()
        out["family_raw"] = raw
        token = raw.strip().strip(".,;:\"'`").upper()
        if token in FAMILIES:
            out["family_value"] = token
            out["family_valid"] = True
        else:
            # the model may emit the label plus a gloss; accept an exact leading token
            for fam in FAMILIES:
                if token.startswith(fam):
                    out["family_value"] = fam
                    out["family_valid"] = True
                    break

    m = _RX_LINE.search(text)
    if m:
        raw = m.group(1).strip()
        out["line_raw"] = raw
        digits = re.findall(r"\d+", raw)
        if digits:
            out["line_value"] = int(digits[0])
            out["line_valid"] = out["line_value"] >= 1

    code = _extract_code(text)
    if code is not None:
        out["repaired_code"] = code
        out["repair_available"] = True

    problems = []
    if not out["family_valid"]:
        problems.append("family")
    if not out["line_valid"]:
        problems.append("line")
    if not out["repair_available"]:
        problems.append("code")
    out["parse_status"] = "ok" if not problems else "missing_" + "_".join(problems)
    return out


if __name__ == "__main__":
    # self-test, no model and no network required
    good = ("ERROR_LINE: 3\nERROR_FAMILY: MISSING_COLON\n"
            "REPAIRED_CODE_BEGIN\nif x:\n    pass\nREPAIRED_CODE_END\n")
    print(parse_output(good))
    bad_family = ("ERROR_LINE: 2\nERROR_FAMILY: SOMETHING_ELSE\n"
                  "REPAIRED_CODE_BEGIN\nx = 1\nREPAIRED_CODE_END\n")
    print(parse_output(bad_family))
    fenced = ("ERROR_FAMILY: QUOTATION\nERROR_LINE: 1\nREPAIRED_CODE_BEGIN\n"
              "```python\nx = 'a'\n```\nREPAIRED_CODE_END\n")
    print(parse_output(fenced))
    print(parse_output("I could not determine the error."))
