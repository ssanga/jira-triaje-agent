import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from src.jira import add_triage_comment, update_issue_priority

load_dotenv()

logger = logging.getLogger(__name__)

JIRA_URL = os.environ["JIRA_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_TOKEN"]

TRIAGE_PATH = Path(__file__).parent.parent / "data" / "triage.json"


def main():
    decisions_raw = os.environ.get("DECISIONS", "{}")
    decisions: dict[str, str] = json.loads(decisions_raw)

    if not decisions:
        logger.warning("No hay decisiones que procesar.")
        return

    logger.info("Procesando %d decisiones", len(decisions))

    with open(TRIAGE_PATH, encoding="utf-8") as f:
        triage: list[dict] = json.load(f)

    index = {item["key"]: item for item in triage}
    processed_keys = set()

    for key, decision in decisions.items():
        if decision != "approve":
            logger.info("%s: rechazado, sin cambios", key)
            processed_keys.add(key)
            continue

        item = index.get(key)
        if not item:
            logger.warning("%s: no encontrado en triage.json, ignorado", key)
            continue

        logger.info("%s: aplicando prioridad %s...", key, item["proposed_priority"])
        try:
            update_issue_priority(JIRA_URL, JIRA_EMAIL, JIRA_TOKEN, item["id"], item["proposed_priority_id"])
            add_triage_comment(JIRA_URL, JIRA_EMAIL, JIRA_TOKEN, item["id"], item["proposed_priority"])
            processed_keys.add(key)
            logger.info("%s: OK — %s → %s", key, item["current_priority"], item["proposed_priority"])
        except Exception:
            logger.exception("Error al aplicar cambios en %s", key)

    remaining = [item for item in triage if item["key"] not in processed_keys]
    with open(TRIAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(remaining, f, ensure_ascii=False, indent=2)

    approved = sum(1 for k, v in decisions.items() if v == "approve" and k in processed_keys)
    logger.info("Resultado: %d aprobados, %d rechazados", approved, len(processed_keys) - approved)
    logger.info("Quedan %d tickets pendientes en triage.json", len(remaining))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    main()
