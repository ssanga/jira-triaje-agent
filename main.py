import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from src.ai import make_client, triage_all
from src.jira import PRIORITY_NAME_TO_ID, extract_description, get_all_jira_bugs

load_dotenv()

logger = logging.getLogger(__name__)

JIRA_URL = os.environ["JIRA_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_TOKEN"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]

OUTPUT_PATH = Path(__file__).parent / "data" / "triage.json"


def main():
    # 1. Cargar todos los bugs de Jira en memoria
    logger.info("Leyendo todos los bugs del proyecto PT...")
    issues = get_all_jira_bugs(JIRA_URL, JIRA_EMAIL, JIRA_TOKEN)

    # 2. Preparar payload para la IA
    tickets = []
    meta = {}  # key → datos originales necesarios para construir el resultado final
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

    # 3. Triar en batches — una llamada por batch, no por ticket
    client = make_client(GITHUB_TOKEN)
    ai_results = triage_all(client, tickets)

    # 4. Combinar resultados
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

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    changed_count = sum(1 for r in results if r["changed"])
    logger.info("Resultado: %d tickets analizados, %d con cambio propuesto", len(results), changed_count)
    logger.info("Escrito en %s", OUTPUT_PATH)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    main()
