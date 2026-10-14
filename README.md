# Marketing Content OS

Plataforma modular para coordinar investigacion, generacion multimedia, renderizado y programacion de publicaciones. El repositorio contiene el orquestador para WSL, plantillas independientes para Hugging Face Spaces y notebooks para workers de Google Colab.

> MVP: API/cola, Spaces privados de voz y guiones, dos notebooks de Colab y programación manual en Mixpost Lite. Requiere configurar cuentas, claves y almacenamiento.

## Estructura

- `apps/api`: API FastAPI y ciclo de vida de trabajos.
- `apps/dashboard`: interfaz Next.js inicial.
- `apps/voice-studio-space`: Space Gradio privado de VoiceStudio/OmniVoice sobre ZeroGPU.
- `apps/script-generator-space`: Space Gradio privado de Qwen3-4B sobre ZeroGPU.
- `packages/python/core`: esquemas compartidos.
- `packages/python/adapters`: clientes para servicios externos.
- `packages/node/video-templates`: punto de entrada de plantillas Remotion.
- `notebooks`: workers iniciales para investigacion y render.
- `infra`: Docker Compose para PostgreSQL, Redis y servicios locales.
- `scripts/clone_third_party.py`: clona los repositorios indicados solo cuando se ejecuta.

## Requisitos

- WSL 2 con Ubuntu, Git y Docker Desktop integrado con WSL.
- Docker Compose v2.
- Python 3.11+ para pruebas locales.
- Node.js 20+ para el dashboard.
- Para despliegues: cuenta Hugging Face y Google; las credenciales se configuran en cada plataforma, no en Git.

## Arranque local en WSL

Desde la raíz del repositorio:

```bash
cp .env.example .env
# Edita .env y establece contrasenas/secretos locales.
docker compose --env-file .env -f infra/docker-compose.yml up --build -d
curl http://localhost:8000/healthz
```

API: `http://localhost:8000`; dashboard de desarrollo: `http://localhost:3001`.
Para iniciar el dashboard fuera de Docker: `cd apps/dashboard && npm install && npm run dev`.

El token `WORKER_API_TOKEN` protege las rutas de reserva, renovacion, finalizacion y fallo de los trabajos. Redis queda preparado para tareas futuras; el MVP actual persiste y reserva trabajos desde PostgreSQL. Los trabajos en ejecucion renuevan su reserva cada minuto; si Colab se desconecta, la reserva vence y el trabajo vuelve a la cola hasta un maximo de tres intentos.

### Probar workers de Colab contra la app local

Para desarrollo se puede dar a la API local un endpoint HTTPS temporal con Cloudflare Quick Tunnel, sin contratar dominio ni abrir puertos entrantes del router. El tunel es solo para pruebas: su hostname cambia al reiniciarlo, no tiene garantia de disponibilidad y el equipo local debe permanecer encendido, conectado a Internet y con Docker activo.

1. Inicia la API, el dashboard y las bases de datos:

   ```bash
   docker compose --env-file .env -f infra/docker-compose.yml up --build -d
   ```

2. Inicia la puerta de workers y el tunel:

   ```bash
   docker compose --profile colab-tunnel --env-file .env -f infra/docker-compose.yml up -d worker-gateway cloudflared
   docker compose --profile colab-tunnel --env-file .env -f infra/docker-compose.yml logs -f cloudflared
   ```

   Copia la URL `https://...trycloudflare.com` que aparece en el log. `Ctrl+C` solo cierra la vista de logs; para parar el tunel ejecuta `docker compose --profile colab-tunnel --env-file .env -f infra/docker-compose.yml stop cloudflared worker-gateway`. Al iniciar otro Quick Tunnel se generara otra URL.

3. La URL del tunel solo reenvia `POST /v1/jobs/next`, `POST /v1/jobs/{id}/heartbeat`, `POST /v1/jobs/{id}/complete` y `POST /v1/jobs/{id}/fail`. No publica el alta/listado de trabajos, PostgreSQL, Mixpost ni la documentacion de la API. La API exige `WORKER_API_TOKEN` y un lease valido. Copia el valor local de `WORKER_API_TOKEN` desde `.env` directamente a los Secrets de Colab; no lo pegues en el notebook ni en Git.

