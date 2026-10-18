# Marketing Content OS

Plataforma modular para coordinar investigacion, generacion multimedia, renderizado y programacion de publicaciones. El repositorio contiene el orquestador para WSL, plantillas independientes para Hugging Face Spaces y notebooks para workers de Google Colab.

> MVP: API/cola, Spaces privados de voz y guiones, dos notebooks de Colab y programación manual en Mixpost Lite. Requiere configurar cuentas, claves y almacenamiento.

Auditoría integral vigente de arquitectura, flujo, credenciales, hallazgos y plan de mejora: [docs/auditoria-integral-marketing-content-os.md](./docs/auditoria-integral-marketing-content-os.md). El [plan funcional y de cómputo](./docs/plan-funcionalidad-y-computo.md) detalla correcciones, matriz de pruebas reales, opciones para trabajar sin GPU y el orden para cerrar seguridad. La [auditoría anterior](./docs/auditoria-marketing-content-os.md) conserva las verificaciones históricas del 16 de octubre.

Para retomar el desarrollo desde el estado verificado, consulta el [manifiesto JSON de estado y trazabilidad](./docs/estado-y-trazabilidad-marketing-content-os.json): inventario de módulos, flujo, repositorios, variables de configuración (sin valores secretos), correcciones, pruebas, límites conocidos y próximos pasos para agentes.

## Estructura

- `apps/api`: API FastAPI y ciclo de vida de trabajos.
- `apps/dashboard`: dashboard Next.js con seguimiento por etapa e importación de medios locales.
- `apps/voice-studio-space`: Space Gradio privado de VoiceStudio/OmniVoice sobre ZeroGPU.
- `apps/script-generator-space`: Space Gradio privado de Qwen3-1.7B en CPU, con Qwen3-4B/ZeroGPU opcional.
- `packages/python/core`: esquemas compartidos.
- `packages/python/adapters`: clientes para servicios externos.
- `packages/node/video-templates`: punto de entrada de plantillas Remotion.
- `notebooks`: workers iniciales para investigacion y render.
- `infra`: Docker Compose para PostgreSQL y servicios locales; Redis y publisher se activan solo con perfiles opcionales.
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

El token `WORKER_API_TOKEN` protege las rutas de reserva, renovacion, finalizacion y fallo de los trabajos. El MVP persiste y reserva trabajos desde PostgreSQL; Redis puede arrancarse con `--profile future-queue` cuando se conecte una cola real. Publisher también es opcional (`--profile publisher`) y no participa en el flujo del dashboard. Los trabajos en ejecucion renuevan su reserva cada minuto; si Colab se desconecta, la reserva vence y el trabajo vuelve a la cola hasta un maximo de tres intentos.

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

3. La URL del tunel solo reenvia las operaciones worker: `POST /v1/jobs/next`, `POST /v1/jobs/{id}/heartbeat`, `POST /v1/jobs/{id}/progress`, `POST /v1/jobs/{id}/complete`, `POST /v1/jobs/{id}/fail` y `POST /v1/workers/heartbeat`. No publica el alta/listado de trabajos, el estado local de workers, la biblioteca, PostgreSQL, Mixpost ni la documentacion de la API. La API exige `WORKER_API_TOKEN` y lease para los trabajos. Copia el valor local de `WORKER_API_TOKEN` desde `.env` directamente a los Secrets de Colab; no lo pegues en el notebook ni en Git.

