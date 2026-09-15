#!/usr/bin/env python3
"""既存の割り当てを検出し、plan用コピーまたは承認後の本番stateに取り込む。"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from validate import ValidationError, identifier, read_yaml, require, snowflake, validate


class API:
    def __init__(self, origin, headers):
        self.origin = origin
        self.headers = {"User-Agent": "lusy-roles", **headers}

    def get(self, path, *, absent_ok=False):
        request = Request(self.origin + path, headers=self.headers)
        for attempt in range(4):
            try:
                with urlopen(request, timeout=60) as response:
                    return json.load(response)
            except HTTPError as error:
                if absent_ok and error.code == 404:
                    return None
                if (error.code == 429 or 500 <= error.code < 600) and attempt < 3:
                    delay = 2 ** (attempt + 1)
                    retry_after = error.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            pass
                    error.close()
                    time.sleep(min(30, max(1, delay)))
                    continue
                # レスポンス本文や認証ヘッダーをログへ出さない。権限不足は欠落と扱わない。
                raise ValidationError(f"APIの読み取りに失敗: {path} (HTTP {error.code})") from None

    def pages(self, path):
        page = 1
        while True:
            items = self.get(f"{path}?per_page=100&page={page}")
            require(isinstance(items, list), f"APIの一覧形式が不正です: {path}")
            yield from items
            if len(items) < 100:
                break
            page += 1


def managed_instances(state):
    for resource in state.get("resources", []):
        if resource["mode"] == "managed" and resource["name"] == "members":
            require(not resource.get("module"), "モジュール内の所属は自動取り込みに対応していません。")
            for instance in resource["instances"]:
                yield resource["type"], instance


def targets(organization, members, state):
    """今回の定義と前回のstateにある本人だけを対象にする。"""
    org = organization["github_organization"]
    usernames = set(members)
    discord_users = {(organization["discord_server_id"], member["discord_user_id"])
                     for member in members.values()}
    for username, identity in state.get("outputs", {}).get("managed_identities", {}).get("value", {}).items():
        require(identity["github_organization"].lower() == org.lower(),
                "Organization変更には管理者によるstateの移行が必要です。")
        usernames.add(username)
        discord_users.add((identity["discord_server_id"], identity["discord_user_id"]))
    # 出力追加以前のstate、または途中まで成功したapplyも引き継ぐ。
    for kind, instance in managed_instances(state):
        attributes = instance["attributes"]
        if kind in ("github_membership", "github_team_membership"):
            usernames.add(attributes["username"].lower())
            if kind == "github_membership":
                require(attributes["id"].split(":")[0].lower() == org.lower(),
                        "Organization変更には管理者によるstateの移行が必要です。")
        elif kind == "discord_member_role":
            discord_users.add((attributes["guild_id"], attributes["user_id"]))
    for username in usernames:
        identifier(username, r"[a-z0-9][a-z0-9-]{0,38}", "管理対象GitHubユーザー名")
    for guild, user in discord_users:
        snowflake(guild, "管理対象Discordサーバー")
        snowflake(user, "管理対象Discordユーザー")
    return usernames, discord_users


def address(kind, key):
    return f"{kind}.members[{json.dumps(key)}]"


def discover(organization, members, state, github, discord):
    usernames, discord_users = targets(organization, members, state)
    org = organization["github_organization"]
    grants = {}

    def add(kind, key, import_id, **attributes):
        grants[address(kind, key)] = {"kind": kind, "key": key, "id": import_id, "attributes": attributes}

    pending = set()
    for username in sorted(usernames):
        membership = github.get(f"/orgs/{org}/memberships/{username}", absent_ok=True)
        if membership:
            require(membership["role"] in ("member", "admin"), "未対応のOrganization権限です。")
            add("github_membership", username, f"{org}:{username}", username=username, role=membership["role"])
            if membership["state"] == "pending":
                pending.add(username)

    if usernames:
        for team in github.pages(f"/orgs/{org}/teams"):
            slug, team_id = team["slug"], str(team["id"])
            identifier(slug, r"[a-z0-9]+(?:-[a-z0-9]+)*", "GitHubチームslug")
            identifier(team_id, r"[1-9][0-9]*", "GitHubチームID")
            for member in github.pages(f"/orgs/{org}/teams/{slug}/members"):
                username = member["login"].lower()
                if username not in usernames:
                    continue
                require(type(member.get("inherited")) is bool,
                        f"{slug}: APIから直接所属と継承所属を区別できません。")
                if member["inherited"]:
                    continue
                require(member["role"] in ("member", "maintainer"), "未対応のチーム権限です。")
                add("github_team_membership", f"{username}/{slug}", f"{team_id}:{username}",
                    username=username, team_id=team_id, role=member["role"])
            if pending:
                for invitation in github.pages(f"/orgs/{org}/teams/{slug}/invitations"):
                    username = (invitation.get("login") or "").lower()
                    if username in pending:
                        membership = github.get(f"/orgs/{org}/teams/{slug}/memberships/{username}")
                        add("github_team_membership", f"{username}/{slug}", f"{team_id}:{username}",
                            username=username, team_id=team_id, role=membership["role"])

    guild_roles = {}
    for guild, user in sorted(discord_users):
        if guild not in guild_roles:
            guild_roles[guild] = {role["id"]: role for role in discord.get(f"/guilds/{guild}/roles")}
        member = discord.get(f"/guilds/{guild}/members/{user}", absent_ok=True)
        if member is None:
            continue
        for role_id in member["roles"]:
            snowflake(role_id, "既存Discordロール")
            require(role_id in guild_roles[guild], "Discordロール一覧が変化しました。再実行してください。")
            role = guild_roles[guild][role_id]
            require(type(role.get("managed")) is bool, "Discordロールの管理元を判別できません。")
            if role_id == guild or role["managed"]:
                continue
            add("discord_member_role", f"{guild}/{user}/{role_id}", f"{guild}:{user}:{role_id}",
                guild_id=guild, user_id=user, role_id=role_id)
    return grants


def adoption_config(organization, grants):
    """CLI importの宛先を一時的に宣言する。APIから得た識別子以外は埋め込まない。"""
    groups = {}
    for grant in grants.values():
        group = groups.setdefault(grant["kind"], {"members": {"for_each": {}}})["members"]
        group["for_each"][grant["key"]] = grant["attributes"]
        for field in grant["attributes"]:
            group[field] = "${each.value." + field + "}"
    if "github_membership" in groups and "github_team_membership" in groups:
        groups["github_team_membership"]["members"]["depends_on"] = ["github_membership.members"]
    return {"locals": {"organization": organization}, "resource": groups}


def terraform(directory, *args, capture=False):
    result = subprocess.run(["terraform", f"-chdir={directory}", *args], check=True,
                            text=True, stdout=subprocess.PIPE if capture else None)
    return result.stdout


def pull_state(directory):
    result = subprocess.run(["terraform", f"-chdir={directory}", "state", "pull"],
                            text=True, capture_output=True, check=False)
    if result.returncode and "No state file was found!" in result.stderr:
        return {}
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        result.check_returncode()
    return json.loads(result.stdout) if result.stdout.strip() else {}


def prepare_directory(source, destination, organization, grants, state, *, adopt_remote=False):
    """planではGCSバックエンドを一切コピーしない。本番取り込みは明示指定時のみ。"""
    destination.mkdir(parents=True)
    for filename in ("versions.tf", "providers.tf", ".terraform.lock.hcl"):
        shutil.copyfile(source / filename, destination / filename)
    if adopt_remote:
        shutil.copyfile(source / "backend.tf", destination / "backend.tf")
    elif state:
        (destination / "terraform.tfstate").write_text(json.dumps(state), encoding="utf-8")
    (destination / "adoption.tf.json").write_text(json.dumps(adoption_config(organization, grants)), encoding="utf-8")


def import_existing(directory, grants, state):
    existing = {address(kind, instance["index_key"])
                for kind, instance in managed_instances(state)}
    for resource_address, grant in sorted(grants.items()):
        if resource_address not in existing:
            terraform(directory, "import", "-no-color", "-input=false", "-lock-timeout=5m",
                      resource_address, grant["id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--members-path", type=Path, default=Path("members"))
    parser.add_argument("--adopt-remote", action="store_true",
                        help="承認後のapply用。本番stateに既存の割り当てを取り込む")
    args = parser.parse_args()
    repo = Path.cwd()
    members_path = args.members_path.resolve()
    # mainまたはprepare_pr_plan.pyが作った検証対象を再確認する。
    validate(members_path.parent)
    organization = read_yaml(repo / "config/organization.yaml")
    members = {path.stem: read_yaml(path) for path in members_path.glob("*.yaml")}
    source = repo / "terraform"
    state = pull_state(source)
    github = API("https://api.github.com", {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10",
    })
    discord = API("https://discord.com/api/v10", {"Authorization": f"Bot {os.environ['DISCORD_BOT_TOKEN']}"})
    grants = discover(organization, members, state, github, discord)
    destination = Path(tempfile.mkdtemp(prefix="lusy-memberships-", dir=os.environ.get("RUNNER_TEMP"))) / "terraform"
    prepare_directory(source, destination, organization, grants, state, adopt_remote=args.adopt_remote)
    terraform(destination, "init", "-no-color", "-input=false", "-lockfile=readonly")
    import_existing(destination, grants, state)
    (destination / "adoption.tf.json").unlink()
    for path in source.glob("*.tf"):
        if path.name != "backend.tf":
            shutil.copyfile(path, destination / path.name)
    # 一時ディレクトリでも、mainの設定と検証済みメンバー定義を使う。
    (destination / "inputs.auto.tfvars.json").write_text(json.dumps({
        "config_path": str(repo / "config"), "members_path": str(members_path),
    }), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"terraform_dir={destination}\n")
    mode = "GCS" if args.adopt_remote else "ローカル"
    print(f"既存の割り当て{len(grants)}件を確認しました。取り込み先: {mode}")


if __name__ == "__main__":
    try:
        main()
    except (ValidationError, subprocess.CalledProcessError) as error:
        print(f"既存の割り当ての確認に失敗しました: {error}", file=sys.stderr)
        sys.exit(1)
