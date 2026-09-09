type RuntimeEnvironment = Record<string, string | undefined>;

export type EngineCredentials = {
  engineToken?: string;
};

export function engineConnection(credentials: EngineCredentials = {}) {
  const runtime = ((globalThis as typeof globalThis & { __SNOW_ENV__?: unknown }).__SNOW_ENV__ ?? {}) as RuntimeEnvironment;
  const rawUrl = runtime.SNOW_ENGINE_URL?.trim();
  if (!rawUrl) {
    throw new Error("O Motor Snow self-hosted ainda não foi configurado neste site.");
  }
  const parsed = new URL(rawUrl);

  const loopback = ["localhost", "127.0.0.1", "::1"].includes(parsed.hostname);
  if (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && loopback)) {
    throw new Error("Use HTTPS para um Motor Snow remoto; HTTP é aceito apenas em localhost.");
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  const apiKey = runtime.SNOW_ENGINE_TOKEN?.trim() || credentials.engineToken?.trim();

  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;

  return {
    baseUrl: parsed.toString().replace(/\/$/, ""),
    headers,
  };
}

export async function readEngineResponse(response: Response) {
  const text = await response.text();
  if (!text) return {} as Record<string, unknown>;

  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    return { message: text.slice(0, 500) } as Record<string, unknown>;
  }
}

export function engineError(payload: Record<string, unknown>, fallback: string) {
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const message = (detail as Record<string, unknown>).message;
    if (typeof message === "string") return message;
  }
  if (typeof payload.message === "string") return payload.message;
  if (typeof payload.error === "string") return payload.error;
  return fallback;
}

export function absoluteClipUrls(payload: Record<string, unknown>, baseUrl: string) {
  const result = payload.result && typeof payload.result === "object"
    ? (payload.result as Record<string, unknown>)
    : null;
  const rawClips = (result?.clips ?? payload.clips) as unknown;
  if (!Array.isArray(rawClips)) return payload;

  const clips = rawClips.map((item) => {
    if (!item || typeof item !== "object") return item;
    const clip = { ...(item as Record<string, unknown>) };
    for (const field of ["video_url", "download_url"]) {
      const value = clip[field];
      if (typeof value === "string" && value.startsWith("/")) {
        clip[field] = new URL(value, `${baseUrl}/`).toString();
      }
    }
    return clip;
  });

  if (result) return { ...payload, result: { ...result, clips } };
  return { ...payload, clips };
}

export function inferProgress(payload: Record<string, unknown>) {
  const explicit = Number(payload.progress);
  if (Number.isFinite(explicit) && explicit > 0) return Math.min(100, explicit);

  const status = String(payload.status ?? payload.state ?? "").toLowerCase();
  if (["completed", "complete", "succeeded", "success"].includes(status)) return 100;
  if (["failed", "error", "cancelled"].includes(status)) return 100;

  const logs = Array.isArray(payload.logs) ? payload.logs.join(" ").toLowerCase() : "";
  if (/refram|caption|subtitle|ffmpeg|render/.test(logs)) return 78;
  if (/gemini|viral|highlight|moment|scene/.test(logs)) return 52;
  if (/transcri|whisper|audio/.test(logs)) return 28;
  if (/download|import|queue/.test(logs)) return 10;
  return 6;
}
