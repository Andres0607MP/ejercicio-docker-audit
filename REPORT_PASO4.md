# PASO 4 — Infraestructura y Despliegue en EC2

**Proyecto:** ejercicio-docker-audit  
**Fecha:** 2026-09-04  
**Registry:** Docker Hub (`andresmancera/mi-api`)  

---

## 1. Objetivo

Desplegar la aplicación en una instancia **AWS EC2** utilizando la imagen publicada en Docker Hub durante el PASO 3.

```
push main
   ↓
pytest → Bandit → Docker build → Trivy → Docker Hub → SSH EC2 → deploy
```

El flujo completo:

```
Internet
   │
   ├── :80  → Nginx Proxy Manager (HTTP)
   └── :443 → Nginx Proxy Manager (HTTPS)
       │
       ├── api.<domain> → Flask API (andresmancera/mi-api) → MySQL
       ├── dozzle.<domain> → Dozzle (logs)
       └── kuma.<domain> → Uptime Kuma (monitorización)
```

---

## 2. Arquitectura

```
                         INTERNET
                            │
                            │ 80 / 443
                            ▼
                  ┌─────────────────────┐
                  │        EC2          │
                  │                     │
                  │  Nginx Proxy       │
                  │  Manager           │
                  │  (:80 :443 :81)    │
                  │                     │
                  │  ┌───────────────┐  │
                  │  │ reverse proxy │  │
                  │  └───────┬───────┘  │
                  │          │           │
                  │          ▼           │
                  │  ┌────────────────┐ │
                  │  │   API Flask    │ │
                  │  │ andresmancera/ │ │
                  │  │    mi-api      │ │
                  │  └───────┬────────┘ │
                  │          │           │
                  │          ▼           │
                  │      MySQL           │
                  │                     │
                  │  Dozzle              │
                  │  Uptime Kuma         │
                  └─────────────────────┘
```

---

## 3. Servicios

| Servicio | Imagen | Red | Volumen | Puerto público |
|----------|--------|-----|---------|----------------|
| API Flask | `andresmancera/mi-api:${IMAGE_TAG}` | proxy + internal | — | No (solo vía NPM) |
| MySQL | `mysql:8.0` | internal | `mysql_data` | No |
| Nginx Proxy Manager | `jc21/nginx-proxy-manager` | proxy | `npm_data`, `npm_letsencrypt` | 80, 443, 81 (localhost) |
| Dozzle | `amir20/dozzle` | proxy | — | No (solo vía NPM) |
| Uptime Kuma | `louislam/uptime-kuma` | proxy | `kuma_data` | No (solo vía NPM) |

---

## 4. Docker Compose producción (`docker-compose.yml`)

El archivo `docker-compose.yml` contiene todos los servicios descritos arriba.

### Estrategia de tags
```
andresmancera/mi-api:${IMAGE_TAG:-latest}
```
- En CI/CD: `IMAGE_TAG` = `${{ github.sha }}` (tag inmutable por commit)
- En rollback: se puede override con cualquier tag SHA anterior
- Default: `latest` (si no se define `IMAGE_TAG`)

### Configuración de la aplicación
```yaml
app:
  image: andresmancera/mi-api:${IMAGE_TAG:-latest}
  env_file: .env
  environment:
    DB_HOST: mysql           # nombre del servicio en red internal
  healthcheck:               # usa /health → "OK" (200)
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5050/health', timeout=5)"]
  networks:
    proxy:                   # NPM puede proxyear a esta red
    internal:                # acceso a MySQL
```

### Configuración de MySQL
```yaml
mysql:
  image: mysql:8.0
  env_file: .env
  healthcheck:               # mysqladmin ping
  networks:
    - internal              # SOLO en red interna
```

---

## 5. Redes Docker

| Red | Servicios | Propósito |
|-----|-----------|-----------|
| `proxy` | nginx-proxy-manager, app, dozzle, uptime-kuma | NPM proxyea servicios externamente (80/443) |
| `internal` | mysql, app | MySQL es privado; app necesita acceder a MySQL |

