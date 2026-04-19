# jira-triaje-agent

Agente autónomo de triaje de incidencias Jira con GitHub Pages + GitHub Actions + GitHub Models.

Analiza bugs abiertos en lote con `gpt-4o`, propone cambios de prioridad, y los comunica a través de **estrategias intercambiables** — actualmente dos implementadas, fácilmente extensibles.

---

## Estrategias de salida

El agente comparte un núcleo común de triaje (Jira → IA → lista de resultados) y puede ejecutar una o varias estrategias en paralelo. Para activar o desactivar una estrategia, edita `ACTIVE_STRATEGIES` en `main.py`.

### Estrategia A — GitHub Pages (revisión humana)

```
main.py → triage.json → GitHub Pages (index.html)
    ↓
Usuario revisa propuestas en la web → Confirmar / Descartar
    ↓
Botón "Enviar decisiones" → escribe decisions.json vía GitHub Contents API
    ↓
apply.yml detecta el push → src/apply.py actualiza Jira → commit
```

**Ventajas:** revisión ticket a ticket, trazabilidad completa, aprobación explícita antes de tocar Jira.  
**Requisito:** el revisor necesita un GitHub Token (classic PAT, scope `repo`).

---

### Estrategia B — Campo personalizado en Jira

```
main.py → PUT /rest/api/3/issue/{id} (campo customfield_10112)
    ↓
Usuario ve "IA: Prioridad Sugerida" directamente en cada ticket de Jira
→ Aprueba cambiando la prioridad real manualmente
```

**Ventajas:** sin web externa, sin tokens adicionales, visible para cualquier usuario con acceso a Jira.  
**Requisito:** campo personalizado `IA: Prioridad Sugerida` añadido al proyecto PT (ya configurado).

---

## Configuración inicial

### 1. Secrets en GitHub

Ve a **Settings → Secrets and variables → Actions** y crea:

| Secret | Valor |
|--------|-------|
| `JIRA_URL` | URL base de Jira, ej: `https://tu-dominio.atlassian.net` |
| `JIRA_EMAIL` | Email de tu cuenta Atlassian |
| `JIRA_TOKEN` | API Token generado en [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) |

El `GITHUB_TOKEN` para GitHub Models lo provee automáticamente GitHub Actions — no hace falta configurarlo.

### 2. Habilitar GitHub Pages (estrategia A)

Ve a **Settings → Pages**:

- **Source:** Deploy from a branch
- **Branch:** `main` / `(root)`

La URL de la web será: `https://<usuario>.github.io/<repo>/`

### 3. Campo personalizado en Jira (estrategia B)

El campo `IA: Prioridad Sugerida` (`customfield_10112`) debe estar añadido al proyecto PT.

Para crearlo en un Jira nuevo ejecuta una sola vez:

```bash
python scripts/setup_jira_field.py
```

Luego actívalo en el proyecto: **Project settings → Fields → busca "IA: Prioridad Sugerida" → Add**.

### 4. Primer triaje manual

Ve a **Actions → Triage y Deploy → Run workflow** para lanzar el primer análisis sin esperar al cron.

### 5. GitHub Token para usar la web (estrategia A)

El usuario que revise los tickets necesita un **classic PAT** con scope `repo`:

- GitHub → **Settings → Developer settings → Tokens (classic) → Generate new token**
- Scope: `repo`
- Se introduce directamente en el campo de la web al enviar — no se almacena en ningún sitio

---

## Uso de la web (estrategia A)

1. Abre `https://<usuario>.github.io/<repo>/`
2. Introduce tu GitHub Token (classic, scope `repo`) en el campo superior
3. Revisa las propuestas del agente — cada card muestra prioridad actual → propuesta y el razonamiento
4. Usa **Confirmar** / **Dejar como está** por ticket, o los botones globales **Confirmar todos** / **Descartar todos**
5. Pulsa **Enviar decisiones a Jira** — el pipeline aplica los cambios aprobados en ~1 minuto

---

## Añadir una nueva estrategia

1. Crea una función en `main.py` con la firma `def strategy_nueva(results: list[dict]) -> None`
2. Añádela a `ACTIVE_STRATEGIES`

Cada resultado en `results` contiene:

| Campo | Descripción |
|-------|-------------|
| `key` | Clave del ticket (ej. `PT-6`) |
| `id` | ID interno de Jira |
| `jira_url` | URL directa al ticket |
| `summary` | Título del ticket |
| `current_priority` | Prioridad actual |
| `proposed_priority` | Prioridad propuesta por la IA |
| `reasoning` | Razonamiento del agente (en español) |
| `changed` | `true` si la prioridad propuesta difiere de la actual |

---

## Instalación local

```bash
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env    # rellenar con tus credenciales
python main.py
```

---

## Estructura del proyecto

```
├── main.py                        # Orquestador: triaje + ejecución de estrategias
├── src/
│   ├── jira.py                    # Cliente Jira REST API (lectura, actualización, comentarios)
│   ├── ai.py                      # Cliente GitHub Models — triaje en batches de 10
│   └── apply.py                   # Aplica decisiones aprobadas desde la web (estrategia A)
├── scripts/
│   └── setup_jira_field.py        # Crea el campo personalizado en Jira (una sola vez)
├── data/
│   └── triage.json                # Resultado del triaje para GitHub Pages (estrategia A)
├── .github/workflows/
│   ├── main.yml                   # Triage: manual o por push
│   └── apply.yml                  # Apply: se activa cuando decisions.json llega al repo (estrategia A)
├── index.html                     # UI web servida por GitHub Pages (estrategia A)
├── requirements.txt
└── .env.example                   # Variables de entorno de ejemplo
```

---

## Workflows

| Workflow | Trigger | Qué hace |
|----------|---------|----------|
| `main.yml` | Push a main / manual | Triaje completo: Jira → IA → ejecuta estrategias activas |
| `apply.yml` | Push de `decisions.json` | Aplica decisiones en Jira, borra decisions.json, commit (estrategia A) |