4. Configura almacenamiento persistente **privado** en Cloudflare R2. La API local y ambos workers necesitan credenciales S3 con permisos solo para ese bucket. Guarda las credenciales en `.env` local y en Colab Secrets:

   - `S3_ENDPOINT_URL`: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`
   - `S3_BUCKET`: nombre del bucket R2.
   - `S3_ACCESS_KEY_ID` y `S3_SECRET_ACCESS_KEY`: credenciales S3 del bucket.

   No habilites `r2.dev` ni acceso público para el bucket. Los workers leen/escriben mediante S3 y el dashboard sirve audio/video con enlaces firmados de cinco minutos. `STORAGE_PUBLIC_BASE_URL` se conserva únicamente para compatibilidad con resultados anteriores.

   Para administrar R2 mediante la REST API desde este equipo, crea un token separado de las credenciales S3. En Cloudflare abre **My Profile > API Tokens > Create Token > Create Custom Token** y configura:

   - **Permissions**: `Account` → `Workers R2 Storage` → `Edit`. La API documenta este permiso como `Workers R2 Storage Write`; `Edit` concede operaciones de lectura/listado y escritura, incluida la configuración del bucket.
   - **Account Resources**: `Include` → `Specific account` → selecciona la cuenta que contiene el bucket.
   - No agregues permisos de Zone/User ni uses `Global API Key`. Puedes establecer una expiración corta para una tarea puntual, pero el token debe seguir activo durante la prueba.

   Guarda el valor secreto del token en `CLOUDFLARE_API_TOKEN`, el identificador de cuenta en `CLOUDFLARE_ACCOUNT_ID` y el nombre en `R2_BUCKET_NAME`, dentro de `.env.cloudflare.local` (archivo ignorado por Git). El campo `CLOUDFLARE_API_TOKEN` recibe el secreto del token Bearer, no su nombre ni el ID mostrado en el panel.

   **Son credenciales distintas:** el token Bearer administra recursos por la REST API; `S3_ACCESS_KEY_ID` y `S3_SECRET_ACCESS_KEY` son credenciales compatibles con S3 para leer/escribir objetos y van en `.env`/Secrets de Colab, con permisos `Object Read & Write` limitados al bucket. No uses `Admin Read & Write` para el acceso S3 de los workers.

   El token REST de Cloudflare solo se requiere para tareas de administración; la API y los workers usan las credenciales S3. Nunca pegues tokens ni claves en el chat, README, notebooks o repositorio.

5. En el dashboard local, ve a **Biblioteca local de medios** y selecciona la carpeta de recursos. WAV, MP4, JPG, PNG y WEBP (hasta 250 MB por archivo) se importan al bucket R2 privado. No se comparte ninguna ruta del disco con Colab; los workers descargan los objetos desde R2. Para una voz clonada, selecciona la muestra WAV, escribe su transcripción exacta y confirma que eres titular o tienes autorización. OmniVoice usará esa referencia para narrar el guion nuevo. Para editar con material propio, selecciona un fondo MP4 o una imagen; se conserva el video, pero se silencia su audio original para priorizar la narración.

6. En **cada notebook** abre el panel **Secrets** (icono de llave), crea cada nombre, pega su valor y habilita el acceso para el notebook. Usa exactamente:

   La plantilla local [`.env.colab.example`](./.env.colab.example) reúne las variables requeridas por los workers. Puedes copiarla a `.env.colab` para preparar tus valores localmente; esa copia queda ignorada por Git. Colab no importa el archivo automáticamente: transfiere cada valor directamente al panel **Secrets** del notebook. No subas `.env.colab` a Drive, al repositorio ni al chat. `API_BASE_URL` debe ser la URL HTTPS del Quick Tunnel activo, sin `/` final; cambia al reiniciar el túnel.

   - En `01_research_scrapegraph.ipynb`: `API_BASE_URL` (la URL `trycloudflare.com`, sin `/` final), `WORKER_API_TOKEN`, `SCRIPT_SPACE_URL` (`https://javiertarazon-marketing-script-generator.hf.space`), `VOICE_STUDIO_URL` (`https://javiertarazon-voice-studio-agent.hf.space`), `HF_TOKEN`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID` y `S3_SECRET_ACCESS_KEY`. Opcional: `YOUTUBE_API_KEY` y `YOUTUBE_REGION_CODE` para ordenar videos recientes de YouTube por vistas por hora; sin esa clave la búsqueda usa el índice web y no puede afirmar tendencias cuantitativas.
   - En `02_render_remotion.ipynb`: `API_BASE_URL`, `WORKER_API_TOKEN`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID` y `S3_SECRET_ACCESS_KEY`.

   Crea `HF_TOKEN` en Hugging Face como token de solo lectura que tenga acceso a tus dos Spaces privados. No compartas ese token en el chat. Los Spaces ya desplegados son privados y usan ZeroGPU, que puede poner las solicitudes en cola y limitar la cuota diaria.

7. Abre ambos notebooks en Google Colab, guarda sus Secrets y ejecuta sus celdas desde arriba. Deja ejecutándose la última celda de cada notebook: ahora registran su presencia en la API y consultan continuamente la cola cada 20 segundos. El dashboard muestra cada worker como conectado, ocupado o desconectado. Al detener la celda se registra la desconexión; si Colab cierra el runtime abruptamente, el dashboard la detecta tras 90 segundos sin señal. Los trabajos permanecen en PostgreSQL y se reencolan al vencer el lease si el worker cayó. Las sesiones gratuitas pueden desconectarse, por lo que tendrás que volver a iniciar el notebook tras una interrupción. Si reinicias el túnel, actualiza `API_BASE_URL` en Secrets y vuelve a ejecutar la configuración.

8. Abre `http://localhost:3001`, crea un trabajo con tema, selecciona las redes y, opcionalmente, agrega una URL de referencia o una voz/fondo propio. El worker busca páginas públicas indexadas con ScrapeGraphAI y DuckDuckGo; no requiere credenciales de esas redes. El dashboard muestra etapa, porcentaje, fuentes extraídas y el resultado o bloqueo por plataforma. La cobertura depende de la indexación y del acceso anónimo permitido por cada sitio; no se evaden inicios de sesión, CAPTCHA ni controles. Al completar investigación y voz, la API crea el trabajo de render. El MP4 final se obtiene mediante un enlace firmado temporal.

