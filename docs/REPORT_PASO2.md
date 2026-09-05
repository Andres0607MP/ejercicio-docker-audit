# PASO 2 — REFACTORIZACIÓN SEGURA Y ARQUITECTURA DOCKER

**Proyecto:** ejercicio-docker-audit
**Fecha:** 2026-09-04

---

## A. ARCHIVOS MODIFICADOS

| Acción | Archivo |
|--------|---------|
| Modificado | `app.py` |
| Modificado | `Dockerfile` |
| Modificado | `test_app.py` |
| Modificado | `.gitignore` |
| Creado | `requirements.txt` |
| Creado | `docker-compose.yml` |
| Creado | `.dockerignore` |
| Creado | `.env.example` |
| Creado | `bandit-results.json` (evidencia) |
| Creado | `bandit-results.txt` (evidencia) |

---

## B. CAMBIOS REALIZADOS

| Archivo | Cambio | Motivo de seguridad |
|----------|--------|-------------------|
| `app.py` | Reemplazadas credenciales hardcodeadas por `os.getenv()` | Elimina **A-01** (B105): credenciales en variables de entorno, no en código fuente |
| `app.py` | Eliminado usuario `root` como `DB_USER` por defecto | Elimina **A-07**: principio de mínimo privilegio |
| `app.py` | SQL con string concatenation → consulta parametrizada con `%s` | Elimina **A-02** (B608): SQL Injection |
| `app.py` | Validación `int()` del parámetro `id` con `try/except` | Elimina **A-10**: validación de entradas |
| `app.py` | `debug=True` → `debug=False` | Elimina **A-03** (B201): RCE vía Werkzeug debugger |
| `app.py` | Manejo seguro de excepciones: `logger.exception()` + mensaje genérico | Elimina **A-09**: Information disclosure |
| `app.py` | `@app.errorhandler(Exception)` global | Elimina **A-12**: trazas expuestas al cliente |
| `app.py` | `/health` estable, elimina `1/0` | Elimina **A-11**: crashes intencionales |
| `app.py` | Headers de seguridad vía Flask-Talisman (CSP, X-Frame, X-Content-Type, Referrer-Policy) | Elimina **A-17** |
| `app.py` | Puerto configurable vía `os.getenv("PORT")` | Elimina **A-18** |
| `app.py` | `connect_timeout=5` en `pymysql.connect()` | Elimina **A-08**: conexiones colgadas/MITM |
| `app.py` | Endpoints retornan JSON en lugar de HTML raw | Reduce superficie de ataque (XSS reflejado) |
| `app.py` | `force_https=False` en Talisman | Apropiado: HTTPS se manejará en reverse proxy (Paso 4) |
| `Dockerfile` | `python:3.8` → `python:3.11-slim` | Elimina **A-13**: base image EOL |
| `Dockerfile` | Flask 1.1.2 → Flask 3.1.3, PyMySQL 0.9.3 → 1.2.0 | Elimina **A-14**: dependencias obsoletas con CVEs |
| `Dockerfile` | `pip install` → `--no-cache-dir` | Mejora imagen, elimina capas innecesarias |
| `Dockerfile` | `USER root` → `USER appuser` | Principio de mínimo privilegio en contenedor |
| `Dockerfile` | CMD: `python app.py` → `gunicorn --bind 0.0.0.0:5050 app:app` | Servidor WSGI de producción |
| `Dockerfile` | Creación de usuario no-root (`useradd`) | Principio de mínimo privilegio |
| `Dockerignore` | Creado: excluye `.git`, `.venv`, `__pycache__`, `*.pyc`, `.env`, tests, resultados de auditoría | Evita secretos y artefactos en la imagen |
| `requirements.txt` | Creado: Flask, PyMySQL, Gunicorn, Flask-Talisman, pytest | Gestión reproducible de dependencias |
| `docker-compose.yml` | Creado: servicios `app` + `db`, red `internal`, volumen `db_data` | Aíslamiento de red, persistencia, no exposición de MySQL al host |
| `.env.example` | Creado: template de variables de entorno con valores ficticios | No coloca secretos reales en el repositorio |
| `.gitignore` | `.env` ignorado; `.env.example` versionado; `bandit-results.*` ignorados | Protección de secretos en Git |
| `test_app.py` | Tests expandidos: /health estable, /buscar válido/inválido, inyección rechazada, sin exposición de excepciones, inspección de fuente para SQL | Cobertura de seguridad |
| `bandit-results.json` | Re-generado post-refactorización | Evidencia actualizada |

---

## C. HALLAZGOS SOLUCIONADOS

Relación de auditoría (Paso 1) → corrección (Paso 2):

