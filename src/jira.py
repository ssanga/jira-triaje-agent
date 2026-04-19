import logging
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

# _JQL = "project = PT AND issuetype = Bug AND statusCategory != Done ORDER BY created DESC"
_JQL = "project = PT AND statusCategory != Done ORDER BY created DESC"
_PAGE_SIZE = 100


def get_all_jira_bugs(jira_url: str, email: str, token: str) -> list[dict]:
    url = f"{jira_url}/rest/api/3/search/jql"
    issues = []
    next_page_token = None
    page_num = 0

    while True:
        payload = {
            "jql": _JQL,
            "fields": ["summary", "description", "priority", "status"],
            "maxResults": _PAGE_SIZE,
        }
        if next_page_token:
            payload["nextPageToken"] = next_page_token

        page_num += 1
        logger.debug("POST %s | página %d", url, page_num)
        resp = requests.post(url, json=payload, auth=(email, token))
        resp.raise_for_status()

        data = resp.json()
        page = data.get("issues", [])
        issues.extend(page)
        logger.info("Página %d: %d tickets acumulados", page_num, len(issues))

        next_page_token = data.get("nextPageToken")
        if not next_page_token or len(page) < _PAGE_SIZE:
            break

    logger.info("Cargados %d bugs en memoria", len(issues))
    return issues


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


def clear_suggested_priority(
    jira_url: str, email: str, token: str,
    issue_id: str, field_id: str,
) -> None:
    url = f"{jira_url}/rest/api/3/issue/{issue_id}"
    payload = {"fields": {field_id: None}}
    resp = requests.put(url, json=payload, auth=(email, token))
    resp.raise_for_status()
    logger.info("Campo IA limpiado en issue %s", issue_id)


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
