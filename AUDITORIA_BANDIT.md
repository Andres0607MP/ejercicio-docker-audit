# Auditoría de Seguridad — PASO 1

**Proyecto:** ejercicio-docker-audit  
**Fecha:** 2026-09-04  
**Herramienta principal:** Bandit 1.9.4  
**Archivo de evidencia:** `bandit-results.json`

---

## ¿Qué se revisó?

Se inspeccionó el código fuente del proyecto (`app.py`, `Dockerfile`, `test_app.py`) y se ejecutó **Bandit**, una herramienta que busca errores de seguridad comunes en código Python.

Además de lo que encontró Bandit, se hizo una **revisión manual** para encontrar otros problemas que la herramienta no detecta.

---

## Resultados de Bandit (antes de corregir)

Bandit encontró **6 problemas** en el código original:

| Severidad | Cantidad |
|-----------|----------|
| High | 1 |
| Medium | 2 |
| Low | 3 |

Estos 6 problemas se detallan en la tabla principal más abajo.

---

## Tabla principal

| ID | Problema encontrado | Archivo | Qué se hizo | Estado |
|-----|---------------------|---------|-------------|--------|
| A-01 | Contraseña escrita en el código | `app.py` | Se pasó a variables de entorno | ✅ Solucionado |
| A-02 | Posible SQL Injection | `app.py` | Se parametrizó la consulta | ✅ Solucionado |
| A-03 | `debug=True` (modo desarrollador activado) | `app.py` | Se eliminó y se usa Gunicorn | ✅ Solucionado |
| A-04 | La app escucha en todas las interfaces (`0.0.0.0`) | `app.py` | Aceptable dentro de un contenedor | ⚠️ Aceptable |
| A-05 | Uso de `random` (no seguro para criptografía) | `app.py` | No se usaba para criptografía | ℹ️ Falso positivo |
| A-06 | Uso de `assert` en los tests | `test_app.py` | Es normal en tests, no en producción | ℹ️ Falso positivo |
| A-07 | Usuario `root` para la base de datos | `app.py` | Se usa `appuser` sin privilegios | ✅ Solucionado |
| A-08 | Conexión a BD sin límite de tiempo | `app.py` | Se agregó `connect_timeout=5` | ✅ Solucionado |
| A-09 | Errores mostrados al usuario (excepciones expuestas) | `app.py` | Se ocultan y se registran en logs | ✅ Solucionado |
| A-10 | No se validaba el ID recibido | `app.py` | Se valida que sea un número entero | ✅ Solucionado |
| A-11 | División por cero en `/health` | `app.py` | Se eliminó y el endpoint es estable | ✅ Solucionado |
| A-12 | No había manejo global de errores | `app.py` | Se agregó `@app.errorhandler` | ✅ Solucionado |
| A-13 | Imagen de Docker desactualizada (Python 3.8) | `Dockerfile` | Se usó `python:3.11-slim` | ✅ Solucionado |
| A-14 | Versiones obsoletas de Flask y PyMySQL | `Dockerfile` | Se actualizaron a versiones nuevas | ✅ Solucionado |
| A-15 | La imagen incluía archivos innecesarios | `Dockerfile` | Se creó `.dockerignore` | ✅ Solucionado |
| A-16 | No se usó `--no-cache-dir` al instalar | `Dockerfile` | Se agregó `--no-cache-dir` | ✅ Solucionado |
| A-17 | No había headers de seguridad | `app.py` | Se agregaron con Flask-Talisman | ✅ Solucionado |
| A-18 | Puerto hardcodeado | `app.py` | Se hace configurable con variable de entorno | ✅ Solucionado |

**Total: 18 problemas**  
- **16 solucionados** (problemas reales)  
- **2 ignorados** (1 falso positivo + 1 aceptable en su contexto)

---

## Detalle de los problemas

### A-01 — Contraseña escrita directamente en el código

**Qué estaba mal:**  
La contraseña de la base de datos (`admin_adso_2026_secreto`) y el usuario (`root`) estaban escritos directamente dentro de `app.py`.

**Riesgo:**  
Cualquier persona que tuviera acceso al código podía ver las credenciales y conectarse a la base de datos.

**Cómo se solucionó:**  
Se eliminó del código y ahora las credenciales vienen de variables de entorno (`os.getenv`). Se creó un archivo `.env.example` como plantilla.

**Estado:** ✅ Solucionado

---

### A-02 — Posible SQL Injection

**Qué estaba mal:**  
La consulta SQL se construía juntando directamente el dato enviado por el usuario:  
`"SELECT * FROM usuarios WHERE id = " + usuario_id`

**Riesgo:**  
Un atacante podría enviar un ID malicioso y modificar o borrar datos de la base de datos.

**Cómo se solucionó:**  
La consulta ahora usa parámetros (`%s`) y el ID se valida como número entero antes de usarlo.

**Estado:** ✅ Solucionado

---

### A-03 — `debug=True` (modo desarrollador activado)

**Qué estaba mal:**  
La aplicación se ejecutaba con `debug=True`, lo que activa el "debugger" de Flask.

