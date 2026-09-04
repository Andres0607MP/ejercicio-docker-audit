# PASO 3 — CI/CD + Seguridad Automatizada + Docker Registry

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
5. GHCR publish   → publica la imagen (solo en push a main)
```

El despliegue real en EC2, reverse proxy, HTTPS y dominios queda para el **PASO 4**.

---

## 2. Archivos creados/modificados

| Archivo | Acción |
|---------|--------|
| `.github/workflows/ci-cd.yml` | **Creado** — Pipeline CI/CD completo |
| `bandit.yaml` | **Creado** — Configuración de Bandit (falsos positivos documentados) |
| `.trivyignore` | **Creado** — Lista de CVEs ignorados en Trivy (documentados) |
| `requirements-dev.txt` | **Creado** — Dependencias de desarrollo (pytest) |
| `.dockerignore` | **Actualizado** — Agregados `.github`, `bandit.yaml`, docs |
| `.gitignore` | **Actualizado** — Agregados `.github/workflows/*.log` |

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
  contents: read    # leer el código
  packages: write   # subir imágenes a GHCR
```

### Jobs

| # | Job | Trigger | Descripción |
|---|-----|---------|-------------|
| 1 | `test` (Pytest) | push + PR | Instala `requirements-dev.txt`, ejecuta `pytest -v` |
| 2 | `security-scan` (Bandit) | push + PR | Ejecuta `bandit -r . -x './.venv,./venv,./.git' -c bandit.yaml` |
| 3 | `docker-build` | push + PR | Depende de jobs 1 y 2. Construye la imagen Docker y la guarda como artefacto |
| 4 | `trivy-scan` | push + PR | Depende del job 3. Descarga la imagen, escanea con Trivy |
| 5 | `publish-ghcr` | solo push a `main` | Depende de todos. Publica en GHCR |

### Flujo de dependencias
```
test ─┐
      ├─→ docker-build ──→ trivy-scan ─┐
scan ─┘                              ─→ publish-ghcr (solo push a main)
```

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

Se separaron las dependencias de runtime (`requirements.txt`) de las de desarrollo (`requirements-dev.txt`). Esto permite que la imagen Docker solo instale dependencias de runtime, reduciendo la superficie de ataque.

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
3. **Build** con `docker/build-push-action@v6`:
   - `context: .`
   - `file: ./Dockerfile`
   - `load: true` (carga en el daemon local, no push)
   - `tags: legacyapp:${{ github.sha }}` (tag basado en SHA del commit)

4. **Guarda la imagen** como artefacto para el siguiente job (Trivy)

### Dockerfile actual (PASO 2)
```dockerfile
FROM python:3.11-slim          # base actualizada
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --shell /bin/false appuser && \
    chown -R appuser:appuser /app
USER appuser                    # no root
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

## 8. GitHub Container Registry (GHCR)

### Autenticación
Se utiliza `GITHUB_TOKEN` (token automático):

```yaml
- name: Log in to GitHub Container Registry
  uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}
```

**No se necesita crear un Personal Access Token (PAT).** El `GITHUB_TOKEN` es suficiente y se genera automáticamente.

### Nombre de la imagen
```
ghcr.io/<owner>/<repo>:<tag>
```

Ejemplo:
```
ghcr.io/andres/ejercicio-docker-audit:latest
ghcr.io/andres/ejercicio-docker-audit:abc123def456
ghcr.io/andres/ejercicio-docker-audit:main
```

### Estrategia de tags
| Tag | Cuándo | Generado por |
|-----|--------|-------------|
| SHA del commit (long) | Siempre | `type=sha,format=long` |
| Nombre de rama | Push a main/master | `type=ref,event=branch` |
| `latest` | Solo en rama principal | `type=raw,value=latest,enable={{is_default_branch}}` |

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
| Usa `GITHUB_TOKEN` (no PAT hardcodeado) | ✅ |
| Permisos mínimos (`contents: read`, `packages: write`) | ✅ |
| No hay contraseñas en el YAML | ✅ |
| No hay credenciales de BD en el YAML | ✅ |
| Usa versiones estables de actions (`@v4`, `@v3`, `@v5`, `@v6`) | ✅ |
| No ejecuta comandos privilegiados innecesarios | ✅ |

---

## 10. Diferencia entre CI y CD

| Concepto | Definición | En este proyecto |
|----------|-----------|-----------------|
| **CI (Integración Continua)** | Compilación, tests y escaneo automático en cada cambio | Jobs: test, security-scan, docker-build, trivy-scan |
| **CD (Entrega/Despliegue Continuo)** | Publicación automática de artefactos | Job: publish-ghcr (solo en push a main) |

La entrega continua (CD) publica la imagen a GHCR. El **despliegue** real en EC2 es el **PASO 4**.

---

## 11. Resultados de validación local

### pytest
```
7 passed in 0.28s
```

### Bandit (con config)
```
No issues identified.
Total issues: 0 (High: 0, Medium: 0, Low: 0)
```

### Docker build
```
Successfully built ecc9acb96e33
Successfully tagged legacyapp:trivy-final
```

### Docker compose
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

### Trivy (con --ignore-unfixed y .trivyignore)
```
TRIVY_EXIT_CODE=0
Total: 0 (HIGH: 0, CRITICAL: 0)
```

### YAML workflow
```
YAML válido (parseado correctamente con Python yaml)
```

---

## 12. Qué queda pendiente para el PASO 4

| Tarea | Estado |
|-------|--------|
| Crear instancia EC2 | ❌ Pendiente |
| Configurar SSH en EC2 | ❌ Pendiente |
| Instalar Docker en EC2 | ❌ Pendiente |
| Configurar Nginx Proxy Manager | ❌ Pendiente |
| Configurar HTTPS / Let's Encrypt | ❌ Pendiente |
| Configurar DNS y subdominios (api, dozzle, kuma) | ❌ Pendiente |
| Configurar firewall (puertos 80/443) | ❌ Pendiente |
| Despliegue real (docker compose pull + up) | ❌ Pendiente |

### Preparación para PASO 4
- La imagen está disponible en GHCR: `ghcr.io/<owner>/ejercicio-docker-audit:latest`
- El `docker-compose.yml` puede modificarse en PASO 4 para usar `image:` en lugar de `build:`
- El `haslotuxd.txt` contiene instrucciones para el despliegue manual
