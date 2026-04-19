import json
import logging

from openai import OpenAI

logger = logging.getLogger(__name__)

GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
BATCH_SIZE = 10

TRIAGE_PROMPT = """Eres un agente experto en triaje de incidencias de software.
Analiza los siguientes tickets de Jira y determina la prioridad más adecuada para cada uno.

Tickets:
{tickets}

Responde ÚNICAMENTE con un array JSON con esta estructura exacta, uno por ticket en el mismo orden:
[
  {{"key": "PT-X", "priority": "Highest|High|Medium|Low|Lowest", "reasoning": "explicación breve en español"}},
  ...
]

No incluyas nada más en tu respuesta, solo el array JSON."""


WORKTYPE_PROMPT = """Eres un agente experto en clasificación de tickets de Jira.
Analiza los siguientes tickets y determina el tipo de trabajo más adecuado para cada uno.

Criterios:
- Bug: incidencias, errores o fallos en producción o en el sistema
- Story: evolutivos, nuevos desarrollos o funcionalidades que implican cambio de código
- Task: tareas de soporte o consultas resueltas por técnicos sin implicar cambio de código

Tickets:
{tickets}

Responde ÚNICAMENTE con un array JSON con esta estructura exacta, uno por ticket en el mismo orden:
[
  {{"key": "PT-X", "worktype": "Bug|Story|Task", "reasoning": "explicación breve en español"}},
  ...
]

No incluyas nada más en tu respuesta, solo el array JSON."""


def make_client(github_token: str) -> OpenAI:
    logger.debug("Creando cliente OpenAI apuntando a %s", GITHUB_MODELS_BASE_URL)
    return OpenAI(base_url=GITHUB_MODELS_BASE_URL, api_key=github_token)


def _format_tickets(tickets: list[dict]) -> str:
    lines = []
    for t in tickets:
        raw_desc = t.get("description") or ""
        desc = raw_desc[:500] if raw_desc else "(sin descripción)"
        lines.append(
            f"- key: {t['key']}\n"
            f"  resumen: {t['summary']}\n"
            f"  descripción: {desc}\n"
            f"  prioridad actual: {t['current_priority']}"
        )
    return "\n\n".join(lines)


def _parse_response(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def triage_batch(client: OpenAI, tickets: list[dict]) -> list[dict]:
    """Triages a batch of tickets in a single LLM call. Returns results indexed by key."""
    prompt = TRIAGE_PROMPT.format(tickets=_format_tickets(tickets))
    logger.debug("Llamando a gpt-4o con batch de %d tickets", len(tickets))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = response.choices[0].message.content
    results = _parse_response(raw)
    logger.debug("Respuesta del modelo: %d resultados", len(results))
    return results


def classify_worktype_batch(client: OpenAI, tickets: list[dict]) -> list[dict]:
    """Clasifica el tipo de trabajo de un batch de tickets en una sola llamada."""
    prompt = WORKTYPE_PROMPT.format(tickets=_format_tickets(tickets))
    logger.debug("Llamando a gpt-4o para worktype con batch de %d tickets", len(tickets))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return _parse_response(response.choices[0].message.content)


def classify_worktype_all(client: OpenAI, tickets: list[dict]) -> dict[str, dict]:
    """Clasifica el tipo de trabajo de todos los tickets en batches."""
    results: dict[str, dict] = {}
    total_batches = (len(tickets) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(tickets), BATCH_SIZE):
        batch = tickets[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        logger.info("Clasificando worktype batch %d/%d (%d tickets)", batch_num, total_batches, len(batch))
        try:
            for r in classify_worktype_batch(client, batch):
                results[r["key"]] = r
        except Exception:
            logger.exception("Error en worktype batch %d, los tickets se omitirán", batch_num)
    return results


def triage_all(client: OpenAI, tickets: list[dict]) -> dict[str, dict]:
    """Triages all tickets in batches. Returns a dict keyed by ticket key."""
    results: dict[str, dict] = {}
    total_batches = (len(tickets) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(tickets), BATCH_SIZE):
        batch = tickets[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        logger.info("Procesando batch %d/%d (%d tickets)", batch_num, total_batches, len(batch))
        try:
            batch_results = triage_batch(client, batch)
            for r in batch_results:
                results[r["key"]] = r
        except Exception:
            logger.exception("Error en batch %d, los tickets se omitirán", batch_num)

    return results