**Riesgo:**  
El debugger permite ver información sensible del sistema y, peor aún, permite ejecutar comandos arbitrarios si se provoca un error.

**Cómo se solucionó:**  
Se eliminó `debug=True` (ahora es `debug=False`) y la aplicación se ejecuta con **Gunicorn**, un servidor apropiado para producción.

**Estado:** ✅ Solucionado

---

### A-04 — La app escucha en todas las interfaces (`0.0.0.0`)

**Qué estaba mal:**  
La aplicación escuchaba en `0.0.0.0`, es decir, en todas las interfaces de red.

**Riesgo:**  
Podría ser accesible desde fuera del contenedor.

**Cómo se solucionó:**  
Se mantiene `0.0.0.0` porque es necesario dentro de un contenedor Docker. El acceso externo se controlará con un proxy inverso en el Paso 4.

**Estado:** ⚠️ Aceptable por el contexto

---

### A-05 — Uso de `random` (no seguro para criptografía)

**Qué estaba mal:**  
Bandit detectó el uso de `random.random()`.

**Riesgo:**  
`random` no es seguro para generar contraseñas, tokens o números aleatorios criptográficos.

**Cómo se solucionó:**  
En este proyecto, `random` solo se usaba para simular fallos en el health check. No tenía ninguna función de seguridad. Se eliminó al corregir el `/health`.

**Estado:** ℹ️ Falso positivo

---

### A-06 — Uso de `assert` en los tests

**Qué estaba mal:**  
Bandit detectó uso de `assert`.

**Riesgo:**  
`assert` se elimina al compilar en modo optimizado, por lo que no debería usarse en código de producción.

**Cómo se solucionó:**  
El `assert` solo está en `test_app.py`, que es código de prueba. Es una práctica normal y no afecta a la aplicación en producción.

**Estado:** ℹ️ Falso positivo

---

### A-07 — Usuario `root` para la base de datos

**Qué estaba mal:**  
La aplicación se conectaba a MySQL usando el usuario `root`.

**Riesgo:**  
El usuario `root` tiene todos los permisos posibles. Si se compromete la aplicación, el atacante tiene acceso completo a la base de datos.

**Cómo se solucionó:**  
Se usa `appuser`, un usuario con privilegios mínimos (solo `SELECT`, `INSERT`, `UPDATE`, `DELETE`).

**Estado:** ✅ Solucionado

---

### A-08 — Conexión a BD sin límite de tiempo

**Qué estaba mal:**  
La conexión a la base de datos no tenía un `connect_timeout`, por lo que podría quedar colgada indefinidamente.

**Riesgo:**  
Una conexión lenta o colgada podría consumir recursos del servidor.

**Cómo se solucionó:**  
Se agregó `connect_timeout=5` segundos.

**Estado:** ✅ Solucionado

---

### A-09 — Errores mostrados al usuario

**Qué estaba mal:**  
Cuando ocurría un error, se enviaba la excepción completa al cliente:  
`return f"<h1>Sistema Caído</h1><p>{e}</p>", 500`

**Riesgo:**  
El usuario podía ver detalles internos: nombres de host, rutas, credenciales parciales, etc.

**Cómo se solucionó:**  
Los errores técnicos ahora se registran en los logs del servidor y el cliente solo recibe: `{"error": "Error interno del servidor"}`.

**Estado:** ✅ Solucionado

---

### A-10 — No se validaba el ID recibido

**Qué estaba mal:**  
El parámetro `id` provenía del usuario y se usaba directamente sin validar que fuera un número.

**Riesgo:**  
Además del SQL injection, un valor inesperado podría causar errores inesperados.

**Cómo se solucionó:**  
Ahora se valida con `int()` y se retorna un error 400 si no es un número entero.

**Estado:** ✅ Solucionado

---

### A-11 — División por cero en `/health`

**Qué estaba mal:**  
El endpoint `/health` tenía `resultado = 1 / 0` que se ejecutaba aleatoriamente, causando errores.

**Riesgo:**  
El health check fallaba aproximadamente el 30% de las veces, lo que podría hacer que sistemas de monitoreo lo consideraran caído.

**Cómo se solucionó:**  
Se eliminó la lógica y el endpoint ahora siempre devuelve `{"status": "ok"}` con código 200.

**Estado:** ✅ Solucionado

---

### A-12 — No había manejo global de errores

**Qué estaba mal:**  
No existía un manejador global de excepciones en la aplicación.

**Riesgo:**  
Cualquier error no capturado podría exponer una traza completa al cliente.

**Cómo se solucionó:**  
Se agregó `@app.errorhandler(Exception)` que captura todos los errores no esperados.

**Estado:** ✅ Solucionado

---

### A-13 — Imagen de Docker desactualizada

**Qué estaba mal:**  
El Dockerfile usaba `python:3.8`, que dejó de recibir soporte en octubre de 2024.

**Riesgo:**  
Sin actualizaciones de seguridad, la imagen podría tener vulnerabilidades conocidas sin parchear.

