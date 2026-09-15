import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_membership_state import (  # noqa: E402
    API, address, adoption_config, discover, import_existing, prepare_directory, pull_state, targets,
)
from validate import ValidationError  # noqa: E402

GUILD = "111111111111111111"
USER = "222222222222222222"
WANTED = "333333333333333333"
EXTRA = "444444444444444444"
MANAGED = "555555555555555555"
ORGANIZATION = {"github_organization": "example-org", "discord_server_id": GUILD}
MEMBERS = {"alice": {"github_username": "alice", "github_org_role": "admin",
                     "discord_user_id": USER, "roles": ["lusy"]}}


class FakeAPI:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, path, *, absent_ok=False):
        self.calls.append(path)
        if path not in self.responses:
            raise AssertionError(f"Unexpected API call: {path}")
        return self.responses[path]

    def pages(self, path):
        return iter(self.get(path))


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.github = FakeAPI({
            "/orgs/example-org/memberships/alice": {"role": "admin", "state": "active"},
            "/orgs/example-org/teams": [
                {"id": 1, "slug": "lusy"}, {"id": 2, "slug": "lusy-lumos-web"}, {"id": 3, "slug": "old"},
            ],
            "/orgs/example-org/teams/lusy/members": [
                {"login": "Alice", "role": "maintainer", "inherited": True},
            ],
            "/orgs/example-org/teams/lusy-lumos-web/members": [
                {"login": "Alice", "role": "maintainer", "inherited": False},
            ],
            "/orgs/example-org/teams/old/members": [
                {"login": "Alice", "role": "maintainer", "inherited": False},
                {"login": "Bob", "role": "member", "inherited": False},
            ],
        })
        self.discord = FakeAPI({
            f"/guilds/{GUILD}/roles": [
                {"id": role, "managed": role == MANAGED} for role in (GUILD, WANTED, EXTRA, MANAGED)
            ],
            f"/guilds/{GUILD}/members/{USER}": {"roles": [GUILD, WANTED, EXTRA, MANAGED]},
        })

    def discover(self, members=MEMBERS, state=None):
        return discover(ORGANIZATION, members, state or {}, self.github, self.discord)

    def test_adopts_desired_and_extra_grants_for_declared_person_only(self):
        grants = self.discover()
        self.assertEqual(set(grants), {
            address("github_membership", "alice"),
            address("github_team_membership", "alice/lusy-lumos-web"),
            address("github_team_membership", "alice/old"),
            address("discord_role_member", f"{GUILD}/{USER}/{WANTED}"),
            address("discord_role_member", f"{GUILD}/{USER}/{EXTRA}"),
        })
        self.assertEqual(grants[address("github_team_membership", "alice/old")]["id"], "3:alice")
        self.assertEqual(grants[address("github_team_membership", "alice/old")]["attributes"]["role"], "maintainer")
        self.assertEqual(grants[address("github_membership", "alice")]["attributes"]["role"], "admin")

    def test_missing_inheritance_metadata_fails_instead_of_guessing(self):
        del self.github.responses["/orgs/example-org/teams/lusy/members"][0]["inherited"]
        with self.assertRaisesRegex(ValidationError, "区別できません"):
            self.discover()

    def test_offboarded_identity_still_discovers_out_of_band_grants(self):
        state = {"outputs": {"managed_identities": {"value": {"alice": {
            **ORGANIZATION, "discord_user_id": USER,
        }}}}}
        self.assertEqual(self.discover({}, state), self.discover())

    def test_legacy_state_and_discord_account_changes_include_both_accounts(self):
        old_user = "666666666666666666"
        state = {"resources": [{"mode": "managed", "type": "discord_role_member", "name": "members",
                                "instances": [{"attributes": {"guild_id": GUILD, "user_id": old_user}}]}]}
        usernames, users = targets(ORGANIZATION, MEMBERS, state)
        self.assertEqual(usernames, {"alice"})
        self.assertEqual(users, {(GUILD, USER), (GUILD, old_user)})

    def test_no_members_and_no_state_do_not_inventory_other_people(self):
        self.assertEqual(self.discover({}), {})
        self.assertEqual(self.github.calls, [])
        self.assertEqual(self.discord.calls, [])

    def test_missing_memberships_are_not_imported(self):
        self.github.responses["/orgs/example-org/memberships/alice"] = None
        self.discord.responses[f"/guilds/{GUILD}/members/{USER}"] = None
        self.github.responses["/orgs/example-org/teams"] = []
        self.assertEqual(self.discover(), {})

    def test_pending_team_invitation_is_imported_with_real_team_role(self):
        self.github.responses["/orgs/example-org/memberships/alice"]["state"] = "pending"
        for slug in ("lusy", "lusy-lumos-web", "old"):
            self.github.responses[f"/orgs/example-org/teams/{slug}/members"] = []
            self.github.responses[f"/orgs/example-org/teams/{slug}/invitations"] = []
        self.github.responses["/orgs/example-org/teams/old/invitations"] = [{"login": "Alice"}]
        self.github.responses["/orgs/example-org/teams/old/memberships/alice"] = {"role": "maintainer", "state": "pending"}
        grants = self.discover()
        self.assertEqual(grants[address("github_team_membership", "alice/old")]["id"], "3:alice")

    def test_changed_organization_requires_state_migration(self):
        state = {"outputs": {"managed_identities": {"value": {"alice": {
            **ORGANIZATION, "github_organization": "another-org", "discord_user_id": USER,
        }}}}}
        with self.assertRaisesRegex(ValidationError, "stateの移行"):
            self.discover(state=state)

    def test_missing_role_metadata_stops_incomplete_discovery(self):
        self.discord.responses[f"/guilds/{GUILD}/roles"] = []
        with self.assertRaisesRegex(ValidationError, "再実行"):
            self.discover()

    def test_import_skips_tracked_addresses_and_never_applies(self):
        grants = self.discover()
        state = {"resources": [{"mode": "managed", "type": "github_membership", "name": "members",
                                "instances": [{"index_key": "alice"}]}]}
        with patch("prepare_membership_state.terraform") as run:
            import_existing(Path("/scratch"), grants, state)
        self.assertEqual(run.call_count, 4)
        for call in run.call_args_list:
            self.assertEqual(call.args[0:2], (Path("/scratch"), "import"))
            self.assertNotIn(address("github_membership", "alice"), call.args)

    def test_preview_has_only_local_state_and_approved_adoption_has_backend(self):
        grants = self.discover()
        state = {"version": 4, "serial": 1, "resources": []}
        with tempfile.TemporaryDirectory() as temp:
            preview, approved = Path(temp) / "preview", Path(temp) / "approved"
            prepare_directory(ROOT / "terraform", preview, ORGANIZATION, grants, state)
            prepare_directory(ROOT / "terraform", approved, ORGANIZATION, grants, state, adopt_remote=True)
            self.assertFalse((preview / "backend.tf").exists())
            self.assertEqual(json.loads((preview / "terraform.tfstate").read_text()), state)
            self.assertEqual((approved / "backend.tf").read_bytes(), (ROOT / "terraform/backend.tf").read_bytes())
            self.assertFalse((approved / "terraform.tfstate").exists())
            config = json.loads((preview / "adoption.tf.json").read_text())
            self.assertEqual(config, adoption_config(ORGANIZATION, grants))
            self.assertIn("alice/old", config["resource"]["github_team_membership"]["members"]["for_each"])


