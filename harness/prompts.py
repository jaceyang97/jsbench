"""Fixed prompt texts for the jsbench harness.

Both texts are hashed (SHA-256) into every run record so any prompt drift is
detectable across runs. Do not edit casually mid-experiment.

v2 (2026-07-19, pre-Phase-1): environment wording updated — agents may extend
their environment from PyPI (proxy allowlists pypi.org/files.pythonhosted.org);
all other egress remains blocked. Phase-0 runs used v1 (different SHA-256).
"""
from __future__ import annotations

import hashlib

SYSTEM_APPEND = """\
You are being evaluated on your ability to solve a mathematical puzzle from \
first principles. General internet access is unavailable in this environment: \
you cannot browse the web, and any attempt to look up the puzzle or its \
solution is a protocol violation. Work from the provided materials, your \
reasoning, and code you write and run locally. A scientific Python 3 stack \
(numpy, scipy, sympy, pandas, z3-solver, ortools, networkx, pillow, \
matplotlib) is preinstalled, and you MAY install additional packages from \
PyPI with pip if you think a better tool exists for the job. Your environment \
is yours to shape."""

TASK_RULES = """\
You are solving a Jane Street monthly puzzle.

The full problem statement is given below. It is also saved at `problem.md` in \
your working directory{images_clause}.

RULES:
- No web access apart from installing packages from PyPI. Do not attempt to \
look up this puzzle or its solution anywhere. Solve it yourself; you may \
write and run code, and you may pip install additional packages if helpful.
- Verify your answer before submitting whenever verification is feasible.
- When you are confident in your final answer, write it to `output/answer.json` \
as JSON of the form {{"answer": "<string>"}} and stop.

ANSWER FORMAT: {answer_format}
- No thousands separators.
- Decimals in plain notation with at least 10 significant digits, unless the \
puzzle specifies otherwise.

PROBLEM ({puzzle_date}):

{problem}
"""

IMAGES_CLAUSE_WITH = (", and the puzzle image(s) are attached to this message "
                      "AND available under `images/` for programmatic inspection")
IMAGES_CLAUSE_WITHOUT = ""


def render_task(problem_md: str, answer_format: str, puzzle_date: str,
                has_images: bool) -> str:
    return TASK_RULES.format(
        images_clause=IMAGES_CLAUSE_WITH if has_images else IMAGES_CLAUSE_WITHOUT,
        answer_format=answer_format,
        puzzle_date=puzzle_date,
        problem=problem_md,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Minimal wrong-answer feedback for same-session retry. The ONLY information
# that crosses back into the session is that the submitted answer was wrong —
# no hint about how, why, or what the correct answer is (per Jace).
RETRY_FEEDBACK = """\
Your submitted answer `{submitted}` is incorrect.

Reconsider your approach, continuing from the work you have already done. When \
you have a new answer you are confident in, overwrite `output/answer.json` with \
it and stop. Do not resubmit the same value."""


def render_retry(submitted: str) -> str:
    return RETRY_FEEDBACK.format(submitted=submitted)


SYSTEM_APPEND_SHA256 = sha256_text(SYSTEM_APPEND)
TASK_RULES_SHA256 = sha256_text(TASK_RULES)
RETRY_FEEDBACK_SHA256 = sha256_text(RETRY_FEEDBACK)
