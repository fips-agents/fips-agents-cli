# Retrospective: Deploy Command End-to-End Fix

**Date:** 2026-05-31
**Effort:** Fix `fips-agents deploy` for both agent and MCP server projects
**Issues:** #55
**Commits:** 8c22c70
**Prior release:** v0.15.0 (introduced deploy), v0.15.1 (CI formatting fix)

## What We Set Out To Do

Fix 6 bugs that prevented `fips-agents deploy` from working end-to-end on a real OpenShift cluster. The command was introduced in v0.15.0 but had never been tested against a live cluster — only unit tests with mocked subprocess calls.

MCP servers (2 bugs): naming mismatch with scaffolded `openshift.yaml`, manifest never applied.
Agents (4 bugs): wrong image reference, no config overrides, route disabled by default, no ImageStream awareness.

## What Changed

| Change | Type | Rationale |
|--------|------|-----------|
| No scope changes | N/A | Fix addressed exactly the 6 items in the issue |

## What Went Well

- All 6 bugs fixed in a single commit with backward compatibility preserved
- MCP servers without `openshift.yaml` fall back to the old naming convention — existing projects aren't broken
- Review agent caught a valid edge case (bare name detection should exclude registry URLs with port numbers like `registry:5000`)
- 49 deploy tests (up from ~30), 86% coverage on deploy.py, 422 total tests passing
- The issue itself was well-written with specific reproduction steps and expected behavior — made the fix straightforward

## Gaps Identified

| Gap | Severity | Resolution |
|-----|----------|------------|
| Deploy command shipped without real-cluster testing | Process gap | Fixed by this effort; see Patterns |
| No integration test against a live cluster in CI | Accept | Not feasible in GitHub Actions; manual checklist is the right answer |
| `--set` values not validated before passing to Helm | Accept | Helm validates them and returns clear errors |
| No build step for agents (only Helm install) | Accept | Agent builds are handled separately via BuildConfig; deploy is deploy-only |

## Action Items

None outstanding. All 6 issues from #55 are resolved and tested.

## Patterns

**Stop:** Shipping new CLI commands that interact with external infrastructure (OpenShift, Helm) without at least one manual smoke test on a real cluster. The v0.15.0 deploy command passed 100% of its unit tests but failed immediately on first real use. Mocking `subprocess.run` verifies argument construction, not behavior.

**Start:** For commands that touch OpenShift/Helm, add a "smoke test checklist" to the release process — a short list of manual invocations to run before cutting the release. Even one `--dry-run` invocation on a real project would have caught the naming mismatch.

**Continue:** Parallel sub-agent execution for implementation + review — consistently effective across all three retros now.

**Continue (recurring):** Integration testing on real OpenShift. The April 10 retro said this explicitly: "the CORS issue, WORKDIR permissions, and tool_use ordering bug were all found only through integration testing." This session's 6 bugs are the same pattern. The lesson keeps proving itself.
