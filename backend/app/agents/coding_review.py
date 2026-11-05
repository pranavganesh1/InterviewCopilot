"""Shared wording for coding answers that are reviewed statically, never run."""

AI_REVIEWED_NOT_EXECUTED = "AI-reviewed, not executed"

CODING_STATIC_REVIEW_RULES = """
Coding answers (NOT executed):
- The candidate's code was NOT run in any sandbox or interpreter.
- Reason about correctness statically from the source text only.
- Never claim specific program outputs, test results, or measured runtimes.
- Give time/space complexity as estimates; say when you are uncertain.
- Do not invent compile or runtime errors you cannot justify from the code text.
"""
