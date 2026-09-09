# Arquitetura do SnowTV

## Visão geral

O SnowTV é dividido em duas partes principais:

1. **Interface** em React/TypeScript, responsável por configuração, envio de jobs, acompanhamento e editor visual.
2. **Snow Engine** em FastAPI/Python, responsável por download/importação, transcrição, seleção editorial, tracking, legendas, renderização, persistência e cache.

## Fluxo de processamento

```mermaid
sequenceDiagram
    participant UI as Interface
    participant API as FastAPI
    participant DB as SQLite
    participant W as Worker/Pipeline
    participant FS as Cache/Arquivos

    UI->>API: cria job (URL ou upload)
    API->>DB: persiste estado
    API->>W: enfileira processamento
    W->>FS: cache/FFprobe/áudio
    W->>W: transcrição + seleção
    W->>W: proxy + tracking
    W->>W: legendas + render
    W->>DB: atualiza progresso/resultado
    UI->>API: consulta status
    API-->>UI: progresso, logs e cortes
```

## Persistência

O backend usa SQLite para estado dos jobs e feedbacks. Artefatos pesados ficam em diretórios locais ignorados pelo Git. O cache é granular para evitar repetir etapas caras.

## Princípios do projeto

- processamento local por padrão;
- fallback em vez de falha quando tracking não é confiável;
- reaproveitamento de caches;
- jobs persistentes e retomáveis;
- heurística offline como caminho padrão;
- aceleração por hardware opcional, não obrigatória.
