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

# Disney on-prem Atlassian (Jira/Confluence Data Center, ~Server v9).
# Per-product PAT pages, NOT the Atlassian Cloud token URL above. Bridge
# until ~2026-06-13 when Disney migrates to Atlassian Cloud + Rovo MCP.
_DISNEY_JIRA_PAT_URL = (
    "https://myjira.disney.com/secure/ViewProfile.jspa"
    "?selectedTab=com.atlassian.pats.pats-plugin:jira-user-personal-access-tokens"
)
_DISNEY_CONFLUENCE_PAT_URL = (
    "https://mywiki.disney.com/plugins/personalaccesstokens/usertokens.action"
)

PM_CREDENTIAL_PROVIDERS: tuple[CredentialProvider, ...] = (
    CredentialProvider(
        id="jira",
        label="Jira API token",
        description=(
            "Primary path for containerized Hive (Force Convergence): Atlassian Cloud API token "
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
    # Disney on-prem Atlassian (Data Center) — 23-day bridge before Cloud migration.
    # PATs are separate per product, scoped per user; never put in .env.
    CredentialProvider(
        id="atlassian_server_jira",
        label="Disney Jira PAT (on-prem)",
        description=(
            "Personal Access Token for myjira.disney.com (Jira Data Center). "
            "Routed through mcp-jedai-atlassian for all Jira tools. If you "
            "see auth errors after 2FA, regenerate the token at the link below."
        ),
        help_url=_DISNEY_JIRA_PAT_URL,
        placeholder="Disney Jira PAT",
    ),
    CredentialProvider(
        id="atlassian_server_confluence",
        label="Disney Confluence PAT (on-prem)",
        description=(
            "Personal Access Token for mywiki.disney.com (Confluence Data Center). "
            "Used by mcp-jedai-atlassian for all Confluence tools."
        ),
        help_url=_DISNEY_CONFLUENCE_PAT_URL,
        placeholder="Disney Confluence PAT",
    ),
)


def get_provider(provider_id: str) -> CredentialProvider | None:
    for provider in PM_CREDENTIAL_PROVIDERS:
        if provider.id == provider_id:
            return provider
    return None
