#!/usr/bin/env python3
"""Validate the access catalog and one JSON file per person without credentials."""

import argparse
import json
import re
import sys
from pathlib import Path


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def read_json(path):
    require(not path.is_symlink(), f"{path}: symlinks are not supported")
    try:
        return json.loads(path.read_text(), object_pairs_hook=unique_object)
    except (OSError, ValueError) as error:
        raise ValidationError(f"{path}: {error}") from error


def fields(value, expected, label):
    require(isinstance(value, dict), f"{label}: expected a JSON object")
    require(set(value) == set(expected), f"{label}: expected exactly these fields: {', '.join(expected)}")


def identifier(value, pattern, label):
    require(isinstance(value, str) and re.fullmatch(pattern, value) is not None,
            f"{label}: invalid identifier {value!r}")


def snowflake(value, label):
    identifier(value, r"[1-9][0-9]{16,19}", label)
    require(int(value) < 2**64, f"{label}: Discord ID exceeds 64 bits")


def string_list(value, label):
    require(isinstance(value, list) and all(isinstance(item, str) for item in value),
            f"{label}: expected an array of strings")
    require(len(value) == len(set(value)), f"{label}: duplicate values")


def validate(root):
    config_dir = root / "config"
    members_dir = root / "members"
    require(config_dir.is_dir() and not config_dir.is_symlink(), "config/ must be a real directory")
    require(members_dir.is_dir() and not members_dir.is_symlink(), "members/ must be a real directory")

    organization = read_json(config_dir / "organization.json")
    fields(organization, ("github_organization", "discord_server_id"), "organization")
    github_pattern = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
    identifier(organization["github_organization"], github_pattern, "GitHub organization")
    snowflake(organization["discord_server_id"], "Discord server ID")

    roles = read_json(config_dir / "roles.json")
    require(isinstance(roles, dict) and roles, "roles.json: expected a nonempty object")
    for name, role in roles.items():
        identifier(name, r"[a-z0-9]+(?:-[a-z0-9]+)*", "Role name")
        fields(role, ("description", "github_teams", "discord_role_ids"), f"Role {name}")
        require(isinstance(role["description"], str) and role["description"].strip(),
                f"Role {name}: description must be a nonempty string")
        require(isinstance(role["github_teams"], dict), f"Role {name}: github_teams must be an object")
        for team, permission in role["github_teams"].items():
            identifier(team, r"[a-z0-9]+(?:-[a-z0-9]+)*", f"Role {name}: GitHub team slug")
            require(permission in ("member", "maintainer"),
                    f"Role {name}: team permission must be member or maintainer")
        string_list(role["discord_role_ids"], f"Role {name}: discord_role_ids")
        for role_id in role["discord_role_ids"]:
            snowflake(role_id, f"Role {name}: Discord role ID")
            require(role_id != organization["discord_server_id"],
                    f"Role {name}: the @everyone role cannot be assigned")
        require(role["github_teams"] or role["discord_role_ids"], f"Role {name}: grants no access")

    usernames, discord_ids = set(), set()
    for path in sorted(members_dir.iterdir()):
        require(not path.is_symlink(), f"{path}: symlinks are not supported")
        if path.name in (".gitkeep", "README.md") and path.is_file():
            continue
        require(path.is_file() and path.suffix == ".json", f"{path}: expected a flat members/<username>.json file")
        member = read_json(path)
        fields(member, ("github_username", "github_org_role", "discord_user_id", "roles"), path.name)
        username = member["github_username"]
        identifier(username, github_pattern, f"{path.name}: GitHub username")
        require("--" not in username, f"{path.name}: GitHub username cannot contain consecutive hyphens")
        require(username == username.lower() and path.stem == username,
                f"{path.name}: filename and github_username must match the lowercase GitHub username")
        require(username not in usernames, f"{path.name}: duplicate GitHub username")
        usernames.add(username)
        require(member["github_org_role"] in ("member", "admin"),
                f"{path.name}: github_org_role must be member or admin (organization owner)")
        snowflake(member["discord_user_id"], f"{path.name}: Discord user ID")
        require(member["discord_user_id"] not in discord_ids, f"{path.name}: duplicate Discord user ID")
        discord_ids.add(member["discord_user_id"])
        string_list(member["roles"], f"{path.name}: roles")
        require(all(role in roles for role in member["roles"]), f"{path.name}: unknown role in roles list")
    return len(usernames)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        count = validate(args.root)
    except ValidationError as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    print(f"Validated organization, roles, and {count} member file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