9. Al terminar, detene las celdas de Colab con el boton Stop y apaga el tunel con el comando del paso 2. No apagues Docker mientras haya trabajos activos. Para produccion/migracion, se conserva el mismo API, esquema y almacenamiento S3; se cambia el endpoint temporal por un dominio fijo con HTTPS y se despliegan API y base de datos en el VPS.

Para iniciar Mixpost Lite (edición MIT) junto con sus servicios aislados de MySQL y Redis:

```bash
docker compose --profile scheduler --env-file .env -f infra/docker-compose.yml up -d mixpost
```

Abre `http://localhost:3002` para completar la configuración inicial de Mixpost. El dashboard permite abrir Mixpost y descargar el MP4 renderizado para subirlo manualmente y programarlo. No hay publicación automática ni integración de API entre las aplicaciones. La imagen `inovector/mixpost:latest` y MySQL necesitan descargarse la primera vez.

**El Mixpost local solo sirve para evaluar la interfaz.** Las conexiones OAuth de redes sociales normalmente necesitan una URL pública HTTPS, un dominio estable y credenciales de desarrollador aprobadas por cada plataforma. Configura `MIXPOST_URL` y `MIXPOST_DOMAIN` con ese dominio antes de conectar cuentas; no expongas la instancia local directamente a Internet.

El adaptador Postiz anterior se conserva en el repositorio, pero ya no forma parte del Compose ni del flujo del dashboard; la programación de este MVP se realiza manualmente en Mixpost.

## Progreso del pipeline y medios locales

La API persiste `progress.stage`, `progress.message` y `progress.percent` en cada trabajo. Los workers Colab actualizan esos datos con un endpoint protegido por el token del worker y su lease, y envían una señal de presencia mientras esperan o trabajan. El dashboard consulta trabajos y sesiones cada 10 segundos y muestra el estado, la etapa y el trabajo activo de cada worker. Una investigación completada genera automáticamente un trabajo separado de render. La app local controla la cola y el estado, pero no puede iniciar una sesión gratuita de Colab: cada notebook debe abrirse y ejecutarse una vez, y reiniciarse si Colab la desconecta.

El dashboard permite seleccionar una carpeta desde el navegador e importar WAV, MP4, JPG, PNG y WEBP al bucket R2 configurado. La API registra sus metadatos en PostgreSQL y sube el archivo con las credenciales S3 locales. El worker de investigación usa una muestra WAV con transcripción para clonación zero-shot; el de render usa un MP4 o una imagen seleccionados como fondo. Los objetos quedan privados y los notebooks reciben claves internas, no enlaces públicos. Límite actual de carga: 250 MB por archivo.

Para habilitar la biblioteca local, completa `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID` y `S3_SECRET_ACCESS_KEY` en `.env`, con permisos de lectura/escritura de objetos en el bucket. En Colab repite esas cuatro variables en Secrets. La API está ligada a `127.0.0.1`; el worker gateway no expone la biblioteca ni los endpoints del dashboard. Las operaciones de clonación deben usar una voz propia o con autorización; el formulario solicita la transcripción exacta y una confirmación.

