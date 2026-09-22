"""External Office, Microsoft Graph and GovDash integration boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from typing import Any

from .configuration import AppConfig
from .evidence import validate_artifacts


OFFICE_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "office.word.inspect_structure",
        "description": "Inspect headings, tables, comments, revisions and metadata for a permitted Word document.",
        "requires": ["path", "expectedVersion"],
    },
    {
        "name": "office.word.revise_range_tracked",
        "description": "Apply bounded tracked changes in a review copy of a permitted Word document.",
        "requires": ["path", "range", "replacement", "operationId", "expectedVersion"],
    },
    {
        "name": "office.word.add_comment",
        "description": "Add a comment to a bounded Word range in a review copy.",
        "requires": ["path", "range", "comment", "operationId", "expectedVersion"],
    },
    {
        "name": "office.word.export_pdf",
        "description": "Export a validated Word review copy to PDF.",
        "requires": ["path", "operationId", "expectedVersion"],
    },
    {
        "name": "office.excel.read_ranges",
        "description": "Read tables, named ranges, formulas and values from a permitted workbook.",
        "requires": ["path", "ranges", "expectedVersion"],
    },
    {
        "name": "office.excel.update_ranges",
        "description": "Update bounded ranges/formulas in a review copy, recalculate, and inspect formula errors.",
        "requires": ["path", "updates", "operationId", "expectedVersion"],
    },
    {
        "name": "office.powerpoint.populate_template",
        "description": "Populate a permitted PowerPoint template and export rendered review slides.",
        "requires": ["templatePath", "updates", "operationId", "expectedVersion"],
    },
    {
        "name": "files.validate_artifacts",
        "description": "Independently inspect model-reported local artifact paths under permitted workspace roots.",
        "requires": ["artifacts"],
    },
]


@dataclass(frozen=True)
class IntegrationStatus:
    configured: bool
    operational: bool
    state: str
    notes: tuple[str, ...]
    capabilities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "operational": self.operational,
            "state": self.state,
            "notes": list(self.notes),
            "capabilities": list(self.capabilities),
        }


class IntegrationManager:
    def __init__(self, config: AppConfig):
        self.config = config

    def status(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace_status(),
            "office": self.office_status(),
            "microsoftGraph": self.microsoft_graph_status(),
            "govdash": self.govdash_status(),
            "toolSchemas": OFFICE_TOOL_SCHEMAS,
        }

    def workspace_status(self) -> dict[str, Any]:
        roots = [str(root) for root in self.config.workspace.allowed_roots]
        notes = [] if roots else ["No permitted workspace roots are configured; artifact inspection will not validate local paths."]
        return {
            "configured": bool(roots),
            "operational": bool(roots),
            "state": "configured" if roots else "missing_workspace_roots",
            "allowedRoots": roots,
            "notes": notes,
        }

    def office_status(self) -> dict[str, Any]:
        if not self.config.office.enabled:
            return IntegrationStatus(
                configured=False,
                operational=False,
                state="disabled",
                notes=("Enable office.enabled on Windows to use installed Office automation.",),
                capabilities=tuple(schema["name"] for schema in OFFICE_TOOL_SCHEMAS if schema["name"].startswith("office.")),
            ).to_dict()
        notes: list[str] = []
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if os.name != "nt":
            notes.append("Installed Office automation requires an interactive Windows session.")
        if not powershell and not self.config.office.bridge_executable:
            notes.append("No PowerShell/bridge executable was found for Office automation.")
        operational = os.name == "nt" and bool(powershell or self.config.office.bridge_executable)
        return IntegrationStatus(
            configured=True,
            operational=operational,
            state="operational" if operational else "blocked",
            notes=tuple(notes) or ("Office bridge is configured for the signed-in Windows user session.",),
            capabilities=tuple(schema["name"] for schema in OFFICE_TOOL_SCHEMAS if schema["name"].startswith("office.")),
        ).to_dict()

    def microsoft_graph_status(self) -> dict[str, Any]:
        config = self.config.microsoft_graph
        token_present = bool(os.environ.get(config.token_environment_variable))
        endpoint = {
            "commercial": "https://graph.microsoft.com",
            "gcc": "https://graph.microsoft.com",
            "gcc_high": "https://graph.microsoft.us",
            "dod": "https://dod-graph.microsoft.us",
        }[config.cloud]
        notes = []
        if not config.enabled:
            notes.append("Microsoft Graph is disabled.")
        if config.enabled and not config.tenant_id:
            notes.append("Tenant ID is not configured.")
        if config.enabled and not config.client_id:
            notes.append("Client ID is not configured.")
        if config.enabled and not token_present:
            notes.append(f"Access token environment variable {config.token_environment_variable} is not set.")
        operational = config.enabled and bool(config.tenant_id and config.client_id and token_present)
        return {
            "configured": config.enabled,
            "authenticated": token_present,
            "operational": operational,
            "state": "operational" if operational else "blocked",
            "cloud": config.cloud,
            "endpoint": endpoint,
            "notes": notes,
            "capabilities": [
                "graph.files.browse_selected_locations",
                "graph.files.read_metadata",
                "graph.files.upload_review_output",
                "graph.excel.create_session_when_supported",
            ],
        }

    def govdash_status(self) -> dict[str, Any]:
        config = self.config.govdash
        notes = []
        if not config.enabled:
            notes.append("GovDash integration is disabled.")
        if config.enabled and config.route == "api":
            notes.append("No tenant-specific GovDash API endpoint is configured in Coven; API writes remain blocked until verified.")
        if config.enabled and config.route == "browser" and config.browser_profile_dir is None:
            notes.append("Browser route requires a dedicated GovDash browser profile directory.")
        if config.enabled and config.route == "sharepoint" and not config.sharepoint_root:
            notes.append("SharePoint exchange route requires a configured selected SharePoint root/location.")
        operational = config.enabled and not notes
        return {
            "configured": config.enabled,
            "operational": operational,
            "state": "operational" if operational else "blocked",
            "route": config.route,
            "baseUrl": config.base_url,
            "sharePointRoot": config.sharepoint_root,
            "browserProfileDir": str(config.browser_profile_dir) if config.browser_profile_dir else "",
            "notes": notes,
            "capabilities": [
                "govdash.sharepoint.retrieve_exported_proposal",
                "govdash.sharepoint.return_reviewed_version",
                "govdash.browser.verify_selected_opportunity",
            ],
        }

    def validate_artifact_claims(self, artifacts: list[Any]) -> list[dict[str, Any]]:
        return validate_artifacts(artifacts, allowed_roots=self.config.workspace.allowed_roots)

    def execute_office_operation(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "files.validate_artifacts":
            artifacts = payload.get("artifacts")
            if not isinstance(artifacts, list):
                raise ValueError("artifacts must be an array.")
            return {"artifacts": self.validate_artifact_claims(artifacts)}
        status = self.office_status()
        if not status["operational"]:
            raise RuntimeError("; ".join(status["notes"]) or "Office bridge is unavailable.")
        raise RuntimeError(
            "Native Office mutation is configured but not executed by this portable backend without the Windows bridge worker."
        )
