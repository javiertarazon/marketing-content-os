import spaces
import gradio as gr
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "Qwen/Qwen3-4B"

tokenizer = None
model = None


@spaces.GPU(duration=120)
def generate(prompt: str) -> str:
    global tokenizer, model
    if not prompt.strip():
        raise gr.Error("Escribe una instrucción para generar contenido.")
    if model is None:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.bfloat16,
            device_map="cuda",
        )
        model.eval()

    messages = [
        {
            "role": "system",
            "content": (
                "Eres un asistente editorial en español. Basa las respuestas "
                "solo en la fuente proporcionada, distingue hechos de opiniones "
                "y no inventes datos ni citas."
            ),
        },
        {"role": "user", "content": prompt.strip()},
    ]
    inputs = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        enable_thinking=False,
        return_tensors="pt",
        return_dict=True,
    ).to(model.device)

    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            max_new_tokens=700,
            do_sample=False,
            repetition_penalty=1.05,
            pad_token_id=tokenizer.eos_token_id,
        )

    answer = generated[0, inputs["input_ids"].shape[1] :]
    result = tokenizer.decode(answer, skip_special_tokens=True).strip()
    if not result:
        raise gr.Error("El modelo no produjo una respuesta.")
    return result


demo = gr.Interface(
    fn=generate,
    inputs=gr.Textbox(label="Instrucción", lines=12),
    outputs=gr.Textbox(label="Resultado", lines=16),
    title="Marketing Content OS — generador editorial",
    api_name="generate",
)

if __name__ == "__main__":
    demo.launch()
