#!/usr/bin/env python3
"""Scrub branded references from hive-conductor and push to upstream maistro-engine.

Run from the maistro-engine root:
    python3 scripts/scrub-and-push-upstream.py
"""
import pathlib
import os
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
base = ROOT / "packages" / "hive-conductor" / "backend"

def scrub():
    # --- chat_completion.py ---
    f = base / "services/chat_completion.py"
    t = f.read_text()
    t = t.replace('_JIRA_BASE = "https://myjira.disney.com"', '_JIRA_BASE = os.environ.get("JIRA_BASE_URL", "").rstrip("/")')
    t = t.replace("your Disney Jira PAT", "your Jira PAT")
    t = t.replace("Add your Disney Jira PAT", "Add your Jira PAT")
    t = t.replace('"project = JEDAI AND status = Blocked"', '"project = MY_PROJECT AND status = Blocked"')
    t = t.replace('confluence_base = "https://mywiki.disney.com"', 'confluence_base = os.environ.get("CONFLUENCE_BASE_URL", "")')
    t = t.replace("project = JEDAI AND updated", '" + os.environ.get("JIRA_PROJECT_KEY", "DEMO") + " AND updated')
    t = t.replace("project = JEDAI AND resolution", '" + os.environ.get("JIRA_PROJECT_KEY", "DEMO") + " AND resolution')
    f.write_text(t)
    print("✓ chat_completion.py")

    # --- engine.py ---
    f = base / "services/engine.py"
    t = f.read_text()
    t = t.replace("JedAI gateway", "LLM gateway")
    f.write_text(t)
    print("✓ engine.py")

    # --- opsagent.py ---
    f = base / "services/opsagent.py"
    t = f.read_text()
    t = t.replace("https://latest.opsagent.wdprapps.disney.com/api/v1", "")
    f.write_text(t)
    print("✓ opsagent.py")

    # --- pm_fleet_v2.py ---
    f = base / "services/pm_fleet_v2.py"
    t = f.read_text()
    t = t.replace('JIRA_PROJECT_KEY = "JEDAI"', 'JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "")')
    t = t.replace('"https://jira.disney.com"', '""')
    f.write_text(t)
    print("✓ pm_fleet_v2.py")

    # --- mcp_manifest_loader.py ---
    f = base / "services/mcp_manifest_loader.py"
    t = f.read_text()
    t = t.replace("JFC_MCP_OVERRIDE_DIR", "HIVE_MCP_OVERRIDE_DIR")
    t = t.replace("jedai-force-convergence", "host-platform")
    f.write_text(t)
    print("✓ mcp_manifest_loader.py")

    # --- daily_report.py ---
    f = base / "routes/daily_report.py"
    t = f.read_text()
    t = t.replace("JEDAI Jira project", "configured Jira project")
    t = t.replace("Disney Jira PAT", "Jira PAT")
    t = t.replace("Disney on-prem base URL", "Jira base URL")
    t = t.replace('"https://myjira.disney.com/rest/api/2/search"', 'f"{os.environ.get(\'JIRA_BASE_URL\', \'\')}/rest/api/2/search"')
    t = t.replace("project = JEDAI AND", 'project = {os.environ.get("JIRA_PROJECT_KEY", "")} AND')
    f.write_text(t)
    print("✓ daily_report.py")

    # --- daily_report_v2.py ---
    f = base / "routes/daily_report_v2.py"
    t = f.read_text()
    t = t.replace('"https://myjira.disney.com/rest/api/2/search"', 'f"{os.environ.get(\'JIRA_BASE_URL\', \'\')}/rest/api/2/search"')
    t = t.replace("project = JEDAI AND", 'project = {os.environ.get("JIRA_PROJECT_KEY", "")} AND')
    t = t.replace('base_id = "app0i9FWbZrctJuS6"', 'base_id = os.environ.get("AIRTABLE_BASE_ID", "")')
    t = t.replace("# JEDAI base", "# configured Airtable base")
    f.write_text(t)
    print("✓ daily_report_v2.py")

    # --- setup_checklist.py ---
    f = base / "routes/setup_checklist.py"
    t = f.read_text()
    t = t.replace("Disney's Atlassian Cloud migration", "Atlassian Cloud migration")
    t = t.replace("_DISNEY_CLOUD_MIGRATION", "_CLOUD_MIGRATION")
    t = t.replace("Disney Jira PAT", "Jira PAT")
    t = t.replace("Disney is on-prem (Server v9) until ~June 13, 2026; after that ", "Your instance may be Server or Cloud. After migration ")
    t = t.replace("https://myjira.disney.com/secure/ViewProfile.jspa", "${JIRA_BASE_URL}/secure/ViewProfile.jspa")
    f.write_text(t)
    print("✓ setup_checklist.py")

    # --- tests ---
    f = base / "tests/test_mcp_defaults_and_manifest.py"
    t = f.read_text()
    t = t.replace("JFC_MCP_OVERRIDE_DIR", "HIVE_MCP_OVERRIDE_DIR")
    f.write_text(t)
    print("✓ test_mcp_defaults_and_manifest.py")

    f = base / "tests/test_daily_status_runner.py"
    t = f.read_text()
    t = t.replace("https://myjira.disney.com", "https://jira.example.com")
    f.write_text(t)
    print("✓ test_daily_status_runner.py")

    f = base / "tests/test_mcp_client_full.py"
    t = f.read_text()
    t = t.replace("me@disney.com", "user@example.com")
    f.write_text(t)
    print("✓ test_mcp_client_full.py")

    print("\n✅ All 11 files scrubbed.")