Para apagar los servicios locales: `docker compose --profile scheduler --env-file .env -f infra/docker-compose.yml down`. Los datos de PostgreSQL y Mixpost se mantienen en volúmenes Docker.

## Hugging Face Spaces

Clona primero VoiceStudio con `python scripts/clone_third_party.py`. Instala la CLI `hf` en WSL (`uv tool install huggingface_hub`) e inicia sesion (`hf auth login`) con un token que permita crear Spaces y subir archivos. La cuenta debe ser elegible para ZeroGPU; las cuentas gratuitas requieren correo verificado y mas de 30 dias de antiguedad, y tienen cuota diaria. Ejecuta `bash scripts/deploy_hf_spaces.sh`: crea/actualiza `voice-studio-agent` como Space privado Gradio con hardware `zero-a10g` (el identificador de ZeroGPU en la CLI actual) y publica la app. No se selecciona T4 ni hardware facturable. Tras publicar, `hf spaces zero-gpu quota` consulta el saldo diario.

El Space carga `k2-fsa/OmniVoice` de forma diferida en CPU por defecto (máximo dos hilos), así las llamadas no solicitan ZeroGPU ni gastan esa cuota. El endpoint Gradio `/predict` recibe texto y atributos de voz, y opcionalmente una muestra WAV más su transcripción exacta para clonación zero-shot. La CPU puede tardar minutos por una narración; el notebook ahora tolera esperas largas. Para volver a GPU se debe configurar `USE_ZEROGPU=1` y se consumirá la cuota compartida. La clonación con una muestra propia y el flujo Colab aún requieren prueba end-to-end.

Para generar investigación editorial y guiones, `apps/script-generator-space` usa `Qwen/Qwen3-1.7B` en CPU por defecto, con dos hilos; la GPU opcional (`USE_ZEROGPU=1`) usa Qwen3-4B y consume cuota. Inicia sesión con `hf auth login` y ejecuta `bash scripts/deploy_hf_script_space.sh`; el script crea/actualiza el Space privado `marketing-script-generator` en ZeroGPU. Configura `SCRIPT_SPACE_URL` y guarda un token HF de solo lectura en el secreto `HF_TOKEN` de Colab. El Space usa el mismo token que el Space de voz. Revisa el build y la cuota antes de producción; el despliegue no se ejecuta automáticamente.

