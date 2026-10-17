---
title: VoiceStudio ZeroGPU Agent
emoji: "🎙️"
sdk: gradio
sdk_version: 6.15.1
python_version: 3.12.12
app_file: app.py
suggested_hardware: zero-a10g
license: agpl-3.0
tags:
  - audio
  - text-to-speech
  - zerogpu
---

Adaptador Gradio privado para el motor OmniVoice incluido en VoiceStudio.
ZeroGPU reserva una GPU compartida durante cada sintesis; en cuentas gratuitas
el uso esta sujeto a la cuota diaria y a la cola de Hugging Face.
Cada llamada reserva como maximo 120 segundos; la cuota efectiva puede variar
segun el hardware asignado. Si la cuota restante es menor que la reserva
requerida, Hugging Face rechazara la solicitud antes de generar audio.

La primera carga descarga los pesos publicos `k2-fsa/OmniVoice`. El endpoint
Gradio `/predict` recibe el texto, genero, edad y tono, y opcionalmente una
muestra de voz WAV mas su transcripcion exacta. OmniVoice usa la muestra para
clonacion zero-shot. Utiliza solo voces propias o autorizadas.

Manten el Space **Private**: Colab debe llamarlo con un token HF de solo lectura
guardado como secreto `HF_TOKEN`. No publiques ese token ni lo anadas al repo.
El codigo del motor VoiceStudio/OmniVoice se distribuye bajo AGPL-3.0; consulta
tambien la licencia del modelo antes de uso comercial.
