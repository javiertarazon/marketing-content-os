# Auditoría de Marketing Content OS

## 1. Resumen ejecutivo

Marketing Content OS fue restaurado y reordenado en `D:\proyectos_javier\marketing-content-os` con un enfoque de MVP funcional en WSL + Docker + Colab. La solución actual combina:

- API local para cola de jobs y lease management.
- dashboard local para seguimiento del pipeline.
- workers de investigación y render en Google Colab.
- Cloudflare Quick Tunnel para exponer la API local a Colab sin abrir puertos.
- Cloudflare R2 para almacenamiento de audio y video.
- Hugging Face Spaces privados para guión y voz.
- Mixpost Lite como flujo manual opcional para revisión y programación.

La plataforma no está “lista para producción” todavía, pero sí quedó preparada para validación real del flujo end-to-end en local y con workers remotos temporales.

## 2. Problemas detectados y su resolución

### 2.1 WSL se perdió y el proyecto estaba incompleto

Problema:
- WSL se reinstalled sin preservar el entorno previo.
- El proyecto existía en disco local, pero no estaba en una estructura Git finalizada.

Solución:
- Se reinstaló WSL 2 + Ubuntu.
- Se restauró la carpeta del proyecto en `D:\proyectos_javier\marketing-content-os`.
- Se validaron Node.js, Git, Docker y Python dentro de Ubuntu.

### 2.2 Colab no podía acceder a localhost

Problema:
- Google Colab no puede acceder a servicios en `localhost` del PC del usuario.

Solución:
- Se usó Cloudflare Quick Tunnel como puente temporal.
- Se configuró un gateway de workers con whitelist de rutas para exponer solo endpoints críticos.
- La API local quedó protegida con `WORKER_API_TOKEN`.

### 2.3 Confusión entre tokens de Cloudflare y credenciales S3

Problema:
- Se mezclaron conceptos de token API de Cloudflare con claves S3 de R2.

Solución:
- Se documentó la separación clara:
  - Token de Cloudflare REST API: gestión del bucket y la cuenta.
  - Access Key ID + Secret Access Key S3: lectura/escritura de objetos.
- Se usa `.env.cloudflare.local` para secretos administradores y `.env` para runtime local.

### 2.4 Secretos expuestos o guardados sin control

Problema:
- Cualquier token o secret guardado en Git o en el chat es riesgoso.

Solución:
- Se mantiene `.env` y `.env.cloudflare.local` ignorados por Git.
- Se usa `.env.example` como template seguro.
- Se insiste en no compartir claves reales en el repositorio ni en la conversación.

### 2.5 R2 activado sin verificar permisos reales

Problema:
- El bucket quedó sin un uso seguro si la cuenta no tenía R2 habilitado o si la clave era incorrecta.

Solución:
- Se verificó que la cuenta tenía R2 habilitado.
- Se validó el acceso S3 con credenciales de objeto.
- Se documentó que `r2.dev` es público por diseño y solo se usa para pruebas.

## 3. Estado funcional del proyecto

### 3.1 Lo que sí quedó funcionando

- WSL + Ubuntu operativo.
- Git operativo y repositorio configurado.
- API local levantada y respondiendo en localhost.
- Dashboard local funcionando.
- PostgreSQL y Redis levantados con Docker Compose.
- Gateway Nginx de workers para Quick Tunnel.
- API con cola de jobs, lease, heartbeat y reencolado.
- R2 con bucket creado y configurado para pruebas.
- README y documentación operativa actualizados.

### 3.2 Lo que aún requiere validación end-to-end

- ejecución real de los notebooks en Colab,
- consumo real del flujo investigación -> guion -> voz -> audio -> render,
- carga real de secretos en Colab Secrets,
- validación del worker de render contra la cola,
- uso final de Mixpost para publicación real,
- migración a VPS/GPU para producción estable.

## 4. Estructura del repositorio y funciones