class APIClientTests(unittest.TestCase):
    def test_initial_missing_state_is_allowed_but_backend_failures_stop(self):
        with patch("prepare_membership_state.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 1, "", "No state file was found!")):
            self.assertEqual(pull_state(Path("/source")), {})
        with patch("prepare_membership_state.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 1, "", "GCS HTTP 403")), patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(subprocess.CalledProcessError):
                pull_state(Path("/source"))

    def test_permission_and_rate_limit_failures_are_never_treated_as_absence(self):
        api = API("https://api.github.com", {})
        for status in (401, 403, 429, 500):
            with self.subTest(status=status), patch("prepare_membership_state.urlopen", side_effect=HTTPError(
                    "https://api.github.com/path", status, "failure", {}, io.BytesIO(b"secret body"))):
                with self.assertRaisesRegex(ValidationError, f"HTTP {status}") as caught:
                    api.get("/path", absent_ok=True)
                self.assertNotIn("secret", str(caught.exception))

    def test_404_is_absence_only_when_explicitly_allowed(self):
        api = API("https://api.github.com", {})
        with patch("prepare_membership_state.urlopen", side_effect=HTTPError("", 404, "", {}, None)):
            self.assertIsNone(api.get("/membership", absent_ok=True))
            with self.assertRaises(ValidationError):
                api.get("/roles")

    def test_pagination_reads_beyond_first_page(self):
        api = API("https://api.github.com", {})
        with patch.object(api, "get", side_effect=[list(range(100)), [100]]) as get:
            self.assertEqual(list(api.pages("/teams")), list(range(101)))
        self.assertEqual([call.args[0] for call in get.call_args_list],
                         ["/teams?per_page=100&page=1", "/teams?per_page=100&page=2"])
