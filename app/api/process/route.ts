import { getDb } from "@/db";
import { projects } from "@/db/schema";
import { engineConnection, engineError, readEngineResponse } from "@/lib/snow-engine";

type ProcessRequest = {
  url?: string;
  language?: string;
  duration?: string;
  clipCount?: number;
  layout?: string;
  performanceProfile?: string;
  captions?: boolean;
  removePauses?: boolean;
  pauseRemoval?: string;
  hookText?: boolean;
  hookMode?: string;
  hookTitle?: string;
  hookPreset?: string;
  captionStyle?: Record<string, unknown>;
  advanced?: Record<string, unknown>;
  engineToken?: string;
};

function validYoutubeUrl(value: string) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/^www\./, "");
    return url.protocol === "https:" && (host === "youtube.com" || host === "m.youtube.com" || host === "youtu.be");
  } catch {
    return false;
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as ProcessRequest;
    const sourceUrl = body.url?.trim() ?? "";
    if (!validYoutubeUrl(sourceUrl)) {
      return Response.json({ error: "Use um link HTTPS válido do YouTube." }, { status: 400 });
    }

    const connection = engineConnection({ engineToken: body.engineToken });
    const response = await fetch(`${connection.baseUrl}/api/process`, {
      method: "POST",
      headers: connection.headers,
      body: JSON.stringify({
        url: sourceUrl,
        acknowledged: true,
        language: body.language ?? "pt",
        duration: body.duration ?? "auto",
        clipCount: body.clipCount ?? 5,
        layout: body.layout ?? "track",
        performanceProfile: body.performanceProfile ?? "auto",
        captions: body.captions ?? true,
        removePauses: body.removePauses ?? true,
        pauseRemoval: body.pauseRemoval ?? "normal",
        hookText: body.hookText ?? true,
        hookMode: body.hookMode ?? "auto",
        hookTitle: body.hookTitle ?? "",
        hookPreset: body.hookPreset ?? "bold",
        captionStyle: body.captionStyle ?? { preset: "karaoke" },
        advanced: body.advanced ?? {},
      }),
      signal: AbortSignal.timeout(25_000),
    });
    const upstream = await readEngineResponse(response);
    if (!response.ok) {
      return Response.json(
        { error: engineError(upstream, "O motor Snow recusou o processamento."), upstreamStatus: response.status },
        { status: response.status === 401 || response.status === 402 ? response.status : 502 },
      );
    }

    const engineJobId = String(upstream.job_id ?? upstream.jobId ?? upstream.id ?? "");
    if (!engineJobId) {
      return Response.json({ error: "O motor Snow não devolveu o código do processamento." }, { status: 502 });
    }

    const ownerEmail = "local-user";
    const projectId = crypto.randomUUID();
    const options = {
      language: body.language ?? "pt",
      duration: body.duration ?? "auto",
      clipCount: body.clipCount ?? 5,
      layout: body.layout ?? "track",
      performanceProfile: body.performanceProfile ?? "auto",
      captions: body.captions ?? true,
      removePauses: body.removePauses ?? true,
      pauseRemoval: body.pauseRemoval ?? "normal",
      hookText: body.hookText ?? true,
      hookMode: body.hookMode ?? "auto",
      hookTitle: body.hookTitle ?? "",
      hookPreset: body.hookPreset ?? "bold",
      captionStyle: body.captionStyle ?? { preset: "karaoke" },
      advanced: body.advanced ?? {},
    };

    try {
      await getDb().insert(projects).values({
        id: projectId,
        ownerEmail,
        engineJobId,
        sourceUrl,
        status: "queued",
        optionsJson: JSON.stringify(options),
      });
    } catch (error) {
      console.warn("SnowTV could not persist a started project", error);
    }

    return Response.json({ ...upstream, job_id: engineJobId, project_id: projectId }, { status: 202 });
  } catch (error) {
    const message = error instanceof Error && error.name === "TimeoutError"
      ? "O motor demorou para responder. Tente novamente em instantes."
      : error instanceof Error
        ? error.message
        : "Não foi possível iniciar o processamento agora.";
    return Response.json({ error: message }, { status: 503 });
  }
}