- `apps/api`: API FastAPI con cola y lease de trabajos.
- `apps/dashboard`: dashboard local de monitoreo.
- `apps/voice-studio-space`: Space de voz generado para Hugging Face.
- `apps/script-generator-space`: Space de generación de guiones.
- `notebooks/01_research_scrapegraph.ipynb`: worker de investigación.
- `notebooks/02_render_remotion.ipynb`: worker de render.
- `infra/docker-compose.yml`: servicios locales (API, DB, Redis, tunnel, gateway).
- `infra/worker-gateway.conf`: whitelist de rutas del tunnel.
- `packages/python/*`: esquemas y adaptadores compartidos.
- `tests/`: validaciones básicas del proyecto.
- `scripts/`: utilidades de despliegue y asistencia.

## 5. Variables y credenciales requeridas

Las credenciales no se deben guardar en Git ni en el chat. Todo debe quedar en:

- `.env` local (ignorado por Git),
- `.env.cloudflare.local` local (ignorado por Git),
- Google Colab Secrets,
- Hugging Face Tokens,
- Cloudflare Dashboard.

### 5.1 Variables principales del proyecto

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `DATABASE_URL`
- `REDIS_URL`
- `WORKER_API_TOKEN`
- `CORS_ORIGINS`
- `VOICE_STUDIO_URL`
- `SCRIPT_SPACE_URL`
- `HF_TOKEN`
- `MIXPOST_URL`
- `MIXPOST_DOMAIN`
- `MIXPOST_APP_KEY`
- `MIXPOST_DB_NAME`
- `MIXPOST_DB_USER`
- `MIXPOST_DB_PASSWORD`
- `MIXPOST_DB_ROOT_PASSWORD`

### 5.2 Variables de Cloudflare y R2

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `R2_BUCKET_NAME`
- `S3_ENDPOINT_URL`
- `S3_BUCKET`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`
- `STORAGE_PUBLIC_BASE_URL`

### 5.3 Variables para Colab

- `API_BASE_URL`
- `WORKER_API_TOKEN`
- `S3_ENDPOINT_URL`
- `S3_BUCKET`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`
- `STORAGE_PUBLIC_BASE_URL`
- `SCRIPT_SPACE_URL`
- `VOICE_STUDIO_URL`
- `HF_TOKEN`

## 6. Dónde se obtienen cada una

### Cloudflare API token

Se genera en:
- Cloudflare Dashboard → My Profile → API Tokens

Debe tener acceso de cuenta a R2 y usar permisos adecuados para el bucket.

### Account ID

Se obtiene de la cuenta de Cloudflare en el dashboard o la URL de la cuenta.

### R2 bucket

Se crea en:
- Cloudflare Dashboard → R2 Object Storage

### Credenciales S3

Se obtienen desde la configuración asociada al bucket en R2.

### Hugging Face token

Se genera en:
- https://huggingface.co/settings/tokens

Debe usarse como token de lectura para Spaces privados.

### Mixpost

Se configura localmente con dominio HTTPS real para publicar en redes sociales.

## 7. Recomendación de seguridad y uso

- No subir `.env` ni `.env.cloudflare.local` al repositorio.
- No pegar tokens ni claves en README, notebooks, chat ni GitHub.
- Usar `r2.dev` solo para pruebas y no como almacenamiento definitivo.
- Separar bien los contextos:
  - token de gestión Cloudflare,
  - credenciales S3 del bucket,
  - token HF,
  - token de la API del worker.
- Para producción, migrar a un dominio fijo y una infraestructura más estable. 

## 8. Siguiente paso recomendado

La siguiente fase debe ser una validación real del flujo completo con Colab, cargando secretos en cada notebook y ejecutando un trabajo real desde la API hasta la publicación final de audio/video en R2 y el dashboard. Esa validación es la que determina si el MVP está listo para una migración a un entorno más estable.