En la cuenta `javiertarazon` están publicados los Spaces privados [Marketing Script Generator](https://huggingface.co/spaces/javiertarazon/marketing-script-generator) y [VoiceStudio](https://huggingface.co/spaces/javiertarazon/voice-studio-agent). La ruta CPU nueva pasó pruebas autenticadas el 18-oct-2026: guion Qwen en 19 s y voz WAV en 39 s; `USE_ZEROGPU=0` quedó fijado en ambos y el saldo se mantuvo en 265.64/300 GPU-segundos antes y después. El token OAuth de `hf auth login` está en la caché de WSL, pero `HF_TOKEN` sigue vacío en `.env`. Para ejecutar el notebook agrega a Colab Secrets un token HF de lectura con acceso a ambos Spaces. Colab no puede leer la caché local de WSL; no pegues tokens en celdas ni en el repositorio.

ZeroGPU gratuito tiene cuota diaria y colas, no es inferencia ilimitada ni un SLA. Las condiciones de elegibilidad y cuota pueden cambiar; verifica la disponibilidad desde tu cuenta Hugging Face. El worker usa la biblioteca open-source ScrapeGraphAI (`search_on_web`) para buscar con DuckDuckGo páginas públicas de las redes elegidas; descarga las páginas accesibles con `requests` y BeautifulSoup. Si una página no es legible, puede utilizar únicamente el fragmento público que devuelve el índice de DuckDuckGo y lo etiqueta como tal en el dashboard. Esta búsqueda no usa APIs ni credenciales de YouTube, Reddit, X, Instagram, TikTok o Facebook. Puede omitir publicaciones no indexadas, devolver resultados antiguos, encontrar perfiles/páginas de negocio en lugar de publicaciones o no acceder a páginas dinámicas/privadas; no equivale a escucha social en tiempo real ni a métricas de tendencias. Los estados por plataforma muestran páginas extraídas, fragmentos, ausencia de contenido legible o errores. El Space Qwen recibe el texto recopilado y produce notas y guion en una inferencia; no garantiza exactitud factual, así que revisa fuentes y guion antes de publicar. No se usa OpenAI.

No publico HyperFrames ni Open-Generative-AI como Spaces Gradio falsos: ambos repos son frameworks/apps, no inferencia Gradio. HyperFrames/Remotion se usan en Colab para render; Open-Generative-AI es una app web/Electron independiente.

## Google Colab

Abre `notebooks/01_research_scrapegraph.ipynb` o `notebooks/02_render_remotion.ipynb` en Colab con la cuenta `javiertarazpon@gmail.com` (sube los archivos desde tu equipo o clona este repositorio despues de publicarlo en GitHub). Este proyecto no recibe acceso a tu Drive ni a tu cuenta. Guarda secretos en **Secrets** de Colab, no en celdas compartidas. Ambos notebooks necesitan `API_BASE_URL`, `WORKER_API_TOKEN`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID` y `S3_SECRET_ACCESS_KEY`. El notebook de investigación también necesita `SCRIPT_SPACE_URL`, `VOICE_STUDIO_URL` y un `HF_TOKEN` de solo lectura con acceso a ambos Spaces privados. Investiga y genera el guion con Qwen3-1.7B en CPU por defecto, llama a VoiceStudio por Gradio con la opción de usar una muestra de voz, sube WAV a R2 privado y encola el render; el segundo notebook descarga el audio y los medios propios para componer el MP4.

Los notebooks mantienen workers de polling mientras sus celdas y runtimes sigan activos. Un Quick Tunnel permite que Colab consulte durante pruebas la API propia de WSL mediante HTTPS temporal; no mantiene el equipo despierto ni elude las restricciones/cuotas de Colab.

El notebook de investigación requiere `API_BASE_URL`, `WORKER_API_TOKEN`, `SCRIPT_SPACE_URL`, `VOICE_STUDIO_URL`, `HF_TOKEN` y credenciales S3/R2 para el resto del pipeline. La URL de referencia es opcional: con ella se analiza esa página y las redes seleccionadas; sin ella, se buscan las plataformas elegidas (o todas si no se selecciona ninguna). La búsqueda social pública usa ScrapeGraphAI con DuckDuckGo, sin claves de plataforma, e informa resultados, bloqueos y errores por plataforma en el dashboard. Esto no garantiza publicaciones recientes ni acceso anónimo a todas las redes. El notebook de render requiere un proyecto Remotion, configuración S3/R2 y el mismo API público. Remotion y HyperFrames son frameworks de render, no Spaces de generación de imágenes; el pipeline necesita una composición/plantilla real.

## Pruebas

```bash
export PATH="$HOME/.local/bin:$PATH"
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r apps/api/requirements-dev.txt -r packages/python/adapters/requirements.txt
python -m pytest tests
```

## Repositorios externos

`python scripts/clone_third_party.py` clona shallow en WSL los repositorios indicados, excepto `MoneyPrinterTurbo` (excluido a petición); omite clones existentes y no actualiza ni sobrescribe destinos previos. No hace falta clonar esos repositorios completos en Colab: cada notebook instala sus dependencias en el runtime. Al publicar el Space de voz, el script empaqueta solo el módulo `omnivoice` y su licencia desde el clon local de VoiceStudio, evitando instalar las dependencias de escritorio/ASR que este MVP no usa. `marketingskills` aporta instrucciones, no una librería runtime. HyperFrames, OpenMontage y Open-Generative-AI quedan clonados como fuentes, pero no son dependencias activas de este MVP. Revisa licencias antes de uso comercial: VoiceStudio es AGPL-3.0, los modelos Qwen3 son Apache-2.0 y Remotion tiene condiciones de licencia comercial.

## Despliegue y seguridad

No se crean recursos de Hugging Face/Colab automáticamente: el despliegue requiere iniciar sesión y configurar tokens y secretos en las cuentas correspondientes. Antes de producción, configura TLS, secretos fuertes, autenticación de usuarios, almacenamiento S3/R2, migraciones de base de datos, límites de uso y políticas de acceso para Mixpost y redes sociales.
