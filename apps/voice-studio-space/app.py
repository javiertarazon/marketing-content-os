import gradio as gr
import numpy as np
import spaces
import torch
from omnivoice import OmniVoice
from omnivoice.utils.dtype import tts_dtype_name

MODEL_ID = "k2-fsa/OmniVoice"
MODEL = OmniVoice.from_pretrained(
    MODEL_ID,
    device_map="cuda",
    dtype=getattr(torch, tts_dtype_name("cuda")),
)


@spaces.GPU(duration=180)
def generate_voice(
    text: str, gender: str, age: str, pitch: str
) -> tuple[int, np.ndarray]:
    if not text.strip():
        raise gr.Error("Escribe el texto que quieres narrar.")

    instruct = ", ".join(item for item in (gender, age, pitch) if item)
    audio = MODEL.generate(
        text=text.strip(),
        language="Spanish",
        instruct=instruct or None,
    )
    waveform = audio[0].squeeze(0).float().cpu().numpy()
    if MODEL.sampling_rate is None:
        raise RuntimeError("OmniVoice no informo la frecuencia de muestreo")
    return MODEL.sampling_rate, waveform


demo = gr.Interface(
    fn=generate_voice,
    inputs=[
        gr.Textbox(label="Texto", lines=6, max_length=5000),
        gr.Dropdown(
            choices=["", "female", "male"],
            value="female",
            label="Voz",
        ),
        gr.Dropdown(
            choices=["", "child", "teenager", "young adult", "middle-aged", "elderly"],
            value="young adult",
            label="Edad de voz",
        ),
        gr.Dropdown(
            choices=["", "very low pitch", "low pitch", "moderate pitch", "high pitch", "very high pitch"],
            value="moderate pitch",
            label="Tono",
        ),
    ],
    outputs=gr.Audio(label="Voz generada"),
    title="VoiceStudio — OmniVoice",
    api_name="predict",
)

demo.queue().launch()
