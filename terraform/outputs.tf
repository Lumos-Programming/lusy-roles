output "managed_members" {
  description = "このリポジトリで管理するGitHubユーザー名。"
  value       = sort(keys(local.members))
}
