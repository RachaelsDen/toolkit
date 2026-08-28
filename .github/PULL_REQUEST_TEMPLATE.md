## Summary

<!-- What this PR changes and why. -->

## Verification

- [ ] Test suite green locally: aggregate == discovery (`python -m unittest pr_guard.pr_guard_test` and `python -m unittest discover -s . -t . -p "pr_guard*_test.py"` — the counts must match)
- [ ] Pure-LOC ceiling respected (≤250 per module, tests included) — measured, not eyeballed

## If this PR will be released

- [ ] `pyproject.toml` version bumped (a vX tag builds artifacts labeled with THIS version — v0.1.1 once shipped 0.1.0-labeled wheels)
- [ ] No CI expectations hardcoded to the current test count (assert the invariant, not the snapshot)
- [ ] After merge to main: tag `vX.Y.Z` and confirm the release workflow publishes wheel + sdist + `pr-guard.pyz`
