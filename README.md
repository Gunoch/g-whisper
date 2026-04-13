# g-whisper

Sistema de ditado por voz local (estilo Wispr Flow), offline, para Windows.
Transcreve microfone em tempo real usando Whisper e injeta o texto onde o cursor estiver.

## Requisitos

- Windows 11
- Python 3.10+ (testado com 3.14)
- Microfone
- ~150MB de espaço livre (download do modelo na primeira execução, em `%USERPROFILE%\.cache\huggingface\`)

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[vad]"
```

O extra `[vad]` adiciona `torch` e `silero-vad` (necessários para o modo hands-free).

## Uso

**Forma recomendada:** double-click em `g-whisper.bat` -- inicia em segundo plano, sem janela de console. Aparece um ícone na bandeja do sistema e uma pill flutuante mostra o status quando você está gravando.

### Ícone da bandeja
Botão direito abre o menu:
- **Modo: push-to-talk / hands-free** — alterna entre os modos
- **Microfone** — submenu com todos os mics detectados, clique para trocar
- **Histórico** — últimas 10 transcrições, clique para copiar
- **Iniciar com Windows** — checkbox; quando ativo, cria atalho em `Startup` para o app abrir no boot
- **Sair** — encerra

Cor do ícone indica status:
- Amarelo: carregando modelo
- Cinza: idle
- Vermelho: gravando
- Azul: transcrevendo
- Verde: hands-free ouvindo

### Pill flutuante no rodapé
Durante gravação mostra 5 barrinhas animadas com o volume real do mic. Clicar na pill durante gravação **cancela** (não transcreve). Ao terminar, mostra ✓ + o texto transcrito por 2s antes de sumir.

### Outras formas de executar
- **Debug** (com console visível): `g-whisper-debug.bat`.
- **Sem tray** (CLI puro): `python run.py`.

### Single-instance
Se você der double-click duas vezes, o segundo processo detecta que já tem um rodando e fecha silenciosamente (Windows toast avisa).

Na primeira execução, o modelo Whisper é baixado automaticamente (~150MB para o modelo `base`).

### Hotkeys (globais, funcionam em qualquer app)

| Tecla | Ação |
|-------|------|
| `F9` (segurar) | Push-to-talk: grava enquanto segurado, transcreve e cola ao soltar |
| `Ctrl+Shift+M` | Alterna entre push-to-talk e hands-free |
| `Ctrl+Shift+Q` | Sair |

### Modos

- **Push-to-talk** (padrão): segura F9, fala, solta. Mais preciso e controlado.
- **Hands-free**: Silero VAD detecta fala automaticamente. Fale naturalmente; após ~500ms de silêncio, o trecho é transcrito e colado.

## Configuração

Edite `config.yaml` para alterar comportamento. Principais campos:

```yaml
transcriber:
  model_size: "base"   # tiny, base, small, medium, large-v3
  device: "cpu"         # cpu, cuda, auto
  compute_type: "int8"  # int8, float16, float32
  language: "pt"        # idioma (pt = PT-BR)

hotkeys:
  push_to_talk: "f9"
  toggle_mode: "ctrl+shift+m"
  quit: "ctrl+shift+q"

output:
  method: "clipboard"       # clipboard (Ctrl+V) ou typing (digita char a char)
  add_trailing_space: true  # adiciona espaço no final
```

Algumas configurações de áudio são fixas por requisito técnico:
`sample_rate=16000`, `channels=1`, `block_size=512` (exigido pelo Silero VAD e faster-whisper).

## Limitações conhecidas

- **Janelas elevadas**: Se o app alvo rodar como administrador e o g-whisper não, o `Ctrl+V` silenciosamente não funciona. Rode os dois no mesmo nível de privilégio.
- **Antivírus**: A biblioteca `keyboard` hook teclado em nível do OS e pode ser sinalizada como keylogger. Adicione exceção se necessário.
- **Clipboard**: O paste usa clipboard + Ctrl+V. O conteúdo anterior é restaurado após o paste, mas pode haver perda se você copiar algo exatamente durante o ciclo de ~200ms da transcrição.
- **Microfone padrão**: Para escolher outro dispositivo, defina `audio.device` no `config.yaml` com o índice do device (use `python -c "import sounddevice; print(sounddevice.query_devices())"` para listar).

## Arquitetura

```
Microfone (sounddevice, 16kHz mono)
    |
    v
[Audio Queue]
    |
    v
VAD worker (Silero, chunks de 512 samples)
    |
    v
[Transcription Queue]
    |
    v
Transcription worker (faster-whisper)
    |
    v
type_text (pyperclip + keyboard Ctrl+V)
```

Ver `gwhisper/` para os módulos individuais.
