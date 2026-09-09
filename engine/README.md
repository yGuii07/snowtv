# Snow Engine

Backend FastAPI self-hosted do SnowTV. Ele processa o vídeo no próprio computador com FFmpeg, faster-whisper, OpenCV, SQLite e yt-dlp.

## Windows: preparar uma vez, iniciar rapidamente

Na primeira execução:

```powershell
cd .\engine
.\setup-windows.ps1
```

O setup:

- procura Python 3.12 e 3.11 por `py`, `python` e `python3`;
- rejeita versões incompatíveis com mensagem clara;
- valida FFmpeg/FFprobe;
- cria ou repara `.venv`;
- instala `requirements.txt` e valida OpenCV, faster-whisper e yt-dlp;
- detecta Deno, mas não bloqueia a instalação se ele estiver ausente.

Depois:

```powershell
.\run-local.ps1
```

`run-local.ps1` apenas valida a instalação e inicia uma instância em `http://127.0.0.1:8000` com um worker.

## Downloader do YouTube

O motor executa o mesmo ambiente Python por subprocesso:

```text
<python-da-venv> -m yt_dlp
```

O próprio yt-dlp baixa fragmentos e chama FFmpeg para o merge. O SnowTV nunca extrai uma URL assinada para baixá-la com requests/httpx.

Tentativas:

1. modo standalone nativo, somente com `--no-playlist` e o template de saída — sem formato, container, cliente ou runtime forçados;
2. `bv*+ba/b`, com retries e runtime JavaScript opcional;
3. `b[height<=1080][ext=mp4]/b[height<=1080]/b/bv*+ba` com configuração alternativa de cliente.

O arquivo final pode ser MP4, WebM, MKV ou MOV; o FFmpeg normaliza a fonte nas etapas seguintes. Cada tentativa registra o comando efetivo sanitizado nos detalhes técnicos do job. Somente depois das três falharem o job recebe `failed`.

Na primeira tentativa o próprio yt-dlp detecta formatos, cliente e Deno como faria no terminal. Nos fallbacks, `yt-dlp[default]` disponibiliza os componentes EJS e o Deno pode ser informado pelo `PATH` ou explicitamente:

```env
SNOW_YTDLP_JS_RUNTIME=deno
SNOW_YTDLP_JS_RUNTIME_PATH=C:\Users\seu-usuario\.deno\bin\deno.exe
SNOW_YTDLP_REMOTE_COMPONENTS=false
```

## Cache

O diretório padrão é `engine/data/cache/`:

- `media/`: fonte com hash SHA-256;
- `urls/`: mapeamento de URL do YouTube para fonte local;
- `metadata/`: resultado do FFprobe;
- `transcripts/`: texto e timestamps por palavra, por fonte/idioma/modelo;
- `selections/`: cortes editoriais por configuração;
- `proxies/`: vídeo leve usado no tracking;
- `tracking/`: pontos suavizados, decisão de split e evidências por timeline/configuração.

Uploads repetidos reutilizam transcrição pelo hash do conteúdo. URLs já processadas podem reutilizar inclusive a mídia. Rerenderizar muda legenda, enquadramento ou render sem executar Whisper novamente.

Desative apenas para diagnóstico:

```env
SNOW_CACHE_ENABLED=false
```

## Perfis e AMD

`SNOW_PERFORMANCE_PROFILE=auto|eco|balanced|quality`.

O encoder padrão continua `libx264`. Se o FFmpeg listar `h264_amf`, a opção **AMD Hardware** fica disponível. O benchmark faz um encode sintético curto; AMF só é usado quando selecionado. Qualquer falha do encoder escolhido repete automaticamente com `libx264`.

Configurações avançadas também podem ser enviadas por job, sem editar `.env`:

- Whisper model/compute/threads;
- largura do proxy;
- intervalo de redetecção;
- encoder;
- CRF e preset FFmpeg.

## Tracking e fallback

- frames analisados em proxy 480/640/720 px;
- Haar para redetecção periódica;
- CSRT/KCF para tracking entre detecções;
- bounding boxes sempre convertidas para `tuple[int, int, int, int]`;
- boxes negativas, vazias ou fora do frame são rejeitadas;
- dead zone, limite de velocidade e smoothing reduzem tremor;
- no modo Auto, uma mudança visual forte de cena reseta o tracker para impedir que o alvo anterior contamine o novo plano;
- no modo Auto, duas faces separadas e persistentes em pelo menos metade das redetecções ativam o layout split;
- zero detecções confiáveis, erro do OpenCV ou erro do tracker resulta em crop central;
- tracking nunca deve encerrar o job.

## Legendas

O motor gera ASS e deixa o FFmpeg/libass renderizar. Cada palavra possui seu timestamp e a palavra atual recebe cor/animação. Os blocos respeitam pausas, pontuação, largura estimada, máximo de palavras, máximo de linhas e margem horizontal de 10%. Títulos automáticos são compactados em até duas linhas. O cache editorial foi versionado para não reutilizar títulos gerados antes dessa correção.

