import { and, desc, eq } from "drizzle-orm";
import { ensureDbSchema, getDb } from "@/db";
import { projects } from "@/db/schema";

async function readyDb() {
  await ensureDbSchema();
  return getDb();
}

export async function GET(request: Request) {
  const ownerEmail = "local-user";
  try {
    const db = await readyDb();
    const rows = await db
      .select()
      .from(projects)
      .where(and(eq(projects.ownerEmail, ownerEmail)))
      .orderBy(desc(projects.createdAt))
      .limit(20);

    return Response.json({
      projects: rows.map((project) => ({
        ...project,
        options: JSON.parse(project.optionsJson),
        result: project.resultJson ? JSON.parse(project.resultJson) : null,
        optionsJson: undefined,
        resultJson: undefined,
      })),
    });
  } catch (error) {
    console.error("SnowTV projects query failed", error);
    return Response.json({ error: "Não foi possível carregar os projetos." }, { status: 500 });
  }
}

type ProjectMutation = {
  action?: "start" | "update" | "delete";
  id?: string;
  engineJobId?: string;
  sourceUrl?: string;
  title?: string;
  status?: string;
  options?: Record<string, unknown>;
  result?: Record<string, unknown>;
  errorMessage?: string | null;
};

export async function POST(request: Request) {
  const ownerEmail = "local-user";
  try {
    const db = await readyDb();
    const body = (await request.json()) as ProjectMutation;
    const id = body.id?.trim() ?? "";
    if (!/^[a-zA-Z0-9_-]{6,160}$/.test(id)) {
      return Response.json({ error: "Projeto inválido." }, { status: 400 });
    }

    if (body.action === "delete") {
      await db.delete(projects).where(and(eq(projects.id, id), eq(projects.ownerEmail, ownerEmail)));
      return Response.json({ ok: true, id });
    }

    if (body.action === "update") {
      await db
        .update(projects)
        .set({
          title: body.title?.slice(0, 180),
          status: body.status?.slice(0, 30),
          resultJson: body.result ? JSON.stringify(body.result) : undefined,
          errorMessage: body.errorMessage?.slice(0, 1000) ?? null,
          updatedAt: new Date().toISOString(),
        })
        .where(and(eq(projects.id, id), eq(projects.ownerEmail, ownerEmail)));
      return Response.json({ ok: true, id });
    }

    const engineJobId = body.engineJobId?.trim() ?? "";
    const sourceUrl = body.sourceUrl?.trim() ?? "";
    if (!/^[a-zA-Z0-9_-]{6,160}$/.test(engineJobId) || !sourceUrl) {
      return Response.json({ error: "Dados do projeto incompletos." }, { status: 400 });
    }

    await db
      .insert(projects)
      .values({
        id,
        ownerEmail,
        engineJobId,
        sourceUrl: sourceUrl.slice(0, 2000),
        title: body.title?.slice(0, 180) || "Vídeo em processamento",
        status: body.status?.slice(0, 30) || "queued",
        optionsJson: JSON.stringify(body.options ?? {}),
      })
      .onConflictDoUpdate({
        target: projects.id,
        set: {
          engineJobId,
          sourceUrl: sourceUrl.slice(0, 2000),
          status: body.status?.slice(0, 30) || "queued",
          optionsJson: JSON.stringify(body.options ?? {}),
          updatedAt: new Date().toISOString(),
        },
      });

    return Response.json({ ok: true, id }, { status: 201 });
  } catch (error) {
    console.error("SnowTV project mutation failed", error);
    return Response.json({ error: "Não foi possível salvar o projeto." }, { status: 500 });
  }
}
