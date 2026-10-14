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

type Integration = {
  id: string;
  name: string;
  identifier: string;
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const publisherBase =
  process.env.NEXT_PUBLIC_PUBLISHER_BASE_URL ?? "http://localhost:8001";

export default function Dashboard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [integrationId, setIntegrationId] = useState("");
  const [publishedJobs, setPublishedJobs] = useState<string[]>([]);
  const [topic, setTopic] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [message, setMessage] = useState("");

  async function refreshJobs() {
    const response = await fetch(`${apiBase}/v1/jobs`, { cache: "no-store" });
    if (!response.ok) throw new Error(`API respondio HTTP ${response.status}`);
    setJobs((await response.json()) as Job[]);
  }

  async function refreshIntegrations() {
    const response = await fetch(`${publisherBase}/v1/integrations`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Postiz respondio HTTP ${response.status}`);
    const available = (await response.json()) as Integration[];
    setIntegrations(available);
    if (!integrationId && available.length > 0) setIntegrationId(available[0].id);
  }

  useEffect(() => {
    refreshJobs().catch((error: Error) => setMessage(error.message));
    refreshIntegrations().catch((error: Error) => setMessage(error.message));
  }, []);

  async function publishJob(job: Job) {
    const integration = integrations.find((item) => item.id === integrationId);
    if (!integration || !job.output?.video_url) {
      setMessage("Selecciona una cuenta conectada y un video renderizado.");
      return;
    }
    setMessage("");
    try {
      const response = await fetch(`${publisherBase}/v1/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_url: job.output.video_url,
          title: job.request.topic,
          platform: integration.identifier,
          integration_id: integration.id,
        }),
      });
      if (!response.ok) {
        const error = (await response.json()) as { detail?: string };
        throw new Error(error.detail ?? `Publisher respondio HTTP ${response.status}`);
      }
      setPublishedJobs((current) => [...current, job.job_id]);
      setMessage("Post aprobado y enviado a Postiz.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo publicar.");
    }
  }

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
      <label style={{ display: "block", marginTop: 12 }}>
        Cuenta de publicación
        <select
          aria-label="Cuenta de publicación"
          value={integrationId}
          onChange={(event) => setIntegrationId(event.target.value)}
          style={{ display: "block", padding: 8, marginTop: 4 }}
        >
          <option value="">Selecciona una cuenta conectada</option>
          {integrations.map((integration) => (
            <option key={integration.id} value={integration.id}>
              {integration.name} ({integration.identifier})
            </option>
          ))}
        </select>
      </label>
      <ul>
        {jobs.map((job) => (
          <li key={job.job_id} style={{ margin: "16px 0" }}>
            <strong>{job.request.topic}</strong> — {job.worker} — {job.status}
            {job.error && <p role="alert">{job.error}</p>}
            {job.worker === "render" && job.status === "succeeded" && job.output?.video_url && (
              <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
                <a href={job.output.video_url} target="_blank" rel="noreferrer">Ver video renderizado</a>
                <button
                  type="button"
                  disabled={!integrationId || publishedJobs.includes(job.job_id)}
                  onClick={() => publishJob(job)}
                >
                  {publishedJobs.includes(job.job_id) ? "Enviado a Postiz" : "Aprobar y publicar"}
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
