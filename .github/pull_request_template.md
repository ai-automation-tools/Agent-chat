## What this changes

<!-- One or two sentences. The why matters more than the what. -->

## Why

## How it was verified

<!-- Name what you actually ran. "All 14 suites pass (350 cases)" beats "tested". -->

- [ ] All suites pass: `Get-ChildItem tests/test_*.py | ForEach-Object { .\.venv\Scripts\python.exe $_.FullName }`
- [ ] `python -m compileall -q src scripts tests` is clean
- [ ] Docs updated in this PR if behavior, setup, or roadmap status changed
- [ ] No machine-specific paths, secrets, or generated-file edits (regenerate instead)
