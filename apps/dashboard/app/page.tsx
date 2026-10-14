"use client";

import { FormEvent, useEffect, useState } from "react";

type Job = {
  job_id: string;
  worker: "research" | "render";
  status: string;
  request: { topic: string };
  output: { video_url?: string } | null;
  error: string | null;
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const mixpostUrl = process.env.NEXT_PUBLIC_MIXPOST_URL ?? "http://localhost:3002";

export default function Dashboard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [topic, setTopic] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [message, setMessage] = useState("");

  async function refreshJobs() {
    const response = await fetch(`${apiBase}/v1/jobs`, { cache: "no-store" });
    if (!response.ok) throw new Error(`API respondio HTTP ${response.status}`);
    setJobs((await response.json()) as Job[]);
  }

  useEffect(() => {
    refreshJobs().catch((error: Error) => setMessage(error.message));
  }, []);

  async function submitJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    try {
      const response = await fetch(`${apiBase}/v1/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          worker: "research",
          request: {
            topic,
            source_url: sourceUrl,
            style: "financial-news",
            duration_seconds: 35,
            platforms: [],
          },
        }),
      });
      if (!response.ok) {
        const error = (await response.json()) as { detail?: string };
        throw new Error(error.detail ?? `API respondio HTTP ${response.status}`);
      }
      setTopic("");
      setSourceUrl("");
      setMessage("Trabajo creado.");
      await refreshJobs();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo crear el trabajo.");
    }
  }

  return (
    <main style={{ maxWidth: 900, margin: "0 auto", padding: 32 }}>
      <h1>Marketing Content OS</h1>
      <p>Cola de investigacion y renderizado</p>
      <p><a href={mixpostUrl} target="_blank" rel="noreferrer">Abrir Mixpost Lite para programar contenido</a></p>
      <form onSubmit={submitJob} style={{ display: "grid", gap: 8, margin: "24px 0" }}>
        <input aria-label="Tema del contenido" required value={topic}
          onChange={(event) => setTopic(event.target.value)} placeholder="Tema del contenido"
          style={{ padding: 10 }} />
        <input aria-label="URL de referencia" type="url" required value={sourceUrl}
          onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://sitio.com/articulo"
          style={{ padding: 10 }} />
        <button type="submit" style={{ padding: "10px 16px" }}>Crear trabajo</button>
      </form>
      {message && <p role="status">{message}</p>}
      <h2>Trabajos recientes</h2>
      <button type="button" onClick={() => refreshJobs().catch((error: Error) => setMessage(error.message))}>
        Actualizar
      </button>
      <ul>
        {jobs.map((job) => (
          <li key={job.job_id} style={{ margin: "16px 0" }}>
            <strong>{job.request.topic}</strong> — {job.worker} — {job.status}
            {job.error && <p role="alert">{job.error}</p>}
            {job.worker === "render" && job.status === "succeeded" && job.output?.video_url && (
              <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                <a href={job.output.video_url} target="_blank" rel="noreferrer">Ver video renderizado</a>
                <a href={job.output.video_url} download>Descargar MP4 para Mixpost</a>
                <a href={mixpostUrl} target="_blank" rel="noreferrer">
                  Revisar y programar manualmente en Mixpost Lite
                </a>
              </div>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
