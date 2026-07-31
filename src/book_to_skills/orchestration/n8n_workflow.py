"""n8n workflow builder for the book-to-skills pipeline.

Generates an n8n-compatible JSON workflow definition that can be
imported directly into n8n. Supports webhook triggers, CLI action
builders, and conditional branching for error handling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEBHOOK_ID = "webhook-trigger"
CLI_ACTION_ID = "cli-action"
IF_ERROR_ID = "if-error"
SUCCESS_ID = "success-branch"
ERROR_ID = "error-branch"
NOOP_ID = "noop-end"

DEFAULT_WEBHOOK_PATH = "book2skills-pipeline"


def build_n8n_workflow(
    *,
    name: str = "Book-to-Skills Pipeline",
    webhook_path: str = DEFAULT_WEBHOOK_PATH,
    stages: list[str] | None = None,
    api_url: str = "http://localhost:8000",
) -> dict[str, Any]:
    """Build a complete n8n workflow definition.

    The workflow is structured as:

        1. **Webhook trigger** — receives HTTP POST with ``file_path``
        2. **CLI action** — executes ``book2skills run pipeline`` via shell
        3. **Conditional (IF)** — checks exit code for success/failure
        4. **Success branch** — logs / stores the result
        5. **Error branch** — sends error notification
        6. **Noop end** — terminal node

    Args:
        name: Human-readable workflow name.
        webhook_path: URL path for the webhook trigger.
        stages: Optional list of pipeline stages to run.
        api_url: Base URL of the book-to-skills API (for reference).

    Returns:
        An n8n workflow definition as a dict, ready to be serialised to JSON.
    """
    stage_args = f"--stages {','.join(stages)}" if stages else ""

    nodes: list[dict[str, Any]] = [
        _webhook_node(webhook_path),
        _cli_action_node(stage_args),
        _if_error_node(),
        _success_node(api_url),
        _error_node(),
        _noop_node(),
    ]

    return {
        "name": name,
        "nodes": nodes,
        "connections": _build_connections(nodes),
        "pinData": {},
        "versionId": "1.0.0",
        "active": False,
        "settings": {
            "executionOrder": "v1",
            "timezone": "UTC",
        },
        "tags": [],
        "id": None,
        "meta": {
            "templateCredsSetupCompleted": True,
            "instanceId": "book-to-skills",
        },
    }


# ---------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------


def _webhook_node(path: str) -> dict[str, Any]:
    """Build a Webhook trigger node."""
    return {
        "id": WEBHOOK_ID,
        "name": "Webhook Trigger",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 1,
        "position": [250, 300],
        "parameters": {
            "path": path,
            "responseMode": "lastNode",
            "responseData": "",
            "options": {},
            "httpMethod": "POST",
            "respondWith": "text",
        },
    }


def _cli_action_node(stage_args: str) -> dict[str, Any]:
    """Build an ``exec`` node that runs the book2skills CLI."""
    cmd = f"book2skills run pipeline '{{{{ $json.file_path }}}}' {stage_args}".strip()
    return {
        "id": CLI_ACTION_ID,
        "name": "Run Pipeline (CLI)",
        "type": "n8n-nodes-base.exec",
        "typeVersion": 1,
        "position": [450, 300],
        "parameters": {
            "command": cmd,
            "options": {
                "shell": True,
                "timeout": 600,
            },
        },
    }


def _if_error_node() -> dict[str, Any]:
    """Build an IF node that checks the CLI exit code."""
    return {
        "id": IF_ERROR_ID,
        "name": "Success?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 1,
        "position": [650, 300],
        "parameters": {
            "conditions": {
                "string": [
                    {
                        "value1": "={{ $json.exitCode }}",
                        "operation": "equal",
                        "value2": "0",
                    }
                ],
            },
        },
    }


def _success_node(api_url: str) -> dict[str, Any]:
    """Build an HTTP Request node that marks success in the API."""
    return {
        "id": SUCCESS_ID,
        "name": "Log Success",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [850, 200],
        "parameters": {
            "method": "POST",
            "url": f"{api_url}/api/v1/pipeline/status/success-handler",
            "authentication": "none",
            "sendBody": True,
            "bodyParameters": {
                "parameters": [
                    {"name": "file_path", "value": "={{ $json.file_path }}"},
                    {"name": "exit_code", "value": "={{ $json.exitCode }}"},
                ],
            },
            "options": {"timeout": 30},
        },
    }


def _error_node() -> dict[str, Any]:
    """Build a node that sends error notification."""
    return {
        "id": ERROR_ID,
        "name": "Send Error Notification",
        "type": "n8n-nodes-base.noOp",
        "typeVersion": 1,
        "position": [850, 400],
        "parameters": {
            "message": "Pipeline execution failed",
        },
    }


def _noop_node() -> dict[str, Any]:
    """Build a terminal NoOp node."""
    return {
        "id": NOOP_ID,
        "name": "Done",
        "type": "n8n-nodes-base.noOp",
        "typeVersion": 1,
        "position": [1050, 300],
        "parameters": {},
    }


# ---------------------------------------------------------------------------
# Connection builder
# ---------------------------------------------------------------------------


def _build_connections(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the n8n connections object from the node list."""
    conn: dict[str, Any] = {}

    for i, node in enumerate(nodes):
        nxt = node.get("next", [])
        if not nxt and i < len(nodes) - 1:
            # Wire sequentially by default
            next_name = nodes[i + 1]["name"]
            if i == 2:  # IF node branches to success (index 3) and error (index 4)
                conn[node["name"]] = {
                    "main": [
                        [{"node": nodes[3]["name"], "type": "main", "index": 0}],
                        [{"node": nodes[4]["name"], "type": "main", "index": 0}],
                    ]
                }
                continue
            conn[node["name"]] = {"main": [[{"node": next_name, "type": "main", "index": 0}]]}
        elif nxt:
            out = []
            for target in nxt:
                out.append({"node": target["node"], "type": "main", "index": 0})
            if out:
                conn[node["name"]] = {"main": [out]}

    return conn


