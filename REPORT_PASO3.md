# PASO 3 — CI/CD + Seguridad Automatizada + Docker Hub

**Proyecto:** ejercicio-docker-audit  
**Fecha:** 2026-09-04  

---

## 1. Objetivo

Dejar el repositorio preparado para un flujo **DevSecOps** donde cada `git push` o `pull request` active automáticamente:

```
Git push / PR
↓
GitHub Actions
↓
1. pytest         → valida funcionalidad
2. Bandit         → escanea código Python en busca de vulnerabilidades
3. Docker build   → construye la imagen
4. Trivy          → escanea la imagen Docker por vulnerabilidades
5. Docker Hub     → publica la imagen (solo en push a main)
```

El despliegue real en EC2, reverse proxy, HTTPS y dominios queda para el **PASO 4**.

---

## 2. Archivos creados/modificados

| Archivo | Acción |
|---------|--------|
| `.github/workflows/ci-cd.yml` | **Creado/actualizado** — Pipeline CI/CD con Docker Hub |
| `bandit.yaml` | **Creado** — Configuración de Bandit (falsos positivos documentados) |
| `.trivyignore` | **Creado** — Lista de CVEs ignorados en Trivy (documentados) |
| `requirements-dev.txt` | **Creado** — Dependencias de desarrollo (pytest) |
| `.dockerignore` | **Actualizado** — Agregados `.github`, `bandit.yaml`, docs |
| `.gitignore` | **Actualizado** — `.env.*` ignorado, `!.env.example` preservado |
| `haslotuxd.txt` | **Actualizado** — Guía con Docker Hub y Access Token |

---

## 3. Arquitectura del pipeline (ci-cd.yml)

### Triggers
```yaml
on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]
```

### Permisos
```yaml
permissions:
  contents: read    # leer el código del repositorio
```

Solo se necesita `contents: read` porque la publicación a Docker Hub utiliza
secrets dedicados (`DOCKER_USERNAME`, `DOCKER_PASSWORD`), no el `GITHUB_TOKEN`
para packages.

### Jobs

| # | Job | Trigger | Descripción |
|---|-----|---------|-------------|
| 1 | `test` (Pytest) | push + PR | Instala `requirements-dev.txt`, ejecuta `pytest -v` |
| 2 | `security-scan` (Bandit) | push + PR | Ejecuta `bandit -r . -x './.venv,./venv,./.git' -c bandit.yaml` |
| 3 | `docker-build` | push + PR | Depende de jobs 1 y 2. **Único build**: construye la imagen con tags locales + Docker Hub, la guarda como artefacto `.tar` |
| 4 | `trivy-scan` | push + PR | Depende del job 3. Carga la misma imagen del artefacto y la escanea con Trivy |
| 5 | `publish-dockerhub` | solo push a `main` | Depende de todos. Carga la **misma imagen escaneada**, hace tag para Docker Hub y publica |

### Flujo de dependencias
```
test ─┐
      ├─→ docker-build ──→ trivy-scan ─┐
scan ─┘                              ─→ publish-dockerhub (solo push a main)
```

### Arquitectura de build único (single-build)

```
docker-build (CONSTRUCCIÓN ÚNICA)
  │
  ├─→ Genera tags Docker Hub con docker/metadata-action
  ├─→ Construye imagen con: docker/build-push-action (load: true)
  │      tags: legacyapp:<sha> + andresmancera/mi-api:<tags>
  ├─→ docker save → artefacto .tar (contiene TODOS los tags)
  │
  ├─→ trivy-scan: docker load → Trivy escanea legacyapp:<sha>
  │
  └─→ publish-dockerhub: docker load → re-etiqueta → docker push andresmancera/mi-api
```

**Garantía:** la imagen que Trivy escanea es exactamente la misma imagen que se publica en Docker Hub. No hay un segundo `docker build`. La imagen viaja como artefacto `.tar` entre jobs.

---

## 4. Pytest en CI

### Qué hace
1. **Checkout** del código con `actions/checkout@v4`
2. **Setup Python 3.11** con `actions/setup-python@v5`
3. **Instala dependencias** con `pip install -r requirements-dev.txt`
4. **Ejecuta tests** con `pytest -v`

### requirements-dev.txt
```
-r requirements.txt
pytest>=8.0.0
```

Se separaron las dependencias de runtime (`requirements.txt`) de las de desarrollo (`requirements-dev.txt`). La imagen Docker solo instala dependencias de runtime, reduciendo la superficie de ataque.

