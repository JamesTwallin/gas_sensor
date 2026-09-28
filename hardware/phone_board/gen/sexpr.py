"""Minimal S-expression reader/writer for KiCad files.

Atoms are kept as Python str. Quoted strings are wrapped in QStr so they are
written back quoted; bare atoms (numbers, keywords) are written as-is.
"""

import re


class QStr(str):
    """A string that was (or must be) quoted in the file."""


_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse(text):
    stack = [[]]
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError(f"bad token at {pos}: {text[pos:pos+40]!r}")
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            done = stack.pop()
            stack[-1].append(done)
        elif m.group(3) is not None:
            stack[-1].append(QStr(m.group(3).replace('\\"', '"').replace("\\\\", "\\")))
        elif m.group(4) is not None:
            stack[-1].append(m.group(4))
    assert len(stack) == 1, "unbalanced parens"
    return stack[0][0] if len(stack[0]) == 1 else stack[0]


def _atom(a):
    if isinstance(a, QStr):
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(a, float):
        s = f"{a:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    if isinstance(a, bool):
        return "yes" if a else "no"
    return str(a)


def dumps(node, indent=0):
    if not isinstance(node, list):
        return _atom(node)
    tab = "\t" * indent
    if not any(isinstance(c, list) for c in node):
        return tab + "(" + " ".join(_atom(c) for c in node) + ")"
    head = []
    rest = []
    for c in node:
        if isinstance(c, list) or rest:
            rest.append(c)
        else:
            head.append(c)
    out = tab + "(" + " ".join(_atom(c) for c in head)
    for c in rest:
        if isinstance(c, list):
            out += "\n" + dumps(c, indent + 1)
        else:
            out += " " + _atom(c)
    return out + "\n" + tab + ")"


def find(node, key):
    """First child list whose head is key."""
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def find_all(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]
