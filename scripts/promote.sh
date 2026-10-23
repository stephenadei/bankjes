#!/usr/bin/env bash
# shellcheck disable=SC2016  # backticks below are markdown, not expansions
# promote.sh <acc|pre> <sha> — promotion step of post-deploy QA (docs/qa.md). pipeline.yml's qa job
# runs it only after QA passed on <env> for <sha>.
#
#   acc → merge <sha> (and master) into pre and push; that push deploys pre and QAs it there.
#   pre → open or refresh the release PR pre → master (label no-automerge) + an evidence comment.
#
# GH_TOKEN must be one whose pushes/PRs trigger workflows (stephenadei's PAT, not GITHUB_TOKEN):
# a GITHUB_TOKEN push would not deploy pre, its PR would never get master's required `test` check,
# and this repo does not let Actions open PRs at all.
# Env: REPO, PUSH_URL, RESULTS (pytest's results.md), RUN_URL, ARTIFACT_URL. DRY_RUN=1 prints the writes.
set -euo pipefail

ENV="${1:?usage: promote.sh <acc|pre> <sha>}"
SHA="${2:?usage: promote.sh <acc|pre> <sha>}"
REPO="${REPO:-stephenadei/bankjes}"
PUSH_URL="${PUSH_URL:-https://github.com/${REPO}.git}"  # tests point this at a local bare repo
RESULTS="${RESULTS:-qa-artifacts/results.md}"
short="${SHA:0:7}"

write() {  # every outward write goes through here
  if [ "${DRY_RUN:-0}" = 1 ]; then printf 'DRY_RUN:' >&2; printf ' %q' "$@" >&2; echo >&2; else "$@"; fi
}

evidence() {  # "## Evidence" first: personal-pr-automerge does not read it as a human comment
  printf '## Evidence — QA on %s for `%s`\n\nRun: %s · Screenshots: %s\n\n' \
    "$ENV" "$short" "${RUN_URL:-n/a}" "${ARTIFACT_URL:-in the run artifacts}"
  cat "$RESULTS"
}

notify() {  # $1 context, $2 text; a missing herald must not fail a green promotion
  if command -v herald >/dev/null; then write env NOTIFY_CONTEXT="$1" herald send "$2" || true
  else echo "herald not on PATH; skipped: $2"; fi
}

git fetch -q origin pre master
ev="$(mktemp)"; trap 'rm -f "$ev"' EXIT

case "$ENV" in
  acc)
    git checkout -q --detach origin/pre
    # Fast-forward when pre ⊆ sha. master is merged in too, so pre ⊇ prd and the release PR is
    # never "behind" under master's strict (up-to-date) protection.
    if ! git -c user.name="bankjes pipeline" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
        merge -q --no-edit -m "promote: acc QA green at $short" "$SHA" origin/master; then
      git merge --abort 2>/dev/null || true
      echo "::error::merging $short + master into pre conflicts; resolve by hand" >&2
      exit 1
    fi
    if [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/pre)" ]; then
      echo "pre already contains $short; nothing to promote"; exit 0
    fi
    echo "pre: $(git rev-parse --short origin/pre) -> $(git log --oneline -1)"
    # Token via a credential helper reading $GH_TOKEN at run time: never in argv, URL or log.
    write git -c credential.helper= -c 'credential.helper=!f() { echo username=x-access-token; echo "password=$GH_TOKEN"; }; f' \
      push -q "$PUSH_URL" HEAD:refs/heads/pre
    # acc evidence lands on the PR that brought sha into develop, when there is one.
    pr="$(gh api "repos/$REPO/commits/$SHA/pulls" --jq '.[0].number // empty' 2>/dev/null)" || pr=""
    if [ -n "$pr" ]; then
      { evidence; printf '\nPromoted to pre as `%s`; pre deploys and runs the same QA next.\n' \
          "$(git rev-parse --short HEAD)"; } > "$ev"
      write gh pr comment "$pr" -R "$REPO" --body-file "$ev"
    fi
    ;;
  pre)
    if git diff --quiet origin/master "$SHA"; then
      echo "pre ($short) has master's tree; no release PR needed"; exit 0
    fi
    pr="$(gh pr list -R "$REPO" --base master --head pre --state open --json number --jq '.[0].number // empty')"
    if [ -z "$pr" ]; then
      write gh label create no-automerge -R "$REPO" --force --color ededed \
        --description "personal-pr-automerge leaves this PR alone"
      url="$(write gh pr create -R "$REPO" --base master --head pre --title "release: pre → prd" \
        --label no-automerge --body "Opened by the pipeline: post-deploy QA passed on acc and on pre (docs/qa.md).
Each pre deploy that passes QA adds an evidence comment; the newest one matches the head commit.

- Merge with **Create a merge commit**, not squash: develop and pre must stay ancestors of master.
- Labelled \`no-automerge\`: personal-pr-automerge squash-merges and deletes the head branch, which would delete \`pre\`.")"
      pr="${url##*/}"; pr="${pr:-NEW}"
    fi
    { evidence; printf '\n### In this release (vs master)\n\n'
      git log --no-merges --format='- %h %s' "origin/master..$SHA" | head -40; } > "$ev"
    write gh pr comment "$pr" -R "$REPO" --body-file "$ev"
    notify personal.log "🟢 bankjes QA green on acc and pre: release PR ready, https://github.com/$REPO/pull/$pr"
    ;;
  *) echo "env must be acc or pre, got: $ENV" >&2; exit 2 ;;
esac
