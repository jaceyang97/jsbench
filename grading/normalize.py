"""Deterministic answer normalization and comparison.

Chain (first success wins):
  1. strip whitespace / thousands separators / currency / percent signs
  2. integer comparison
  3. float comparison under grader tolerance ({"type":"exact"} => ==,
     {"type":"rel","eps":e} => relative, {"type":"abs","eps":e} => absolute)
  4. sympy symbolic equivalence (answer_type == "expression")
  5. casefolded string comparison (also checked against aliases)

No LLM judge anywhere. Grader dict schema: see data/graders/*.json.
"""
from __future__ import annotations

import re

_STRIP_RE = re.compile(r"[\s$€£¥,_]")


def clean(s: str) -> str:
    s = str(s).strip()
    s = _STRIP_RE.sub("", s)
    s = s.rstrip("%")
    # strip surrounding quotes/markdown bold
    s = s.strip("\"'").strip()
    if s.startswith("**") and s.endswith("**"):
        s = s[2:-2]
    return s


def try_int(s: str) -> int | None:
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def try_float(s: str) -> float | None:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def floats_equal(a: float, b: float, tolerance: dict) -> bool:
    t = tolerance.get("type", "exact")
    if t == "exact":
        return a == b
    eps = float(tolerance.get("eps", 1e-9))
    if t == "abs":
        return abs(a - b) <= eps
    if t == "rel":
        scale = max(abs(a), abs(b), 1e-300)
        return abs(a - b) / scale <= eps
    raise ValueError(f"unknown tolerance type {t}")


def sympy_equal(a: str, b: str) -> bool:
    try:
        import sympy
        ea = sympy.sympify(a, rational=True)
        eb = sympy.sympify(b, rational=True)
        return sympy.simplify(ea - eb) == 0
    except Exception:
        return False


_MATH_NORM = str.maketrans({"√": "sqrt", "π": "pi", "×": "*", "·": "*", "^": "**"})


def numeric_value(s: str) -> float | None:
    """Best-effort numeric evaluation: plain float, else sympy evalf.

    Lets an exact form like '(229-60*sqrt(5))/192' match a decimal ground
    truth (and vice versa)."""
    f = try_float(s)
    if f is not None:
        return f
    try:
        import sympy
        expr = sympy.sympify(s.translate(_MATH_NORM))
        if expr.free_symbols:
            return None
        return float(expr.evalf(30))
    except Exception:
        return None


def _compare_scalar(s: str, e: str, tol: dict, answer_type: str,
                    grader: dict) -> tuple[bool, str]:
    # integers
    si, ei = try_int(s), try_int(e)
    if si is not None and ei is not None:
        return (si == ei), "int"

    # numeric (plain float or exact symbolic form on either side)
    sv, ev = numeric_value(s), numeric_value(e)
    if sv is not None and ev is not None:
        num_tol = tol if tol.get("type") != "exact" else {"type": "rel", "eps": 1e-9}
        return floats_equal(sv, ev, num_tol), "numeric"

    # symbolic equivalence
    if answer_type == "expression" and sympy_equal(s, e):
        return True, "sympy"

    # strings (+ aliases)
    if s.casefold() == e.casefold():
        return True, "string"
    for alias in grader.get("aliases", []):
        if s.casefold() == clean(alias).casefold():
            return True, "alias"
    return False, "mismatch"


def normalize_and_compare(submitted, expected, grader: dict) -> tuple[bool, str]:
    """Return (correct, reason)."""
    if submitted is None:
        return False, "no answer submitted"
    tol = grader.get("tolerance", {"type": "exact"})
    answer_type = grader.get("answer_type", "string")

    # Models often submit "exact_form = decimal" (e.g. "(229-60*sqrt(5))/192
    # = 0.4939370904" or "π - 1 ≈ 2.1415926..."). Accept if ANY side of an
    # equality/approximation separator matches.
    sub_str = str(submitted).replace("≈", "=").replace("~", "=")
    if "=" in sub_str and answer_type != "multi":
        for side in sub_str.split("="):
            side = side.strip()
            if not side:
                continue
            ok, why = normalize_and_compare(side, expected, grader)
            if ok:
                return True, f"eq-side-{why}"

    if answer_type == "multi":
        # multi-part answers: parts separated by comma/semicolon, order matters;
        # aliases hold alternative full lists (e.g. rotations of a tuple answer)
        sp = [p for p in re.split(r"[;,]", str(submitted)) if p.strip()]
        last_reason = "multi"
        for i, cand in enumerate([expected] + list(grader.get("aliases", []))):
            ep = [p for p in re.split(r"[;,]", str(cand)) if p.strip()]
            if len(sp) != len(ep):
                last_reason = f"multi-count({len(sp)}!={len(ep)})"
                continue
            for spart, epart in zip(sp, ep):
                ok, _ = _compare_scalar(clean(spart), clean(epart), tol, "expression", grader)
                if not ok:
                    last_reason = f"multi-part-mismatch({spart.strip()!r})"
                    break
            else:
                return True, "multi" if i == 0 else "multi-alias"
        return False, last_reason

    # aliases may hold exact symbolic forms; accept any matching alias wholesale
    for alias in grader.get("aliases", []):
        ok, why = _compare_scalar(clean(submitted), clean(alias), tol, answer_type, grader)
        if ok:
            return True, f"alias-{why}"

    return _compare_scalar(clean(submitted), clean(expected), tol, answer_type, grader)
