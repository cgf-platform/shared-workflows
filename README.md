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

Two workflows, split along a privilege boundary. Add both to a service repo.

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
    uses: cgf-platform/shared-workflows/.github/workflows/service-validate.yml@v2.0.0
    with:
      service-name: order-service
```

No secrets. No write scope. Dependencies resolve from GitHub Packages with the
caller's `GITHUB_TOKEN`.

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
    uses: cgf-platform/shared-workflows/.github/workflows/service-release.yml@v2.0.0
    with:
      image-name: order-service
    secrets:
      GPR_USER: ${{ secrets.GPR_USER }}
      GPR_KEY: ${{ secrets.GPR_KEY }}
```

Exposes `digest` and `image` as outputs. Consume the digest; never a tag.

## Inputs

**`service-validate`** — `service-name` (required), `java-version` (`21`),
`timeout-minutes` (`30`).

**`service-release`** — `image-name` (required), `java-version` (`21`),
`severity-cutoff` (`high`), `publish-latest` (`false`), `timeout-minutes` (`45`).

## Design rules

**Build once, promote many.** The release job runs `build` and `bootBuildImage`
in one Gradle invocation, so the image is packaged from the output that was just
tested. The published **digest** is the deployment identity; tags are aliases for
humans. Nothing downstream may rebuild.

**The validate path holds no write scope.** Not "no production secrets" — none at
all. This rules out `dorny/test-reporter` and similar, which need `checks: write`;
results go to the run summary instead, rendered by
[`jvm-report`](.github/actions/jvm-report/).

**Assert, don't claim.** The release logs `java -version` from inside the built
image. Seven `-PBP_*` flags in a previous version never reached the buildpack, so
images shipped a full JDK under a step named "JRE" and nothing caught it.

**Everything is pinned.** Third-party actions by commit SHA with a version
comment; consumers pin this repo by immutable tag. There is deliberately no
moving `v2` alias — a moving tag is `@master` with better manners.

## Repository layout

```
.github/
  actions/
    setup-jvm/      wrapper validation + JDK + Gradle cache
    jvm-report/     JUnit + JaCoCo -> run summary; uploads HTML reports
  workflows/
    service-validate.yml
    service-release.yml
```

Composite actions are referenced as `cgf-platform/shared-workflows/.github/actions/<name>@<tag>`,
not `./.github/actions/<name>` — inside a reusable workflow a relative path
resolves against the *caller's* checkout, not this repo.

`jvm-report/summarize.py` is a real file rather than an embedded `run:` block so
it can be read, run and tested locally:

```bash
cd <service-repo> && SERVICE_NAME=order-service python3 path/to/summarize.py
```

## Versioning

See [CHANGELOG.md](CHANGELOG.md). Semantics are the usual ones with one addition
worth stating plainly:

> **Tightening a gate is a MAJOR**, even though no input or signature changes.
> Moving the Grype cutoff from `critical` to `high` alters nothing in the
> interface and turns green builds red across every consumer.

[adr]: https://github.com/cgf-platform/platform-gitops/blob/main/docs/adr/ADR-001-platform-vs-product-repositories.md
