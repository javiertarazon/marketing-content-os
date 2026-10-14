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

La primera carga descarga los pesos publicos `k2-fsa/OmniVoice`. El endpoint
Gradio es `/predict` y recibe el texto, genero, edad y tono. Los selectores
usan unicamente atributos de voz admitidos por OmniVoice.

Manten el Space **Private**: Colab debe llamarlo con un token HF de solo lectura
guardado como secreto `HF_TOKEN`. No publiques ese token ni lo anadas al repo.
El codigo del motor VoiceStudio/OmniVoice se distribuye bajo AGPL-3.0; consulta
tambien la licencia del modelo antes de uso comercial.