| ID Auditoría | Hallazgo | Solución aplicada |
|------------|----------|-------------------|
| A-01 | B105 — Credencial hardcodeada | Sustituido por `os.getenv("DB_PASS")`; template en `.env.example` |
| A-02 | B608 — SQL Injection | Consulta parametrizada con `%s` + validación `int()` |
| A-03 | B201 — `debug=True` | `debug=False`; migración a Gunicorn |
| A-04 | B104 — `0.0.0.0` | **Mantenido** (documentado como necesario en contenedor) |
| A-05 | B311 — `random` no cripto | **Falso positivo** — no aplica (era health check, ya corregido) |
| A-06 | B101 — `assert` en tests | **Falso positivo** — es estándar en pytest |
| A-07 | Usuario `root` | `DB_USER=appuser` en `.env.example` |
| A-08 | Sin `connect_timeout` | Añadido `connect_timeout=5` en `pymysql.connect()` |
| A-09 | Exposición de excepciones | `logger.exception()` + mensaje genérico `{"error": "..."}` |
| A-10 | Sin validación de entrada | `try: int(usuario_id) except ValueError → 400` |
| A-11 | `1/0` en /health | Eliminado; /health siempre retorna 200 `{"status":"ok"}` |
| A-12 | Sin handler global | `@app.errorhandler(Exception)` añadido |
| A-13 | Python 3.8 EOL | `python:3.11-slim` |
| A-14 | Flask 1.1.2 / PyMySQL 0.9.3 | Flask 3.1.3 / PyMySQL 1.2.0 |
| A-15 | `COPY .` sin `.dockerignore` | `.dockerignore` creado y configurado |
| A-16 | Sin `--no-cache-dir` | Añadido en Dockerfile |
| A-17 | Sin headers de seguridad | Flask-Talisman (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy) |
| A-18 | Puerto hardcodeado | `PORT = int(os.getenv("PORT", "5050"))` |

### Hallazgos que no aplican / pendientes

| ID | Razón |
|----|-------|
| A-04 (B104) | `0.0.0.0` es necesario dentro del contenedor para que Gunicorn escuche. La exposición externa se controla via Docker/reverse proxy. **Aceptable/justificado**. |
| A-05 (B311) | `random.random()` era solo para health check. Ya no existe. **Falso positivo**. |
| A-06 (B101) | `assert` en tests. **Falso positivo** — práctica estándar en pytest. |

---

## D. RESULTADOS DE PRUEBAS

### pytest
```
6 passed in 0.22s
```

Tests cubiertos:
1. `/health` retorna 200
2. `/health` retorna JSON `{"status": "ok"}`
3. `/buscar?id=42` acepta ID válido (parametrizado)
4. `/buscar?id=1;DROP TABLE` rechaza con 400
5. No hay string concatenation de SQL en el código fuente
6. `/nonexistent` no expone excepciones al cliente

### Bandit (post-refactor)
```
Total issues (by severity):
    Low: 13
    Medium: 1
    High: 0
Total issues (by confidence):
    Medium: 1
    High: 13
```

- **0 High** — B201 (debug=True), B105 (hardcoded password), B608 (SQL injection) **ELIMINADOS**
- **1 Medium** — B104 (`0.0.0.0`): **aceptable/falso positivo** en contexto de contenedor
- **13 Low** — B101 (`assert`): **falsos positivos** — todos en `test_app.py` (código de test)

### Docker Build
```
Successfully tagged ejercicio-docker-audit-app:latest
```

### Docker Compose
```
Container legacyapp   Started   0.0.0.0:5051->5050/tcp
Container legacydb    Started   3306/tcp (no expuesto al host)
```

### /health endpoint
```
HTTP 200
{"status":"ok"}

Headers de seguridad:
  X-Frame-Options: SAMEORIGIN
  X-Content-Type-Options: nosniff
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'
  Referrer-Policy: strict-origin-when-cross-origin
```

### Usuario en contenedor
```
uid=1000(appuser) gid=1000(appuser)  — NO root
```

---

## E. ESTRUCTURA FINAL

```text
ejercicio-docker-audit/
├── app.py                  # Flask app refactorizada (89 líneas)
├── requirements.txt        # Flask, PyMySQL, Gunicorn, Flask-Talisman, pytest
├── Dockerfile              # python:3.11-slim, gunicorn, non-root user
├── docker-compose.yml      # app + db, red internal, volumen db_data
├── .dockerignore           # excluye .git, .env, venv, tests, auditorías
├── .env.example            # template de variables de entorno
├── test_app.py             # 6 tests de funcionalidad y seguridad
├── .gitignore              # .env, bandit-results.* ignorados
├── bandit-results.json     # evidencia (no versionada)
├── bandit-results.txt      # evidencia (no versionada)
├── AUDITORIA_BANDIT.md     # informe del PASO 1
└── .git/
```

---

## F. DECISIONES TÉCNICAS