Presets: `none`, `karaoke`, `bold`, `minimal`, `podcast`, `highlight`, `bounce`, `pop`, `deep`, `glitch`. Na UI, esses presets aparecem como Snow Karaoke, Snow Beast, Snow Clean, Snow Podcast, Snow Focus, Snow Bounce, Snow Popline, Snow Deep Diver e Snow Glitch. Efeitos adicionais `scale` e `fade` também são aceitos.

As safe zones elevam a margem inferior para Shorts, Reels ou TikTok. `BorderStyle=3` fornece fundo em caixa quando o preset pede; cantos perfeitamente arredondados dependem de suporte futuro do renderizador.

## Remoção de pausas

- `off`: preserva tudo;
- `light`: remove apenas silêncios longos;
- `normal`: equilíbrio padrão;
- `aggressive`: jump cuts mais próximos.

As pausas curtas permanecem. A timeline editada é aplicada simultaneamente a vídeo, áudio e timestamps de legenda.

## API

| Método | Endpoint | Finalidade |
| --- | --- | --- |
| GET | `/health` | versões, hardware, perfil, encoders e dependências |
| GET | `/api/capabilities` | presets e capacidades do motor |
| POST | `/api/benchmark` | benchmark curto do PC/encoders |
| POST | `/api/process` | cria job por URL do YouTube |
| POST | `/api/process/upload` | cria job por upload multipart |
| GET | `/api/status/{job_id}` | progresso, estágio, logs e resultado |
| GET | `/api/jobs` | lista projetos locais |
| POST | `/api/jobs/{job_id}/rerender` | cria render usando a fonte/caches existentes |
| POST | `/api/jobs/{job_id}/cancel` | solicita cancelamento persistente no próximo ponto seguro |
| POST | `/api/jobs/{job_id}/resume` | retoma job cancelado/falho reutilizando caches |
| POST | `/api/jobs/{job_id}/feedback` | salva avaliação local do corte |
| GET | `/api/jobs/{job_id}/feedback` | lista avaliações locais do projeto |
| DELETE | `/api/jobs/{job_id}` | exclui job concluído/falho e seus MP4 |

Os estágios são `queued`, `downloading`, `importing`, `extracting_audio`, `transcribing`, `analyzing`, `selecting`, `tracking`, `rendering`, `completed`, `failed` e `cancelled`.

## Métricas

Cada resultado inclui `timings` e grava `metrics.json` com:

- download/hash/probe;
- áudio;
- transcrição;
- seleção;
- proxy;
- tracking;
- render;
- total.

## Configuração essencial

```env
SNOW_PERFORMANCE_PROFILE=auto
SNOW_WORKER_CONCURRENCY=1
SNOW_WHISPER_MODEL=auto
SNOW_WHISPER_DEVICE=auto
SNOW_WHISPER_COMPUTE_TYPE=auto
SNOW_VIDEO_ENCODER=auto
SNOW_CACHE_ENABLED=true
SNOW_LLM_PROVIDER=heuristic
```

Para Ollama local:

```env
SNOW_LLM_PROVIDER=ollama
SNOW_LLM_MODEL=qwen2.5:7b
SNOW_LLM_BASE_URL=http://host.docker.internal:11434
```

Se o LLM opcional falhar, a seleção volta para a heurística local.

## Dados e segurança

Jobs ficam em `engine/data/jobs/` e o estado em `engine/data/snow-engine.sqlite3`. Jobs que estavam `queued` ou `processing` são reenfileirados após reinício.

Em localhost, o token pode ficar vazio. As origens locais `localhost`, `127.0.0.1` e `[::1]` são aceitas em qualquer porta HTTP de desenvolvimento. Para rede/Internet, configure `SNOW_API_TOKEN`, HTTPS, firewall e `SNOW_CORS_ORIGINS` restrito.


## Editorial Engine 2.1 / selector v5

A seleção local usa ranking explicável com componentes `hook`, `context`, `completeness`, `clarity`, `emotion`, `novelty`, `pacing`, `shareability` e `boundary`. Pontuação, pausas word-level e limites máximos formam unidades naturais. A seleção final usa uma função qualidade × diversidade, penalizando simultaneamente overlap temporal e proximidade semântica lexical. O selector v5 deriva títulos curtos do conteúdo real de cada trecho e evita repetir títulos já usados no mesmo job. Os modos `auto`, `viral`, `educational`, `podcast`, `storytelling` e `commentary` continuam offline e determinísticos.

Ajustes manuais enviados em `clipOverrides` são aplicados **depois** da seleção cacheada, permitindo corrigir início/fim/título sem invalidar o Whisper ou o ranking editorial.
