"use client";

import { CSSProperties, FormEvent, useEffect, useMemo, useRef, useState } from "react";

type SourceMode = "link" | "upload";
type ProcessingState = "idle" | "starting" | "processing" | "completed" | "failed";
type EngineState = "unknown" | "checking" | "online" | "offline";
type CaptionPresetKey = "none" | "karaoke" | "bold" | "minimal" | "podcast" | "highlight" | "bounce" | "pop" | "deep" | "glitch";

type CaptionStyle = {
  preset: CaptionPresetKey;
  font: string;
  size: number;
  weight: "normal" | "bold" | "black";
  uppercase: boolean;
  alignment: "left" | "center" | "right";
  position: number;
  marginBottom?: number;
  maxWords: number;
  maxLines: number;
  primaryColor: string;
  highlightColor: string;
  outlineColor: string;
  outline: number;
  shadow: number;
  background: boolean;
  backgroundOpacity: number;
  spacing: number;
  animation: "none" | "karaoke" | "bounce" | "pop" | "glitch" | "scale" | "fade";
  semanticHighlight: boolean;
  safeZone: "shorts" | "reels" | "tiktok";
};

type CustomCaptionPreset = { name: string; style: CaptionStyle };

type AdvancedOptions = {
  whisperModel: "auto" | "tiny" | "base" | "small" | "medium";
  computeType: "auto" | "int8" | "float32";
  cpuThreads: number;
  analysisWidth: number;
  faceRedetectSeconds: number;
  encoder: "auto" | "cpu" | "amd";
  crf: number;
  ffmpegPreset: "auto" | "veryfast" | "faster" | "fast" | "medium";
};

type Clip = {
  title?: string;
  video_title_for_youtube_short?: string;
  video_url?: string;
  download_url?: string;
  start?: number;
  end?: number;
  score?: number;
  viral_score?: number;
  reason?: string;
  selection_method?: string;
  score_breakdown?: Record<string, number>;
  duration?: number;
  caption_preset?: string;
  layout?: string;
};

type SavedProject = {
  id: string;
  sourceUrl: string;
  title: string;
  status: string;
  createdAt: string;
  engineJobId?: string;
  options?: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  errorMessage?: string | null;
};

const captionPresets: Array<{ key: CaptionPresetKey; name: string; sample: string; tone: string }> = [
  { key: "none", name: "Sem legenda", sample: "Aa", tone: "plain" },
  { key: "karaoke", name: "Snow Karaoke", sample: "AGORA", tone: "yellow" },
  { key: "bold", name: "Snow Beast", sample: "IMPACTO", tone: "cyan" },
  { key: "minimal", name: "Snow Clean", sample: "Elegante", tone: "minimal" },
  { key: "podcast", name: "Snow Podcast", sample: "conversa real", tone: "boxed" },
  { key: "highlight", name: "Snow Focus", sample: "VALOR", tone: "mint" },
  { key: "bounce", name: "Snow Bounce", sample: "PULA", tone: "pink" },
  { key: "pop", name: "Snow Popline", sample: "POP!", tone: "orange" },
  { key: "deep", name: "Snow Deep Diver", sample: "Profundo", tone: "deep" },
  { key: "glitch", name: "Snow Glitch", sample: "GLITCH", tone: "glitch" },
];

const captionPresetDefaults: Record<CaptionPresetKey, Partial<CaptionStyle>> = {
  none: { size: 66, weight: "normal", uppercase: false, primaryColor: "#FFFFFF", highlightColor: "#FFD65F", outlineColor: "#101822", outline: 0, shadow: 0, background: false, spacing: 0, animation: "none" },
  karaoke: { size: 70, weight: "black", uppercase: true, primaryColor: "#FFFFFF", highlightColor: "#FFD65F", outlineColor: "#101822", outline: 8, shadow: 2, background: false, spacing: 0, animation: "karaoke" },
  bold: { size: 76, weight: "black", uppercase: true, primaryColor: "#FFFFFF", highlightColor: "#61D7FF", outlineColor: "#08121E", outline: 10, shadow: 3, background: false, spacing: 0, animation: "pop" },
  minimal: { size: 58, weight: "normal", uppercase: false, primaryColor: "#FFFFFF", highlightColor: "#BFEFFF", outlineColor: "#101820", outline: 3, shadow: 1, background: false, spacing: 0, animation: "none" },
  podcast: { size: 64, weight: "black", uppercase: false, primaryColor: "#FFFFFF", highlightColor: "#FFD65F", outlineColor: "#07111D", outline: 5, shadow: 1, background: true, spacing: 0, animation: "karaoke" },
  highlight: { size: 70, weight: "black", uppercase: true, primaryColor: "#FFFFFF", highlightColor: "#8FF1C1", outlineColor: "#091521", outline: 8, shadow: 2, background: false, spacing: 0, animation: "karaoke" },
  bounce: { size: 72, weight: "black", uppercase: true, primaryColor: "#FFFFFF", highlightColor: "#FF7CC8", outlineColor: "#0A1420", outline: 8, shadow: 3, background: false, spacing: 0, animation: "bounce" },
  pop: { size: 74, weight: "black", uppercase: true, primaryColor: "#FFFFFF", highlightColor: "#FF8A65", outlineColor: "#09131F", outline: 9, shadow: 3, background: false, spacing: 0, animation: "pop" },
  deep: { size: 66, weight: "black", uppercase: false, primaryColor: "#EAF6FF", highlightColor: "#5FD6FF", outlineColor: "#07111C", outline: 6, shadow: 2, background: true, spacing: 1, animation: "karaoke" },
  glitch: { size: 70, weight: "black", uppercase: true, primaryColor: "#FFFFFF", highlightColor: "#5FFFE4", outlineColor: "#32125F", outline: 7, shadow: 2, background: false, spacing: 1.5, animation: "glitch" },
};

const stageLabels: Record<string, string> = {
  queued: "Na fila",
  downloading: "Baixando e mesclando",
  importing: "Validando arquivo",
  analyzing: "Analisando conteúdo",
  extracting_audio: "Extraindo áudio",
  transcribing: "Transcrevendo",
  selecting: "Selecionando cortes",
  tracking: "Reenquadrando",
  rendering: "Renderizando MP4",
  completed: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
};

const demoClips: Clip[] = [
  { title: "A decisão que muda o rumo da conversa", start: 74, end: 119, viral_score: 92 },
  { title: "O erro que quase todo iniciante comete", start: 308, end: 351, viral_score: 88 },
  { title: "Por que disciplina vale mais que motivação", start: 622, end: 675, viral_score: 84 },
];

const processingSteps = [
  "Importando o vídeo",
  "Transcrevendo cada fala",
  "Encontrando os melhores momentos",
  "Reenquadrando e aplicando legendas",
];

const LOCAL_ENGINE_URL = "http://127.0.0.1:8000";

function normalizeEngineUrl(value: string) {
  const parsed = new URL(value.trim());
  if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error("Use um endereço HTTP ou HTTPS para o Motor Snow.");
  return parsed.toString().replace(/\/$/, "");
}

function engineError(payload: Record<string, unknown>, fallback: string) {
  if (typeof payload.error === "string") return payload.error;
  if (typeof payload.detail === "string") return payload.detail;
  if (payload.detail && typeof payload.detail === "object") {
    const detail = payload.detail as Record<string, unknown>;
    if (typeof detail.message === "string") return detail.message;
  }
  return fallback;
}

function engineHeaders(token: string, json = false) {
  const headers: Record<string, string> = {};
  if (json) headers["Content-Type"] = "application/json";
  if (token.trim()) headers.Authorization = `Bearer ${token.trim()}`;
  return headers;
}

async function persistProject(payload: Record<string, unknown>) {
  try {
    await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    // The rendering job must keep running even if project history is temporarily unavailable.
  }
}

function formatTime(seconds?: number) {
  if (seconds === undefined) return "00:00";
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function durationOf(clip: Clip) {
  if (clip.duration !== undefined) return `${Math.max(0, Math.round(clip.duration))}s`;
  if (clip.start === undefined || clip.end === undefined) return "—";
  return `${Math.max(0, Math.round(clip.end - clip.start))}s`;
}

function projectDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Agora";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(date);
}

