# Marketing Content OS

Plataforma modular para coordinar investigacion, generacion multimedia, renderizado y publicacion. El repositorio contiene el orquestador para WSL, plantillas independientes para Hugging Face Spaces y notebooks para workers de Google Colab.

> MVP: API/cola, un Space de voz, dos notebooks de Colab y publicación bajo aprobación en Postiz. Requiere configurar cuentas, claves y almacenamiento.

## Estructura

- `apps/api`: API FastAPI y ciclo de vida de trabajos.
- `apps/dashboard`: interfaz Next.js inicial.
- `apps/publisher-service`: servicio de publicacion con adaptador Postiz.
- `apps/voice-studio-space`: Space Gradio privado de VoiceStudio/OmniVoice sobre ZeroGPU.
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

Desde la raiz del repositorio:

```bash
cp .env.example .env
# Edita .env y establece contrasenas/secretos locales.
docker compose --env-file .env -f infra/docker-compose.yml up --build -d
curl http://localhost:8000/healthz
```

API: `http://localhost:8000`; dashboard de desarrollo: `http://localhost:3001`.
Para iniciar el dashboard fuera de Docker: `cd apps/dashboard && npm install && npm run dev`.

El token `WORKER_API_TOKEN` protege las rutas de reserva y finalizacion de trabajos. No expongas los puertos ni uses los valores de desarrollo en produccion. Redis queda preparado para tareas futuras; el MVP actual persiste y reserva trabajos desde PostgreSQL.

El publisher usa la API pública de Postiz: configura `POSTIZ_BASE_URL` (Postiz Cloud: `https://api.postiz.com/public/v1`; self-hosted: URL terminada en `/api/public/v1`) y `POSTIZ_API_KEY`. Conecta YouTube, TikTok, Instagram o Facebook en Postiz. El dashboard lista las integraciones de video y el botón **Aprobar y publicar** sube el MP4 público de S3/R2 a Postiz antes de publicarlo. Los archivos enviados a Postiz deben ser MP4 menores de 49 MB; ajusta bitrate/duración o el almacenamiento si tus renders exceden ese tamaño. No hagas clic hasta revisar el video.

Para apagar los servicios locales: `docker compose --env-file .env -f infra/docker-compose.yml down`. Los datos de PostgreSQL se mantienen en un volumen Docker.

## Hugging Face Spaces

Clona primero VoiceStudio con `python scripts/clone_third_party.py`. Instala la CLI `hf` en WSL (`uv tool install huggingface_hub`) e inicia sesion (`hf auth login`) con un token que permita crear Spaces y subir archivos. La cuenta debe ser elegible para ZeroGPU; las cuentas gratuitas requieren correo verificado y mas de 30 dias de antiguedad, y tienen cuota diaria. Ejecuta `bash scripts/deploy_hf_spaces.sh`: crea/actualiza `voice-studio-agent` como Space privado Gradio con hardware `zero-a10g` (el identificador de ZeroGPU en la CLI actual) y publica la app. No se selecciona T4 ni hardware facturable. Tras publicar, `hf spaces zero-gpu quota` consulta el saldo diario.

El Space carga el modelo `k2-fsa/OmniVoice` mediante el paquete del repositorio VoiceStudio y reserva ZeroGPU solo durante cada inferencia. El endpoint Gradio es `/predict`; llama con `gradio_client` y un token HF de solo lectura. Añade `VOICE_STUDIO_URL` y `HF_TOKEN` a `.env` para el cliente local, y guarda `HF_TOKEN` como secreto de Colab para invocar el Space privado. La cuota gratuita de ZeroGPU es limitada (5 minutos diarios segun las condiciones publicadas por Hugging Face); la cola y descarga inicial del modelo pueden hacer el servicio lento. No se afirma que el Space este publicado hasta completar el inicio de sesion y el build en tu cuenta.

No publico HyperFrames ni Open-Generative-AI como Spaces Gradio falsos: ambos repos son frameworks/apps, no inferencia Gradio. HyperFrames/Remotion se usan en Colab para render; Open-Generative-AI es una app web/Electron independiente. Para generar guiones este MVP requiere `OPENAI_API_KEY`; cambiarlo por el backend de Open-Generative-AI requiere adaptar su cliente/proveedores por separado.

## Google Colab

Abre `notebooks/01_research_scrapegraph.ipynb` o `notebooks/02_render_remotion.ipynb` en Colab con la cuenta `javiertarazpon@gmail.com` (sube los archivos desde tu equipo o clona este repositorio despues de publicarlo en GitHub). Este proyecto no recibe acceso a tu Drive ni a tu cuenta. Guarda secretos en **Secrets** de Colab, no en celdas compartidas. En ambos notebooks configura `API_BASE_URL`, `WORKER_API_TOKEN`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` y `STORAGE_PUBLIC_BASE_URL`. El notebook de investigación requiere además `OPENAI_API_KEY`, `VOICE_STUDIO_URL` y un `HF_TOKEN` de solo lectura que pueda leer el Space privado. El primer notebook investiga, genera el guion, llama a VoiceStudio por Gradio, sube WAV a S3/R2 y encola el render; el segundo renderiza MP4 con una composicion Remotion basica y lo sube al bucket.

Los notebooks procesan trabajos manualmente. Colab gratuito no permite dejar workers de computacion distribuida/polling corriendo de fondo. Ademas, un API escuchando en `localhost` de WSL no es accesible desde Colab: hace falta un VPS/dominio HTTPS o una conexion privada permitida por Google. No uses tuneles para eludir las restricciones de Colab.

El notebook de investigacion requiere `OPENAI_API_KEY`, `API_BASE_URL`, `WORKER_API_TOKEN` y una `source_url` por trabajo. El de render requiere un proyecto Remotion, configuracion S3/R2 y el mismo API publico. Remotion y HyperFrames son frameworks de render, no Spaces de generacion de imagenes; el pipeline necesita una composicion/plantilla real.

## Pruebas

```bash
export PATH="$HOME/.local/bin:$PATH"
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -r apps/api/requirements-dev.txt -r packages/python/adapters/requirements.txt
python -m pytest tests
```

## Repositorios externos

`python scripts/clone_third_party.py` clona shallow en WSL los repositorios indicados, excepto `MoneyPrinterTurbo` (excluido a peticion); omite clones existentes y no actualiza ni sobrescribe destinos previos. No hace falta clonar esos repositorios completos en Colab: cada notebook instala sus dependencias en el runtime. Al publicar el Space, el script empaqueta solo el modulo `omnivoice` y su licencia desde el clon local de VoiceStudio, evitando instalar las dependencias de escritorio/ASR que este MVP no usa. `marketingskills` aporta instrucciones, no una libreria runtime. HyperFrames, OpenMontage y Open-Generative-AI quedan clonados como fuentes, pero no son dependencias activas de este MVP; Open-Generative-AI no sustituye aun la API de guiones de OpenAI. Revisa licencias antes de uso comercial: VoiceStudio es AGPL-3.0 y Remotion tiene condiciones de licencia comercial.

## Despliegue y seguridad

No se crean recursos de Hugging Face/Colab automaticamente: el despliegue requiere iniciar sesion y configurar tokens y secretos en las cuentas correspondientes. Antes de produccion, configura TLS, secretos fuertes, autenticacion de usuarios, almacenamiento S3/R2, migraciones de base de datos, limites de uso y politicas de acceso para Postiz y redes sociales.
