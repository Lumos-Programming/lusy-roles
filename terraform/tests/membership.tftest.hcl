mock_provider "github" {}
mock_provider "discord" {}

variables {
  config_path = "tests/fixtures/config"
}

run "onboard_and_merge_overlapping_roles" {
  command = apply
  variables {
    members_path = "tests/fixtures/full"
  }

  assert {
    condition     = length(github_membership.members) == 2 && length(github_team_membership.members) == 3
    error_message = "Create one organization membership per person and deduplicate team grants."
  }
  assert {
    condition     = github_team_membership.members["alice/lusy"].role == "maintainer"
    error_message = "Overlapping grants must retain the higher team permission."
  }
  assert {
    condition     = github_team_membership.members["bob/lusy"].role == "maintainer"
    error_message = "Organization owners must be team maintainers."
  }
  assert {
    condition     = length(discord_role_member.members) == 3
    error_message = "重複するDiscordロールを統合し、ユーザーとロールの組ごとに管理する。"
  }
  assert {
    condition     = discord_role_member.members["111111111111111111/444444444444444444/222222222222222222"].user_id == "444444444444444444" && discord_role_member.members["111111111111111111/444444444444444444/222222222222222222"].guild_id == "111111111111111111"
    error_message = "Discord grants must target the configured server and person."
  }
}

run "remove_member_and_downgrade_roles" {
  command = apply
  variables {
    members_path = "tests/fixtures/reduced"
  }
  assert {
    condition     = length(github_membership.members) == 1 && length(github_team_membership.members) == 1 && length(discord_role_member.members) == 1
    error_message = "Removing a member must remove all their managed memberships."
  }
  assert {
    condition     = github_team_membership.members["alice/lusy"].role == "member" && length(discord_role_member.members) == 1
    error_message = "Removing a role must revoke elevated access and keep remaining grants."
  }
}

run "remove_last_discord_grant" {
  command = apply
  variables {
    members_path = "tests/fixtures/github_only"
  }
  assert {
    condition     = length(discord_role_member.members) == 0 && length(github_team_membership.members) == 1
    error_message = "Removing the last Discord grant must destroy the role resource while retaining GitHub access."
  }
}

run "retain_organization_only" {
  command = apply
  variables {
    members_path = "tests/fixtures/org_only"
  }
  assert {
    condition     = length(github_membership.members) == 1 && length(github_team_membership.members) == 0 && length(discord_role_member.members) == 0
    error_message = "An empty role list must retain only organization membership."
  }
}

run "offboard_last_member" {
  command = apply
  variables {
    members_path = "tests/fixtures/empty"
  }
  assert {
    condition     = length(github_membership.members) == 0 && length(github_team_membership.members) == 0 && length(discord_role_member.members) == 0
    error_message = "An empty directory must remove every managed membership."
  }
}

run "validate_current_roster" {
  command = plan
  variables {
    config_path  = "../config"
    members_path = "../members"
  }
}