4. Configura almacenamiento persistente para audio y videos. En Cloudflare crea un bucket R2, genera credenciales S3 con permisos solo para ese bucket y guarda sus valores unicamente en Colab Secrets:

   - `S3_ENDPOINT_URL`: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`
   - `S3_BUCKET`: nombre del bucket R2.
   - `S3_ACCESS_KEY_ID` y `S3_SECRET_ACCESS_KEY`: credenciales S3 del bucket.
   - `STORAGE_PUBLIC_BASE_URL`: URL publica del bucket (para pruebas se puede habilitar `r2.dev`; para uso estable, un dominio personalizado).

   Configura el bucket como publico solo si aceptas que cualquiera con la URL pueda ver los WAV y MP4 generados. R2 Standard indica actualmente un nivel gratuito de 10 GB-mes, 1 millon de operaciones Class A, 10 millones Class B y salida de datos sin costo; verifica el precio vigente y elimina medios que ya no necesites.

5. En **cada notebook** abre el panel **Secrets** (icono de llave), crea cada nombre, pega su valor y habilita el acceso para el notebook. Usa exactamente:

   - En `01_research_scrapegraph.ipynb`: `API_BASE_URL` (la URL `trycloudflare.com`, sin `/` final), `WORKER_API_TOKEN`, `SCRIPT_SPACE_URL` (`https://javiertarazon-marketing-script-generator.hf.space`), `VOICE_STUDIO_URL` (`https://javiertarazon-voice-studio-agent.hf.space`), `HF_TOKEN`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` y `STORAGE_PUBLIC_BASE_URL`.
   - En `02_render_remotion.ipynb`: `API_BASE_URL`, `WORKER_API_TOKEN` y los cinco secretos `S3_*`/`STORAGE_PUBLIC_BASE_URL`.

   Crea `HF_TOKEN` en Hugging Face como token de solo lectura que tenga acceso a tus dos Spaces privados. No compartas ese token en el chat. Los Spaces ya desplegados son privados y usan ZeroGPU, que puede poner las solicitudes en cola y limitar la cuota diaria.

6. Abre ambos notebooks en Google Colab y ejecuta sus celdas desde arriba. Deja la ultima celda ejecutandose en cada runtime: los workers consultan sus respectivas colas cada 30 segundos y siguen esperando trabajos hasta que detengas la celda. Colab gratuito puede desconectar o limitar runtimes; no es un worker 24/7. Si reinicias el tunel, actualiza `API_BASE_URL` en Secrets y vuelve a ejecutar la celda de configuracion.

7. Abre `http://localhost:3001`, crea un trabajo con tema y URL publica del articulo. La API lo deja en `queued` para `research`; el worker 01 lo investiga, genera guion y audio y, al completar, la API crea automaticamente otro trabajo `queued` para `render`. El worker 02 produce el MP4. El dashboard consulta la cola automaticamente cada 10 segundos. Comprueba estados y errores en esa pagina.

8. Al terminar, detene las celdas de Colab con el boton Stop y apaga el tunel con el comando del paso 2. No apagues Docker mientras haya trabajos activos. Para produccion/migracion, se conserva el mismo API, esquema y almacenamiento S3; se cambia el endpoint temporal por un dominio fijo con HTTPS y se despliegan API y base de datos en el VPS.

Para iniciar Mixpost Lite (edición MIT) junto con sus servicios aislados de MySQL y Redis:

```bash
docker compose --profile scheduler --env-file .env -f infra/docker-compose.yml up -d mixpost
```

Abre `http://localhost:3002` para completar la configuración inicial de Mixpost. El dashboard permite abrir Mixpost y descargar el MP4 renderizado para subirlo manualmente y programarlo. No hay publicación automática ni integración de API entre las aplicaciones. La imagen `inovector/mixpost:latest` y MySQL necesitan descargarse la primera vez.

**El Mixpost local solo sirve para evaluar la interfaz.** Las conexiones OAuth de redes sociales normalmente necesitan una URL pública HTTPS, un dominio estable y credenciales de desarrollador aprobadas por cada plataforma. Configura `MIXPOST_URL` y `MIXPOST_DOMAIN` con ese dominio antes de conectar cuentas; no expongas la instancia local directamente a Internet.

El adaptador Postiz anterior se conserva en el repositorio, pero ya no forma parte del Compose ni del flujo del dashboard; la programación de este MVP se realiza manualmente en Mixpost.

Para apagar los servicios locales: `docker compose --profile scheduler --env-file .env -f infra/docker-compose.yml down`. Los datos de PostgreSQL y Mixpost se mantienen en volúmenes Docker.

## Hugging Face Spaces

Clona primero VoiceStudio con `python scripts/clone_third_party.py`. Instala la CLI `hf` en WSL (`uv tool install huggingface_hub`) e inicia sesion (`hf auth login`) con un token que permita crear Spaces y subir archivos. La cuenta debe ser elegible para ZeroGPU; las cuentas gratuitas requieren correo verificado y mas de 30 dias de antiguedad, y tienen cuota diaria. Ejecuta `bash scripts/deploy_hf_spaces.sh`: crea/actualiza `voice-studio-agent` como Space privado Gradio con hardware `zero-a10g` (el identificador de ZeroGPU en la CLI actual) y publica la app. No se selecciona T4 ni hardware facturable. Tras publicar, `hf spaces zero-gpu quota` consulta el saldo diario.