# ---------------------------------------------------------------------------
# Helper: CLI action builders
# ---------------------------------------------------------------------------


def build_cli_list_books() -> str:
    """Return the CLI command to list available books."""
    return "book2skills list books"


def build_cli_list_skills() -> str:
    """Return the CLI command to list generated skills."""
    return "book2skills list skills"


def build_cli_run_pipeline(
    file_path: str,
    stages: list[str] | None = None,
    incremental: bool = True,
) -> str:
    """Return the CLI command string for a pipeline run.

    Args:
        file_path: Path to the book file.
        stages: Optional list of stage names.
        incremental: Whether to enable incremental mode.

    Returns:
        A shell command string.
    """
    parts = ["book2skills", "run", "pipeline", file_path]
    if stages:
        parts.append(f"--stages {','.join(stages)}")
    if not incremental:
        parts.append("--no-incremental")
    return " ".join(parts)


def build_cli_run_stage(stage_name: str, file_path: str) -> str:
    """Return the CLI command string for a single stage run.

    Args:
        stage_name: Pipeline stage to run (e.g. ``extract``, ``chunk``).
        file_path: Path to the book file.

    Returns:
        A shell command string.
    """
    return f"book2skills run stage {stage_name} {file_path}"


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def export_workflow_to_json(
    *,
    name: str = "Book-to-Skills Pipeline",
    webhook_path: str = DEFAULT_WEBHOOK_PATH,
    stages: list[str] | None = None,
    api_url: str = "http://localhost:8000",
    output_path: str | None = None,
) -> str:
    """Build and serialise an n8n workflow to a JSON string.

    Args:
        name: Workflow name.
        webhook_path: Webhook URL path.
        stages: Optional stage list.
        api_url: Base API URL.
        output_path: If provided, write the JSON to this file.

    Returns:
        The JSON string of the workflow definition.
    """
    workflow = build_n8n_workflow(
        name=name,
        webhook_path=webhook_path,
        stages=stages,
        api_url=api_url,
    )

    json_str = json.dumps(workflow, indent=2, ensure_ascii=False)

    if output_path:
        _p = Path(output_path)
        _p.parent.mkdir(parents=True, exist_ok=True)
        _p.write_text(json_str, encoding="utf-8")

    return json_str