### Razonamiento
- **MySQL** está SOLO en `internal` → no accesible públicamente ni desde Docker Hub
- **La app** está en AMBAS redes → puede hablar con MySQL (internal) y ser alcanzada por NPM (proxy)
- **Dozzle y Uptime Kuma** están en `proxy` → accesibles vía NPM pero sin puertos expuestos al host
- **NPM** está en `proxy` → expone 80, 443 al Internet

---

## 6. Volúmenes

| Volumen |Servicio| Propósito |
|---------|--------|-----------|
| `mysql_data` | MySQL | Datos de la base (persistencia) |
| `npm_data` | Nginx Proxy Manager | Configuración y datos de usuarios |
| `npm_letsencrypt` | Nginx Proxy Manager | Certificados SSL/TLS de Let's Encrypt |
| `kuma_data` | Uptime Kuma | Configuración de monitoreo |

---

## 7. Variables de entorno (`.env.example`)

El archivo `.env.example` documenta todas las variables de producción:

| Variable | Descripción | Valor en `.example` |
|----------|-------------|---------------------|
| `DB_HOST` | Host de MySQL | `mysql` |
| `DB_PORT` | Puerto de MySQL | `3306` |
| `DB_USER` | Usuario de BD | `appuser` |
| `DB_PASS` | Password de BD | `change_me_in_ec2` |
| `DB_NAME` | Nombre de BD | `legacydb` |
| `MYSQL_ROOT_PASSWORD` | Root password (MySQL) | `change_me_in_ec2` |
| `IMAGE_TAG` | Tag de la imagen Docker Hub | `latest` |

**IMPORTANTE:** El `.env` real se crea manualmente en la EC2. Nunca se commitea.

---

## 8. Docker Hub

### Registry
- **Usuario:** `andresmancera`
- **Repositorio:** `mi-api`
- **Imagen:** `andresmancera/mi-api`
- **Tags publicados:** SHA del commit, `latest`, nombre de rama

### ¿Imagen pública o privada?
- Si la imagen es **pública**: la EC2 puede hacer `docker pull` sin credenciales
- Si la imagen es **privada**: la EC2 necesita `docker login` con Docker Hub

**Recomendación:** Mantener la imagen **privada** para mayor seguridad.  
El deploy en CI/CD pasa las credenciales de Docker Hub al EC2 via secrets.

### Deploy desde Docker Hub (en EC2)
```bash
docker login -u "andresmancera" -p "<access-token>"
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
```

---

## 9. EC2

### Estado actual
La instancia EC2 **ya existe** pero no se han configurado las credenciales ni
el despliegue. La configuración está preparada pero pendiente de ejecución.

### Instalar Docker y Docker Compose en EC2
```bash
# SSH a la instancia
ssh -i <clave-privada.pem> <EC2_USER>@<EC2_PUBLIC_IP>

# Instalar Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Instalar Docker Compose
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verificar
docker --version
docker compose version
```

### Docker login desde EC2 (si imagen privada)
```bash
docker login -u "andresmancera" -p "<access-token>"
# o para evitar que la password aparezca en el historial:
echo "<access-token>" | docker login -u "andresmancera" --password-stdin
```

### Directorio de producción
```bash
mkdir -p ~/deploy
# Copiar docker-compose.yml y .env
# Crear .env manualmente con credenciales reales
# docker compose -f docker-compose.yml up -d
```

---

## 10. Security Group (AWS)

### Puertos permitidos
| Puerto | Destino | Comentario |
|--------|---------|------------|
| 22 | 0.0.0.0/0 o IP específica | SSH (restringir a IP administrativa) |
| 80 | 0.0.0.0/0 | HTTP (NPM) |
| 443 | 0.0.0.0/0 | HTTPS (NPM) |

