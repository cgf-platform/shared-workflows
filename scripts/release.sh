#!/usr/bin/env bash
# Cut a release of shared-workflows.
#
# Exists because the reusable workflows reference their own composite actions by
# tag, and GitHub does not allow expressions in `uses:`. Every release must
# therefore rewrite those references. Forgetting means the new workflow silently
# loads the PREVIOUS release's actions -- a failure with no error message.
#
#   ./scripts/release.sh v3.0.0          rewrite refs, commit, tag
#   ./scripts/release.sh v3.0.0 --check  verify only; changes nothing
#
set -euo pipefail

SELF_REF='cgf-platform/shared-workflows/.github/actions'
version="${1:-}"
mode="${2:-}"

if [[ ! "$version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "usage: $0 vX.Y.Z [--check]" >&2
  exit 2
fi

cd "$(dirname "$0")/.."
# Plain glob rather than mapfile: macOS ships bash 3.2, which has no mapfile.
workflows=(.github/workflows/*.yml)

# A release tag must capture the whole repo state -- changelog and scripts
# included, not just the reference rewrite this script performs. Refuse to tag
# a tree with unrelated pending work rather than silently tagging half of it.
if [[ "$mode" != "--check" ]] && [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "Working tree is not clean. Commit everything you intend to release first," >&2
  echo "then re-run; this script only rewrites and commits the action references." >&2
  git status --short --untracked-files=all >&2
  exit 1
fi

if [[ "$mode" == "--check" ]]; then
  stale=$(grep -n "$SELF_REF/[a-z-]*@" "${workflows[@]}" | grep -v "@${version}$" || true)
  if [[ -n "$stale" ]]; then
    echo "Internal action references not at ${version}:" >&2
    echo "$stale" >&2
    exit 1
  fi
  echo "All internal action references are at ${version}."
  exit 0
fi

for wf in "${workflows[@]}"; do
  perl -pi -e "s{(${SELF_REF}/[a-z-]+)\@\S+}{\$1\@${version}}g" "$wf"
done

# Prove the rewrite landed everywhere before creating anything permanent.
"$0" "$version" --check

if git diff --quiet; then
  echo "No reference changes; working tree already at ${version}."
else
  git add "${workflows[@]}"
  git commit -m "chore(release): point internal action refs at ${version}"
fi

if git rev-parse -q --verify "refs/tags/${version}" >/dev/null; then
  echo "Tag ${version} already exists. Tags are immutable here -- pick a new version." >&2
  exit 1
fi

git tag -a "$version" -m "Release ${version}"
echo
echo "Tagged ${version}. Push with:"
echo "  git push origin master --follow-tags"