def git_push():
    os.chdir(ROOT)
    branch = "feat/dashboard-widgets-agnostic"

    # Create branch
    subprocess.run(["git", "checkout", "-b", branch], check=False)

    # Stage hive-conductor changes
    subprocess.run(["git", "add", "-A", "packages/hive-conductor/"], check=True)

    # Commit
    msg = """feat: NL-to-widget dashboard, tool calling, streaming + agnostic scrub

- Dashboard with chat bar: natural language creates/removes widgets
- useDashboardLayout hook with persistence (GET/PUT /v1/dashboard/layout)
- DashboardChatBar component with suggestion chips
- create_widget + explain_widget tools in chat_completion
- dashboard_layout.py backend route for per-user layout persistence
- All branded references replaced with env-configurable values
  - JIRA_BASE_URL, JIRA_PROJECT_KEY, CONFLUENCE_BASE_URL from env
  - AIRTABLE_BASE_ID from env
  - HIVE_MCP_OVERRIDE_DIR (renamed from JFC_MCP_OVERRIDE_DIR)
  - OPSAGENT_URL defaults to empty (configure per deployment)
  - Test fixtures use example.com domains"""
    subprocess.run(["git", "commit", "-m", msg], check=True)

    # Ensure upstream remote exists
    subprocess.run(
        ["git", "remote", "add", "upstream", "https://github.com/BlakeMatthews-dev/maistro-engine.git"],
        check=False,
    )

    # Push
    result = subprocess.run(["git", "push", "-u", "upstream", branch], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"\n🚀 Pushed to upstream/{branch}")
        print("Open PR at: https://github.com/BlakeMatthews-dev/maistro-engine/compare/main...feat/dashboard-widgets-agnostic")
    else:
        print(f"\n⚠️  Push failed: {result.stderr}")
        print("You may need to authenticate. Run manually:")
        print(f"  cd {ROOT}")
        print(f"  git push -u upstream {branch}")


if __name__ == "__main__":
    print("=" * 60)
    print("Scrubbing branded references...")
    print("=" * 60)
    scrub()
    print()
    print("=" * 60)
    print("Committing and pushing to upstream...")
    print("=" * 60)
    git_push()