### Puertos BLOQUEADOS (no expuestos)
| Puerto | Servicio | Razon |
|--------|----------|-------|
| 3306 | MySQL | Solo red `internal` |
| 5050 | Flask API | Solo NPM proxyea, no expuesto |
| 5051 | Flask dev | Solo desarrollo |
| 8080 | Alternativo | No usado en prod |
| 9000 | PHP-FPM | No usado |
| 3001 | Kuma alt | No usado |
| 81 | NPM admin | Solo `127.0.0.1:81:81` (localhost) |

---

## 11. Firewall interno (UFW)

### Configuración recomendada
```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

### IMPORTANTE: UFW y Docker
UFW no filtra tráfico de contenedores Docker por defecto. Las reglas de
Security Group de AWS son el firewall de primera instancia. UFW actúa como
segundo nivel de defensa en el SO.

Para restringir containers con UFW, se necesitaría configuración adicional
(`DOCKER-USER` chain en iptables), pero fuera del alcance del PASO 4.

---

## 12. Nginx Proxy Manager (NPM)

### Puertos
| Puerto | Uso | Exposición |
|--------|-----|------------|
| 80 | HTTP (entrada) | Público (0.0.0.0:80) |
| 443 | HTTPS (entrada) | Público (0.0.0.0:443) |
| 81 | Admin UI | Localhost solo (127.0.0.1:81) |

### Primer uso
1. Acceder a `http://<EC2_IP>:81` (vía localhost o SSH tunnel)
2. Credenciales por defecto: `admin@example.com` / `changeme`
3. Cambiar password inmediatamente

### Configurar proxy para servicios
En la UI de NPM → **Proxy Manager** → **Add Proxy Host**:
- **Domain Names:** `api.example.com`
- **Scheme:** `http`
- **Forward Hostname/IP:** `app`
- **Port:** `5050`

---

## 13. Subdominios

| Subdominio | Servicio | Forward Hostname | Forward Port |
|------------|----------|------------------|--------------|
| `api.<domain>` | Flask API | `app` | `5050` |
| `dozzle.<domain>` | Dozzle | `dozzle` | `9999` |
| `kuma.<domain>` | Uptime Kuma | `uptime-kuma` | `3001` |

### DNS
Los registros A deben apuntar a la IP pública de la EC2:
```
api.example.com    → <EC2_PUBLIC_IP>
dozzle.example.com → <EC2_PUBLIC_IP>
kuma.example.com   → <EC2_PUBLIC_IP>
```

> **PLACEHOLDER:** Reemplaza `<domain>` con tu dominio real y `<EC2_PUBLIC_IP>`
> con la IP de tu instancia. **NO inventado.**

---

## 14. HTTPS (Let's Encrypt)

NPM gestiona certificados Let's Encrypt automáticamente.

### Proceso
1. Configurar DNS (registro A → IP EC2)
2. En NPM → Proxy Host → Editar → SSL
3. Habilitar **Request a new SSL Certificate**
4. NPM solicita automáticamente a Let's Encrypt
5. Certificado se almacena en `npm_letsencrypt:/etc/letsencrypt`

### Certificados
- **NO** almacenar certificados privos en Git
- NPM gestiona los certificados dentro del volumen `npm_letsencrypt`
- Let's Encrypt requiere que el dominio resuelva a la IP pública de la EC2

---

## 15. Dozzle

- ** imagen:** `amir20/dozzle:latest`
- **Puerto interno:** 9999 (no expuesto al host)
- **Acceso:** vía NPM → `dozzle.<domain>`
- **Función:** visor de logs de contenedores Docker en tiempo real
- **Socket:** `/var/run/docker.sock:/var/run/docker.sock:ro` (read-only)

---

## 16. Uptime Kuma

- **Imagen:** `louislam/uptime-kuma:latest`
- **Puerto interno:** 3001 (no expuesto al host)
- **Acceso:** vía NPM → `kuma.<domain>`
- **Función:** monitorización de uptime
- **Checks sugeridos:**
  - **API:** HTTP `http://app:5050/health`
  - **NPM:** HTTP `http://nginx-proxy-manager:81` (o TCP port 80)
  - **MySQL:** TCP `mysql:3306`

