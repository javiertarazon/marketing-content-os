---
title: Marketing Script Generator
emoji: "✍️"
sdk: gradio
sdk_version: 6.15.1
python_version: 3.12.12
app_file: app.py
suggested_hardware: zero-a10g
license: apache-2.0
tags:
  - text-generation
  - qwen3
  - zerogpu
---

Private Gradio Space for generating research notes and short Spanish video
scripts with `Qwen/Qwen3-4B`.

Create the Space as **Private** with ZeroGPU hardware. The free personal tier
currently allows up to two ZeroGPU Spaces and five minutes of GPU use per day;
requests can queue and the quota is shared with other ZeroGPU work on the
account. Do not use this service for unattended or time-critical production.

Call the `/generate` Gradio endpoint with `gradio_client` and a read-only
Hugging Face token that can access this private Space. Never commit that token.
