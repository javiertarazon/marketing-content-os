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


@spaces.GPU(duration=120)
def generate_voice(
    text: str,
    gender: str,
    age: str,
    pitch: str,
    reference_audio: str | None,
    reference_text: str,
) -> tuple[int, np.ndarray]:
    if not text.strip():
        raise gr.Error("Escribe el texto que quieres narrar.")
    if bool(reference_audio) != bool(reference_text.strip()):
        raise gr.Error("La muestra de voz requiere su transcripción exacta.")

    instruct = ", ".join(item for item in (gender, age, pitch) if item)
    reference = {}
    if reference_audio:
        reference = {
            "ref_audio": reference_audio,
            "ref_text": reference_text.strip(),
        }
    audio = MODEL.generate(
        text=text.strip(),
        language="Spanish",
        instruct=instruct or None,
        **reference,
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
        gr.Audio(
            type="filepath",
            label="Muestra WAV de una voz propia o autorizada (opcional)",
        ),
        gr.Textbox(
            label="Transcripción exacta de la muestra",
            lines=3,
            max_length=5000,
        ),
    ],
    outputs=gr.Audio(label="Voz generada"),
    title="VoiceStudio — OmniVoice",
    api_name="predict",
)

demo.queue().launch()