function LogoMark() {
  return (
    <span className="logo-mark" aria-hidden="true">
      <span className="logo-play" />
      <i className="snow-dot snow-dot-one" />
      <i className="snow-dot snow-dot-two" />
    </span>
  );
}

function NavGlyph({ label }: { label: string }) {
  return <span className="nav-glyph" aria-hidden="true">{label.slice(0, 1)}</span>;
}

export default function SnowStudio({ firstName, initialProjects }: { firstName: string; initialProjects: SavedProject[] }) {
  const [sourceMode, setSourceMode] = useState<SourceMode>("link");
  const [videoUrl, setVideoUrl] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("pt");
  const [duration, setDuration] = useState("auto");
  const [clipCount, setClipCount] = useState("5");
  const [layout, setLayout] = useState("auto");
  const [performanceProfile, setPerformanceProfile] = useState("auto");
  const [editorialStyle, setEditorialStyle] = useState("auto");
  const [captions, setCaptions] = useState(true);
  const [pauseRemoval, setPauseRemoval] = useState("normal");
  const [hookMode, setHookMode] = useState("auto");
  const [hookTitle, setHookTitle] = useState("");
  const [hookPreset, setHookPreset] = useState("bold");
  const [captionEditorOpen, setCaptionEditorOpen] = useState(false);
  const [captionTab, setCaptionTab] = useState<"presets" | "font" | "effects">("presets");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [captionStyle, setCaptionStyle] = useState<CaptionStyle>({
    preset: "karaoke", font: "Arial", size: 70, weight: "black", uppercase: true,
    alignment: "center", position: 76, maxWords: 5, maxLines: 2, primaryColor: "#FFFFFF",
    highlightColor: "#FFD65F", outlineColor: "#101822", outline: 8, shadow: 2,
    background: false, backgroundOpacity: 55, spacing: 0, animation: "karaoke",
    semanticHighlight: true, safeZone: "shorts",
  });
  const [customCaptionPresets, setCustomCaptionPresets] = useState<CustomCaptionPreset[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const parsed = JSON.parse(localStorage.getItem("snowtv_caption_presets") || "[]") as unknown;
      return Array.isArray(parsed) ? parsed.slice(0, 12) as CustomCaptionPreset[] : [];
    } catch {
      return [];
    }
  });
  const [clipFeedback, setClipFeedback] = useState<Record<number, "good" | "bad">>({});
  const [advanced, setAdvanced] = useState<AdvancedOptions>({
    whisperModel: "auto", computeType: "auto", cpuThreads: 0, analysisWidth: 0,
    faceRedetectSeconds: 0, encoder: "auto", crf: 0, ffmpegPreset: "auto",
  });
  const [state, setState] = useState<ProcessingState>("idle");
  const [activeStep, setActiveStep] = useState(0);
  const [clips, setClips] = useState<Clip[]>([]);
  const [message, setMessage] = useState("");
  const [progress, setProgress] = useState(0);
  const [currentStage, setCurrentStage] = useState("queued");
  const [jobLogs, setJobLogs] = useState<string[]>([]);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [currentJobId, setCurrentJobId] = useState("");
  const [currentProjectId, setCurrentProjectId] = useState("");
  const [demoMode, setDemoMode] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [engineUrl, setEngineUrl] = useState(() => typeof window === "undefined" ? LOCAL_ENGINE_URL : localStorage.getItem("snowtv_engine_url") || LOCAL_ENGINE_URL);
  const [engineToken, setEngineToken] = useState(() => typeof window === "undefined" ? "" : sessionStorage.getItem("snowtv_engine_token") || "");
  const [engineState, setEngineState] = useState<EngineState>("unknown");
  const [engineInfo, setEngineInfo] = useState("Pronto para conectar ao seu computador");
  const [engineHealth, setEngineHealth] = useState<Record<string, unknown> | null>(null);
  const [benchmark, setBenchmark] = useState<Record<string, unknown> | null>(null);
  const [benchmarking, setBenchmarking] = useState(false);
  const [savedProjects, setSavedProjects] = useState(initialProjects);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/projects")
      .then((response) => response.ok ? response.json() : null)
      .then((payload: { projects?: SavedProject[] } | null) => {
        if (!cancelled && payload?.projects) {
          setSavedProjects(payload.projects);
          const active = payload.projects.find((project) => ["queued", "processing"].includes(project.status) && project.engineJobId);
          if (active?.engineJobId) {
            const storedEngine = localStorage.getItem("snowtv_engine_url") || LOCAL_ENGINE_URL;
            setCurrentJobId(active.engineJobId);
            setCurrentProjectId(active.id);
            setState("processing");
            setMessage("Retomando o acompanhamento do projeto salvo…");
            void pollJob(active.engineJobId, active.id, storedEngine);
          }
        }
      })
      .catch(() => undefined);

    return () => {
      cancelled = true;
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
    // Resume uses the connection snapshot that existed when the studio opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sourceReady = useMemo(() => {
    if (sourceMode === "link") {
      try {
        return new URL(videoUrl).protocol === "https:";
      } catch {
        return false;
      }
    }
    return Boolean(selectedFile);
  }, [selectedFile, sourceMode, videoUrl]);

  function openSettings() {
    setEngineUrl(localStorage.getItem("snowtv_engine_url") || LOCAL_ENGINE_URL);
    setEngineToken(sessionStorage.getItem("snowtv_engine_token") || "");
    setSettingsOpen(true);
  }

  async function testEngine(rawUrl = engineUrl, token = engineToken) {
    setEngineState("checking");
    setEngineInfo("Verificando FFmpeg, Whisper e fila…");
    try {
      const baseUrl = normalizeEngineUrl(rawUrl);
      const response = await fetch(`${baseUrl}/health`, {
        headers: engineHeaders(token),
        signal: AbortSignal.timeout(12000),
      });
      const payload = (await response.json()) as Record<string, unknown>;
      if (!response.ok || payload.status === "degraded") throw new Error("O motor respondeu, mas FFmpeg/ffprobe não estão prontos.");
      setEngineState("online");
      setEngineHealth(payload);
      setEngineInfo(`${String(payload.transcription ?? "Whisper local")} · ${String(payload.selection ?? "seleção local")}`);
      return true;
    } catch (error) {
      setEngineState("offline");
      setEngineInfo(error instanceof Error ? error.message : "Não foi possível alcançar o Motor Snow.");
      return false;
    }
  }

  async function runEngineBenchmark() {
    setBenchmarking(true);
    setBenchmark(null);
    try {
      const baseUrl = normalizeEngineUrl(engineUrl);
      const response = await fetch(`${baseUrl}/api/benchmark`, {
        method: "POST",
        headers: engineHeaders(engineToken),
        signal: AbortSignal.timeout(60000),
      });
      const payload = (await response.json()) as Record<string, unknown>;
      if (!response.ok) throw new Error(engineError(payload, "O benchmark não pôde ser executado."));
      setBenchmark(payload);
    } catch (error) {
      setBenchmark({ error: error instanceof Error ? error.message : "Falha no benchmark." });
    } finally {
      setBenchmarking(false);
    }
  }

  function processingOptions() {
    return {
      language,
      duration,
      clipCount: Number(clipCount),
      layout,
      performanceProfile,
      editorialStyle,
      captions,
      removePauses: pauseRemoval !== "off",
      pauseRemoval,
      hookText: hookMode !== "off",
      hookMode,
      hookTitle,
      hookPreset,
      captionStyle,
      advanced,
    };
  }

  async function saveConnection() {
    try {
      const normalized = normalizeEngineUrl(engineUrl);
      setEngineUrl(normalized);
      localStorage.setItem("snowtv_engine_url", normalized);
      if (engineToken.trim()) sessionStorage.setItem("snowtv_engine_token", engineToken.trim());
      else sessionStorage.removeItem("snowtv_engine_token");
      const connected = await testEngine(normalized, engineToken);
      if (connected) setSettingsOpen(false);
    } catch (error) {
      setEngineState("offline");
      setEngineInfo(error instanceof Error ? error.message : "Endereço inválido.");
    }
  }

  function startDemo() {
    setDemoMode(true);
    setState("processing");
    setMessage("Demonstração do fluxo — nenhum minuto será consumido.");
    setProgress(6);
    setClips([]);
    setActiveStep(0);
    [1, 2, 3].forEach((step, index) => window.setTimeout(() => { setActiveStep(step); setProgress(28 + step * 22); }, 900 * (index + 1)));
    window.setTimeout(() => {
      setClips(demoClips);
      setState("completed");
      setProgress(100);
      setMessage("3 cortes de demonstração encontrados.");
    }, 3900);
  }

  function saveCaptionPreset() {
    const name = window.prompt("Nome do novo preset de legenda:")?.trim().slice(0, 40);
    if (!name) return;
    const next = [
      { name, style: { ...captionStyle } },
      ...customCaptionPresets.filter((item) => item.name.toLowerCase() !== name.toLowerCase()),
    ].slice(0, 12);
    setCustomCaptionPresets(next);
    localStorage.setItem("snowtv_caption_presets", JSON.stringify(next));
    setMessage(`Preset “${name}” salvo neste navegador.`);
  }

  function removeCaptionPreset(name: string) {
    const next = customCaptionPresets.filter((item) => item.name !== name);
    setCustomCaptionPresets(next);
    localStorage.setItem("snowtv_caption_presets", JSON.stringify(next));
  }

  async function pollJob(jobId: string, projectId?: string, directEngineUrl?: string, failures = 0) {
    try {
      const response = directEngineUrl
        ? await fetch(`${directEngineUrl}/api/status/${encodeURIComponent(jobId)}`, {
            headers: engineHeaders(engineToken),
          })
        : await fetch("/api/status", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jobId, engineToken: engineToken.trim() || undefined }),
          });
      const payload = (await response.json()) as Record<string, unknown>;
      if (!response.ok) throw new Error(engineError(payload, "Falha ao consultar o vídeo."));
      setEngineState("online");
      setCurrentJobId(jobId);

      const nextProgress = Number(payload.progress ?? 0);
      const nextStage = String(payload.stage ?? payload.state ?? "processing").toLowerCase();
      const logs = Array.isArray(payload.logs) ? payload.logs.filter((item): item is string => typeof item === "string") : [];
      const entries = Array.isArray(payload.log_entries) ? payload.log_entries : [];
      const detailedLogs = entries.flatMap((item) => {
        if (!item || typeof item !== "object") return [];
        const entry = item as Record<string, unknown>;
        const label = typeof entry.message === "string" ? entry.message : "Evento do motor";
        const detail = typeof entry.detail === "string" ? `\n${entry.detail}` : "";
        return [`${label}${detail}`];
      });
      setProgress(Number.isFinite(nextProgress) ? Math.max(0, Math.min(100, nextProgress)) : 0);
      setCurrentStage(nextStage);
      setJobLogs(detailedLogs.length ? detailedLogs : logs);
      if (logs.length) setMessage(logs[logs.length - 1]);

      const nextStatus = String(payload.status ?? payload.state ?? "processing").toLowerCase();
      const result = (payload.result ?? {}) as Record<string, unknown>;
      const outputClips = (result.clips ?? payload.clips ?? []) as Clip[];

      if (["completed", "complete", "succeeded", "success"].includes(nextStatus)) {
        setActiveStep(3);
        setClips(outputClips);
        setState("completed");
        setProgress(100);
        setCurrentStage("completed");
        setMessage(`${outputClips.length} cortes prontos para revisar.`);
        if (projectId) {
          const projectTitle = outputClips[0]?.video_title_for_youtube_short ?? outputClips[0]?.title ?? "Cortes prontos";
          setSavedProjects((current) => current.map((project) => project.id === projectId ? { ...project, title: projectTitle, status: "completed", result: payload } : project));
          void persistProject({ action: "update", id: projectId, title: projectTitle, status: "completed", result: payload });
        }
        return;
      }
      if (["failed", "error", "cancelled"].includes(nextStatus)) {
        const failureMessage = String(payload.error ?? "O motor não conseguiu processar este vídeo.");
        const savedStatus = nextStatus === "cancelled" ? "cancelled" : "failed";
        setState("failed");
        setProgress(100);
        setCurrentStage("failed");
        setMessage(failureMessage);
        if (projectId) {
          setSavedProjects((current) => current.map((project) => project.id === projectId ? { ...project, status: savedStatus, errorMessage: failureMessage } : project));
          void persistProject({ action: "update", id: projectId, status: savedStatus, errorMessage: failureMessage, result: payload });
        }
        return;
      }

      if (nextProgress >= 75) setActiveStep(3);
      else if (nextProgress >= 45) setActiveStep(2);
      else if (nextProgress >= 15) setActiveStep(1);
      pollTimer.current = setTimeout(() => pollJob(jobId, projectId, directEngineUrl, 0), 4500);
    } catch {
      if (failures < 4) {
        setState("processing");
        setMessage(`Conexão temporariamente indisponível. Nova tentativa ${failures + 1}/5…`);
        pollTimer.current = setTimeout(() => pollJob(jobId, projectId, directEngineUrl, failures + 1), 2500 + failures * 1500);
        return;
      }
      setState("failed");
      setMessage("Perdi a conexão com o motor, mas o job continua salvo. Reconecte o motor para retomar o acompanhamento.");
    }
  }

  async function submitVideo(event: FormEvent) {
    event.preventDefault();
    setDemoMode(false);
    setMessage("");
    setClips([]);
    setJobLogs([]);
    setDetailsOpen(false);

    if (!sourceReady) {
      setState("failed");
      setMessage(sourceMode === "link" ? "Cole um link HTTPS válido do YouTube para continuar." : "Escolha um arquivo de vídeo para continuar.");
      return;
    }

    setState("starting");
    setActiveStep(0);
    setProgress(1);
    setCurrentStage("queued");
    setMessage("Enviando o vídeo para o motor Snow…");
    try {
      const options = processingOptions();
      const directEngineUrl = engineUrl.trim() ? normalizeEngineUrl(engineUrl) : undefined;
      let response: Response;
      if (sourceMode === "upload") {
        if (!directEngineUrl || !selectedFile) throw new Error("Configure o endereço do Motor Snow para enviar arquivos.");
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("options", JSON.stringify(options));
        response = await fetch(`${directEngineUrl}/api/process/upload`, {
          method: "POST",
          headers: engineHeaders(engineToken),
          body: formData,
        });
      } else if (directEngineUrl) {
        response = await fetch(`${directEngineUrl}/api/process`, {
          method: "POST",
          headers: engineHeaders(engineToken, true),
          body: JSON.stringify({ url: videoUrl.trim(), ...options }),
        });
      } else {
        response = await fetch("/api/process", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: videoUrl.trim(), ...options, engineToken: engineToken.trim() || undefined }),
        });
      }
      const payload = (await response.json()) as Record<string, unknown>;
      if (!response.ok) throw new Error(engineError(payload, "Não foi possível iniciar o processamento."));
      const jobId = String(payload.job_id ?? payload.jobId ?? payload.id ?? "");
      if (!jobId) throw new Error("O motor não devolveu o código do processamento.");
      const projectId = String(payload.project_id ?? crypto.randomUUID());
      setCurrentJobId(jobId);
      setCurrentProjectId(projectId);
      const sourceLabel = sourceMode === "upload" ? selectedFile?.name ?? "Arquivo enviado" : videoUrl.trim();
      setSavedProjects((current) => [{
        id: projectId,
        engineJobId: jobId,
        sourceUrl: sourceLabel,
        title: "Vídeo em processamento",
        status: "processing",
        createdAt: new Date().toISOString(),
        options,
      }, ...current.filter((project) => project.id !== projectId)].slice(0, 6));
      void persistProject({
        action: "start",
        id: projectId,
        engineJobId: jobId,
        sourceUrl: sourceLabel,
        title: "Vídeo em processamento",
        status: "processing",
        options,
      });
      setState("processing");
      setProgress(2);
      setEngineState("online");
      setMessage("Processamento iniciado. O job continuará mesmo se você fechar esta aba.");
      await pollJob(jobId, projectId, directEngineUrl);
    } catch (error) {
      setState("failed");
      if (error instanceof TypeError && engineUrl.includes("127.0.0.1")) {
        setEngineState("offline");
        setMessage("Não consegui alcançar o Motor Snow local. Inicie o serviço na porta 8000 e teste a conexão em “Configurar motor”.");
      } else {
        setMessage(error instanceof Error ? error.message : "Não foi possível iniciar o processamento.");
      }
    }
  }

  function openProject(project: SavedProject) {
    setCurrentJobId(project.engineJobId ?? "");
    setCurrentProjectId(project.id);
    const payload = project.result ?? {};
    const result = payload.result && typeof payload.result === "object"
      ? payload.result as Record<string, unknown>
      : payload;
    const storedClips = Array.isArray(result.clips) ? result.clips as Clip[] : [];
    if (storedClips.length) {
      setClips(storedClips);
      setState("completed");
      setProgress(100);
      setCurrentStage("completed");
      setMessage(`${storedClips.length} cortes carregados da biblioteca.`);
      window.setTimeout(() => document.querySelector(".progress-card")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    }
    const options = project.options ?? {};
    if (typeof options.language === "string") setLanguage(options.language);
    if (typeof options.duration === "string") setDuration(options.duration);
    if (typeof options.clipCount === "number") setClipCount(String(options.clipCount));
    if (typeof options.layout === "string") setLayout(options.layout);
    if (typeof options.performanceProfile === "string") setPerformanceProfile(options.performanceProfile);
    if (typeof options.editorialStyle === "string") setEditorialStyle(options.editorialStyle);
    if (typeof options.captions === "boolean") setCaptions(options.captions);
    if (typeof options.pauseRemoval === "string") setPauseRemoval(options.pauseRemoval);
    if (typeof options.hookMode === "string") setHookMode(options.hookMode);
    if (typeof options.hookTitle === "string") setHookTitle(options.hookTitle);
    if (typeof options.hookPreset === "string") setHookPreset(options.hookPreset);
    if (options.captionStyle && typeof options.captionStyle === "object") {
      setCaptionStyle((current) => ({ ...current, ...(options.captionStyle as Partial<CaptionStyle>) }));
    }
    if (options.advanced && typeof options.advanced === "object") {
      setAdvanced((current) => ({ ...current, ...(options.advanced as Partial<AdvancedOptions>) }));
    }
  }

  async function rateClip(index: number, rating: "good" | "bad") {
    if (!currentJobId || !engineUrl.trim()) return;
    setClipFeedback((current) => ({ ...current, [index]: rating }));
    try {
      const baseUrl = normalizeEngineUrl(engineUrl);
      await fetch(`${baseUrl}/api/jobs/${encodeURIComponent(currentJobId)}/feedback`, {
        method: "POST",
        headers: engineHeaders(engineToken, true),
        body: JSON.stringify({ clipIndex: index, rating, reasons: [] }),
      });
    } catch {
      // Feedback is optional and must never interfere with editing/downloading.
    }
  }

  async function adjustClipTiming(index: number, clip: Clip) {
    if (!currentJobId) return;
    const startValue = window.prompt("Início do corte em segundos", String(clip.start ?? 0));
    if (startValue === null) return;
    const endValue = window.prompt("Fim do corte em segundos", String(clip.end ?? Math.max(1, Number(startValue) + 30)));
    if (endValue === null) return;
    const start = Number(startValue.replace(",", "."));
    const end = Number(endValue.replace(",", "."));
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start + 0.3) {
      setMessage("Use tempos válidos; o fim precisa ser maior que o início.");
      return;
    }
    const title = window.prompt("Título do corte (opcional)", clip.video_title_for_youtube_short ?? clip.title ?? "") ?? undefined;
    await rerenderJob(currentJobId, `Ajuste manual do corte ${index}`, { clipOverrides: [{ index, start, end, title }] });
  }

  async function rerenderJob(jobId: string, sourceLabel = "Projeto rerenderizado", extraOptions: Record<string, unknown> = {}) {
    if (!jobId) return;
    setState("starting");
    setMessage("Criando uma nova renderização usando os caches existentes…");
    setProgress(1);
    try {
      const baseUrl = normalizeEngineUrl(engineUrl);
      const options = { ...processingOptions(), ...extraOptions };
      const response = await fetch(`${baseUrl}/api/jobs/${encodeURIComponent(jobId)}/rerender`, {
        method: "POST",
        headers: engineHeaders(engineToken, true),
        body: JSON.stringify(options),
      });
      const payload = (await response.json()) as Record<string, unknown>;
      if (!response.ok) throw new Error(engineError(payload, "Não foi possível rerenderizar o projeto."));
      const nextJobId = String(payload.job_id ?? "");
      if (!nextJobId) throw new Error("O motor não devolveu o novo job.");
      const projectId = crypto.randomUUID();
      const project: SavedProject = {
        id: projectId,
        engineJobId: nextJobId,
        sourceUrl: sourceLabel,
        title: "Rerenderizando com cache",
        status: "processing",
        createdAt: new Date().toISOString(),
        options,
      };
      setSavedProjects((current) => [project, ...current].slice(0, 20));
      void persistProject({ action: "start", id: projectId, engineJobId: nextJobId, sourceUrl: sourceLabel, title: project.title, status: "processing", options });
      setCurrentJobId(nextJobId);
      setCurrentProjectId(projectId);
      setState("processing");
      await pollJob(nextJobId, projectId, baseUrl);
    } catch (error) {
      setState("failed");
      setMessage(error instanceof Error ? error.message : "Falha ao rerenderizar.");
    }
  }

  async function cancelJob() {
    if (!currentJobId || !engineUrl.trim()) return;
    try {
      const baseUrl = normalizeEngineUrl(engineUrl);
      const response = await fetch(`${baseUrl}/api/jobs/${encodeURIComponent(currentJobId)}/cancel`, {
        method: "POST",
        headers: engineHeaders(engineToken),
      });
      const payload = (await response.json()) as Record<string, unknown>;
      if (!response.ok) throw new Error(engineError(payload, "Não foi possível cancelar o job."));
      if (pollTimer.current) clearTimeout(pollTimer.current);
      setState("failed");
      setCurrentStage("cancelled");
      setProgress(100);
      setMessage("Processamento cancelado. Você pode retomá-lo usando os caches existentes.");
      if (currentProjectId) {
        setSavedProjects((current) => current.map((project) => project.id === currentProjectId ? { ...project, status: "cancelled", errorMessage: "Cancelado pelo usuário" } : project));
        void persistProject({ action: "update", id: currentProjectId, status: "cancelled", errorMessage: "Cancelado pelo usuário" });
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao cancelar o job.");
    }
  }

  async function resumeJob(jobId = currentJobId, projectId = currentProjectId) {
    if (!jobId || !engineUrl.trim()) return;
    try {
      const baseUrl = normalizeEngineUrl(engineUrl);
      const response = await fetch(`${baseUrl}/api/jobs/${encodeURIComponent(jobId)}/resume`, {
        method: "POST",
        headers: engineHeaders(engineToken),
      });
      const payload = (await response.json()) as Record<string, unknown>;
      if (!response.ok) throw new Error(engineError(payload, "Não foi possível retomar o job."));
      setState("processing");
      setProgress(0);
      setCurrentStage("queued");
      setMessage("Job retomado; caches válidos serão reutilizados.");
      if (projectId) {
        setCurrentProjectId(projectId);
        setSavedProjects((current) => current.map((project) => project.id === projectId ? { ...project, status: "processing", errorMessage: null } : project));
        void persistProject({ action: "update", id: projectId, status: "processing", errorMessage: null });
      }
      await pollJob(jobId, projectId || undefined, baseUrl);
    } catch (error) {
      setState("failed");
      setMessage(error instanceof Error ? error.message : "Falha ao retomar o job.");
    }
  }

  async function renameProject(project: SavedProject) {
    const title = window.prompt("Novo nome do projeto:", project.title)?.trim();
    if (!title) return;
    setSavedProjects((current) => current.map((item) => item.id === project.id ? { ...item, title } : item));
    await persistProject({ action: "update", id: project.id, title, status: project.status });
  }

  async function deleteProject(project: SavedProject) {
    if (!window.confirm(`Excluir “${project.title}”? Os MP4 locais desse job também serão removidos.`)) return;
    setSavedProjects((current) => current.filter((item) => item.id !== project.id));
    await persistProject({ action: "delete", id: project.id });
    if (project.engineJobId) {
      try {
        const baseUrl = normalizeEngineUrl(engineUrl);
        await fetch(`${baseUrl}/api/jobs/${encodeURIComponent(project.engineJobId)}`, {
          method: "DELETE",
          headers: engineHeaders(engineToken),
        });
      } catch {
        // The site record is already removed; the local engine can be cleaned later.
      }
    }
  }

  const detectedHardware = (engineHealth?.hardware ?? {}) as Record<string, unknown>;
  const detectedDependencies = (engineHealth?.dependencies ?? {}) as Record<string, unknown>;
  const detectedProfile = (engineHealth?.profile ?? {}) as Record<string, unknown>;
  const detectedRuntime = (engineHealth?.runtime ?? {}) as Record<string, unknown>;
  const benchmarkHardware = (benchmark?.hardware ?? {}) as Record<string, unknown>;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#top" aria-label="SnowTV, início">
          <LogoMark /><span>SnowTV</span><b>LOCAL</b>
        </a>
        <nav className="main-nav" aria-label="Navegação principal">
          <a className="nav-item active" href="#novo-corte"><NavGlyph label="Novo" />Novo corte</a>
          <a className="nav-item" href="#projetos"><NavGlyph label="Projetos" />Projetos</a>
          <a className="nav-item" href="#projetos"><NavGlyph label="Biblioteca" />Biblioteca</a>
          <a className="nav-item" href="#novo-corte" onClick={() => setCaptionEditorOpen(true)}><NavGlyph label="Estilos" />Estilos de legenda</a>
        </nav>
        <div className="engine-card">
          <div className="engine-line"><span className={`status-light ${engineState}`} /><span>Motor Snow</span></div>
          <p>{engineState === "online" ? "Self-hosted conectado" : engineState === "offline" ? "Motor local desconectado" : "FFmpeg + Whisper no seu computador"}</p>
          <button type="button" onClick={openSettings}>Configurar motor</button>
        </div>
        <div className="profile-row">
          <span className="avatar">{firstName.slice(0, 1).toUpperCase()}</span>
          <span><strong>{firstName}</strong><small>Workspace pessoal</small></span>
          <button type="button" aria-label="Mais opções">•••</button>
        </div>
      </aside>

      <main className="main-content" id="top">
        <header className="mobile-header">
          <a className="brand" href="#top"><LogoMark /><span>SnowTV</span></a>
          <button type="button" onClick={openSettings}>Motor</button>
        </header>

        <section className="hero" id="novo-corte">
          <div>
            <p className="eyebrow"><span /> ESTÚDIO AUTOMÁTICO</p>
            <h1>Um vídeo longo.<br /><em>Uma semana de cortes.</em></h1>
            <p className="hero-copy">O SnowTV encontra os trechos mais fortes, transforma em 9:16, acompanha quem está falando e adiciona legendas automaticamente.</p>
          </div>
          <div className="hero-proof" aria-label="Recursos incluídos">
            <span>9:16</span><span>10 estilos</span><span>Clip Score</span><span>Cache local</span>
          </div>
        </section>

        <section className="creator-card" aria-labelledby="creator-title">
          <div className="card-heading">
            <div><span className="step-number">01</span><span><h2 id="creator-title">Adicione seu vídeo</h2><p>Use um link do YouTube ou envie o arquivo original.</p></span></div>
            <span className="private-pill">Privado por padrão</span>
          </div>

          <form onSubmit={submitVideo}>
            <div className="source-tabs" role="tablist" aria-label="Origem do vídeo">
              <button type="button" className={sourceMode === "link" ? "active" : ""} onClick={() => setSourceMode("link")} role="tab" aria-selected={sourceMode === "link"}>Link do vídeo</button>
              <button type="button" className={sourceMode === "upload" ? "active" : ""} onClick={() => setSourceMode("upload")} role="tab" aria-selected={sourceMode === "upload"}>Enviar arquivo <small>LOCAL</small></button>
            </div>

            {sourceMode === "link" ? (
              <label className="url-field">
                <span className="youtube-badge">▶</span>
                <input type="url" value={videoUrl} onChange={(event) => setVideoUrl(event.target.value)} placeholder="Cole aqui o link do YouTube" aria-label="Link do vídeo do YouTube" />
                {sourceReady && <span className="valid-check">✓</span>}
              </label>
            ) : (
              <label className="upload-field">
                <input type="file" accept="video/mp4,video/quicktime,video/x-msvideo" onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} />
                <span className="upload-icon">↑</span>
                <strong>{selectedFile ? selectedFile.name : "Arraste seu vídeo ou clique para escolher"}</strong>
                <small>{selectedFile ? `${(selectedFile.size / 1024 / 1024).toFixed(1)} MB selecionados` : "MP4, MOV, MKV, AVI ou WebM · limite configurável"}</small>
              </label>
            )}

            <div className="settings-grid">
              <label><span>Idioma falado</span><select value={language} onChange={(event) => setLanguage(event.target.value)}><option value="pt">Português (Brasil)</option><option value="auto">Detectar automaticamente</option><option value="en">Inglês</option><option value="es">Espanhol</option></select></label>
              <label><span>Duração dos cortes</span><select value={duration} onChange={(event) => setDuration(event.target.value)}><option value="auto">Automática natural</option><option value="15_30">15–30 segundos</option><option value="30_45">30–45 segundos</option><option value="30_60">30–60 segundos</option><option value="45_90">45–90 segundos</option></select></label>
              <label><span>Quantidade máxima</span><select value={clipCount} onChange={(event) => setClipCount(event.target.value)}><option value="3">3 cortes</option><option value="5">5 cortes</option><option value="8">8 cortes</option><option value="12">12 cortes</option></select></label>
              <label><span>Enquadramento</span><select value={layout} onChange={(event) => setLayout(event.target.value)}><option value="auto">Auto inteligente</option><option value="track">Acompanhar pessoa</option><option value="split">Conversa dividida</option><option value="blur">Fundo desfocado</option><option value="center">Corte central</option><option value="horizontal">Manter horizontal</option></select></label>
              <label><span>Performance</span><select value={performanceProfile} onChange={(event) => setPerformanceProfile(event.target.value)}><option value="auto">Auto recomendado</option><option value="eco">Eco</option><option value="balanced">Balanced</option><option value="quality">Quality</option></select></label>
              <label><span>Estilo editorial</span><select value={editorialStyle} onChange={(event) => setEditorialStyle(event.target.value)}><option value="auto">Auto</option><option value="viral">Viral / entretenimento</option><option value="educational">Educacional</option><option value="podcast">Podcast / conversa</option><option value="storytelling">Storytelling</option><option value="commentary">Comentário / opinião</option></select></label>
            </div>

            <div className="toggle-row">
              <label className="toggle-control"><input type="checkbox" checked={captions} onChange={(event) => setCaptions(event.target.checked)} /><span className="toggle-track" /><span>Legendas dinâmicas</span></label>
              <label className="toggle-control"><input type="checkbox" checked={pauseRemoval !== "off"} onChange={(event) => setPauseRemoval(event.target.checked ? "normal" : "off")} /><span className="toggle-track" /><span>Remover pausas</span></label>
              <label className="toggle-control"><input type="checkbox" checked={hookMode !== "off"} onChange={(event) => setHookMode(event.target.checked ? "auto" : "off")} /><span className="toggle-track" /><span>Título de gancho</span></label>
            </div>

            <div className="customize-actions">
              <button type="button" className={captionEditorOpen ? "active" : ""} onClick={() => setCaptionEditorOpen((value) => !value)}>Aa Personalizar legendas <span>{captionPresets.find((item) => item.key === captionStyle.preset)?.name}</span></button>
              <button type="button" className={advancedOpen ? "active" : ""} onClick={() => setAdvancedOpen((value) => !value)}>⚙ Configurações avançadas <span>Opcional</span></button>
            </div>

            {captionEditorOpen && (
              <section className="caption-editor" aria-label="Editor de legendas">
                <div className="editor-heading"><div><strong>Legenda</strong><small>Preview visual ao vivo · render final word-level via ASS/libass.</small></div><span>WORD-LEVEL</span></div>
                <div className="caption-live-workspace">
                  <div className={`caption-live-preview animation-${captionStyle.animation}`}>
                    <span className={`safe-zone-guide ${captionStyle.safeZone}`}>{captionStyle.safeZone}</span>
                    <div
                      className="caption-live-line"
                      style={{
                        top: `${captionStyle.position}%`, fontFamily: captionStyle.font,
                        fontSize: `${Math.max(18, captionStyle.size * 0.42)}px`,
                        fontWeight: captionStyle.weight === "normal" ? 400 : captionStyle.weight === "bold" ? 700 : 900,
                        textTransform: captionStyle.uppercase ? "uppercase" : "none",
                        textAlign: captionStyle.alignment, color: captionStyle.primaryColor,
                        letterSpacing: `${captionStyle.spacing}px`,
                        WebkitTextStroke: `${Math.min(4, captionStyle.outline * 0.35)}px ${captionStyle.outlineColor}`,
                        textShadow: `0 ${captionStyle.shadow}px ${Math.max(1, captionStyle.shadow * 1.4)}px rgba(0,0,0,.85)`,
                        background: captionStyle.background ? `rgb(6 16 27 / ${captionStyle.backgroundOpacity}%)` : "transparent",
                      } as CSSProperties}
                    >
                      O <em style={{ color: captionStyle.highlightColor }}>momento</em> certo muda tudo
                    </div>
                  </div>
                  <div className="caption-preview-meta"><strong>Preview 9:16</strong><span>{captionStyle.font} · {captionStyle.size}px · {captionStyle.safeZone}</span><button type="button" onClick={saveCaptionPreset}>Salvar como preset</button></div>
                </div>
                <div className="caption-tabs">
                  <button type="button" className={captionTab === "presets" ? "active" : ""} onClick={() => setCaptionTab("presets")}>Predefinições</button>
                  <button type="button" className={captionTab === "font" ? "active" : ""} onClick={() => setCaptionTab("font")}>Fonte</button>
                  <button type="button" className={captionTab === "effects" ? "active" : ""} onClick={() => setCaptionTab("effects")}>Efeitos</button>
                </div>

                {captionTab === "presets" && (
                  <div className="preset-grid">
                    {captionPresets.map((preset) => (
                      <button type="button" key={preset.key} className={captionStyle.preset === preset.key ? "selected" : ""} onClick={() => { setCaptionStyle((current) => ({ ...current, ...captionPresetDefaults[preset.key], preset: preset.key })); setCaptions(preset.key !== "none"); }}>
                        <span className={`preset-preview ${preset.tone}`}>{preset.sample}</span><strong>{preset.name}</strong><small>{preset.key === "none" ? "Título opcional" : "Palavra ativa sincronizada"}</small>
                      </button>
                    ))}
                    {customCaptionPresets.map((preset) => (
                      <button type="button" key={`custom-${preset.name}`} className="custom-preset" onClick={() => { setCaptionStyle({ ...preset.style }); setCaptions(preset.style.preset !== "none"); }}>
                        <span className="preset-preview custom">{preset.name.slice(0, 2).toUpperCase()}</span><strong>{preset.name}</strong><small>Preset personalizado</small><i role="button" tabIndex={0} aria-label={`Excluir preset ${preset.name}`} onClick={(event) => { event.stopPropagation(); removeCaptionPreset(preset.name); }}>×</i>
                      </button>
                    ))}
                  </div>
                )}

                {captionTab === "font" && (
                  <div className="editor-controls">
                    <label><span>Fonte</span><select value={captionStyle.font} onChange={(event) => setCaptionStyle((current) => ({ ...current, font: event.target.value }))}><option>Arial</option><option>Arial Black</option><option>Verdana</option><option>Trebuchet MS</option><option>Liberation Sans</option></select></label>
                    <label><span>Tamanho · {captionStyle.size}</span><input type="range" min="38" max="110" value={captionStyle.size} onChange={(event) => setCaptionStyle((current) => ({ ...current, size: Number(event.target.value) }))} /></label>
                    <label><span>Peso</span><select value={captionStyle.weight} onChange={(event) => setCaptionStyle((current) => ({ ...current, weight: event.target.value as CaptionStyle["weight"] }))}><option value="normal">Normal</option><option value="bold">Bold</option><option value="black">Black</option></select></label>
                    <label><span>Alinhamento</span><select value={captionStyle.alignment} onChange={(event) => setCaptionStyle((current) => ({ ...current, alignment: event.target.value as CaptionStyle["alignment"] }))}><option value="left">Esquerda</option><option value="center">Centro</option><option value="right">Direita</option></select></label>
                    <label><span>Posição vertical · {captionStyle.position}%</span><input type="range" min="45" max="82" value={captionStyle.position} onChange={(event) => setCaptionStyle((current) => ({ ...current, position: Number(event.target.value) }))} /></label>
                    <label><span>Margem inferior</span><select value={captionStyle.marginBottom ?? ""} onChange={(event) => setCaptionStyle((current) => ({ ...current, marginBottom: event.target.value ? Number(event.target.value) : undefined }))}><option value="">Automática</option><option value="240">240 px</option><option value="300">300 px</option><option value="360">360 px</option><option value="440">440 px</option></select></label>
                    <label><span>Palavras por bloco</span><select value={captionStyle.maxWords} onChange={(event) => setCaptionStyle((current) => ({ ...current, maxWords: Number(event.target.value) }))}><option value="3">3</option><option value="4">4</option><option value="5">5</option><option value="6">6</option><option value="8">8</option></select></label>
                    <label><span>Máximo de linhas</span><select value={captionStyle.maxLines} onChange={(event) => setCaptionStyle((current) => ({ ...current, maxLines: Number(event.target.value) }))}><option value="1">1</option><option value="2">2</option><option value="3">3</option></select></label>
                    <label><span>Safe zone</span><select value={captionStyle.safeZone} onChange={(event) => setCaptionStyle((current) => ({ ...current, safeZone: event.target.value as CaptionStyle["safeZone"] }))}><option value="shorts">YouTube Shorts</option><option value="reels">Instagram Reels</option><option value="tiktok">TikTok</option></select></label>
                    <label className="color-control"><span>Texto</span><input type="color" value={captionStyle.primaryColor} onChange={(event) => setCaptionStyle((current) => ({ ...current, primaryColor: event.target.value }))} /></label>
                    <label className="color-control"><span>Destaque</span><input type="color" value={captionStyle.highlightColor} onChange={(event) => setCaptionStyle((current) => ({ ...current, highlightColor: event.target.value }))} /></label>
                    <label className="color-control"><span>Contorno</span><input type="color" value={captionStyle.outlineColor} onChange={(event) => setCaptionStyle((current) => ({ ...current, outlineColor: event.target.value }))} /></label>
                  </div>
                )}

                {captionTab === "effects" && (
                  <>
                    <div className="editor-controls">
                      <label><span>Espessura · {captionStyle.outline}</span><input type="range" min="0" max="14" value={captionStyle.outline} onChange={(event) => setCaptionStyle((current) => ({ ...current, outline: Number(event.target.value) }))} /></label>
                      <label><span>Sombra · {captionStyle.shadow}</span><input type="range" min="0" max="12" value={captionStyle.shadow} onChange={(event) => setCaptionStyle((current) => ({ ...current, shadow: Number(event.target.value) }))} /></label>
                      <label><span>Opacidade do fundo · {captionStyle.backgroundOpacity}%</span><input type="range" min="0" max="100" value={captionStyle.backgroundOpacity} onChange={(event) => setCaptionStyle((current) => ({ ...current, backgroundOpacity: Number(event.target.value) }))} /></label>
                      <label><span>Espaçamento · {captionStyle.spacing}</span><input type="range" min="-2" max="8" step="0.5" value={captionStyle.spacing} onChange={(event) => setCaptionStyle((current) => ({ ...current, spacing: Number(event.target.value) }))} /></label>
                      <label><span>Animação</span><select value={captionStyle.animation} onChange={(event) => setCaptionStyle((current) => ({ ...current, animation: event.target.value as CaptionStyle["animation"] }))}><option value="none">Nenhuma</option><option value="karaoke">Karaoke</option><option value="bounce">Bounce</option><option value="pop">Pop</option><option value="scale">Scale</option><option value="fade">Fade</option><option value="glitch">Glitch</option></select></label>
                    </div>
                    <div className="editor-toggles">
                      <label><input type="checkbox" checked={captionStyle.uppercase} onChange={(event) => setCaptionStyle((current) => ({ ...current, uppercase: event.target.checked }))} /> MAIÚSCULAS</label>
                      <label><input type="checkbox" checked={captionStyle.semanticHighlight} onChange={(event) => setCaptionStyle((current) => ({ ...current, semanticHighlight: event.target.checked }))} /> Destacar palavras importantes</label>
                      <label><input type="checkbox" checked={captionStyle.background} onChange={(event) => setCaptionStyle((current) => ({ ...current, background: event.target.checked }))} /> Fundo da legenda</label>
                    </div>
                    <div className="hook-controls">
                      <label><span>Gancho visual</span><select value={hookMode} onChange={(event) => setHookMode(event.target.value)}><option value="off">Desligado</option><option value="auto">Automático</option><option value="custom">Texto editável</option></select></label>
                      <label><span>Estilo do gancho</span><select value={hookPreset} onChange={(event) => setHookPreset(event.target.value)}><option value="clean">Clean</option><option value="bold">Bold</option><option value="boxed">Boxed</option></select></label>
                      {hookMode === "custom" && <label className="hook-title-field"><span>Título</span><input maxLength={100} value={hookTitle} onChange={(event) => setHookTitle(event.target.value)} placeholder="O ERRO QUE QUASE TODO HOMEM COMETE" /></label>}
                      <label><span>Remoção de pausas</span><select value={pauseRemoval} onChange={(event) => setPauseRemoval(event.target.value)}><option value="off">Off</option><option value="light">Leve</option><option value="normal">Normal</option><option value="aggressive">Agressivo</option></select></label>
                    </div>
                  </>
                )}
              </section>
            )}

            {advancedOpen && (
              <section className="advanced-editor" aria-label="Configurações avançadas">
                <div className="editor-heading"><div><strong>Ajuste fino do motor</strong><small>Deixe em Auto para usar o preset do seu computador.</small></div><span>AVANÇADO</span></div>
                <div className="editor-controls advanced-grid">
                  <label><span>Whisper</span><select value={advanced.whisperModel} onChange={(event) => setAdvanced((current) => ({ ...current, whisperModel: event.target.value as AdvancedOptions["whisperModel"] }))}><option value="auto">Auto</option><option value="tiny">Tiny</option><option value="base">Base</option><option value="small">Small</option><option value="medium">Medium</option></select></label>
                  <label><span>Compute</span><select value={advanced.computeType} onChange={(event) => setAdvanced((current) => ({ ...current, computeType: event.target.value as AdvancedOptions["computeType"] }))}><option value="auto">Auto</option><option value="int8">CPU INT8</option><option value="float32">CPU Float32</option></select></label>
                  <label><span>Threads · {advanced.cpuThreads || "Auto"}</span><input type="range" min="0" max="12" value={advanced.cpuThreads} onChange={(event) => setAdvanced((current) => ({ ...current, cpuThreads: Number(event.target.value) }))} /></label>
                  <label><span>Proxy de análise</span><select value={advanced.analysisWidth} onChange={(event) => setAdvanced((current) => ({ ...current, analysisWidth: Number(event.target.value) }))}><option value="0">Auto</option><option value="480">480 px</option><option value="640">640 px</option><option value="720">720 px</option></select></label>
                  <label><span>Encoder</span><select value={advanced.encoder} onChange={(event) => setAdvanced((current) => ({ ...current, encoder: event.target.value as AdvancedOptions["encoder"] }))}><option value="auto">Auto seguro</option><option value="cpu">CPU libx264</option><option value="amd">AMD Hardware</option></select></label>
                  <label><span>CRF · {advanced.crf || "Auto"}</span><input type="range" min="0" max="28" value={advanced.crf} onChange={(event) => setAdvanced((current) => ({ ...current, crf: Number(event.target.value) }))} /></label>
                  <label><span>Preset FFmpeg</span><select value={advanced.ffmpegPreset} onChange={(event) => setAdvanced((current) => ({ ...current, ffmpegPreset: event.target.value as AdvancedOptions["ffmpegPreset"] }))}><option value="auto">Auto</option><option value="veryfast">Very fast</option><option value="faster">Faster</option><option value="fast">Fast</option><option value="medium">Medium</option></select></label>
                  <label><span>Redetectar face · {advanced.faceRedetectSeconds || "Auto"}s</span><input type="range" min="0" max="3" step="0.2" value={advanced.faceRedetectSeconds} onChange={(event) => setAdvanced((current) => ({ ...current, faceRedetectSeconds: Number(event.target.value) }))} /></label>
                </div>
                <p className="advanced-note">Workers: {String(detectedRuntime.workers ?? 1)} · Cache persistente: {detectedRuntime.cache_enabled === false ? "desligado" : "ativo"} · Diretório: {String(detectedRuntime.projects_dir ?? "engine/data/jobs")}. Altere estes três valores no engine/.env e reinicie o motor.</p>
              </section>
            )}

            <div className="action-row">
              <span className="cost-note">Processamento próprio · sem cobrança por minuto</span>
              <div>
                <button className="demo-button" type="button" onClick={startDemo}>Ver demonstração</button>
                <button className="primary-button" type="submit" disabled={state === "starting" || state === "processing"}><span>{state === "starting" || state === "processing" ? "Processando…" : "Criar cortes com IA"}</span><b>→</b></button>
              </div>
            </div>
          </form>
        </section>

        {(state !== "idle" || clips.length > 0) && (
          <section className={`progress-card ${state}`} aria-live="polite">
            <div className="progress-head">
              <div><span className="step-number">02</span><span><h2>{state === "completed" ? "Seus cortes estão prontos" : state === "failed" ? "Algo precisa de atenção" : "SnowTV trabalhando"}</h2><p>{message}</p></span></div>
              {demoMode && <span className="demo-pill">MODO DEMO</span>}
            </div>
            {(state === "starting" || state === "processing") && (
              <div className="real-progress">
                <div><strong>{stageLabels[currentStage] ?? "Processando"}</strong><span>{Math.round(progress)}%</span></div>
                <progress max="100" value={progress} aria-label={`Progresso ${Math.round(progress)}%`} />
                <small>O job fica salvo no motor e continua após refresh ou fechamento da aba.</small>
                <button className="cancel-job-button" type="button" onClick={cancelJob}>Cancelar processamento</button>
              </div>
            )}
            {(state === "starting" || state === "processing") && (
              <div className="pipeline">
                {processingSteps.map((step, index) => <div className={index < activeStep ? "done" : index === activeStep ? "current" : ""} key={step}><span>{index < activeStep ? "✓" : index + 1}</span><p>{step}</p></div>)}
              </div>
            )}
            {state === "failed" && <div className="error-actions"><button type="button" onClick={openSettings}>Configurar motor</button>{currentStage === "cancelled" && currentJobId && <button type="button" onClick={() => resumeJob()}>Retomar job</button>}<button type="button" onClick={() => setState("idle")}>Voltar ao vídeo</button></div>}
            {jobLogs.length > 0 && (
              <div className="job-details">
                <button type="button" onClick={() => setDetailsOpen((value) => !value)}>{detailsOpen ? "Ocultar detalhes" : "Ver detalhes do processamento"} <span>{jobLogs.length}</span></button>
                {detailsOpen && <ol>{jobLogs.map((log, index) => <li key={`${log}-${index}`}>{log}</li>)}</ol>}
              </div>
            )}
            {state === "completed" && currentJobId && !demoMode && (
              <div className="rerender-banner"><span><strong>Quer trocar legenda ou enquadramento?</strong><small>Altere as opções acima e rerenderize sem repetir o Whisper.</small></span><button type="button" onClick={() => rerenderJob(currentJobId, "Rerenderização do projeto atual")}>Rerenderizar com ajustes</button></div>
            )}
            {clips.length > 0 && (
              <div className="clips-grid">
                {clips.map((clip, index) => {
                  const title = clip.video_title_for_youtube_short ?? clip.title ?? `Corte ${index + 1}`;
                  const score = clip.viral_score ?? clip.score ?? 80 - index * 4;
                  const playableUrl = clip.video_url ?? clip.download_url;
                  return (
                    <article className="clip-card" key={`${title}-${index}`}>
                      <div className={`clip-preview tone-${index % 3}`}>
                        {playableUrl ? <video src={playableUrl} controls playsInline preload="metadata" /> : <><div className="fake-person"><span /><i /></div><p><strong>VOCÊ PRECISA</strong><br />OUVIR ISSO</p><button type="button" aria-label={`Reproduzir ${title}`}>▶</button></>}
                        <span className="score-badge">Clip Score {score}</span>
                      </div>
                      <div className="clip-info"><h3>{title}</h3><p>{formatTime(clip.start)}–{formatTime(clip.end)} · {durationOf(clip)}</p>{clip.reason && <small className="clip-reason">{clip.reason}</small>}{clip.score_breakdown && <div className="score-breakdown">{Object.entries(clip.score_breakdown).filter(([key]) => key !== "penalty").sort((a,b) => Number(b[1])-Number(a[1])).slice(0,4).map(([key,value]) => <span key={key}><b>{key.replace("context","Contexto").replace("completeness","Conclusão").replace("clarity","Clareza").replace("hook","Hook").replace("emotion","Emoção").replace("pacing","Ritmo").replace("boundary","Boundary").replace("shareability","Compart.").replace("novelty","Novidade")}</b>{value}</span>)}</div>}<div className="clip-feedback"><span>Esse corte vale publicar?</span><button type="button" className={clipFeedback[index + 1] === "good" ? "active" : ""} onClick={() => rateClip(index + 1, "good")}>👍 Bom</button><button type="button" className={clipFeedback[index + 1] === "bad" ? "active bad" : ""} onClick={() => rateClip(index + 1, "bad")}>👎 Ruim</button></div><div><button type="button" onClick={() => { setCaptionEditorOpen(true); window.setTimeout(() => document.querySelector(".caption-editor")?.scrollIntoView({ behavior: "smooth" }), 50); }}>Editar estilo</button><button type="button" onClick={() => adjustClipTiming(index + 1, clip)}>Ajustar tempo</button>{playableUrl ? <a href={clip.download_url ?? playableUrl} target="_blank" rel="noreferrer">Baixar ↓</a> : <button type="button" disabled>Baixar ↓</button>}</div></div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        )}

        <section className="projects-section" id="projetos">
          <div className="section-title"><div><p className="eyebrow"><span /> SEU CONTEÚDO</p><h2>Projetos recentes</h2></div><span>20 mais recentes</span></div>
          {savedProjects.length === 0 ? (
            <div className="empty-projects"><span>＋</span><div><strong>Seu primeiro projeto começa acima.</strong><p>Quando o processamento terminar, ele ficará salvo aqui para você revisar e baixar.</p></div></div>
          ) : (
            <div className="project-list">
              {savedProjects.map((project) => (
                <article className="project-row" key={project.id}>
                  <span className="project-thumb">▶</span>
                  <div>
                    <strong>{project.title}</strong>
                    <p>{project.sourceUrl.replace(/^https?:\/\//, "").slice(0, 54)}</p>
                  </div>
                  <time>{projectDate(project.createdAt)}</time>
                  <span className={`project-status ${project.status}`}>{["completed", "complete", "succeeded", "success"].includes(project.status) ? "Pronto" : project.status === "failed" ? "Falhou" : "Processando"}</span>
                  <div className="project-actions">
                    <button type="button" onClick={() => openProject(project)} aria-label={`Abrir ${project.title}`}>↗</button>
                    {project.engineJobId && <button type="button" onClick={() => rerenderJob(project.engineJobId!, project.sourceUrl)} aria-label={`Rerenderizar ${project.title}`}>↻</button>}
                    {project.engineJobId && ["cancelled", "failed"].includes(project.status) && <button type="button" onClick={() => resumeJob(project.engineJobId!, project.id)} aria-label={`Retomar ${project.title}`}>▶</button>}
                    <button type="button" onClick={() => renameProject(project)} aria-label={`Renomear ${project.title}`}>✎</button>
                    {["completed", "complete", "succeeded", "success", "failed"].includes(project.status) && <button type="button" onClick={() => deleteProject(project)} aria-label={`Excluir ${project.title}`}>×</button>}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>

      <nav className="mobile-nav" aria-label="Navegação móvel">
        <a className="active" href="#novo-corte"><NavGlyph label="Novo" />Novo</a>
        <a href="#projetos"><NavGlyph label="Projetos" />Projetos</a>
        <button type="button" onClick={openSettings}><NavGlyph label="Motor" />Motor</button>
      </nav>

      {settingsOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setSettingsOpen(false)}>
          <section className="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-title"><div><p className="eyebrow"><span /> CONEXÃO SEGURA</p><h2 id="settings-title">Motor de processamento</h2></div><button type="button" onClick={() => setSettingsOpen(false)} aria-label="Fechar">×</button></div>
            <div className="engine-summary"><LogoMark /><span><strong>Snow Engine próprio</strong><small>FFmpeg + faster-whisper + tracking facial</small></span><b className={engineState}>{engineState === "online" ? "ONLINE" : engineState === "checking" ? "TESTANDO" : "LOCAL"}</b></div>
            <label className="modal-field"><span>Endereço do motor <small>(seu computador ou servidor)</small></span><input type="url" value={engineUrl} onChange={(event) => setEngineUrl(event.target.value)} placeholder="http://127.0.0.1:8000" autoComplete="url" /></label>
            <label className="modal-field"><span>Token de acesso <small>(opcional em localhost)</small></span><input type="password" value={engineToken} onChange={(event) => setEngineToken(event.target.value)} placeholder="Mesmo valor de SNOW_API_TOKEN" autoComplete="off" /></label>
            <p className={`connection-result ${engineState}`}>{engineInfo}</p>
            {engineHealth && (
              <div className="hardware-panel">
                <div><span>CPU</span><strong>{String(detectedHardware.cpu ?? "Não identificada")}</strong></div>
                <div><span>RAM</span><strong>{String(detectedHardware.ram_gb ?? "—")} GB</strong></div>
                <div><span>Perfil recomendado</span><strong>{String(detectedProfile.name ?? "Auto").toUpperCase()}</strong></div>
                <div><span>Whisper</span><strong>{String(detectedProfile.whisper_model ?? "small")} · {String(detectedProfile.compute_type ?? "int8")}</strong></div>
                <div className="dependency-strip"><span className={detectedDependencies.ffmpeg ? "ok" : "missing"}>FFmpeg</span><span className={detectedDependencies.yt_dlp ? "ok" : "missing"}>yt-dlp</span><span className={detectedDependencies.deno ? "ok" : "optional"}>Deno {detectedDependencies.deno ? "✓" : "opcional"}</span></div>
              </div>
            )}
            {benchmark && (
              <div className={`benchmark-result ${benchmark.error ? "failed" : ""}`}>
                {benchmark.error ? <p>{String(benchmark.error)}</p> : <><strong>{String(benchmark.recommendation ?? "Benchmark concluído")}</strong><p>{String(benchmarkHardware.cpu ?? "CPU detectada")} · {String(benchmarkHardware.ram_gb ?? "—")} GB RAM</p><small>{String(benchmark.note ?? "libx264 permanece como fallback seguro.")}</small></>}
              </div>
            )}
            <p className="security-note">O vídeo e a transcrição são enviados apenas para este endereço. O token fica somente nesta sessão do navegador; a eventual chave do LLM é configurada no próprio motor.</p>
            <div className="modal-actions"><button type="button" onClick={() => testEngine()} disabled={engineState === "checking"}>Testar conexão</button><button type="button" onClick={runEngineBenchmark} disabled={benchmarking || engineState !== "online"}>{benchmarking ? "Benchmark…" : "Benchmark do PC"}</button><button type="button" onClick={() => setSettingsOpen(false)}>Cancelar</button><button className="primary-button" type="button" onClick={saveConnection} disabled={engineState === "checking"}><span>Salvar conexão</span><b>✓</b></button></div>
          </section>
        </div>
      )}
    </div>
  );
}
