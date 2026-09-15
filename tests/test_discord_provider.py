"""実プロバイダーとローカルREST APIでimport・削除planを検証する。"""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUILD = "111111111111111111"
USER = "222222222222222222"
WANTED = "333333333333333333"
EXTRA = "444444444444444444"


class DiscordProviderTests(unittest.TestCase):
    def test_import_and_deletion_plan_use_only_rest_reads(self):
        requests = []
        status = [200]

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.command, self.path))
                expected = self.path == f"/guilds/{GUILD}/members/{USER}"
                code = status[0] if expected else 404
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                body = {"roles": [WANTED, EXTRA]} if code == 200 else {"code": 50013, "message": "Missing Permissions"}
                self.wfile.write(json.dumps(body).encode())

            def do_PUT(self):
                requests.append((self.command, self.path))
                self.send_error(405)

            do_DELETE = do_PUT
            do_PATCH = do_PUT
            do_POST = do_PUT

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server, tempfile.TemporaryDirectory() as temp:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.shutdown)
            directory = Path(temp)
            shutil.copyfile(ROOT / "terraform/versions.tf", directory / "versions.tf")
            shutil.copyfile(ROOT / "terraform/.terraform.lock.hcl", directory / ".terraform.lock.hcl")
            env = {**os.environ, "DISCORD_BOT_TOKEN": "local-test-token",
                   "DISCORD_API_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                   "TF_IN_AUTOMATION": "true", "TF_INPUT": "false"}

            def terraform(*args, success=True):
                result = subprocess.run(["aqua", "exec", "--", "terraform", f"-chdir={directory}", *args],
                                        env=env, capture_output=True, text=True, timeout=60)
                if success:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result

            def configure(roles):
                (directory / "main.tf.json").write_text(json.dumps({
                    "provider": {"discord": {}},
                    "resource": {"discord_member_role": {"members": {
                        "for_each": {role: role for role in roles},
                        "guild_id": GUILD, "user_id": USER, "role_id": "${each.value}",
                    }}},
                }))

            configure([WANTED, EXTRA])
            terraform("init", "-input=false", "-lockfile=readonly",
                      f"-plugin-dir={ROOT / 'terraform/.terraform/providers'}")
            for role in (WANTED, EXTRA):
                terraform("import", "-input=false", f'discord_member_role.members["{role}"]', f"{GUILD}:{USER}:{role}")
            configure([WANTED])
            terraform("plan", "-input=false", "-out=roles.tfplan")
            plan = json.loads(terraform("show", "-json", "roles.tfplan").stdout)
            changes = {item["index"]: item["change"]["actions"] for item in plan["resource_changes"]}
            self.assertEqual(changes, {WANTED: ["no-op"], EXTRA: ["delete"]})

            # 認証失敗で既存の割り当てを消失扱いにしない。
            status[0] = 403
            failure = terraform("plan", "-input=false", "-no-color", success=False)
            self.assertNotEqual(failure.returncode, 0)
            self.assertIn("403 Forbidden", failure.stderr)
            self.assertGreaterEqual(len(requests), 5)
            self.assertEqual(set(requests), {("GET", f"/guilds/{GUILD}/members/{USER}")})