El Space carga el modelo `k2-fsa/OmniVoice` mediante el paquete del repositorio VoiceStudio y reserva ZeroGPU solo durante cada inferencia. El endpoint Gradio es `/predict`; llama con `gradio_client` y un token HF de solo lectura. Añade `VOICE_STUDIO_URL` y `HF_TOKEN` a `.env` para el cliente local, y guarda `HF_TOKEN` como secreto de Colab para invocar el Space privado. La cuota gratuita de ZeroGPU es limitada (5 minutos diarios segun las condiciones publicadas por Hugging Face); la cola y descarga inicial del modelo pueden hacer el servicio lento. No se afirma que el Space este publicado hasta completar el inicio de sesion y el build en tu cuenta.

Para generar investigación editorial y guiones, `apps/script-generator-space` carga `Qwen/Qwen3-4B` de forma diferida en ZeroGPU. Inicia sesión con `hf auth login` y ejecuta `bash scripts/deploy_hf_script_space.sh`; el script crea un Space privado `marketing-script-generator` con hardware `zero-a10g`. Configura `SCRIPT_SPACE_URL` con la URL asignada y guarda un token HF de solo lectura en el secreto `HF_TOKEN` de Colab. El Space usa el mismo token que el Space de voz. Revisa el build antes de usarlo; no se despliega automáticamente ni se ha verificado la elegibilidad/cuota de tu cuenta.

ZeroGPU gratuito tiene cuota diaria y colas, no es inferencia ilimitada ni un SLA. Las condiciones de elegibilidad y cuota pueden cambiar; verifica la disponibilidad desde tu cuenta Hugging Face. La extracción del artículo web se hace con `requests` y BeautifulSoup en Colab; el Space recibe el texto extraído y produce notas de investigación y un guion en una única inferencia. Qwen no garantiza exactitud factual: revisa el guion y las fuentes antes de publicar. No se usa OpenAI.

No publico HyperFrames ni Open-Generative-AI como Spaces Gradio falsos: ambos repos son frameworks/apps, no inferencia Gradio. HyperFrames/Remotion se usan en Colab para render; Open-Generative-AI es una app web/Electron independiente.

## Google Colab

Abre `notebooks/01_research_scrapegraph.ipynb` o `notebooks/02_render_remotion.ipynb` en Colab con la cuenta `javiertarazpon@gmail.com` (sube los archivos desde tu equipo o clona este repositorio despues de publicarlo en GitHub). Este proyecto no recibe acceso a tu Drive ni a tu cuenta. Guarda secretos en **Secrets** de Colab, no en celdas compartidas. Ambos notebooks necesitan `API_BASE_URL`, `WORKER_API_TOKEN`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` y `STORAGE_PUBLIC_BASE_URL`. El notebook de investigación también necesita `SCRIPT_SPACE_URL`, `VOICE_STUDIO_URL` y un `HF_TOKEN` de solo lectura con acceso a ambos Spaces privados. Investiga y genera el guion mediante Qwen en ZeroGPU, llama a VoiceStudio por Gradio, sube WAV a S3/R2 y encola el render; el segundo notebook renderiza MP4 con una composición Remotion básica y lo sube al bucket.

Los notebooks mantienen workers de polling mientras sus celdas y runtimes sigan activos. Un Quick Tunnel permite que Colab consulte durante pruebas la API propia de WSL mediante HTTPS temporal; no mantiene el equipo despierto ni elude las restricciones/cuotas de Colab.

El notebook de investigación requiere `API_BASE_URL`, `WORKER_API_TOKEN` y una `source_url` por trabajo. El de render requiere un proyecto Remotion, configuración S3/R2 y el mismo API público. Remotion y HyperFrames son frameworks de render, no Spaces de generación de imágenes; el pipeline necesita una composición/plantilla real.

## Pruebas

```bash
export PATH="$HOME/.local/bin:$PATH"
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r apps/api/requirements-dev.txt -r packages/python/adapters/requirements.txt
python -m pytest tests
```

## Repositorios externos

`python scripts/clone_third_party.py` clona shallow en WSL los repositorios indicados, excepto `MoneyPrinterTurbo` (excluido a petición); omite clones existentes y no actualiza ni sobrescribe destinos previos. No hace falta clonar esos repositorios completos en Colab: cada notebook instala sus dependencias en el runtime. Al publicar el Space de voz, el script empaqueta solo el módulo `omnivoice` y su licencia desde el clon local de VoiceStudio, evitando instalar las dependencias de escritorio/ASR que este MVP no usa. `marketingskills` aporta instrucciones, no una librería runtime. HyperFrames, OpenMontage y Open-Generative-AI quedan clonados como fuentes, pero no son dependencias activas de este MVP. Revisa licencias antes de uso comercial: VoiceStudio es AGPL-3.0, Qwen3-4B es Apache-2.0 y Remotion tiene condiciones de licencia comercial.

## Despliegue y seguridad

No se crean recursos de Hugging Face/Colab automáticamente: el despliegue requiere iniciar sesión y configurar tokens y secretos en las cuentas correspondientes. Antes de producción, configura TLS, secretos fuertes, autenticación de usuarios, almacenamiento S3/R2, migraciones de base de datos, límites de uso y políticas de acceso para Mixpost y redes sociales.
