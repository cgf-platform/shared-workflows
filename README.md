# shared-workflows

Reusable GitHub Actions workflows for CGF platform services. Product-neutral by
[ADR-001][adr]: this repo owns *how* a service is built, verified and published,
and nothing product-specific.

Public on purpose. A private repo on a free-plan organisation cannot expose a
reusable workflow to another organisation — `actions/permissions/access` reaches
only `organization` (same-org) or `enterprise` — and the failure surfaces as a
misleading *"workflow was not found"*. See ADR-001 Amendment 1.

**Because it is public, callers must pass secrets explicitly. Never
`secrets: inherit`.** The `workflow_call.secrets` block is the boundary: it is
what guarantees this repo sees two credentials rather than a caller's entire
secret set.

## Usage

A JVM service repo adds two caller workflows, split along a privilege boundary:
`validate` (pull requests, no write scope) and `release` (post-merge, publishes).
Promotion and Dockerfile apps use the other two reusable workflows, see
[Inputs](#inputs).

### `.github/workflows/validate.yml`

```yaml
name: Validate

on:
  pull_request:
    branches: [ master, feature/**, epic/** ]

jobs:
  validate:
    permissions:
      contents: read
      packages: read
      actions: read
    uses: cgf-platform/shared-workflows/.github/workflows/service-validate.yml@v3.10.0
    with:
      service-name: order-service
    secrets:
      GPR_USER: ${{ secrets.GPR_USER }}
      GPR_KEY: ${{ secrets.GPR_KEY }}
```

No write scope — `actions: read` is required by the SARIF upload and is
read-only. The one credential is `GPR_USER`/`GPR_KEY`, the same pair the release
uses, and it must be a **read-only** (`read:packages`) token: code that runs in
`./gradlew build` on a PR branch can read it. It is needed because the
`build-conventions` plugin lives in the `cgf-platform` organisation, which a
service's `GITHUB_TOKEN` cannot read — GitHub Packages answers it with a 404.

The secrets are optional: without them the job falls back to `GITHUB_TOKEN`, which
resolves `dineroo-event-contracts` but resolves the plugin only from a warm Gradle
cache, so a `build-conventions` version bump fails validation until a release has
run. Call this workflow from `pull_request` only, never `pull_request_target`.

### `.github/workflows/release.yml`

```yaml
name: Release

on:
  push:
    branches: [ master ]

jobs:
  release:
    permissions:
      contents: read
      packages: write
      security-events: write
      actions: read
    uses: cgf-platform/shared-workflows/.github/workflows/service-release.yml@v3.10.0
    with:
      image-name: order-service
    secrets:
      GPR_USER: ${{ secrets.GPR_USER }}
      GPR_KEY: ${{ secrets.GPR_KEY }}
```

Exposes `digest` and `image` as outputs. Consume the digest; never a tag.

## Inputs

**`service-validate`** — `service-name` (required), `java-version` (empty: read
`javaVersion` from the service's `gradle.properties`, fall back to `21`),
`timeout-minutes` (`30`). Secrets (optional, read-only): `GPR_USER`, `GPR_KEY`.

**`service-release`** — `image-name` (required), `version` (required),
`java-version` (empty, as above), `severity-cutoff` (`high`),
`vulnerability-exceptions-file` (`.github/vulnerability-exceptions.json`),
`enable-code-scanning` (`false`), `generate-sbom` (`true`, informational, never
blocks), `publish-latest` (`false`), `timeout-minutes` (`45`).

**`service-promote`** — `image-name`, `version` (`1.2.3` or `v1.2.3`),
`ledger-repo` (`dineroo-gn/dineroo-deployment`). Secret: `LEDGER_TOKEN`.

**`docker-release`** — `image-name`, `version`, `build-args`, `context`, `platforms`.
For Dockerfile apps such as the Next.js frontends.

**`library-validate`** / **`library-publish`** — for Gradle libraries and plugins
published to GitHub Packages (`build-conventions`, `platform-starters`,
`platform-catalog`, `platform-migrations`). `library-validate` is read-only PR CI
(`library-name`, `java-version`, `timeout-minutes`). `library-publish` is the manual,
versioned release (`library-name`, `version`): build, publish, then tag, so a tag
never names an unpublished version. The library's build reads `releaseVersion` and
publishes with the `USERNAME`/`TOKEN` environment variables.

**One JDK source.** `java-version` is optional everywhere. Left empty, the
[`setup-jvm`](.github/actions/setup-jvm/) action reads `javaVersion` from
`gradle.properties`, the same property the `build-conventions` plugin uses for the
Gradle toolchain and the Paketo JRE, so a JDK upgrade is one line in the service.

### Accepting a finding for a limited time

When a finding is fixed upstream but the fix has not reached your image yet -- the
usual case is a Go stdlib CVE in the Paketo buildpack helpers, which stays red until
Paketo rebuilds -- record an exception in the service repo instead of lowering
`severity-cutoff`:

```json
[
  {
    "id": "GO-2026-6613-stdlib",
    "owner": "your-name",
    "reason": "Fixed in Go 1.27.2 (2026-10-08); Paketo has not rebuilt its buildpack helpers yet.",
    "expires": "2026-10-25"
  }
]
```

`id` is exactly the ID in the gate's table and matches that one finding (every
location of it). The run summary keeps listing accepted findings with owner and
expiry. After `expires` (inclusive) the finding blocks again; a malformed file fails
the release rather than being ignored. Delete the entry once the fix lands.

## Design rules

**Build once, promote many.** The release job runs `build` and `bootBuildImage`
in one Gradle invocation, so the image is packaged from the output that was just
tested. The published **digest** is the deployment identity; tags are aliases for
humans. Nothing downstream may rebuild.

**The validate path holds no write scope.** Its only credential is the read-only
`GPR_*` pair that resolves packages; nothing it holds can publish or deploy. This
rules out `dorny/test-reporter` and similar, which need `checks: write`;
results go to the run summary instead, rendered by
[`jvm-report`](.github/actions/jvm-report/).

**Assert, don't claim.** The release reads the buildpack's own metadata to report
whether the image contains a JDK or a JRE. Seven `-PBP_*` flags in a previous
version never reached the buildpack, so images shipped a full JDK under a step
named "JRE" and nothing caught it.

**A blocked release must explain itself.** The scan reports and the gate decides,
as separate steps. Grype's own failure is one line naming no CVE, and its findings
are only visible through code scanning -- so when the SARIF upload fails, a release
is blocked with no way to see why. The gate always writes the finding table to the
run summary first.

**Everything is pinned.** Third-party actions by commit SHA with a version
comment; consumers pin this repo by immutable tag. There is deliberately no
moving `v2` alias — a moving tag is `@master` with better manners.

## Repository layout

```
.github/
  actions/
    setup-jvm/                wrapper validation + JDK (from gradle.properties) + Gradle cache
    jvm-report/               JUnit + JaCoCo -> run summary; uploads HTML reports
    image-facts/              size, platform, run-as user, JDK-vs-JRE, buildpacks
    vulnerability-gate/       renders Grype SARIF, then gates on severity
    validate-release-version/ strict semver check + "release must be new", env-only
  workflows/
    service-validate.yml      PR build, no write scope
    service-release.yml       build once, scan, SBOM, publish, GitHub Release
    service-promote.yml       write a released digest to the deploy ledger
    docker-release.yml        the same release flow for Dockerfile apps
    library-validate.yml      PR build for a Gradle library
    library-publish.yml       manual versioned publish of a Gradle library
    ci.yml                    this repo's own CI (not reusable)
tests/                        behaviour tests for the helper scripts
```

Composite actions are referenced as `cgf-platform/shared-workflows/.github/actions/<name>@<tag>`,
not `./.github/actions/<name>` — inside a reusable workflow a relative path
resolves against the *caller's* checkout, not this repo.

`jvm-report/summarize.py` is a real file rather than an embedded `run:` block so
it can be read, run and tested locally:

```bash
cd <service-repo> && SERVICE_NAME=order-service python3 path/to/summarize.py
```

## Checks on this repo

Every service runs code from here, so a mistake in a workflow is a fleet-wide
incident. [`ci.yml`](.github/workflows/ci.yml) runs on every pull request:

- `python3 -m unittest discover -s tests -v`, the behaviour tests for the helper scripts.
- **actionlint** (which also runs shellcheck over every `run:` block), pinned by digest.
- **zizmor**, a security audit of workflows and composite actions. Policy:
  [`.github/zizmor.yml`](.github/zizmor.yml). Inputs, secrets and the actor reach
  scripts through `env:`, never `${{ }}` interpolation into a `run:` block.
- A check that every internal action ref points at one version.

## Cutting a release

```bash
./scripts/release.sh v3.10.0          # rewrite internal refs, commit, tag
./scripts/release.sh v3.10.0 --check  # verify only
```

The reusable workflows reference their own composite actions by tag, and GitHub
allows no expressions in `uses:`. So a release must rewrite those references, and
forgetting means the new workflow silently loads the *previous* release's
actions — a failure with no error message. The script does the rewrite, proves it
landed, then tags. Do not tag by hand.

## Versioning

See [CHANGELOG.md](CHANGELOG.md). Semantics are the usual ones with one addition
worth stating plainly:

> **Tightening a gate is a MAJOR**, even though no input or signature changes.
> Moving the Grype cutoff from `critical` to `high` alters nothing in the
> interface and turns green builds red across every consumer.

[adr]: https://github.com/cgf-platform/platform-gitops/blob/main/docs/adr/ADR-001-platform-vs-product-repositories.md
