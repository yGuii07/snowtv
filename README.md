# SnowTV

**Gerador local de cortes verticais para Shorts, Reels e TikTok.**

O SnowTV transforma vídeos longos em cortes 9:16 prontos para redes sociais usando um pipeline local de processamento. O objetivo é oferecer uma alternativa self-hosted a ferramentas que cobram por minuto, mantendo controle sobre os arquivos, caches e renderizações.

O projeto combina **Python, FastAPI, React/TypeScript, faster-whisper, OpenCV, FFmpeg e yt-dlp**. O fluxo principal funciona sem API paga; integrações com LLM compatível com OpenAI ou Ollama são opcionais.

> **Status:** fluxo principal validado em Windows com processamento local em CPU. A suíte automatizada do backend possui **40 testes aprovados**. Veja [Validação](docs/testing/VALIDATION.md).

## Demonstração

### Novo corte

![Tela inicial do SnowTV](docs/screenshots/home.jpg)

### Motor local

O Snow Engine detecta hardware, perfil recomendado e dependências antes do processamento.

![Motor local conectado](docs/screenshots/motor-local.jpg)

### Pipeline em execução

O progresso do job é persistido e exibido por etapa, do download/transcrição até reenquadramento, legendas e render.

![Processamento em andamento](docs/screenshots/processamento.jpg)

### Editor de legendas

Presets visuais permitem ajustar estilo sem refazer a transcrição.

![Editor de estilos de legenda](docs/screenshots/estilos-legenda.jpg)

### Cortes gerados

Os resultados exibem duração, contexto, métricas editoriais e `Clip Score`.

![Cortes gerados pelo SnowTV](docs/screenshots/cortes-gerados.jpg)

### Saída final 9:16

Render real validado em **1080 × 1920, 30 fps**, com reenquadramento e legendas dinâmicas.

<p align="center">
  <img src="docs/screenshots/resultado-final.jpg" alt="Exemplo de corte vertical final" width="280">
</p>

## O que o SnowTV faz

- importa vídeos locais ou baixa conteúdo com `yt-dlp`;
- extrai áudio e metadados com FFmpeg/FFprobe;
- transcreve falas com timestamps por palavra usando `faster-whisper`;
- identifica trechos com maior potencial editorial;
- reduz cortes repetitivos por similaridade temporal e semântica;
- ajusta início e fim com base em pontuação e pausas;
- acompanha rostos e reenquadra automaticamente para 9:16;
- aplica fallback para crop central quando o tracking não é confiável;
- gera legendas ASS animadas e personalizáveis;
- permite estilos editoriais e presets de legenda;
- renderiza H.264/AAC com FFmpeg;
- persiste jobs e feedbacks em SQLite;
- reutiliza caches de mídia, transcrição, seleção, proxy e tracking;
- permite cancelar, retomar e rerenderizar jobs sem refazer etapas válidas.

## Pipeline

```mermaid
flowchart LR
    A[Upload / YouTube] --> B[Cache + FFprobe]
    B --> C[FFmpeg: áudio 16 kHz]
    C --> D[faster-whisper]
    D --> E[Editorial Engine]
    E --> F[Proxy de análise]
    F --> G[OpenCV: tracking / crop]
    G --> H[ASS / libass: legendas]
    H --> I[FFmpeg: render 9:16]
    I --> J[MP4 final + métricas]
```

## Arquitetura

```text
SnowTV/
├── app/                     # interface React/TypeScript
├── engine/                  # Snow Engine (FastAPI/Python)
│   ├── snow_engine/         # pipeline, API, jobs, tracking e render
│   ├── tests/               # testes automatizados do backend
│   └── data/                # ignorado pelo Git; jobs, caches e SQLite
├── db/                      # persistência usada pela interface
├── worker/                  # entry point da interface
├── docs/                    # validação, testes e histórico
└── tests/                   # testes do frontend/contratos
```

A interface envia um job ao **Snow Engine**. O backend executa as etapas pesadas em CPU, persiste o estado localmente e devolve progresso, logs e resultados pela API.

## Stack

### Backend / processamento

- Python 3.11/3.12
- FastAPI
- SQLite
- faster-whisper
- OpenCV
- FFmpeg / FFprobe / libass
- yt-dlp

### Interface

- React
- TypeScript
- Next/Vinext
- Vite

### Infraestrutura e execução

- Docker (CPU)
- perfil NVIDIA opcional
- scripts PowerShell para Windows
- cache local de pipeline

## Recursos técnicos relevantes

### Seleção editorial

O Editorial Engine usa ranking explicável com componentes como hook, contexto, conclusão, clareza, emoção, novidade, ritmo, compartilhamento e qualidade de boundary. A seleção final combina qualidade e diversidade para reduzir clipes semanticamente repetitivos.

### Tracking e reenquadramento

O pipeline usa proxy leve para análise facial, redetecção periódica, tracking entre detecções, smoothing e reset após mudanças fortes de cena. Quando não há tracking confiável, o job continua com crop central seguro em vez de falhar.

### Legendas

As legendas finais são renderizadas em ASS/libass. Há presets, destaque por palavra, safe zones, controle de fonte, tamanho, posição, contorno, fundo, cores e efeitos. O pipeline inclui quebra por largura e limite de linhas para evitar texto fora da área segura.

