# jira-triaje-agent

Agente autónomo de triaje de incidencias Jira con GitHub Pages + GitHub Actions + GitHub Models.

Analiza bugs abiertos con `gpt-4o`, propone cambios de prioridad, y permite a usuarios de negocio
aprobar los cambios desde una web estática sin necesidad de acceso a Jira.

## Arquitectura

```
GitHub Actions (cron 8h/12h/16h L-V)
    ↓
main.py → lee bugs de Jira → llama a GitHub Models (gpt-4o)
    ↓
Escribe data/triage.json → commit automático
    ↓
GitHub Pages sirve index.html leyendo ese JSON
    ↓
Usuario abre la web → aprueba/rechaza propuestas
    ↓
Click dispara repository_dispatch con Fine-grained PAT
    ↓
apply.yml → apply.py → actualiza prioridades en Jira + comentario de trazabilidad
```

## Configuración inicial

### 1. Secrets en GitHub

Ve a **Settings → Secrets and variables → Actions** y crea:

| Secret | Valor |
|--------|-------|
| `JIRA_URL` | URL base de Jira, ej: `https://tu-dominio.atlassian.net` |
| `JIRA_EMAIL` | Email de tu cuenta Atlassian |
| `JIRA_TOKEN` | API Token generado en [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) |

El `GITHUB_TOKEN` para GitHub Models lo provee automáticamente GitHub Actions.

### 2. Fine-grained PAT para la web

Crea un token en **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**:

- **Repository access:** solo este repo
- **Permissions → Actions:** Read and Write
- **Permissions → Contents:** Read-only
- Todo lo demás: No access

Pega el token en `index.html`, reemplazando `TU_PAT_AQUI`:

```js
const GITHUB_PAT = "github_pat_xxxxx...";
```

### 3. Habilitar GitHub Pages

Ve a **Settings → Pages**:

- **Source:** Deploy from a branch
- **Branch:** `main` / `(root)`

La URL de la web será: `https://<usuario>.github.io/<repo>/`

### 4. Primer triaje manual

Ve a **Actions → Triage agent → Run workflow** para lanzar el primer análisis sin esperar al cron.

## Instalación local

```bash
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env    # rellenar con tus credenciales
python main.py
```

## Estructura del proyecto

```
├── main.py                          # Agente de triaje (entry point)
├── apply.py                         # Aplicar decisiones aprobadas (entry point)
├── src/
│   ├── jira.py                      # Cliente Jira REST API
│   └── ai.py                        # Cliente GitHub Models (gpt-4o)
├── data/
│   └── triage.json                  # Resultado del triaje (generado automáticamente)
├── .github/workflows/
│   ├── triage.yml                   # Cron de análisis
│   └── apply.yml                    # Aplicar decisiones vía repository_dispatch
├── index.html                       # UI web (GitHub Pages)
└── .env.example                     # Variables de entorno de ejemplo
```