---

## 17. Healthcheck

### API Flask
```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5050/health', timeout=5)"]
```
- Endpoint: `GET /health` → 200 OK
- Periodo: 30s
- Timeout: 10s
- Retries: 3
- Start period: 30s (espera al inicio)

### MySQL
```yaml
healthcheck:
  test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1"]
```

### Uptime Kuma
Configurar checks de monitorización en la UI:
1. **API:** HTTP(S) → `https://api.<domain>/health`
2. **NPM:** HTTP → `http://nginx-proxy-manager:81`
3. **MySQL:** MySQL → `mysql:3306`

---

## 18. Deploy SSH (GitHub Actions → EC2)

### Job en workflow
```yaml
deploy-ec2:
  name: Deploy to EC2
  runs-on: ubuntu-latest
  needs: [test, security-scan, trivy-scan, publish-dockerhub]
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  steps:
    - name: Checkout código
      uses: actions/checkout@v4

    - name: Copy prod compose to EC2
      uses: appleboy/scp-action@v1
      with:
        host: ${{ secrets.SERVER_HOST }}
        username: ${{ secrets.SERVER_USER }}
        key: ${{ secrets.SERVER_SSH_KEY }}
        source: "docker-compose.yml"
        target: "~/deploy/"

    - name: Deploy on EC2
      uses: appleboy/ssh-action@v1
      env:
        DOCKER_USERNAME: ${{ secrets.DOCKER_USERNAME }}
        DOCKER_PASSWORD: ${{ secrets.DOCKER_PASSWORD }}
        IMAGE_TAG: ${{ github.sha }}
      with:
        host: ${{ secrets.SERVER_HOST }}
        username: ${{ secrets.SERVER_USER }}
        key: ${{ secrets.SERVER_SSH_KEY }}
        envs: DOCKER_USERNAME,DOCKER_PASSWORD,IMAGE_TAG
        script: |
          set -e
          cd ~/deploy
          docker login -u "$DOCKER_USERNAME" -p "$DOCKER_PASSWORD"
          docker compose -f docker-compose.yml pull
          docker compose -f docker-compose.yml up -d --remove-orphans
          echo "Deploy completado exitosamente"
```

### Orden del workflow
```
push main
  → test (pytest) ─┐
                   ├─→ docker-build ──→ trivy-scan ─→ publish-dockerhub ──→ deploy-ec2 (SSH EC2)
  → security-scan ─┘
```

### Garantía de imagen única
- **Build** se hace una vez en `docker-build`
- **Trivy** escanea la misma imagen (artefacto `.tar`)
- **publish-dockerhub** publica la misma imagen a Docker Hub
- **deploy-ec2** hace `docker pull` de la misma imagen desde Docker Hub

La imagen desplegada en EC2 es idéntica a la escaneada. No hay rebuild.

---

## 19. Secrets de GitHub

### Secrets para PASO 3 (CI/CD + Docker Hub)
| Secret | Valor | Cómo crear |
|--------|-------|------------|
| `DOCKER_USERNAME` | `andresmancera` | GitHub → Settings → Secrets → Actions |
| `DOCKER_PASSWORD` | Docker Hub Access Token | https://hub.docker.com → Security → New Access Token |

### Secrets para PASO 4 (Deploy EC2)
| Secret | Descripción | Cómo crear |
|--------|-------------|------------|
| `SERVER_HOST` | IP pública o DNS de la EC2 | IP de la instancia EC2 en AWS |
| `SERVER_USER` | Usuario SSH (ej: `ubuntu`) | Según la AMI usada |
| `SERVER_SSH_KEY` | Clave privada SSH | `cat <clave.pem>` y pegar completa |

### Cómo crear las secrets
1. GitHub → tu repositorio → Settings → Secrets and variables → Actions
2. Click en "New repository secret"
3. Ingresar nombre y valor
4. Click en "Add secret"

> **REGLA DE ORO:** Nunca comitear secrets ni credenciales en el repositorio.
> Usar siempre GitHub Secrets.

