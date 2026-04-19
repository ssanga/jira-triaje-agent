import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from src.ai import make_client, triage_all
from src.jira import PRIORITY_NAME_TO_ID, extract_description, get_all_jira_bugs, set_suggested_priority

load_dotenv()

logger = logging.getLogger(__name__)

JIRA_URL = os.environ["JIRA_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_TOKEN"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

OUTPUT_PATH = Path(__file__).parent / "data" / "triage.json"

# ── Estrategias ────────────────────────────────────────────────────────────────
# Cada estrategia recibe la lista de resultados del triaje y actúa de forma
# independiente. Para añadir una nueva alternativa, implementa una función con
# la misma firma y añádela a ACTIVE_STRATEGIES.

def strategy_github_pages(results: list[dict]) -> None:
    """Escribe triage.json para que GitHub Pages sirva la UI de revisión."""
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    changed = sum(1 for r in results if r["changed"])
    logger.info("[GitHub Pages] %d tickets escritos en %s (%d con cambio)", len(results), OUTPUT_PATH, changed)


def strategy_jira_field(results: list[dict]) -> None:
    """Escribe la sugerencia de prioridad directamente en el campo personalizado de Jira."""
    field_id = "customfield_10112"
    logger.info("[Jira Field] Escribiendo sugerencias en campo %s...", field_id)
    ok = 0
    for r in results:
        try:
            set_suggested_priority(
                JIRA_URL, JIRA_EMAIL, JIRA_TOKEN,
                r["id"], field_id,
                r["proposed_priority"], r["reasoning"],
            )
            ok += 1
        except Exception as exc:
            logger.warning("[Jira Field] No se pudo actualizar %s: %s", r["key"], exc)
    logger.info("[Jira Field] %d/%d tickets actualizados", ok, len(results))


# Estrategias activas — comenta las que no quieras ejecutar en cada demostración
ACTIVE_STRATEGIES = [
    # strategy_github_pages,
    strategy_jira_field,
]

# ── Núcleo de triaje ───────────────────────────────────────────────────────────

def run_triage() -> list[dict]:
    """Lee bugs de Jira, los analiza con IA y devuelve la lista de resultados."""
    logger.info("Leyendo todos los bugs del proyecto PT...")
    issues = get_all_jira_bugs(JIRA_URL, JIRA_EMAIL, JIRA_TOKEN)

    tickets = []
    meta = {}
    for issue in issues:
        key = issue["key"]
        fields = issue["fields"]
        priority_obj = fields.get("priority") or {}
        current_priority = priority_obj.get("name", "Medium")
        tickets.append({
            "key": key,
            "summary": fields.get("summary", ""),
            "description": extract_description(fields.get("description")),
            "current_priority": current_priority,
        })
        meta[key] = {
            "id": issue["id"],
            "current_priority": current_priority,
            "current_priority_id": PRIORITY_NAME_TO_ID.get(current_priority, "3"),
        }

    client = make_client(GITHUB_TOKEN)
    ai_results = triage_all(client, tickets)

    results = []
    for t in tickets:
        key = t["key"]
        ai = ai_results.get(key)
        if not ai:
            logger.warning("%s: sin respuesta de la IA, omitido", key)
            continue

        proposed_priority = ai.get("priority", t["current_priority"])
        proposed_priority_id = PRIORITY_NAME_TO_ID.get(proposed_priority, meta[key]["current_priority_id"])
        changed = proposed_priority != t["current_priority"]

        results.append({
            "key": key,
            "jira_url": f"{JIRA_URL}/browse/{key}",
            "id": meta[key]["id"],
            "summary": t["summary"],
            "current_priority": t["current_priority"],
            "current_priority_id": meta[key]["current_priority_id"],
            "proposed_priority": proposed_priority,
            "proposed_priority_id": proposed_priority_id,
            "reasoning": ai.get("reasoning", ""),
            "changed": changed,
        })
        logger.info("%s: %s → %s %s", key, t["current_priority"], proposed_priority, "(cambio)" if changed else "(igual)")

    logger.info("Triaje completado: %d tickets, %d con cambio propuesto",
                len(results), sum(1 for r in results if r["changed"]))
    return results


def main():
    results = run_triage()
    for strategy in ACTIVE_STRATEGIES:
        logger.info("Ejecutando estrategia: %s", strategy.__name__)
        strategy(results)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    main()
