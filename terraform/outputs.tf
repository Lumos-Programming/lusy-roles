output "managed_members" {
  description = "このリポジトリで管理するGitHubユーザー名。"
  value       = sort(keys(local.members))
}

output "managed_identities" {
  description = "ファイル削除後も既存の割り当てを検出するための管理対象アカウント。"
  value = {
    for key, member in local.members : key => {
      github_organization = local.organization.github_organization
      discord_server_id   = local.organization.discord_server_id
      discord_user_id     = member.discord_user_id
    }
  }
}
