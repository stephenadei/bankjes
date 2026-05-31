# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues on `stephenadei/bankjes`.
Use the `gh` CLI for all operations.

## ⚠️ Account guard — verify before EVERY gh / git operation

This repo is **personal** (`stephenadei`). The maintainer is frequently signed
in to a **second, work account (`stephenatohpen`)** in the same shell. A `gh`
command run under the wrong active account silently lands on the wrong repo or
fails with "Repository not found".

Before any `gh issue`, `gh pr`, `gh label`, or `git push`:

```bash
gh auth status 2>&1 | grep -A1 'Active account: true'   # must show stephenadei
# if not:
gh auth switch --user stephenadei
git remote -v                                            # confirm origin = stephenadei/bankjes
```

Treat this as non-optional. The active account can change between turns.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with `--label` / `--state` filters.
- **Comment**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically inside a clone.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.
