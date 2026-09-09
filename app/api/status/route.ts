import { eq } from "drizzle-orm";
import { getDb } from "@/db";
import { projects } from "@/db/schema";
import {
  absoluteClipUrls,
  engineConnection,
  engineError,
  inferProgress,
  readEngineResponse,
} from "@/lib/snow-engine";

type StatusRequest = {
  jobId?: string;
  engineToken?: string;
};

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as StatusRequest;
    const jobId = body.jobId?.trim() ?? "";
    if (!/^[a-zA-Z0-9_-]{6,160}$/.test(jobId)) {
      return Response.json({ error: "Código de processamento inválido." }, { status: 400 });
    }

    const connection = engineConnection({ engineToken: body.engineToken });
    const response = await fetch(`${connection.baseUrl}/api/status/${encodeURIComponent(jobId)}`, {
      headers: connection.headers,
      signal: AbortSignal.timeout(20_000),
    });
    const upstream = await readEngineResponse(response);
    if (!response.ok) {
      return Response.json(
        { error: engineError(upstream, "Não foi possível consultar este processamento.") },
        { status: response.status === 404 ? 404 : 502 },
      );
    }

    const normalized = absoluteClipUrls(upstream, connection.baseUrl);
    const status = String(normalized.status ?? normalized.state ?? "processing").toLowerCase();
    const progress = inferProgress(normalized);
    const terminal = ["completed", "complete", "succeeded", "success", "failed", "error", "cancelled"].includes(status);
    const result = normalized.result && typeof normalized.result === "object"
      ? (normalized.result as Record<string, unknown>)
      : {};
    const clips = Array.isArray(result.clips)
      ? result.clips as Array<Record<string, unknown>>
      : Array.isArray(normalized.clips)
        ? normalized.clips as Array<Record<string, unknown>>
        : [];
    const firstClip = clips[0] ?? {};
    const projectTitle = String(
      normalized.video_title
      ?? normalized.title
      ?? result.video_title
      ?? result.title
      ?? firstClip.video_title_for_youtube_short
      ?? firstClip.title
      ?? "Novo projeto",
    ).slice(0, 180);

    try {
      await getDb()
        .update(projects)
        .set({
          status,
          title: terminal ? projectTitle : undefined,
          resultJson: terminal ? JSON.stringify(normalized) : undefined,
          errorMessage: ["failed", "error", "cancelled"].includes(status)
            ? engineError(normalized, "Falha no processamento")
            : null,
          updatedAt: new Date().toISOString(),
        })
        .where(eq(projects.engineJobId, jobId));
    } catch (error) {
      console.warn("SnowTV could not update project status", error);
    }

    return Response.json({ ...normalized, status, progress });
  } catch (error) {
    const message = error instanceof Error && error.name === "TimeoutError"
      ? "O motor ainda está ocupado. O SnowTV tentará novamente."
      : error instanceof Error
        ? error.message
        : "Não foi possível consultar o processamento agora.";
    return Response.json({ error: message }, { status: 503 });
  }
}
