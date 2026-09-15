locals {
  organization = yamldecode(file("${var.config_path}/organization.yaml"))
  roles        = yamldecode(file("${var.config_path}/roles.yaml"))
  members = {
    for filename in fileset(var.members_path, "*.yaml") :
    trimsuffix(filename, ".yaml") => yamldecode(file("${var.members_path}/${filename}"))
  }

  member_teams = {
    for key, member in local.members : key => toset(flatten([
      for role in member.roles : keys(local.roles[role].github_teams)
    ]))
  }

  github_team_memberships = merge({}, [
    for key, member in local.members : {
      for team in local.member_teams[key] : "${key}/${team}" => {
        member_key = key
        team       = team
        # Organization所有者はチームのmaintainerにする必要がある。
        # 複数のロールが同じチームを指定した場合は高い権限を採用する。
        role = member.github_org_role == "admin" || anytrue([
          for role in member.roles : lookup(local.roles[role].github_teams, team, "member") == "maintainer"
        ]) ? "maintainer" : "member"
      }
    }
  ]...)

  discord_member_roles = {
    for key, member in local.members : key => toset(flatten([
      for role in member.roles : local.roles[role].discord_role_ids
    ]))
  }

  discord_role_memberships = merge({}, [
    for key, member in local.members : {
      for role_id in local.discord_member_roles[key] :
      "${local.organization.discord_server_id}/${member.discord_user_id}/${role_id}" => {
        user_id = member.discord_user_id
        role_id = role_id
      }
    }
  ]...)
}

resource "github_membership" "members" {
  for_each = local.members

  username = each.value.github_username
  role     = each.value.github_org_role
}

resource "github_team_membership" "members" {
  for_each = local.github_team_memberships

  team_id  = each.value.team
  username = github_membership.members[each.value.member_key].username
  role     = each.value.role
}

# 個別のロール付与APIを使い、管理対象外のロールには触れない。
# 全IDをキーに含め、ID変更時は旧権限の削除と新権限の作成を行う。
resource "discord_role_member" "members" {
  for_each = local.discord_role_memberships

  guild_id = local.organization.discord_server_id
  user_id  = each.value.user_id
  role_id  = each.value.role_id
}
