#!/usr/bin/env python3
"""PRのメンバー定義だけを取得し、mainのコードでplanするための入力を作る。"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from validate import ValidationError, require, validate


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def member_path(path):
    return path == "members/.gitkeep" or re.fullmatch(r"members/[a-z0-9][a-z0-9-]*\.yaml", path)


def prepare_snapshot(repo, base_sha, head_sha, destination):
    """コードをcheckoutせず、検証済みの通常ファイルだけを新しいディレクトリに置く。"""
    ancestor = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", base_sha, head_sha], check=False
    )
    require(ancestor.returncode == 0, "最新のmainをPRブランチに取り込んでください。")
    changed = git(repo, "diff", "--no-renames", "--name-only", "-z", base_sha, head_sha).decode().split("\0")
    require(any(changed), "PRに変更がありません。")
    for path in filter(None, changed):
        require(member_path(path), f"メンバー定義以外の変更はPR planの対象外です: {path}")

    entries = git(repo, "ls-tree", "-r", "-z", head_sha, "--", "members").decode().split("\0")
    members_dir = destination / "members"
    members_dir.mkdir(parents=True)
    for entry in filter(None, entries):
        metadata, path = entry.split("\t", 1)
        mode, kind, oid = metadata.split()
        require(member_path(path) and mode == "100644" and kind == "blob",
                f"通常のメンバーYAMLファイルだけを指定できます: {path}")
        require(int(git(repo, "cat-file", "-s", oid)) <= 65536, f"ファイルが大きすぎます: {path}")
        (members_dir / Path(path).name).write_bytes(git(repo, "cat-file", "blob", oid))

    # config、スクリプト、Terraform、依存定義は承認済みのmainから使用する。
    shutil.copytree(repo / "config", destination / "config")
    validate(destination)
    return members_dir.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    require(re.fullmatch(r"[1-9][0-9]*", args.pr_number), "PR番号は正の整数にしてください。")
    require(re.fullmatch(r"[a-f0-9]{40}", args.expected_sha), "PRの完全なhead SHAを指定してください。")
    repository = os.environ["GITHUB_REPOSITORY"]
    pr = json.loads(subprocess.check_output(["gh", "api", f"repos/{repository}/pulls/{args.pr_number}"]))
    require(pr["state"] == "open" and pr["base"]["ref"] == "main", "main向けの未マージPRを指定してください。")
    require(pr["head"]["sha"] == args.expected_sha, "PRが更新されています。最新SHAで新しく実行してください。")
    repo = Path.cwd()
    base_sha = git(repo, "rev-parse", "HEAD").decode().strip()
    subprocess.run(["git", "fetch", "--no-tags", "origin", f"refs/pull/{args.pr_number}/head"], check=True)
    head_sha = git(repo, "rev-parse", "FETCH_HEAD").decode().strip()
    require(head_sha == args.expected_sha, "取得中にPRが更新されました。再実行してください。")
    destination = Path(tempfile.mkdtemp(prefix="lusy-pr-plan-", dir=os.environ["RUNNER_TEMP"]))
    members_dir = prepare_snapshot(repo, base_sha, head_sha, destination)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"members_path={members_dir}\nhead_sha={head_sha}\n")
    print(f"PR #{args.pr_number} ({head_sha}) のメンバー定義を検証しました。")


if __name__ == "__main__":
    try:
        main()
    except (ValidationError, subprocess.CalledProcessError) as error:
        print(f"PR planの準備に失敗しました: {error}", file=sys.stderr)
        sys.exit(1)
