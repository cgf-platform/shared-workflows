# shared-workflows changelog

Consumers pin an immutable `vX.Y.Z` tag. There is no moving `v1` alias by design —
a moving tag is `@master` with better manners. Renovate opens the bump PRs.

**MAJOR** — an input or secret is removed or renamed; an optional input becomes
required; a caller must grant a new permission; **or a gate is tightened such that
a previously-passing build can now fail**. That last case is the one teams miss.
**MINOR** — a new optional input with a safe default, or a step that cannot fail an
existing green build. **PATCH** — a fix restoring intended behaviour.

---

## v2.0.0

**Breaking. Callers must be rewritten and must adopt deliberately, per service.**

`service-ci.yml` is replaced by two workflows:

| Was | Now |
|---|---|
| `service-ci.yml` (pull_request + push) | `service-validate.yml` (pull_request) and `service-release.yml` (push) |

**Why:** the single workflow forced every caller to grant `packages: write` and
`security-events: write` to *both* paths, so pull-request runs held write
credentials they never used. The validate workflow now receives **no secrets at
all** and holds `contents: read` + `packages: read`.

Named for the work rather than the trigger, so it stays correct if a merge queue is
added later and the same checks must run on `merge_group` events.

### Changes

- **Validate path takes no PAT.** Dependencies resolve from GitHub Packages with the
  caller's `GITHUB_TOKEN`, which works because service repos and
  `dineroo-event-contracts` share an organisation.
- **Release builds once.** `build` and `bootBuildImage` run in one job, so the
  image is packaged from the output that was just tested. The previous two-job
  shape recompiled everything in the packaging job.
- **Image scan tightened:** `severity-cutoff: critical` → `high`, plus
  `only-fixed: true`. This is the change that can newly fail a passing build; it is
  why this release is MAJOR. `only-fixed` is what makes the tighter cutoff
  survivable — without it the first unfixable finding halts publishing with no
  override path.
- **Scan results reach the Security tab.** Output is SARIF and uploaded, consuming
  the `security-events: write` that callers already granted and nothing used.
- **Inert source scan removed.** It ran before the build, so no resolved dependency
  JARs existed to catalog, and `fail-build: false` meant it could not act on a
  finding. Measured cost: ~54s per service per run, ~8 min across the fleet.
- **`:latest` is opt-in** via `publish-latest`, default `false`. It must never be a
  deployment reference.
- **Release manifest published** as an artifact, naming the immutable digest,
  commit, and run URL. This is the deployment contract; promotion reads the digest
  and never rebuilds.
- **Digest exposed** as a workflow output.
- **Runtime asserted:** the release logs `java -version` from inside the built
  image, so a claim like "JRE 21" is verified rather than asserted.
- **Wrapper validation added** on both paths; `gradle/actions/setup-gradle`
  replaces `cache: gradle`.
- **Coverage summary fixed.** It summed columns 4/5 (instructions) and labelled the
  result "Lines", contradicting the `counter = "LINE"` gate in the build files. Now
  reads columns 8/9.
- **Concurrency:** PR runs cancel on supersede; releases queue and never cancel
  mid-flight.

### Fixed after the first canary run

- **`actions: read` added.** `codeql-action/upload-sarif` calls
  `GET /actions/runs/{id}`; without it the upload failed with *"Resource not
  accessible by integration"*, so a blocked release left no findings behind.
  Callers must grant it on both workflows.
- **Runtime probe corrected.** `docker run --entrypoint java` can never work on a
  Paketo image — the launcher is what puts the JVM on `PATH`. Replaced by reading
  the buildpack metadata label, which states JDK vs JRE definitively.
- **Action pins bumped to current majors.** The first pins were to
  checkout v4 / setup-java v4 / upload-artifact v4 / gradle v4 / login v3, all of
  which run on Node 20 — now forced to Node 24 by the runner. Now v7 / v6 / v7 /
  v6 / v4, and CodeQL v3 → v4 ahead of its December 2026 deprecation.
- **Scan split into report and gate.** Grype's failure names no CVE, and its
  findings were only visible through code scanning. `fail-build` is now `false`
  and a separate gate step renders the finding table into the run summary before
  failing, so a blocked release always says what blocked it.

### Migration

Replace `.github/workflows/ci.yml` with `validate.yml` and `release.yml`. Callers pinned at `v1.0.0` are unaffected until they bump.

**Expect the first bumped service to go red.** Raising the cutoff to `high` on an
image that currently ships a full JDK will surface fixable findings that were
previously invisible. Bump one low-risk service first and budget triage time.

**Branch protection:** the required check name changes from `ci` to `validate`.
Update protection rules in the same change or merges will block on a check that no
longer runs.

---

## v1.0.0

First pinned release. Declares `GPR_USER` and `GPR_KEY` explicitly in
`workflow_call.secrets`, so callers stop using `secrets: inherit`.