### Cache e retomada

O SnowTV reaproveita artefatos válidos entre execuções:

- mídia e URLs;
- metadados;
- transcrição;
- seleção editorial;
- proxies;
- tracking.

Isso permite ajustar legenda, enquadramento ou cortes sem retranscrever o vídeo inteiro. Jobs podem ser cancelados e retomados usando o estado persistido.

## API principal do Snow Engine

| Método | Endpoint | Finalidade |
| --- | --- | --- |
| `GET` | `/health` | hardware, versões e dependências |
| `GET` | `/api/capabilities` | capacidades e presets |
| `POST` | `/api/process` | processar URL |
| `POST` | `/api/process/upload` | processar upload |
| `GET` | `/api/status/{job_id}` | progresso e resultado |
| `GET` | `/api/jobs` | listar projetos locais |
| `POST` | `/api/jobs/{job_id}/rerender` | rerender usando caches |
| `POST` | `/api/jobs/{job_id}/cancel` | cancelar job |
| `POST` | `/api/jobs/{job_id}/resume` | retomar job |
| `DELETE` | `/api/jobs/{job_id}` | remover job e saídas |

A documentação completa do motor está em [engine/README.md](engine/README.md).

## Instalação no Windows

### Requisitos

- Windows 10/11;
- Python 3.11 ou 3.12;
- Node.js compatível com o projeto;
- FFmpeg e FFprobe no `PATH`;
- Deno opcional, recomendado para alguns fluxos do YouTube.

### 1. Preparar o motor

No PowerShell:

```powershell
cd .\engine
.\setup-windows.ps1
```

Nas próximas execuções:

```powershell
cd .\engine
.\run-local.ps1
```

Confirme o backend em:

```text
http://127.0.0.1:8000/health
```

### 2. Iniciar a interface

Em outro PowerShell, na raiz do projeto:

```powershell
npm.cmd install
npm.cmd run dev
```

Abra o endereço exibido pelo Vite, normalmente `http://localhost:5173`.

## Início rápido no Windows

Depois de instalar os pré-requisitos, a forma mais simples de iniciar o projeto é pela raiz:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-snowtv.ps1
```

O script:

- prepara a `.venv` do backend caso ainda não exista;
- instala as dependências Node caso `node_modules` ainda não exista;
- inicia FastAPI e o frontend;
- abre a interface no navegador;
- encerra os processos filhos quando o launcher é finalizado.

## Perfil de desempenho usado no desenvolvimento

A versão atual foi pensada para funcionar também sem GPU dedicada. No Ryzen 5 4600G com 16 GB de RAM, o perfil `AUTO` seleciona uma configuração balanceada.

| Item | Configuração de referência |
| --- | --- |
| Whisper | `small` |
| Dispositivo | CPU |
| Compute | `int8` |
| Threads Whisper | 8 |
| Threads FFmpeg | 6 |
| Jobs pesados | 1 |
| Proxy facial | 640 px |
| Encoder padrão | `libx264` |
| Saída | 1080 × 1920, 30 fps |

Também existem perfis `ECO`, `BALANCED`, `QUALITY` e `AUTO`.

## Testes e validação

Comandos principais:

```bash
PYTHONPATH=engine python3 -m unittest discover -s engine/tests -v
python3 -m compileall -q engine/snow_engine
npx tsc --noEmit
npm test
```

Na auditoria técnica mais recente:

```text
Python: 40 testes descobertos; 40 aprovados
TypeScript: OK
ESLint: OK
Frontend build: OK
Node tests: 2 OK
```

Esses resultados estão documentados em [docs/testing/VALIDATION.md](docs/testing/VALIDATION.md). O fluxo principal também foi validado manualmente no Windows com vídeo real; o checklist completo permanece em [docs/testing/MANUAL_TEST_WINDOWS.md](docs/testing/MANUAL_TEST_WINDOWS.md).

## Privacidade e segurança

- processamento principal local;
- nenhuma API paga obrigatória;
- `.env`, caches, jobs, outputs e banco local são ignorados pelo Git;
- token da API pode ficar vazio em localhost;
- para uso em rede, configure token, HTTPS, firewall e CORS restrito;
- chaves de provedores opcionais devem ficar apenas em `.env`.

## Limitações atuais

- o tracking automático ainda depende da qualidade e composição do vídeo;
- split automático com duas pessoas precisa de mais validação em vídeos reais;
- cancelamento de processos externos é cooperativo e ocorre em pontos seguros;
- o preview de legenda é visual e não é pixel-perfect em relação ao libass;
- cancelamento e retomada continuam como cenários recomendados para validação manual recorrente.

## Roadmap

- ampliar validação com vídeos reais e múltiplos interlocutores;
- medir tempo e consumo de RAM em diferentes perfis;
- melhorar tracking e decisão automática de split;
- expandir testes end-to-end;

## Histórico

Consulte [CHANGELOG.md](CHANGELOG.md) para o histórico de mudanças e [`docs/testing`](docs/testing/) para o roteiro de validação.

---

Projeto criado como ferramenta de uso próprio para automatizar a produção de cortes verticais sem depender de cobrança recorrente por minuto de vídeo.
