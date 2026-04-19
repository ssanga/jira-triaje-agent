import logging
import os
from datetime import date

import requests

logger = logging.getLogger(__name__)

PRIORITY_NAME_TO_ID = {
    "Highest": "1",
    "High": "2",
    "Medium": "3",
    "Low": "4",
    "Lowest": "5",
}

_PAGE_SIZE = 100

_JQL_ALL_OPEN          = "project = PT AND statusCategory != Done ORDER BY created DESC"
_JQL_NEEDS_PRIORITY    = "project = PT AND statusCategory != Done AND cf[10112] is EMPTY ORDER BY created DESC"
_JQL_NEEDS_WORKTYPE    = "project = PT AND statusCategory != Done AND cf[10113] is EMPTY ORDER BY created DESC"
_JQL_NEEDS_ANY         = "project = PT AND statusCategory != Done AND (cf[10112] is EMPTY OR cf[10113] is EMPTY) ORDER BY created DESC"

_FIELDS_FULL      = ["summary", "description", "priority", "status"]
_FIELDS_BASIC     = ["summary", "description", "priority"]
_FIELDS_AUTO_APPLY = ["summary", "description", "priority", "issuetype"]


def _fetch_issues(jira_url: str, email: str, token: str, jql: str, fields: list[str]) -> list[dict]:
    url = f"{jira_url}/rest/api/3/search/jql"
    issues, next_page_token, page_num = [], None, 0
    while True:
        payload = {"jql": jql, "fields": fields, "maxResults": _PAGE_SIZE}
        if next_page_token:
            payload["nextPageToken"] = next_page_token
        page_num += 1
        logger.debug("POST %s | página %d | jql: %s", url, page_num, jql[:60])
        resp = requests.post(url, json=payload, auth=(email, token))
        resp.raise_for_status()
        data = resp.json()
        page = data.get("issues", [])
        issues.extend(page)
        logger.info("Página %d: %d tickets acumulados", page_num, len(issues))
        next_page_token = data.get("nextPageToken")
        if not next_page_token or len(page) < _PAGE_SIZE:
            break
    logger.info("Cargados %d tickets en memoria", len(issues))
    return issues


def get_all_open_tickets(jira_url: str, email: str, token: str) -> list[dict]:
    """Todos los tickets abiertos del proyecto — usado por la estrategia GitHub Pages."""
    return _fetch_issues(jira_url, email, token, _JQL_ALL_OPEN, _FIELDS_FULL)


def get_tickets_needing_priority(jira_url: str, email: str, token: str) -> list[dict]:
    """Tickets sin sugerencia de prioridad IA (campo customfield_10112 vacío)."""
    return _fetch_issues(jira_url, email, token, _JQL_NEEDS_PRIORITY, _FIELDS_BASIC)


def get_tickets_needing_worktype(jira_url: str, email: str, token: str) -> list[dict]:
    """Tickets sin sugerencia de tipología IA (campo customfield_10113 vacío)."""
    return _fetch_issues(jira_url, email, token, _JQL_NEEDS_WORKTYPE, _FIELDS_BASIC)


def get_tickets_needing_any_suggestion(jira_url: str, email: str, token: str) -> list[dict]:
    """Tickets sin al menos una sugerencia IA — usados por la estrategia auto-apply."""
    return _fetch_issues(jira_url, email, token, _JQL_NEEDS_ANY, _FIELDS_AUTO_APPLY)


def update_issue_type(jira_url: str, email: str, token: str, issue_id: str, type_name: str) -> None:
    url = f"{jira_url}/rest/api/3/issue/{issue_id}"
    resp = requests.put(url, json={"fields": {"issuetype": {"name": type_name}}}, auth=(email, token))
    resp.raise_for_status()
    logger.info("Tipo actualizado en issue %s → %s", issue_id, type_name)


def add_auto_apply_comment(
    jira_url: str, email: str, token: str, issue_id: str,
    old_priority: str, new_priority: str,
    old_type: str, new_type: str,
) -> None:
    fecha = date.today().isoformat()
    lines = [f"[Agente de triaje IA] Cambios aplicados automáticamente el {fecha}:"]
    if old_priority != new_priority:
        lines.append(f"  • Prioridad: {old_priority} → {new_priority}")
    if old_type != new_type:
        lines.append(f"  • Tipología: {old_type} → {new_type}")
    texto = "\n".join(lines)
    url = f"{jira_url}/rest/api/3/issue/{issue_id}/comment"
    payload = {
        "body": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": texto}]}],
        }
    }
    resp = requests.post(url, json=payload, auth=(email, token))
    resp.raise_for_status()
    logger.info("Comentario de trazabilidad añadido en issue %s", issue_id)