### Tres tipos de credenciales

| Tipo | Dónde viven | Uso |
|------|-------------|-----|
| **Credenciales locales** | Tu PC | `docker login` local, `docker compose` local |
| **Secrets de GitHub Actions** | GitHub → Settings → Secrets → Actions | CI/CD: Docker Hub upload + SSH deploy |
| **Credenciales EC2** | Dentro de la instancia EC2 | `docker login` en EC2, `.env` de producción |

---

## 20. Rollback

### Estrategia: tags inmutables por commit SHA

Docker Hub contiene estos tags (generados por `docker/metadata-action`):
- `andresmancera/mi-api:<commit-sha>` — tag único inmutable
- `andresmancera/mi-api:main` — tag de rama
- `andresmancera/mi-api:latest` — apunta a última versión

### Rollback paso a paso

1. **Identificar el SHA anterior deseado:**
   ```bash
   # En GitHub → tu repositorio → commits
   # Copia el SHA del commit anterior (ej: abc123def456)
   ```

2. **En la EC2, hacer login y pull del tag específico:**
   ```bash
   cd ~/deploy
   docker login -u "andresmancera" -p "<access-token>"
   docker compose -f docker-compose.yml up -d IMAGE_TAG=abc123def456
   ```

3. **Verificar:**
   ```bash
   curl -H "Host: api.<domain>" http://localhost:80/health
   # Debe retornar: OK
   ```

4. **El rollback dís para trás:**
   - `docker-compose.yml` usa `${IMAGE_TAG:-latest}`
   - El override `IMAGE_TAG=<sha>` toma precedencia sobre `.env`
   - No se necesita modificar el compose file

### Rollback vía Git revert
Si el problema fue un código defectuoso:
```bash
git revert <commit-sha>
git push origin main
# El workflow corre todo el pipeline con el SHA revertido
# y publica la imagen corregida automáticamente
```

---

## 21. Verificaciones

### Local (antes de push a GitHub)
```bash
docker compose config                          # dev compose OK
docker compose -f docker-compose.yml config  # prod compose OK
python3 -c "import yaml; yaml.safe_load(...)"  # YAML workflow OK
pytest -v                                      # 7 passed
bandit -r . -c bandit.yaml                     # 0 issues
```

### En EC2 (después del deploy)
```bash
# SSH a la instancia
ssh -i <clave>.pem <user>@<ip>

# Verificar contenedores
docker compose -f docker-compose.yml ps

# Verificar health
docker compose -f docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}"

# Probar API vía NPM (o directamente)
curl -H "Host: api.example.com" http://localhost:80/health
# → OK

# Ver logs
docker compose -f docker-compose.yml logs -f app
docker compose -f docker-compose.yml logs -f nginx-proxy-manager
```

### Verificar imagen publicada
```bash
docker pull andresmancera/mi-api:latest
docker images | grep mi-api
```

---

## 22. Evidencias que capturar para el informe

| Evidencia | Cómo obtenerla |
|-----------|----------------|
| Workflow completo verde en GitHub Actions | Screenshot de 6 jobs con ✓ verde |
| Imagen en Docker Hub | Screenshot de https://hub.docker.com/repositories/andresmancera |
| Contenedores en EC2 | `docker ps` en la instancia |
| Health check funcionando | `curl http://<domain>/health` → `OK` |
| Headers de seguridad | `curl -sI http://<domain>/health` (CSP, X-Frame, etc.) |
| Ports listening | `ss -tlnp` en EC2 (solo 80,443,81,22) |
| Security Group en AWS | Screenshot de inbound rules |
| NPM proxy configurado | Screenshot de proxy host en UI |
| Let's Encrypt activo | `curl -sI https://<domain>` (200 + certificado) |
| Rollback documentado | Screenshot de `docker compose up -d IMAGE_TAG=<sha>` |

---

## 23. Estado pendiente