**Cómo se solucionó:**  
Se cambió a `python:3.11-slim`, una versión actualizada y soportada.

**Estado:** ✅ Solucionado

---

### A-14 — Versiones obsoletas de dependencias

**Qué estaba mal:**  
Se usaban Flask 1.1.2 y PyMySQL 0.9.3, versiones antiguas con vulnerabilidades conocidas.

**Riesgo:**  
Las versiones antiguas pueden tener errores de seguridad documentados (CVEs).

**Cómo se solucionó:**  
Se actualizaron a Flask 3.1.3 y PyMySQL 1.2.0.

**Estado:** ✅ Solucionado

---

### A-15 — La imagen incluía archivos innecesarios

**Qué estaba mal:**  
El Dockerfile hacía `COPY . /app` copiando todo, incluyendo `.git`, tests y resultados.

**Riesgo:**  
La imagen era más grande y podía exponer información innecesaria.

**Cómo se solucionó:**  
Se creó `.dockerignore` que excluye estos archivos de la imagen.

**Estado:** ✅ Solucionado

---

### A-16 — Sin `--no-cache-dir`

**Qué estaba mal:**  
`pip install` no usaba `--no-cache-dir`, dejando caché en la imagen.

**Riesgo:**  
La imagen era más grande de lo necesario y contenía artefactos innecesarios.

**Cómo se solucionó:**  
Se agregó `pip install --no-cache-dir -r requirements.txt`.

**Estado:** ✅ Solucionado

---

### A-17 — No había headers de seguridad

**Qué estaba mal:**  
La aplicación no enviaba headers de seguridad como `X-Frame-Options`, `Content-Security-Policy`, etc.

**Riesgo:**  
La aplicación era vulnerable a clickjacking y otros ataques del navegador.

**Cómo se solucionó:**  
Se integró **Flask-Talisman** que agrega automáticamente estos headers.

**Estado:** ✅ Solucionado

---

### A-18 — Puerto hardcodeado

**Qué estaba mal:**  
El puerto de escucha (5050) estaba escrito directamente en el código.

**Riesgo:**  
Dificultaba el despliegue en entornos donde se necesitaba otro puerto.

**Cómo se solucionó:**  
El puerto ahora viene de la variable de entorno `PORT`, con valor por defecto de 5050.

**Estado:** ✅ Solucionado

---

## Bandit: antes y después

| Momento | High | Medium | Low |
|---------|------|--------|-----|
| Antes del PASO 2 | 1 | 2 | 3 |
| Después del PASO 2 | 0 | 1 | 13 |

**Después de las correcciones:**

- **0 High** — Se eliminaron los problemas críticos (`debug=True`, credenciales hardcodeadas, SQL injection).
- **1 Medium** — B104 (`0.0.0.0`): **aceptable** en contexto de contenedor Docker.
- **13 Low** — B101 (`assert`): **falsos positivos**, todos en `test_app.py` (código de tests, no de producción).

---

## Resumen de correcciones aplicadas en el PASO 2

- Se eliminaron las credenciales del código y se usan variables de entorno.
- Se protegieron las consultas SQL con parámetros.
- Se eliminó `debug=True` y se usa Gunicorn como servidor.
- Se usa un usuario sin privilegios (`appuser`) en lugar de `root`.
- Se valida el ID recibido como número entero.
- Se ocultan los errores del cliente y se registran en logs.
- Se eliminó la división por cero en `/health`.
- Se agregó manejo global de errores.
- Se actualizó a Python 3.11-slim, Flask 3.x y PyMySQL 1.x.
- Se creó `requirements.txt` con las dependencias.
- Se creó `.dockerignore` para excluir archivos innecesarios.
- Se agregaron headers de seguridad con Flask-Talisman.
- El puerto es configurable con variables de entorno.
- Se creó `docker-compose.yml` con MySQL en una red interna (no expuesto al host).
- Se creó `.env.example` como plantilla (el `.env` real no entra en Git).

---

## Resultados verificados

| Verificación | Resultado |
|-------------|-----------|
| `pytest` | 6 passed |
| `bandit` (post-refactor) | 0 High, 1 Medium, 13 Low |
| `docker compose build` | SUCCESS |
| `docker compose up` | SUCCESS |
| `/health` | HTTP 200 — `{"status": "ok"}` |
| Headers de seguridad | X-Frame-Options, X-Content-Type-Options, CSP, Referrer-Policy |
| Usuario en contenedor | appuser (uid 1000, no root) |
| MySQL | En red interna, no expuesto al host |

---

## Comando utilizado para Bandit

```bash
# Escaneo inicial (PASO 1)
bandit -r . -x './.venv,./venv,./.git' -f json -o bandit-results.json -f txt

# Escaneo posterior (PASO 2)
bandit -r . -x './.venv,./venv,./.git' -f json -o bandit-results.json
bandit -r . -x './.venv,./venv,./.git' -f txt -o bandit-results.txt
```

**Archivos de evidencia:**
- `bandit-results.json` — salida en formato JSON
- `bandit-results.txt` — salida legible
