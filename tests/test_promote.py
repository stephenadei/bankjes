"""scripts/promote.sh against a throwaway bare origin: what reaches `pre`, and when a release PR opens.

Real git, fake `gh` (logs its argv). PATH is pinned so the host's herald/gh are never reached.
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "promote.sh"
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
}


def git(cwd, *args):
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(work, name, text):
    (work / name).write_text(text)
    git(work, "add", name)
    git(work, "commit", "-qm", f"{name}={text}")
    return git(work, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(work))
    commit(work, "app.txt", "v1")
    git(work, "push", "-q", "origin", "HEAD:master", "HEAD:pre", "HEAD:develop")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "gh").write_text('#!/bin/sh\necho "$*" >> "$GH_LOG"\n'
                             '[ "$1 $2" = "pr create" ] && echo https://github.com/x/y/pull/7\nexit 0\n')
    (fake / "gh").chmod(0o755)
    (tmp_path / "results.md").write_text("**1 passed, 0 failed, 0 skipped**\n")

    def promote(env, sha):
        run_env = {**os.environ, **GIT_ENV, "PATH": f"{fake}:/usr/bin:/bin", "GH_LOG": str(tmp_path / "gh.log"),
                   "GH_TOKEN": "x", "REPO": "x/y", "PUSH_URL": str(origin),
                   "RESULTS": str(tmp_path / "results.md")}
        return subprocess.run(["bash", str(SCRIPT), env, sha], cwd=work, env=run_env,
                              capture_output=True, text=True)

    def gh_calls():
        log = tmp_path / "gh.log"
        return log.read_text() if log.exists() else ""

    return work, origin, promote, gh_calls


def on_develop(work, name, text):
    git(work, "checkout", "-q", "--detach", "origin/develop")
    return commit(work, name, text)


def test_acc_fast_forwards_pre(repo):
    work, origin, promote, _ = repo
    sha = on_develop(work, "feature.txt", "x")
    assert promote("acc", sha).returncode == 0
    assert git(origin, "rev-parse", "pre") == sha  # fast-forward, no merge commit


def test_acc_also_brings_master_hotfix_into_pre(repo):
    work, origin, promote, _ = repo
    hotfix = commit(work, "hotfix.txt", "h")
    git(work, "push", "-q", "origin", "HEAD:master")
    sha = on_develop(work, "feature.txt", "x")
    assert promote("acc", sha).returncode == 0
    for ancestor in (sha, hotfix):  # pre ⊇ develop's commit and ⊇ prd
        git(origin, "merge-base", "--is-ancestor", ancestor, "pre")


def test_acc_conflict_pushes_nothing(repo):
    work, origin, promote, _ = repo
    before = git(origin, "rev-parse", "pre")
    commit(work, "app.txt", "hot")
    git(work, "push", "-q", "origin", "HEAD:master")
    sha = on_develop(work, "app.txt", "dev")
    r = promote("acc", sha)
    assert r.returncode == 1 and "conflicts" in r.stderr
    assert git(origin, "rev-parse", "pre") == before


def test_pre_opens_release_pr_with_evidence(repo):
    work, origin, promote, gh_calls = repo
    sha = on_develop(work, "feature.txt", "x")
    git(work, "push", "-q", "origin", "HEAD:pre")
    assert promote("pre", sha).returncode == 0
    calls = gh_calls()
    assert "pr create -R x/y --base master --head pre" in calls and "--label no-automerge" in calls
    assert "pr comment 7 -R x/y --body-file" in calls


def test_pre_without_changes_opens_nothing(repo):
    work, origin, promote, gh_calls = repo
    assert promote("pre", git(origin, "rev-parse", "master")).returncode == 0
    assert gh_calls() == ""
