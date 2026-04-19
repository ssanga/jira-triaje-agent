import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from src.ai import make_client, suggest_priority_all, suggest_worktype_all
from src.jira import (
    PRIORITY_NAME_TO_ID,
    add_auto_apply_comment,
    extract_description,
    get_all_open_tickets,
    get_tickets_needing_any_suggestion,
    get_tickets_needing_priority,
    get_tickets_needing_worktype,
    set_suggested_priority,
    set_suggested_worktype,
    update_issue_priority,
    update_issue_type,
)

load_dotenv()

logger = logging.getLogger(__name__)

JIRA_URL = os.environ["JIRA_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_TOKEN"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

OUTPUT_PATH = Path(__file__).parent / "data" / "triage.json"

# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_ticket_payload(issue: dict) -> dict:
    fields = issue["fields"]
    priority_obj = fields.get("priority") or {}
    current_priority = priority_obj.get("name", "Medium")
    return {
        "key": issue["key"],
        "id": issue["id"],
        "summary": fields.get("summary", ""),
        "description": extract_description(fields.get("description")),
        "current_priority": current_priority,
        "current_priority_id": PRIORITY_NAME_TO_ID.get(current_priority, "3"),
        "jira_url": f"{JIRA_URL}/browse/{issue['key']}",
    }

# ── Estrategias ────────────────────────────────────────────────────────────────
# Cada estrategia es autónoma: obtiene sus propios tickets y actúa de forma
# independiente. Para añadir una nueva alternativa, implementa una función sin
# parámetros y añádela a ACTIVE_STRATEGIES.

def strategy_github_pages() -> None:
    """Obtiene todos los tickets abiertos, triaja prioridad con IA y escribe triage.json."""
    issues = get_all_open_tickets(JIRA_URL, JIRA_EMAIL, JIRA_TOKEN)
    tickets = [_to_ticket_payload(i) for i in issues]

    client = make_client(GITHUB_TOKEN)
    ai_results = suggest_priority_all(client, tickets)

    results = []
    for t in tickets:
        ai = ai_results.get(t["key"])
        if not ai:
            logger.warning("%s: sin respuesta de la IA, omitido", t["key"])
            continue
        proposed_priority = ai.get("priority", t["current_priority"])
        results.append({
            **t,
            "proposed_priority": proposed_priority,
            "proposed_priority_id": PRIORITY_NAME_TO_ID.get(proposed_priority, t["current_priority_id"]),
            "reasoning": ai.get("reasoning", ""),
            "changed": proposed_priority != t["current_priority"],
        })
        logger.info("%s: %s → %s", t["key"], t["current_priority"], proposed_priority)

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    changed = sum(1 for r in results if r["changed"])
    logger.info("[GitHub Pages] %d tickets escritos en %s (%d con cambio)", len(results), OUTPUT_PATH, changed)


def strategy_jira_field() -> None:
    """Escribe sugerencias de prioridad y tipología solo en tickets que aún no las tienen."""
    client = make_client(GITHUB_TOKEN)
    priority_field = "customfield_10112"
    worktype_field = "customfield_10113"

    # ── Prioridad ──
    issues = get_tickets_needing_priority(JIRA_URL, JIRA_EMAIL, JIRA_TOKEN)
    if issues:
        tickets = [_to_ticket_payload(i) for i in issues]
        logger.info("[Jira Field] Sugiriendo prioridad para %d tickets sin campo IA...", len(tickets))
        ai_results = suggest_priority_all(client, tickets)
        ok = 0
        for t in tickets:
            ai = ai_results.get(t["key"])
            if not ai:
                continue
            try:
                set_suggested_priority(
                    JIRA_URL, JIRA_EMAIL, JIRA_TOKEN,
                    t["id"], priority_field,
                    ai["priority"], ai.get("reasoning", ""),
                )
                ok += 1
            except Exception as exc:
                logger.warning("[Jira Field] Error prioridad en %s: %s", t["key"], exc)
        logger.info("[Jira Field] Prioridad: %d/%d tickets actualizados", ok, len(tickets))
    else:
        logger.info("[Jira Field] Todos los tickets ya tienen sugerencia de prioridad")

    # ── Tipología ──
    issues = get_tickets_needing_worktype(JIRA_URL, JIRA_EMAIL, JIRA_TOKEN)
    if issues:
        tickets = [_to_ticket_payload(i) for i in issues]
        logger.info("[Jira Field] Sugiriendo tipología para %d tickets sin campo IA...", len(tickets))
        wt_results = suggest_worktype_all(client, tickets)
        ok = 0
        for t in tickets:
            wt = wt_results.get(t["key"])
            if not wt:
                continue
            try:
                set_suggested_worktype(
                    JIRA_URL, JIRA_EMAIL, JIRA_TOKEN,
                    t["id"], worktype_field,
                    wt["worktype"], wt.get("reasoning", ""),
                )
                ok += 1
            except Exception as exc:
                logger.warning("[Jira Field] Error tipología en %s: %s", t["key"], exc)
        logger.info("[Jira Field] Tipología: %d/%d tickets actualizados", ok, len(tickets))
    else:
        logger.info("[Jira Field] Todos los tickets ya tienen sugerencia de tipología")


def strategy_auto_apply() -> None:
    """Aplica automáticamente prioridad y tipología sugeridas por IA sin revisión humana.
    Actualiza los campos reales de Jira, rellena los campos IA y deja un comentario de trazabilidad.
    """
    client = make_client(GITHUB_TOKEN)
    priority_field = "customfield_10112"
    worktype_field = "customfield_10113"

    issues = get_tickets_needing_any_suggestion(JIRA_URL, JIRA_EMAIL, JIRA_TOKEN)
    if not issues:
        logger.info("[Auto Apply] Todos los tickets ya tienen sugerencias IA — nada que hacer")
        return

    tickets = [_to_ticket_payload(i) for i in issues]

    # Añadir tipo actual al payload (no está en _to_ticket_payload)
    for t, issue in zip(tickets, issues):
        t["current_type"] = (issue["fields"].get("issuetype") or {}).get("name", "Task")

    logger.info("[Auto Apply] Procesando %d tickets...", len(tickets))

    priority_results = suggest_priority_all(client, tickets)
    worktype_results = suggest_worktype_all(client, tickets)

    applied = 0
    for t in tickets:
        key = t["key"]
        pri = priority_results.get(key)
        wt  = worktype_results.get(key)

        new_priority = pri["priority"] if pri else None
        new_type     = wt["worktype"]  if wt  else None

        try:
            # Campos reales
            if new_priority:
                update_issue_priority(
                    JIRA_URL, JIRA_EMAIL, JIRA_TOKEN,
                    t["id"], PRIORITY_NAME_TO_ID.get(new_priority, "3"),
                )
            if new_type:
                update_issue_type(JIRA_URL, JIRA_EMAIL, JIRA_TOKEN, t["id"], new_type)

            # Campos IA
            if new_priority:
                set_suggested_priority(
                    JIRA_URL, JIRA_EMAIL, JIRA_TOKEN,
                    t["id"], priority_field,
                    new_priority, pri.get("reasoning", ""),
                )
            if new_type:
                set_suggested_worktype(
                    JIRA_URL, JIRA_EMAIL, JIRA_TOKEN,
                    t["id"], worktype_field,
                    new_type, wt.get("reasoning", ""),
                )

            # Comentario de trazabilidad (solo si hubo cambio real)
            priority_changed = new_priority and new_priority != t["current_priority"]
            type_changed     = new_type     and new_type     != t["current_type"]
            if priority_changed or type_changed:
                add_auto_apply_comment(
                    JIRA_URL, JIRA_EMAIL, JIRA_TOKEN, t["id"],
                    t["current_priority"], new_priority or t["current_priority"],
                    t["current_type"],    new_type     or t["current_type"],
                )

            applied += 1
            logger.info("[Auto Apply] %s → prioridad: %s | tipología: %s", key, new_priority, new_type)
        except Exception as exc:
            logger.warning("[Auto Apply] Error en %s: %s", key, exc)

    logger.info("[Auto Apply] %d/%d tickets procesados", applied, len(tickets))


# Estrategias activas — comenta las que no quieras ejecutar en cada demostración
ACTIVE_STRATEGIES = [
    # strategy_github_pages,
    # strategy_jira_field,
    strategy_auto_apply,
]

# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    for strategy in ACTIVE_STRATEGIES:
        logger.info("Ejecutando estrategia: %s", strategy.__name__)
        strategy()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    main()
