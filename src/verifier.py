"""Conservative isolated-repair verification of an erroneous snippet against its reference."""

import ast
import difflib
import io
import keyword
import tokenize
import warnings


def parse_error(code):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)
        try:
            ast.parse(code)
        except (SyntaxError, ValueError) as exc:
            return str(exc)
    return None


def tokens(code):
    result = []
    ignored = {tokenize.ENCODING, tokenize.ENDMARKER, tokenize.NEWLINE,
               tokenize.NL, tokenize.COMMENT}
    try:
        for token in tokenize.generate_tokens(io.StringIO(code).readline):
            if token.type not in ignored and not (
                token.type == tokenize.ERRORTOKEN and token.string.isspace()
            ):
                value = '' if token.type in {tokenize.INDENT, tokenize.DEDENT} else token.string
                result.append((token.type, value))
    except tokenize.TokenError as exc:
        if exc.args[0] not in {'EOF in multi-line statement', 'unexpected EOF in multi-line statement'}:
            return None
    except (IndentationError, SyntaxError):
        return None
    return result


def edits(before, after):
    return [(tag, before[i:j], after[k:l])
            for tag, i, j, k, l in difflib.SequenceMatcher(
                a=before, b=after, autojunk=False).get_opcodes() if tag != 'equal']


def verify(error_code, reference):
    """Return verified family and evidence, or None with an inconclusive reason."""
    if parse_error(reference) is not None:
        return None, 'reference_does_not_parse'
    message = parse_error(error_code)
    if message is None:
        return None, 'erroneous_snippet_parses'

    changes = edits(error_code, reference)
    changed_chars = ''.join(old + new for _, old, new in changes)
    significant = ''.join(c for c in changed_chars if not c.isspace())
    indentation = lambda code: [line[:len(line) - len(line.lstrip(' \t'))]
                                for line in code.splitlines()]
    if significant and set(significant) <= set('\'"') and (
        'string literal' in message or 'string literal' in message.lower()
    ) and indentation(error_code) == indentation(reference):
        return 'QUOTATION', 'quote_only_repair_and_string_diagnostic'

    before, after = tokens(error_code), tokens(reference)
    if before is None or after is None:
        return None, 'incomplete_tokenization'
    delta = edits(before, after)
    if len(delta) == 1:
        tag, old, new = delta[0]
        if tag == 'insert' and len(new) == 1 and new[0][0] == tokenize.OP:
            family = {':': 'MISSING_COLON', ',': 'MISSING_COMMA',
                      ')': 'MISSING_CLOSER', ']': 'MISSING_CLOSER',
                      '}': 'MISSING_CLOSER'}.get(new[0][1])
            if family:
                return family, 'single_token_inserted_by_reference_repair'
        if tag == 'replace' and len(old) == len(new) == 1:
            if old[0][0] == new[0][0] == tokenize.OP and (
                old[0][1] in ')]}' and new[0][1] in ')]}'
            ):
                return 'BRACKET_MISMATCH', 'single_closing_delimiter_replaced'
            if old[0][0] == new[0][0] == tokenize.NAME and (
                keyword.iskeyword(old[0][1]) and
                new[0][1].isidentifier() and not keyword.iskeyword(new[0][1])
            ):
                return 'KEYWORD_AS_IDENTIFIER', 'keyword_token_replaced_with_identifier'

    if "Missing parentheses in call to 'print'" in message:
        # Require exactly the insertion of one matched pair around print arguments.
        if len(delta) == 2 and all(tag == 'insert' for tag, _, _ in delta):
            if [new for _, _, new in delta] == [[(tokenize.OP, '(')], [(tokenize.OP, ')')]]:
                for i, token in enumerate(after[:-1]):
                    if token == (tokenize.NAME, 'print') and after[i + 1] == (tokenize.OP, '('):
                        depth = 0
                        for j in range(i + 1, len(after)):
                            if after[j] == (tokenize.OP, '('):
                                depth += 1
                            elif after[j] == (tokenize.OP, ')'):
                                depth -= 1
                                if depth == 0:
                                    if after[:i + 1] + after[i + 2:j] + after[j + 1:] == before:
                                        return 'PRINT_STATEMENT', 'print_parentheses_inserted'
                                    break
    return None, 'repair_not_verified_by_conservative_rules'