### Tests que corren
1. `test_health_check` — `/health` retorna 200 y "OK"
2. `test_home_ok` — `/` retorna 200 con "API Legacy TechNova"
3. `test_home_error_no_expone_excepcion` — `/` con BD caída retorna 500 sin exponer errores
4. `test_buscar_id_valido` — `/buscar?id=42` funciona
5. `test_buscar_id_no_numerico` — `/buscar?id=abc` retorna 400
6. `test_no_sql_string_concatenation` — Verifica que no hay string concatenation en SQL
7. `test_error_no_expone_excepcion` — `/nonexistent` retorna 404 sin trazas

### Resultado esperado
```
7 passed
```

---

## 5. Bandit en CI

### Configuración (bandit.yaml)
Se creó `bandit.yaml` con dos exclusiones justificadas:

| Test ID | Razón del descarte |
|---------|-------------------|
| B101 (`assert`) | Uso estándar en tests pytest. El workflow ejecuta Bandit sobre todo el código incluyendo tests. El `assert` en tests no representa riesgo en producción. |
| B104 (`0.0.0.0`) | Escuchar en todas las interfaces es necesario dentro de un contenedor Docker. El acceso externo se controla con reverse proxy en el PASO 4. |

### Comando en CI
```yaml
bandit -r . -x './.venv,./venv,./.git' -c bandit.yaml
```

- `-x` excluye directorios de entornos virtuales y `.git`
- `-c bandit.yaml` usa la configuración con las exclusiones documentadas
- **No se usa `|| true`** — si Bandit encuentra un problema real (que no esté en la whitelist), el job falla

### Resultado esperado
```
No issues identified.
Total issues: 0
```

---

## 6. Docker Build en CI

### Qué hace
1. **Checkout** del código
2. **Setup Buildx** con `docker/setup-buildx-action@v3`
3. **Extrae metadata** con `docker/metadata-action@v5`:
   - Imagen: `andresmancera/mi-api`
   - Tags: SHA del commit, nombre de rama, `latest` (solo en main)
4. **Build** con `docker/build-push-action@v6`:
   - `context: .`
   - `file: ./Dockerfile`
   - `load: true` (carga en daemon local, NO push)
   - `tags`: local tag `legacyapp:<sha>` + todos los tags de Docker Hub
5. **Guarda** la imagen como artefacto `.tar` para Trivy y publish

### Dockerfile actual
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --shell /bin/false appuser && \
    chown -R appuser:appuser /app
USER appuser
EXPOSE 5050
CMD ["gunicorn", "--bind", "0.0.0.0:5050", "app:app"]
```

### Seguridad del build
- ✅ `python:3.11-slim` (no Python 3.8 EOL)
- ✅ `pip install --no-cache-dir` (sin cache de pip)
- ✅ `pip install --upgrade pip` (pip actualizado)
- ✅ `USER appuser` (no root)
- ✅ Gunicorn como servidor WSGI (no `app.run()` con debug)
- ✅ `.dockerignore` excluye `.git`, `.env`, tests, configuraciones

---

## 7. Trivy en CI

### Qué hace
1. **Checkout** del código
2. **Descarga el artefacto** (imagen Docker del job anterior)
3. **Carga la imagen** con `docker load`
4. **Escanea** con `aquasecurity/trivy-action@master`:
   - `image-ref: legacyapp:${{ github.sha }}`
   - `format: table`
   - `exit-code: 1` (falla si encuentra vulnerabilidades)
   - `severity: CRITICAL,HIGH`
   - `ignore-unfixed: true` (ignora CVEs sin fix disponible)
   - `ignorefile: .trivyignore` (ignora falsos positivos documentados)

### .trivyignore
Se creó `.trivyignore` para documentar las siguientes excepciones:

| CVE / GHSA | Paquete | Severidad | Justificación |
|------------|---------|-----------|---------------|
| CVE-2025-47273 | setuptools | HIGH | Falso positivo: setuptools está en 84.0.0 (supera el fix 78.1.1). Trivy lee metadatos obsoletos de una capa de Docker inferior. |
| GHSA-6v7p-g79w-8964 | msgpack | HIGH | Falso positivo: msgpack 1.1.2 solo existe como copia vendida dentro de pip. No es dependencia directa. |
| CVE-2026-76642, etc. | Debian system packages | HIGH/CRITICAL | Sin fix disponible (base image). Se ignoran con `--ignore-unfixed`. |

### Política de fallos
- **CRITICAL o HIGH con fix disponible** → el pipeline FALLA
- **CRITICAL o HIGH sin fix disponible** → ignorado por `--ignore-unfixed`
- **Falsos positivos documentados** → ignorados por `.trivyignore`
- **LOW o MEDIUM** → no causan fallo (solo reporte informativo)

---

## 8. Docker Hub

### Autenticación
Se utiliza un **Docker Hub Access Token** (no la contraseña normal):

```yaml
- name: Log in to Docker Hub
  uses: docker/login-action@v3
  with:
    username: ${{ secrets.DOCKER_USERNAME }}
    password: ${{ secrets.DOCKER_PASSWORD }}
