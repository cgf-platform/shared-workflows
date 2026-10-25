# shared-workflows changelog

Consumers pin an immutable `vX.Y.Z` tag. There is no moving `v1` alias by design —
a moving tag is `@master` with better manners. Renovate opens the bump PRs.

**MAJOR** — an input or secret is removed or renamed; an optional input becomes
required; a caller must grant a new permission; **or a gate is tightened such that
a previously-passing build can now fail**. That last case is the one teams miss.
**MINOR** — a new optional input with a safe default, or a step that cannot fail an
existing green build. **PATCH** — a fix restoring intended behaviour.

---

## v3.10.0

Hardens the pipeline against script injection, gives the repo its own CI, and adds the
building blocks for fleet-wide automation. Nothing here can fail a build that is green
today, so this is a MINOR.

**Security**
- **Script injection closed.** `inputs.version`, `inputs.image-name`, step outputs,
  `github.actor` and `secrets.GITHUB_TOKEN` were interpolated straight into `run:`
  scripts in `service-release`, `service-promote` and `docker-release`. Anyone able to
  start a release with a crafted version (`1.2.3"; curl ... | sh`) controlled a step
  that holds `packages: write`. They now reach scripts through `env:` only, and the
  version is validated as strict `MAJOR.MINOR.PATCH` first.
- Checkouts that never push now set `persist-credentials: false`. The promote workflow's
  ledger checkout keeps the token on purpose, because the next step pushes with it.
- zizmor reported 34 findings before this change (11 of them template injection) and
  none after. Policy is in `.github/zizmor.yml`.

**New**
- **`generate-sbom` on `service-release`** (default `true`). An SPDX SBOM of the exact
  image about to be published is attached as a run artifact. Informational: it can never
  fail a release.
- **`ledger-repo` on `service-promote`**, defaulting to today's
  `cgf-studio/dineroo-deployment`. The ledger can move without forking the workflow.
- **`java-version` is now optional everywhere and defaults to empty.** `setup-jvm` then
  reads `javaVersion` from the service's `gradle.properties` (the property
  `build-conventions` already uses for the toolchain and the Paketo JRE), falling back to
  21. A JDK upgrade becomes one line in the service. Every service sets `javaVersion=21`
  today, so behaviour is unchanged. A malformed value fails loudly instead of silently
  falling back.
- **`library-validate` and `library-publish`** reusable workflows for Gradle libraries and
  plugins published to GitHub Packages. They replace four near-identical manual
  `release.yml` files and add PR CI where there was none.
- **`validate-release-version`** composite action: one tested implementation of the
  semver and "release must be new" check that was copy-pasted into three workflows.
- **`ci.yml`**: this repo now lints itself (actionlint, zizmor, shellcheck, the Python
  tests, and a check that internal action refs agree on one version).

Callers need no change beyond bumping the tag.

---

## v3.2.0 to v3.8.0 (reconstructed from git history)

These releases were tagged without changelog entries. From the commit log:

- **v3.2.0** (2026-09-13): semantic versioning. The release takes a human-supplied
  `version` and tags the image `v<version>`.
- **v3.3.0** (2026-09-13): the released semver is stamped into the Gradle build, so the
  artifact reports `vX.Y.Z` instead of a SNAPSHOT.
- **v3.4.0** (2026-09-13): release no longer writes the deploy ledger. Promotion is a
  separate step.
- **v3.5.0** (2026-09-13): new reusable `service-promote` workflow.
- **v3.6.0** (2026-09-13): promote accepts a version or a `vX.Y.Z` tag.
- **v3.7.0** (2026-09-14): new reusable `docker-release` for Dockerfile apps.
- **v3.8.0** (2026-10-09): the PAT is the default secret.

A stray tag `3.8.0` (no `v`) points at the same commit as `v3.8.0`; it can be deleted.

---

## v3.9.0

Adds a way to accept a single finding for a limited time, without lowering
`severity-cutoff` for everything else.

Motivation: a Go stdlib CVE is fixed upstream (so Grype's `only-fixed` counts it as
fixable) days before Paketo rebuilds the buildpack helpers that ship in every
Spring Boot image. During that window no builder, pin or dependency bump can clear
the finding, and the release is blocked on something the service team cannot change.

- **New input `vulnerability-exceptions-file` on `service-release`**, default
  `.github/vulnerability-exceptions.json`; the gate action takes the same as
  `exceptions-file`. A JSON list of `{id, owner, reason, expires}` where `id` is the
  finding ID from the gate table and `expires` is `YYYY-MM-DD`, inclusive.
- Accepted findings are still listed in the run summary, with owner and expiry.
- An **expired** exception stops applying: the finding blocks again and the summary
  says which exception lapsed.
- A **malformed** file fails the gate (it is never skipped), so a typo cannot turn
  into a silent bypass. A **missing** file means no exceptions, so existing callers
  behave exactly as before.
- Behaviour tests for the gate: `python3 -m unittest discover -s tests`.

No caller change is required; a service that has no exceptions file is unaffected.

---

## v3.1.0

Fixes a latent failure found on the first `mock-server` release run: on a private
free-plan repository, GitHub code scanning (Advanced Security) is unavailable, so
`upload-sarif` errored -- and with no `continue-on-error` it would have failed
even a clean release, not just this vulnerable one.

- **New input `enable-code-scanning`, default `false`.** The SARIF upload is
  skipped unless a repo can actually use code scanning (public, or GHAS). The
  vulnerability gate never depended on it: findings are rendered in the run
  summary regardless, which is why this run still showed the full CVE table.
- **`continue-on-error` on the upload step**, so even where code scanning is
  enabled a transient outage cannot fail a release.

No caller change beyond bumping the tag. `security-events: write` stays granted
but dormant until `enable-code-scanning: true`.

---


## v3.0.0

**Breaking. Callers must grant `actions: read` in addition to their existing
permissions.** A called workflow's `permissions:` block *replaces* rather than
extends, so granting it in the caller alone is not enough and vice versa -- both
sides move together. That is what makes this MAJOR rather than a patch.

Cut after the first canary run of `v2.0.0` on `mock-server`, which surfaced four
problems. `v2.0.0` remains tagged and immutable; it never produced a successful
release.

### Fixes

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

### Also in this release

- **Scan split into report and gate.** `fail-build` is now `false` on the scan;
  a separate `vulnerability-gate` action renders the finding table into the run
  summary and *then* fails. Grype's own failure names no CVE, and its findings
  were only visible through code scanning -- so when the SARIF upload failed, the
  release was blocked with no way to see why.
- **`image-facts` action added**, reading the buildpack metadata label to report
  JDK-vs-JRE definitively.
- **`severity-cutoff` is an input**, so a service with an unresolvable finding can
  be unblocked without forking the workflow.

### Migration from v2.0.0

1. Add `actions: read` to both callers.
2. Bump both `uses:` references to `@v3.0.0`.

**Branch protection:** required check names are `validate` and `release`
(previously `ci`). Update protection rules in the same change or merges block on
a check that no longer runs.

**Expect the first bumped service to go red.** The `high` + `only-fixed` gate on
an image that still ships a full JDK will surface findings that were previously
invisible. The gate now lists them, so this is triage rather than guesswork.

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