| Tarea | Estado |
|-------|--------|
| Instancia EC2 existe | ✅ Existe |
| Docker Hub imagen publicada | ✅ (PASO 3) |
| Secrets `DOCKER_USERNAME`/`DOCKER_PASSWORD` creadas | ⚠ Pendiente usuario |
| Secrets `SERVER_HOST`/`USER`/`SSH_KEY` creadas | ❌ Pendiente (PASO 4) |
| SSH desde GitHub Actions a EC2 | ⚠ Pendiente secrets |
| Deploy de prueba en EC2 | ❌ Pendiente conexión |
| DNS/subdominios configurados | ❌ Pendiente dominio |
| HTTPS/Let's Encrypt configurado | ❌ Pendiente dominio |

---

## 24. Comandos de referencia

### En EC2 (inicialización manual)
```bash
# 1. Crear directorio
mkdir -p ~/deploy && cd ~/deploy

# 2. Copiar archivos (desde tu PC)
scp -i <clave>.pem docker-compose.yml <user>@<ip>:~/deploy/

# 3. Crear .env en EC2
cat > .env << 'EOF'
DB_HOST=mysql
DB_PORT=3306
DB_USER=appuser
DB_PASS=<real-password>
DB_NAME=legacydb
MYSQL_ROOT_PASSWORD=<real-root-pass>
IMAGE_TAG=latest
EOF

# 4. Login Docker Hub (si imagen privada)
docker login -u "andresmancera" -p "<access-token>"

# 5. Levantar stack
docker compose -f docker-compose.yml up -d

# 6. Verificar
docker compose -f docker-compose.yml ps
```

### En GitHub Actions (automático)
Al hacer `git push origin main`:
1. Corre todo el pipeline (test, bandit, build, trivy, push)
2. El job `deploy-ec2` corre al final
3. Copia `docker-compose.yml` al EC2 vía SCP
4. SSH ejecuta: `docker pull` + `docker compose up -d`

### Rollback manual en EC2
```bash
cd ~/deploy
docker compose -f docker-compose.yml up -d IMAGE_TAG=<commit-sha-anterior>
```

---

## 25. Qué NO hacer

- ❌ Migrar a GHCR (Docker Hub es el registry definitivo)
- ❌ Commitear `.env`
- ❌ Commitear claves SSH
- ❌ Hardcodear credenciales Docker Hub en el workflow
- ❌ Hardcodear IP de EC2 en el workflow
- ❌ Inventar dominio ni certificados
- ❌ Abrir puertos 3306, 5050, 9000 al Internet
- ❌ Saltar los checks de seguridad (test, bandit, trivy)
- ❌ Deploy sin pasar por Docker Hub
- ❌ Crear imágenes diferentes para prod vs CI

---

## Confirmaciones

1. **Docker Hub sigue siendo el registry ✓** — El workflow usa `DOCKER_USERNAME`/`DOCKER_PASSWORD` y `andresmancera/mi-api`. No hay referencias a GHCR.
2. **Ningún secreto hardcodeado ✓** — Todas las credenciales usan GitHub Secrets.
3. **Ninguna credencial inventada ✓** — SERVER_HOST, SERVER_USER, SERVER_SSH_KEY usan placeholders de secrets. EC2 IP y dominio no inventados.
4. **Single-build mantenido ✓** — Misma imagen para Trivy y Docker Hub y EC2.
5. **No se ejecutó deploy real ✓** — Pendiente secrets del usuario.

---

## Flujo consolidado PASO 3 + PASO 4

```
PASO 3: CI/CD
┌─────────────────────────────────────────────────────────┐
│ pytest → Bandit → Docker build → Trivy → Docker Hub     │
│  (single-build: una imagen, un .tar, un artefacto)      │
└─────────────────────────────────────────────────────────┘

PASO 4: Deploy
┌─────────────────────────────────────────────────────────┐
│ Docker Hub → SSH EC2 → docker pull → docker compose up -d │
│  (misma imagen, tag por commit SHA)                      │
└─────────────────────────────────────────────────────────┘
```
