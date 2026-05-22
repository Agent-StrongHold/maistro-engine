"""Credential provider catalog — labels and token-creation URLs for the UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CredentialProvider:
    id: str
    label: str
    description: str
    help_url: str
    placeholder: str = ""


_ATLASSIAN_MCP_TOKEN_URL = (
    "https://id.atlassian.com/manage-profile/security/api-tokens"
    "?autofillToken&expiryDays=max&appId=mcp&selectedScopes=all"
)

# on-prem Jira Server Atlassian (Jira/Confluence Data Center, ~Server v9).
# Per-product PAT pages, NOT the Atlassian Cloud token URL above. Bridge
# until ~2026-06-13 when migrates to Atlassian Cloud + Rovo MCP.
_SERVER_JIRA_PAT_URL = (
    "https://jira.example.com/secure/ViewProfile.jspa"
    "?selectedTab=com.atlassian.pats.pats-plugin:jira-user-personal-access-tokens"
)
_SERVER_CONFLUENCE_PAT_URL = (
    "https://wiki.example.com/plugins/personalaccesstokens/usertokens.action"
)

PM_CREDENTIAL_PROVIDERS: tuple[CredentialProvider, ...] = (
    CredentialProvider(
        id="jira",
        label="Jira API token",
        description=(
            "Primary path for containerized Hive: Atlassian Cloud API token "
            "for Jira REST. Pair with ATLASSIAN_SITE_URL in deployment env (e.g. https://your-org.atlassian.net)."
        ),
        help_url=_ATLASSIAN_MCP_TOKEN_URL,
        placeholder="Atlassian API token",
    ),
    CredentialProvider(
        id="atlassian_rovo_mcp",
        label="Atlassian Rovo MCP token",
        description=(
            "Optional headless bridge to Rovo MCP when your org admin enables API token auth. "
            "Used by the Hive process or an mcp-remote sidecar — not Cursor. Dev-only: OAuth via .cursor/mcp.json."
        ),
        help_url=_ATLASSIAN_MCP_TOKEN_URL,
        placeholder="Atlassian MCP-scoped API token",
    ),
    CredentialProvider(
        id="github",
        label="GitHub personal access token",
        description="Used for repository and PR context in program workflows.",
        help_url="https://github.com/settings/tokens?type=beta",
        placeholder="ghp_…",
    ),
    CredentialProvider(
        id="confluence",
        label="Confluence API token",
        description=(
            "Confluence REST for containerized deployments (same Atlassian token model as Jira)."
        ),
        help_url=_ATLASSIAN_MCP_TOKEN_URL,
        placeholder="Atlassian API token",
    ),
    # on-prem Jira Server Atlassian (Data Center) — 23-day bridge before Cloud migration.
    # PATs are separate per product, scoped per user; never put in .env.
    CredentialProvider(
        id="atlassian_server_jira",
        label="Jira PAT (on-prem)",
        description=(
            "Personal Access Token for jira.example.com (Jira Data Center). "
            "Routed through mcp-atlassian for all Jira tools. If you "
            "see auth errors after 2FA, regenerate the token at the link below."
        ),
        help_url=_SERVER_JIRA_PAT_URL,
        placeholder="Jira PAT",
    ),
    CredentialProvider(
        id="atlassian_server_confluence",
        label="Confluence PAT (on-prem)",
        description=(
            "Personal Access Token for wiki.example.com (Confluence Data Center). "
            "Used by mcp-atlassian for all Confluence tools."
        ),
        help_url=_SERVER_CONFLUENCE_PAT_URL,
        placeholder="Confluence PAT",
    ),
    CredentialProvider(
        id="airtable",
        label="Airtable personal access token",
        description=(
            "Used to poll Airtable bases for daily status updates. Create a token "
            "scoped to data.records:read on the base(s) you want the fleet to see."
        ),
        help_url="https://airtable.com/create/tokens/new",
        placeholder="pat… (Airtable PAT)",
    ),
)


def get_provider(provider_id: str) -> CredentialProvider | None:
    for provider in PM_CREDENTIAL_PROVIDERS:
        if provider.id == provider_id:
            return provider
    return None
