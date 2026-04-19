# jira-triaje-agent

Agente autónomo de triaje de incidencias Jira con GitHub Pages + GitHub Actions + GitHub Models.

Analiza bugs abiertos en lote con `gpt-4o`, propone cambios de prioridad, y permite a usuarios de negocio aprobar o descartar cada propuesta desde una web estática — sin acceso a Jira ni infraestructura adicional.

---

## Arquitectura

```
GitHub Actions (cron 8h/12h/16h L-V o manual)
    ↓
main.py → lee TODOS los bugs del proyecto PT de Jira (paginado)
    ↓
src/ai.py → llama a GitHub Models (gpt-4o) en batches de 10 tickets por llamada
    ↓
Escribe data/triage.json → commit automático a main
    ↓
GitHub Pages sirve index.html leyendo ese JSON
    ↓
Usuario abre la web → introduce su GitHub Token → revisa propuestas
→ Confirmar / Descartar (uno a uno, o "Confirmar todos" / "Descartar todos")
    ↓
Botón "Enviar decisiones" → escribe decisions.json en el repo vía Contents API
    ↓
apply.yml detecta el push de decisions.json
    ↓
src/apply.py → actualiza prioridades en Jira (PUT /rest/api/3/issue/{id})
             → añade comentario de trazabilidad en cada ticket aprobado
             → borra decisions.json → actualiza triage.json → commit
```

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

### 2. Habilitar GitHub Pages

Ve a **Settings → Pages**:

- **Source:** Deploy from a branch
- **Branch:** `main` / `(root)`

La URL de la web será: `https://<usuario>.github.io/<repo>/`

### 3. Primer triaje manual

Ve a **Actions → Triage y Deploy → Run workflow** para lanzar el primer análisis sin esperar al cron.

### 4. GitHub Token para usar la web

El usuario que revise los tickets necesita un **classic PAT** con scope `repo`:

- GitHub → **Settings → Developer settings → Tokens (classic) → Generate new token**
- Scope: `repo`
- Se introduce directamente en el campo de la web al enviar — no se almacena en ningún sitio

---

## Uso de la web

1. Abre `https://<usuario>.github.io/<repo>/`
2. Introduce tu GitHub Token (classic, scope `repo`) en el campo superior
3. Revisa las propuestas del agente — cada card muestra prioridad actual → propuesta y el razonamiento
4. Usa **Confirmar** / **Dejar como está** por ticket, o los botones globales **Confirmar todos** / **Descartar todos**
5. Pulsa **Enviar decisiones a Jira** — el pipeline aplica los cambios aprobados en ~1 minuto

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
├── main.py                        # Entry point: triaje (Jira → IA → triage.json)
├── src/
│   ├── jira.py                    # Cliente Jira REST API (lectura, actualización, comentarios)
│   ├── ai.py                      # Cliente GitHub Models — triaje en batches de 10
│   └── apply.py                   # Entry point: aplica decisiones aprobadas en Jira
├── data/
│   └── triage.json                # Resultado del triaje (generado automáticamente)
├── .github/workflows/
│   ├── main.yml                   # Triage: cron 8h/12h/16h L-V + push + manual
│   └── apply.yml                  # Apply: se activa cuando decisions.json llega al repo
├── index.html                     # UI web servida por GitHub Pages
├── requirements.txt
└── .env.example                   # Variables de entorno de ejemplo
```

---

## Workflows

| Workflow | Trigger | Qué hace |
|----------|---------|----------|
| `main.yml` | Cron / push a main / manual | Triaje completo: Jira → IA → commit triage.json |
| `apply.yml` | Push de `decisions.json` | Aplica decisiones en Jira, borra decisions.json, commit |
