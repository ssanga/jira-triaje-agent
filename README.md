# jira-triaje-agent

Agente autónomo de triaje de incidencias Jira con GitHub Pages + GitHub Actions + GitHub Models.

Analiza tickets abiertos en lote con `gpt-4o`, sugiere prioridad y tipología, y los comunica a través de **tres estrategias intercambiables** — desde revisión humana completa hasta aplicación automática sin intervención.

---

## Estrategias de salida

Cada estrategia es autónoma: obtiene sus propios tickets de Jira con el JQL más eficiente para su caso de uso. Para activar o desactivar una estrategia, edita `ACTIVE_STRATEGIES` en `main.py`.

---

### Estrategia A — GitHub Pages (revisión humana)

```
main.py → obtiene todos los tickets abiertos → IA sugiere prioridad
    ↓
Escribe data/triage.json → commit automático a main
    ↓
GitHub Pages sirve index.html
    ↓
Usuario revisa propuestas → Confirmar / Descartar (uno a uno o en bloque)
    ↓
"Enviar decisiones" → escribe decisions.json vía GitHub Contents API
    ↓
apply.yml detecta el push → src/apply.py actualiza prioridades en Jira → commit
```

**Cuándo usarla:** cuando se requiera aprobación humana explícita antes de modificar Jira.  
**Requisito:** el revisor necesita un GitHub Token (classic PAT, scope `repo`).

---

### Estrategia B — Campos IA en Jira (sugerencia visible)

```
main.py → obtiene tickets sin campo IA relleno (JQL: cf[10112] is EMPTY / cf[10113] is EMPTY)
    ↓
IA sugiere prioridad  → escribe "IA: Prioridad Sugerida"  (customfield_10112)
IA sugiere tipología  → escribe "IA: Tipología Sugerida"  (customfield_10113)
    ↓
Usuario ve las sugerencias directamente en el ticket de Jira
→ Aprueba aplicando el cambio manualmente
```

**Cuándo usarla:** cuando el equipo ya tiene acceso a Jira y se quiere sugerencia visible sin herramientas externas.  
**Ventaja clave:** solo procesa tickets que aún no tienen el campo IA relleno — eficiente en proyectos grandes.

---

### Estrategia C — Auto Apply (totalmente autónoma)

```
main.py → obtiene tickets sin al menos una sugerencia IA
    ↓
IA sugiere prioridad Y tipología en batches
    ↓
Aplica Priority real en Jira      (PUT /rest/api/3/issue/{id})
Aplica Issue Type real en Jira    (PUT /rest/api/3/issue/{id})
Rellena campos IA                 (customfield_10112 y customfield_10113)
Añade comentario de trazabilidad  (solo si hubo cambio real)
```

**Cuándo usarla:** modo producción — confianza total en la IA, sin revisión humana.  
**Comentario en ticket:** `[Agente de triaje IA] Cambios aplicados automáticamente el YYYY-MM-DD: • Prioridad: Medium → High • Tipología: Task → Bug`

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

### 2. Campos personalizados en Jira (estrategias B y C)

| Campo | ID | Descripción |
|-------|----|-------------|
| `IA: Prioridad Sugerida` | `customfield_10112` | Prioridad propuesta por la IA con razonamiento |
| `IA: Tipología Sugerida` | `customfield_10113` | Tipo de trabajo propuesto por la IA con razonamiento |

Para crearlos en un Jira nuevo, ejecuta una sola vez:

```bash
python scripts/setup_jira_field.py
```

Luego actívalos en el proyecto: **Project settings → Fields → busca el campo → Add**.

### 3. Habilitar GitHub Pages (estrategia A)

Ve a **Settings → Pages**:

- **Source:** Deploy from a branch
- **Branch:** `main` / `(root)`

La URL de la web será: `https://<usuario>.github.io/<repo>/`

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

1. Implementa una función sin parámetros en `main.py`: `def strategy_nueva() -> None`
2. Dentro, usa los helpers de `src/jira.py` para obtener tickets y los de `src/ai.py` para analizarlos
3. Añádela a `ACTIVE_STRATEGIES`

Funciones de obtención de tickets disponibles en `src/jira.py`:

| Función | JQL aplicado |
|---------|-------------|
| `get_all_open_tickets()` | Todos los tickets abiertos |
| `get_tickets_needing_priority()` | `cf[10112] is EMPTY` |
| `get_tickets_needing_worktype()` | `cf[10113] is EMPTY` |
| `get_tickets_needing_any_suggestion()` | `cf[10112] is EMPTY OR cf[10113] is EMPTY` |

Funciones de análisis IA disponibles en `src/ai.py`:

| Función | Qué devuelve |
|---------|-------------|
| `suggest_priority_all(client, tickets)` | `{key: {priority, reasoning}}` |
| `suggest_worktype_all(client, tickets)` | `{key: {worktype, reasoning}}` |

---

## Scripts de utilidad

| Script | Uso |
|--------|-----|
| `python scripts/setup_jira_field.py` | Crea los campos personalizados en Jira (una sola vez) |
| `python -m scripts.reset_priorities` | Resetea prioridades a Medium y limpia campos IA (útil para demos) |

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
├── main.py                        # Orquestador: estrategias A, B y C
├── src/
│   ├── jira.py                    # Cliente Jira REST API (lectura, escritura, comentarios)
│   ├── ai.py                      # Cliente GitHub Models — suggest_priority_all / suggest_worktype_all
│   └── apply.py                   # Aplica decisiones aprobadas desde la web (estrategia A)
├── scripts/
│   ├── setup_jira_field.py        # Crea campos personalizados en Jira (una sola vez)
│   └── reset_priorities.py        # Resetea datos para demos
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
| `main.yml` | Push a main / manual | Ejecuta las estrategias activas en `ACTIVE_STRATEGIES` |
| `apply.yml` | Push de `decisions.json` | Aplica decisiones en Jira, borra decisions.json, commit (estrategia A) |
