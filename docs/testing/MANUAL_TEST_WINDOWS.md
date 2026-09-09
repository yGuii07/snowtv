# SnowTV — teste de aceitação no Windows

## Preparação

Na raiz do projeto, execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-snowtv.ps1
```

O script prepara o backend e o frontend quando necessário, inicia os dois serviços e abre a interface local.

## Checklist

- [x] A interface abre sem erro.
- [x] `http://127.0.0.1:8000/health` responde e o motor aparece ONLINE.
- [x] Um vídeo pode ser baixado por URL.
- [x] A transcrição é concluída.
- [x] Cinco cortes foram selecionados e exibidos.
- [x] O tracking/reenquadramento vertical gera saída 9:16.
- [x] O editor de legendas abre e os presets são carregados.
- [x] Título e legenda não aparecem duplicados após a correção do gancho.
- [x] A renderização final conclui.
- [x] MP4s finais 1080x1920/30 fps foram reproduzidos e inspecionados.
- [ ] Cancelar um job funciona.
- [ ] Retomar/reprocessar um job funciona conforme esperado.
- [ ] O cache é reaproveitado quando aplicável.

## Hardware de referência

O projeto foi pensado para funcionar localmente em CPU e já foi trabalhado em uma máquina com Ryzen 5 4600G e 16 GB de RAM, sem exigir NVIDIA/CUDA.