### ¿Por qué se eliminó `root`?
El usuario `root` tenía privilegios administrativos completos. Se reemplazó por `appuser` (un usuario con privilegios mínimos sobre la BD `legacydb`). En MySQL, el usuario `appuser` solo necesita `SELECT`, `INSERT`, `UPDATE`, `DELETE` sobre las tablas de la aplicación. En el PASO 3, se creará un script de inicialización que otorgue estos privilegios específicos.

### ¿Por qué variables de entorno?
Las credenciales nunca deben estar en el código fuente (controlado por Git). Las variables de entorno permiten cambiar credenciales entre entornos (dev/staging/prod) sin tocar el código, y facilitan la rotación de secretos. El `.env` real se mantiene fuera de Git vía `.gitignore`.

### ¿Por qué Gunicorn?
El servidor de desarrollo de Flask (`app.run()`) no es adecuado para producción: es lento, no soporta concurrencia real y carece de características como graceful reload. Gunicorn es un servidor WSGI robusto, con soporte para múltiples workers, configuración de timeouts y mejor rendimiento.

### ¿Por qué `0.0.0.0` se mantiene dentro del contenedor?
Dentro de un contenedor, `0.0.0.0` significa "escuchar en todas las interfaces de red del contenedor". Esto es necesario porque Docker asigna una IP interna al contenedor. No equivale a exponer el servicio a Internet: la exposición se controla mediante el mapeo de puertos en `docker-compose.yml` (`ports:`) y, posteriormente, mediante un reverse proxy (Nginx) en el PASO 4.

### ¿Por qué MySQL no se publica hacia Internet?
En `docker-compose.yml`, el servicio `db` no tiene directiva `ports:`. Esto significa que MySQL solo es accesible desde la red interna de Docker (`internal`). La aplicación (`app`) se conecta a `db:3306` dentro de la misma red. El host no puede acceder directamente a MySQL, reduciendo la superficie de ataque.

### ¿Por qué `.dockerignore`?
Sin `.dockerignore`, la directiva `COPY . .` en el Dockerfile incluye el directorio `.git` (que contiene todo el histórico), archivos de prueba, cache de Python y resultados de auditoría. Esto: (1) infla la imagen, (2) puede exponer información sensible, (3) ralentiza el build.

### ¿Qué headers de seguridad se agregaron?
- **X-Frame-Options: SAMEORIGIN** — previene clickjacking
- **X-Content-Type-Options: nosniff** — evita MIME sniffing
- **Content-Security-Policy** — restringe fuentes de contenido a 'self'
- **Referrer-Policy: strict-origin-when-cross-origin** — controla leak de referrer
- **Strict-Transport-Security** — Flask-Talismar lo agrega automáticamente cuando HTTPS está activado

### ¿Qué versión de Python/dependencias elegí y por qué?
- **Python 3.11-slim**: versión soportada y mantenida (3.8 está EOL desde octubre 2024). La variante `slim` reduce el tamaño de la imagen sin sacrificar compatibilidad.
- **Flask 3.1.3**: versión estable más reciente, compatible con Python 3.11, corrige CVEs de versiones anteriores.
- **PyMySQL 1.2.0**: versión actual, compatible con MySQL 8.0 y con Python 3.11.
- **Flask-Talisman 1.1.0**: última versión disponible (no existe 2.0.0); proporciona configuración de security headers de forma declarativa.
- **Gunicorn 26.2.0**: última versión estable.

---

## CRITERIOS DE ACEPTACIÓN — VERIFICACIÓN

| Criterio | Estado |
|----------|--------|
| No hay contraseñas hardcodeadas | ✅ |
| La aplicación no utiliza `root` | ✅ |
| Las credenciales vienen de variables de entorno | ✅ |
| Existe `.env.example` | ✅ |
| `.env` está en `.gitignore` | ✅ |
| La consulta SQL está parametrizada | ✅ |
| El `id` recibido es validado | ✅ |
| `debug=True` fue eliminado | ✅ |
| Existe manejo seguro de excepciones | ✅ |
| No se muestran excepciones internas al cliente | ✅ |
| Existe handler global de errores | ✅ |
| `/health` funciona de manera estable | ✅ |
| Se eliminó la división por cero intencional | ✅ |
| Las dependencias fueron actualizadas | ✅ |
| Existe `requirements.txt` | ✅ |
| Existe Gunicorn | ✅ |
| Existe `.dockerignore` | ✅ |
| Docker utiliza una imagen moderna | ✅ |
| Docker ejecuta como usuario no root | ✅ |
| Existe `docker-compose.yml` | ✅ |
| MySQL no queda expuesto al host | ✅ |
| Existe persistencia para MySQL | ✅ |
| Existen headers de seguridad básicos | ✅ |
| El puerto es configurable | ✅ |
| Los tests pasan | ✅ |
| Bandit vuelve a ejecutarse correctamente | ✅ |
| La aplicación funciona dentro de Docker | ✅ |