def extract_description(description_field) -> str:
    if not description_field:
        return ""
    if isinstance(description_field, str):
        return description_field
    # ADF format — extract plain text from content nodes
    texts = []
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                texts.append(node.get("text", ""))
            for child in node.get("content", []):
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(description_field)
    return " ".join(texts)


def update_issue_priority(jira_url: str, email: str, token: str, issue_id: str, priority_id: str) -> None:
    url = f"{jira_url}/rest/api/3/issue/{issue_id}"
    payload = {"fields": {"priority": {"id": priority_id}}}
    logger.debug("PUT %s | priority_id=%s", url, priority_id)
    resp = requests.put(url, json=payload, auth=(email, token))
    resp.raise_for_status()
    logger.info("Prioridad actualizada en issue %s → id=%s", issue_id, priority_id)


def set_suggested_priority(
    jira_url: str, email: str, token: str,
    issue_id: str, field_id: str, priority: str, reasoning: str,
) -> None:
    url = f"{jira_url}/rest/api/3/issue/{issue_id}"
    value = f"{priority} — {reasoning}" if reasoning else priority
    payload = {"fields": {field_id: value}}
    logger.debug("PUT %s | campo %s = %r", url, field_id, value)
    resp = requests.put(url, json=payload, auth=(email, token))
    resp.raise_for_status()
    logger.info("Campo IA actualizado en issue %s → %s", issue_id, priority)


def set_suggested_worktype(
    jira_url: str, email: str, token: str,
    issue_id: str, field_id: str, worktype: str, reasoning: str,
) -> None:
    url = f"{jira_url}/rest/api/3/issue/{issue_id}"
    value = f"{worktype} — {reasoning}" if reasoning else worktype
    payload = {"fields": {field_id: value}}
    resp = requests.put(url, json=payload, auth=(email, token))
    resp.raise_for_status()
    logger.info("Campo tipología actualizado en issue %s → %s", issue_id, worktype)


def clear_suggested_priority(
    jira_url: str, email: str, token: str,
    issue_id: str, field_id: str,
) -> None:
    url = f"{jira_url}/rest/api/3/issue/{issue_id}"
    payload = {"fields": {field_id: None}}
    resp = requests.put(url, json=payload, auth=(email, token))
    resp.raise_for_status()
    logger.info("Campo IA limpiado en issue %s", issue_id)


def _get_all_issues(jira_url: str, email: str, token: str, project_key: str) -> list[dict]:
    jql = f"project = {project_key} AND statusCategory != Done ORDER BY created DESC"
    return _fetch_issues(jira_url, email, token, jql, ["summary"])


def reset_priorities(project_key: str) -> None:
    """Resetea la prioridad a Medium y limpia el campo IA en todos los issues abiertos del proyecto."""
    jira_url = os.environ["JIRA_URL"]
    email = os.environ["JIRA_EMAIL"]
    token = os.environ["JIRA_TOKEN"]
    issues = _get_all_issues(jira_url, email, token, project_key)
    logger.info("Reseteando prioridad a Medium en %d issues...", len(issues))
    for issue in issues:
        url = f"{jira_url}/rest/api/3/issue/{issue['id']}"
        resp = requests.put(url, json={"fields": {"priority": {"id": "3"}, "customfield_10112": None, "customfield_10113": None}}, auth=(email, token))
        resp.raise_for_status()
        logger.info("  %s → Medium, campo IA limpiado", issue["key"])


def reset_issue_types(project_key: str) -> None:
    """Resetea el tipo de todos los issues abiertos del proyecto a Task."""
    jira_url = os.environ["JIRA_URL"]
    email = os.environ["JIRA_EMAIL"]
    token = os.environ["JIRA_TOKEN"]
    issues = _get_all_issues(jira_url, email, token, project_key)
    logger.info("Reseteando tipo a Task en %d issues...", len(issues))
    for issue in issues:
        url = f"{jira_url}/rest/api/3/issue/{issue['id']}"
        resp = requests.put(url, json={"fields": {"issuetype": {"name": "Task"}, "customfield_10113": None}}, auth=(email, token))
        resp.raise_for_status()
        logger.info("  %s → Task", issue["key"])


def add_triage_comment(jira_url: str, email: str, token: str, issue_id: str, priority_name: str) -> None:
    fecha = date.today().isoformat()
    texto = f"[Agente de triaje] Prioridad actualizada a {priority_name} — aprobado por usuario de negocio el {fecha}"
    url = f"{jira_url}/rest/api/3/issue/{issue_id}/comment"
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": texto}]}],
        }
    }
    logger.debug("POST %s | comentario de trazabilidad", url)
    resp = requests.post(url, json=payload, auth=(email, token))
    resp.raise_for_status()
    logger.info("Comentario añadido en issue %s", issue_id)
