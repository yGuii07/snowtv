# Validação do SnowTV

Este documento registra o estado de validação técnica da versão pública do projeto.

## Testes automatizados

A suíte automatizada do backend cobre seleção de cortes, legendas, pipeline e regras auxiliares.

```text
Ran 40 tests
OK
```

A compilação dos módulos Python também foi validada com:

```bash
python -m compileall -q engine/snow_engine
```

## Validação real no Windows

Em 8 de setembro de 2026, o fluxo principal foi retestado em uma máquina com:

- AMD Ryzen 5 4600G with Radeon Graphics;
- 15,4 GB de RAM detectados pelo motor;
- processamento em CPU;
- `faster-whisper small` com `int8`;
- perfil `BALANCED`.

O teste real confirmou:

- inicialização conjunta pelo `start-snowtv.ps1`;
- Snow Engine online em `127.0.0.1:8000`;
- detecção de FFmpeg, yt-dlp e ambiente local;
- download de vídeo por URL do YouTube;
- processamento persistente por etapas;
- transcrição;
- seleção de cinco cortes;
- `Clip Score` e métricas editoriais;
- reenquadramento 9:16;
- presets e editor visual de legendas;
- renderização final;
- reprodução e download dos MP4s gerados.

Dois arquivos renderizados foram inspecionados com FFprobe:

```text
clip-01: 1080x1920, 30 fps, 30.7 s
clip-02: 1080x1920, 30 fps, 33.07 s
```

## Correção encontrada durante o reteste

Durante o primeiro render real, o título de gancho e a legenda dinâmica apareciam simultaneamente nos primeiros segundos do corte, duplicando visualmente o texto.

A lógica de legendas foi alterada para dar prioridade visual ao gancho:

1. enquanto o gancho está visível, a legenda dinâmica é ocultada;
2. ao término do gancho, a legenda normal passa a ser exibida;
3. palavras que atravessam o instante de transição também respeitam esse limite.

Foi adicionado um teste automatizado específico para o caso, elevando a suíte para 40 testes. O corte foi renderizado novamente e a duplicação deixou de ocorrer.

## Cenários que continuam recomendados para validação recorrente

O fluxo principal está validado, mas os seguintes casos devem continuar sendo testados ao evoluir o projeto:

- cancelamento e retomada de jobs;
- vídeos com múltiplos interlocutores;
- tracking em cenas com movimento forte ou baixa iluminação;
- split automático com duas pessoas;
- diferentes fontes e estilos de legenda;
- vídeos longos com maior consumo de memória.

O roteiro detalhado está em [MANUAL_TEST_WINDOWS.md](MANUAL_TEST_WINDOWS.md).