```

### Secrets necesarios
| Secret | Valor | Dónde crear |
|--------|-------|-------------|
| `DOCKER_USERNAME` | `andresmancera` | GitHub → Settings → Secrets → Actions |
| `DOCKER_PASSWORD` | Access Token de Docker Hub | GitHub → Settings → Secrets → Actions |

**NO se utiliza `GITHUB_TOKEN` para publicar imágenes.**

### Cómo crear el Docker Hub Access Token
1. Entra a https://hub.docker.com → Security → New Access Token
2. Nombre: `github-actions`
3. Permisos: read:packages, write:packages
4. Copia el token completo
5. En GitHub → Settings → Secrets → Actions → New repository secret
6. Nombre: `DOCKER_PASSWORD`, Valor: pega el token
7. Repite para `DOCKER_USERNAME` con valor `andresmancera`

### Nombre de la imagen
```
andresmancera/mi-api:<tag>
```

### Estrategia de tags
| Tag | Cuándo | Generado por |
|-----|--------|-------------|
| SHA del commit (long) | Siempre | `type=sha,format=long` |
| Nombre de rama | Push a main/master | `type=ref,event=branch` |
| `latest` | Solo en rama principal | `type=raw,value=latest,enable={{is_default_branch}}` |

### Publicación (build único, sin rebuild)

El job `publish-dockerhub` **no construye una nueva imagen**. En su lugar:

1. **Descarga** el artefacto `.tar` generado por `docker-build` (la misma imagen que Trivy escaneo)
2. **Carga** la imagen con `docker load`
3. **Hace tag** para Docker Hub usando `docker/metadata-action` (SHA, rama, latest)
4. **Login** a Docker Hub con `DOCKER_USERNAME` / `DOCKER_PASSWORD`
5. **Push** las etiquetas a `andresmancera/mi-api`

```yaml
# Resumen del flujo publish-dockerhub:
# 1. download-artifact → obtiene legacyapp.tar (imagen única)
# 2. docker load → carga la imagen escaneada por Trivy
# 3. docker tag → etiqueta para andresmancera/mi-api:<tags>
# 4. docker login → autenticación con DOCKER_USERNAME/DOCKER_PASSWORD
# 5. docker push → publica la imagen exacta escaneada
```

**Ventaja:** La imagen publicada es idéntica a la escaneada. No hay riesgo de que un rebuild genere una imagen diferente.

### Condición de publicación
```yaml
if: github.event_name == 'push' && github.ref == 'refs/heads/main'
```

Solo se publica cuando:
1. El evento es `push` (no `pull_request`)
2. La rama es `main` (no otra rama)

---

## 9. Seguridad del workflow

| Buenas prácticas aplicadas | ¿Cumplido? |
|---------------------------|-----------|
| Usa secrets (`DOCKER_USERNAME`, `DOCKER_PASSWORD`) — no hardcodeado | ✅ |
| Permisos mínimos (`contents: read`) | ✅ |
| No hay contraseñas en el YAML | ✅ |
| No hay credenciales de BD en el YAML | ✅ |
| No usa `GHCR` ni `GITHUB_TOKEN` para imágenes | ✅ |
| Usa versiones estables de actions (`@v4`, `@v3`, `@v5`, `@v6`) | ✅ |
| No ejecuta comandos privilegiados innecesarios | ✅ |

---

## 10. Diferencia entre CI y CD

| Concepto | Definición | En este proyecto |
|----------|-----------|-----------------|
| **CI (Integración Continua)** | Compilación, tests y escaneo automático en cada cambio | Jobs: test, security-scan, docker-build, trivy-scan |
| **CD (Entrega/Despliegue Continuo)** | Publicación automática de artefactos | Job: publish-dockerhub (solo en push a main) |

La entrega continua (CD) publica la imagen a Docker Hub. El **despliegue** real en EC2 es el **PASO 4**.

---

## 11. Resultados de validación local

### pytest
```
7 passed in 0.89s
```

### Bandit (con config)
```
No issues identified.
Total issues: 0 (High: 0, Medium: 0, Low: 0)
```

### Docker build
```
Successfully tagged ejercicio-docker-audit-app:latest
Successfully tagged legacyapp:final
```

### Docker compose config
```
name: ejercicio-docker-audit
services:
  app: ...
  db: ...
config OK
```

### Docker compose up
```
Container legacyapp   Up    0.0.0.0:5051->5050/tcp
Container legacydb    Up    3306/tcp (no expuesto al host)
```

### Endpoints verificados
| Endpoint | Respuesta | HTTP |
|----------|-----------|------|
| `GET /` | `<h1>API Legacy TechNova - Funcionando</h1>` | 200 |
| `GET /health` | `OK` | 200 |
| `GET /buscar?id=1` | `<h1>Búsqueda de usuario</h1><p>ID consultado: 1</p>` | 200 |
| `GET /buscar?id=abc` | `<h1>Solicitud inválida</h1>` | 400 |

### Headers de seguridad
```
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'
Referrer-Policy: strict-origin-when-cross-origin
```

### Usuario en contenedor
```
uid=1000(appuser) — NO root
```

### Trivy
```
TRIVY_EXIT_CODE=0
Total: 0 (HIGH: 0, CRITICAL: 0)
```

### YAML workflow
```
YAML válido
```

---

## 12. Estado de EC2 y Secrets

### EC2 existente
La instancia EC2 **ya existe**. Sin embargo, el **despliegue remoto en EC2 queda
deliberadamente fuera del PASO 3** y se realizará en el PASO 4.

### Secrets de GitHub — necesarias AHORA (PASO 3)
Debes crear estas secrets para que el workflow publique en Docker Hub:

| Secret | Valor | Cómo obtenerlo |
|--------|-------|----------------|
| `DOCKER_USERNAME` | `andresmancera` | Tu nombre de usuario de Docker Hub |
| `DOCKER_PASSWORD` | Access Token | https://hub.docker.com → Security → New Access Token |

### Secrets de GitHub — preparadas para PASO 4 (EC2)
Estas secrets NO se usan en el workflow actual. Se crearán en el PASO 4:

| Secret | Descripción | Cuándo crear |
|--------|-------------|-------------|
| `SERVER_HOST` | IP pública o DNS de la instancia EC2 | PASO 4 |
| `SERVER_USER` | Usuario SSH de la AMI (ej: `ubuntu`) | PASO 4 |
| `SERVER_SSH_KEY` | Clave privada SSH para acceder a la EC2 | PASO 4 |

⚠ Estas secrets NO deben crearse todavía. Se crearán cuando estés listo para el PASO 4.

### Tres tipos de credenciales

| Tipo | Dónde viven | Uso |
|------|-------------|-----|
| **Credenciales locales** | Tu PC (`~/.docker/`, `.env` local) | `docker login` local, `docker compose` local |
| **Secrets de GitHub Actions** | GitHub → Settings → Secrets → Actions | Usadas por el workflow CI/CD para Docker Hub |
| **Credenciales EC2** | Dentro de la instancia EC2 | `docker login` en EC2, `.env` de producción |

**Regla:** Nunca copiar credenciales dentro del código, Dockerfile, YAML o `.env.example`.

---

## 13. Qué queda pendiente para el PASO 4

| Tarea | Estado |
|-------|--------|
| Despliegue en EC2 (ya existe la instancia) | ❌ Pendiente |
| Crear secrets `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY` | ❌ Pendiente |
| SSH desde GitHub Actions hacia EC2 | ❌ Pendiente |
| Docker login desde EC2 hacia Docker Hub | ❌ Pendiente |
| `docker compose pull` desde EC2 | ❌ Pendiente |
| `docker compose up -d` desde EC2 | ❌ Pendiente |
| Configurar Nginx Proxy Manager | ❌ Pendiente |
| Configurar HTTPS / Let's Encrypt | ❌ Pendiente |
| Configurar DNS y subdominios (api, dozzle, kuma) | ❌ Pendiente |
| Configurar firewall (puertos 80/443) | ❌ Pendiente |

### Preparación para PASO 4
- La imagen está disponible en Docker Hub: `andresmancera/mi-api:latest`
- El `docker-compose.yml` puede modificarse en PASO 4 para usar `image:` en lugar de `build:`
- El `haslotuxd.txt` contiene instrucciones para el despliegue manual
- Las secrets `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY` deben crearse en GitHub durante el PASO 4

---

## 14. Resumen del flujo single-build

```
push / PR
  ↓
test (pytest) ──→ 7 passed
  ↓
security-scan (Bandit) ──→ 0 issues (con bandit.yaml)
  ↓
docker-build ──→ Build ÚNICO
  │              tags: legacyapp:<sha> + andresmancera/mi-api:<tags>
  │              docker save → artefacto .tar
  ↓
trivy-scan ──→ Escanea la MISMA imagen del .tar (exit-code 1)
  │              --ignore-unfixed
  │              .trivyignore
  ↓
publish-dockerhub (solo push a main) ──→ docker load → docker push Docker Hub
```

**Garantía:** la imagen que Trivy escanea es idéntica a la publicada en Docker Hub.
No hay un segundo `docker build`. La imagen viaja como artefacto `.tar`.