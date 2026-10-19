# OpenAGY Bridge 🌉

Ponte local e multiplataforma de alta performance que conecta o **OpenCode** à sua sessão autenticada do **Google Antigravity (`agy`)**, permitindo utilizar as cotas e modelos avançados do Antigravity no OpenCode como se fosse um provedor padrão compatível com a API da OpenAI.

---

## 📑 Sumário

- [Arquitetura & Fluxo de Execução](#-arquitetura--fluxo-de-execução)
- [Segurança & Prevenção de Banimento](#-segurança--prevenção-de-banimento)
- [Compatibilidade Multiplataforma](#-compatibilidade-multiplataforma)
- [Modelos Disponíveis](#-modelos-disponíveis)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação e Inicialização Rápida](#-instalação-e-inicialização-rápida)
  - [Linux](#-linux)
  - [Windows](#-windows)
  - [macOS](#-macos)
- [Estrutura de Configuração no OpenCode](#-estrutura-de-configuração-no-opencode)
- [Suporte a Chamadas de Ferramentas (Tool Calling)](#-suporte-a-chamadas-de-ferramentas-tool-calling)
- [Variáveis de Ambiente & Parâmetros de Inicialização](#-variáveis-de-ambiente--parâmetros-de-inicialização)
- [Validação e Diagnóstico Local](#-validação-e-diagnóstico-local)
- [Solução de Problemas (FAQ)](#-solução-de-problemas-faq)

---

## 🏗️ Arquitetura & Fluxo de Execução

O **OpenAGY** atua como uma camada mediadora estritamente local entre o OpenCode e o CLI oficial do Antigravity:

```text
┌─────────────────────────┐
│     OpenCode Client     │  (Editor / Chat / Terminal)
└────────────┬────────────┘
             │  Protocolo HTTP OpenAI (/v1/chat/completions)
             ▼
┌─────────────────────────┐
│     OpenAGY Bridge      │  (FastAPI em 127.0.0.1:8080)
│  - CLI Engine           │  - Conversor de esquemas e limites
│  - Parser Tool Calling  │  - Streaming em tempo real (SSE)
└────────────┬────────────┘
             │  Invocação local por processo (PTY no Unix / Pipes no Windows)
             ▼
┌─────────────────────────┐
│  Antigravity CLI (agy)  │  (Binário local já autenticado)
└────────────┬────────────┘
             │  Conexão oficial do Google Antigravity
             ▼
┌─────────────────────────┐
│  Google Cloud Backends  │  (Execução com cota legítima do usuário)
└─────────────────────────┘
```

---

## 🛡️ Segurança & Prevenção de Banimento

* **Zero Chamadas Diretas a APIs Privadas:** A ponte **não** efetua conexões HTTP diretas para endpoints internos privados do Google (como `cloudcode-pa.googleapis.com`). Fazer requisições diretas a partir de IPs ou headers não reconhecidos poderia acarretar suspensão ou banimento da conta Google.
* **100% Processamento Local:** Toda a comunicação externa, renovação de tokens OAuth e validação de cotas permanecem sob controle do executável nativo do Antigravity (`agy`).
* **Isolamento de Credenciais:** O OpenCode nunca tem acesso aos seus tokens do Google; ele conversa apenas com a API local da ponte em `http://127.0.0.1:8080`.

---

## 🌐 Compatibilidade Multiplataforma

O OpenAGY foi desenvolvido para funcionar sem atritos em qualquer sistema operacional moderno:

| Sistema | Terminal Suportado | Modo de Streaming | Descoberta do Binário `agy` | Caminho do `opencode.json` |
| :--- | :--- | :--- | :--- | :--- |
| **Linux** | Bash, Zsh, Sh | Pipes assíncronos (`asyncio.subprocess.PIPE`) | `~/.local/bin`, `/usr/local/bin`, `/usr/bin`, `PATH` | `$XDG_CONFIG_HOME/opencode/` ou `~/.config/opencode/` |
| **Windows** | CMD, PowerShell | Pipes assíncronos (`asyncio.subprocess.PIPE`) | `agy.exe`, `agy.cmd`, `%LOCALAPPDATA%`, `%USERPROFILE%\.local\bin` | `%APPDATA%\opencode\` ou `%USERPROFILE%\.config\opencode\` |
| **macOS** | Zsh, Bash | Pipes assíncronos (`asyncio.subprocess.PIPE`) | `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin` | `~/.config/opencode/` |

---

## 🤖 Modelos Disponíveis

A ponte registra e disponibiliza no seletor de modelos do OpenCode os seguintes modelos, com janelas de contexto e cotas configuradas de acordo com as especificações do Antigravity:

| Identificador no OpenCode | Nome de Exibição | Janela de Contexto | Limite de Saída |
| :--- | :--- | :--- | :--- |
| `openagy/gemini-3.8-flash-high` | **Gemini 3.8 Flash High** *(Padrão)* | 1.048.576 tokens | 8.192 tokens |
| `openagy/gemini-3.8-flash-medium` | **Gemini 3.8 Flash Medium** | 1.048.576 tokens | 8.192 tokens |
| `openagy/gemini-3.1-pro-high` | **Gemini 3.1 Pro High** *(Raciocínio Profundo)* | 2.097.152 tokens | 8.192 tokens |
| `openagy/claude-sonnet-5-5-high` | **Claude Sonnet 5.5** *(via Antigravity)* | 200.000 tokens | 8.192 tokens |
| `openagy/gpt-oss-120b-medium` | **GPT-OSS 120B** | 128.000 tokens | 8.192 tokens |

---

## 📋 Pré-requisitos

1. **Python 3.10 ou superior** instalado e acessível no PATH do sistema.
2. **Google Antigravity CLI (`agy`)** instalado e autenticado na máquina (`agy` funcional no terminal).
3. **OpenCode** instalado na máquina.

---

## 🚀 Instalação e Inicialização Rápida

### 🐧 Linux

1. **Instalação e configuração automática:**
```bash
chmod +x install.sh run.sh
./install.sh
```
> **Nota para Debian/Ubuntu:** Se o pacote do ambiente virtual não estiver instalado, instale com:
> ```bash
> sudo apt update && sudo apt install -y python3 python3-venv python3-pip
> ```

2. **Iniciar a ponte:**
```bash
./run.sh
```

---

### 🪟 Windows

#### Opção 1: Via Prompt de Comando (CMD)
1. **Instalação e configuração automática:**
```cmd
install.bat
```
2. **Iniciar a ponte:**
```cmd
run.bat
```

#### Opção 2: Via PowerShell
1. **Instalação e configuração automática:**
```powershell
.\install.ps1
```
> **Nota:** Se o PowerShell bloquear a execução de scripts locais, habilite na sessão atual:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```
2. **Iniciar a ponte:**
```powershell
.\run.ps1
```

---

### 🍎 macOS

1. **Instalação e configuração automática:**
```bash
chmod +x install.sh run.sh
./install.sh
```
2. **Iniciar a ponte:**
```bash
./run.sh
```

---

## ⚙️ Estrutura de Configuração no OpenCode

O script [setup_opencode.py](file:///Users/egsl/Documents/projects/openagy/setup_opencode.py) atualiza o arquivo `opencode.json` de forma segura, criando um backup timestamped (`opencode.json.bak-<timestamp>`) e preservando quaisquer outros provedores e servidores MCP pré-existentes (como `zrq-engine`).

A configuração inserida no arquivo segue o formato exigido pelo OpenCode:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "openagy": {
      "name": "OpenAGY",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://127.0.0.1:8080/v1",
        "apiKey": "openagy-key"
      },
      "models": {
        "gemini-3.8-flash-high": {
          "name": "Gemini 3.8 Flash High (Antigravity)",
          "limit": {
            "context": 1048576,
            "output": 8192
          }
        },
        "gemini-3.8-flash-medium": {
          "name": "Gemini 3.8 Flash Medium (Antigravity)",
          "limit": {
            "context": 1048576,
            "output": 8192
          }
        },
        "gemini-3.1-pro-high": {
          "name": "Gemini 3.1 Pro High (Antigravity)",
          "limit": {
            "context": 2097152,
            "output": 8192
          }
        },
        "claude-sonnet-5-5-high": {
          "name": "Claude Sonnet 5.5 (Antigravity)",
          "limit": {
            "context": 200000,
            "output": 8192
          }
        },
        "gpt-oss-120b-medium": {
          "name": "GPT-OSS 120B (Antigravity)",
          "limit": {
            "context": 128000,
            "output": 8192
          }
        }
      }
    }
  }
}
```

---

## 🛠️ Suporte a Chamadas de Ferramentas (Tool Calling)

O OpenCode utiliza chamadas de ferramentas (Function Calling) para ler arquivos, aplicar edições de código e executar comandos de terminal.

### 1. Tradução em Tempo Real
Quando o OpenCode envia ferramentas no parâmetro `tools` do request da OpenAI:
1. O OpenAGY formata as especificações das ferramentas nas instruções de sistema do modelo.
2. O modelo emite blocos estructurados de chamada de função (`tool_call`).
3. O OpenAGY intercepta o bloco e o devolve ao OpenCode como um evento delta padrão da OpenAI (`delta.tool_calls`), acionando a execução automática da ferramenta pelo OpenCode.

### 2. Permissões Headless Automáticas
Em execuções não interativas ou headless do Antigravity, o `jetski` poderia bloquear comandos com:
> `jetski: no output produced — a tool required the "command" permission that headless mode cannot prompt for, so it was auto-denied.`

Para evitar esse problema, o OpenAGY:
* Passa automaticamente a flag `--dangerously-skip-permissions` na chamada local do `agy`.
* Pré-autoriza as regras em `~/.gemini/antigravity-cli/settings.json`:
  ```json
  {
    "permissions": {
      "allow": [
        "command(*)",
        "command()",
        "read_file(*)",
        "edit_file(*)",
        "*"
      ]
    }
  }
  ```

---

## 🔧 Variáveis de Ambiente & Parâmetros de Inicialização

Você pode customizar o comportamento da ponte tanto por linha de comando quanto definindo variáveis de ambiente:

| Variável de Ambiente | Argumento CLI | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `OPENAGY_HOST` | `--host` | `127.0.0.1` | Endereço de escuta do servidor HTTP |
| `OPENAGY_PORT` | `--port` | `8080` | Porta TCP do servidor |
| `OPENAGY_API_KEY` | `--api-key` | `openagy-key` | Chave de API para autenticação |
| `OPENAGY_REQUIRE_KEY` | `--require-key` | `false` | Se ativo, rejeita requisições sem o Bearer token correspondente |
| `OPENAGY_AGY_BIN` | N/A | *(Automático)* | Caminho customizado para o executável do Antigravity (`agy`) |
| `OPENAGY_ENGINE` | `--engine` | `cli` | Motor de backend (`cli` para local ou `cloudcode`) |
| `OPENAGY_LOG_LEVEL` | N/A | `INFO` | Nível de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `OPENCODE_CONFIG_PATH` | `--config` *(no setup)* | *(Automático)* | Caminho customizado para o arquivo `opencode.json` |

### Exemplo de Inicialização com Parâmetros Customizados:
```bash
# Rodar em porta diferente com chave customizada
python3 main.py --port 9000 --api-key minha-chave-secreta --require-key
```

E para configurar o OpenCode com esses mesmos parâmetros:
```bash
python3 setup_opencode.py --port 9000 --key minha-chave-secreta
```

---

## 🔍 Validação e Diagnóstico Local

### 1. Testar o Antigravity Local diretamente:
```bash
python3 test_local_agy.py
```
Esse script envia uma solicitação simples ao executável local e valida se o streaming via terminal/pipes está respondendo corretamente.

### 2. Verificar o status da ponte:
```bash
curl http://127.0.0.1:8080/health
```

Resposta esperada:
```json
{
  "status": "healthy",
  "service": "OpenAGY Bridge",
  "mode": "local-antigravity",
  "active_engine": "cli",
  "local_antigravity_bin": "/Users/egsl/.local/bin/agy",
  "local_antigravity_ready": true,
  "endpoints": {
    "models": "/v1/models",
    "chat_completions": "/v1/chat/completions"
  }
}
```

### 3. Listar modelos via API compatível OpenAI:
```bash
curl http://127.0.0.1:8080/v1/models
```

---

## ❓ Solução de Problemas (FAQ)

### 1. `ConnectionRefused: Unable to connect. Is the computer able to access the url?`
* **Causa:** O OpenCode tentou enviar uma mensagem, mas a ponte OpenAGY não estava ativa.
* **Solução:** Inicie a ponte executando `./run.sh` (Linux/macOS) ou `run.bat` / `.\run.ps1` (Windows) antes de enviar mensagens pelo OpenCode.

### 2. Os modelos `openagy/...` não aparecem no seletor do OpenCode
* **Causa:** O OpenCode carrega as configurações na inicialização.
* **Solução:**
  1. Feche e reabra o OpenCode.
  2. Verifique se o arquivo `opencode.json` foi devidamente atualizado pelo script de instalação.
  3. No Windows, garanta que o arquivo em `%APPDATA%\opencode\opencode.json` contenha o bloco `"openagy"`.

### 3. `ModuleNotFoundError: No module named 'pty'` no Windows
* **Causa:** Versões anteriores tentavam importar o módulo Unix `pty` em ambiente Windows.
* **Solução:** Atualizado no [cli_engine.py](file:///Users/egsl/Documents/projects/openagy/openagy/engines/cli_engine.py). No Windows, o motor utiliza pipes assíncronos nativos automaticamente.

### 4. Erro de execução de script no PowerShell (`ExecutionPolicy`)
* **Causa:** Política de segurança padrão do Windows bloqueando scripts `.ps1`.
* **Solução:** Execute no PowerShell antes de rodar os scripts:
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  ```
  Ou utilize o script em lote correspondente: `install.bat` e `run.bat`.

### 5. `Error: no output produced — a tool required the "command" permission`
* **Causa:** O `jetski` do Antigravity bloqueou a execução de uma ferramenta em modo não interativo.
* **Solução:** O instalador configura automaticamente as permissões em `~/.gemini/antigravity-cli/settings.json` e passa a flag `--dangerously-skip-permissions` para liberar a execução segura pelo OpenCode.

### 6. `[WinError 206] O nome do arquivo ou a extensão é muito grande` no Windows
* **Causa:** O Windows possui um limite estrito para linhas de comando (`cmd.exe` tem limite de 8.191 caracteres; chamadas Win32 nativas têm 32.767 caracteres). Históricos longos ou wrappers `.cmd`/`.bat` excediam essa cota.
* **Solução:** O OpenAGY prioriza automaticamente o binário nativo `agy.exe` em vez de wrappers `.cmd`/`.bat`, e orça dinamicamente o histórico de mensagens para respeitar os limites do sistema operacional sem perder o contexto essencial.

### 7. `Timed out waiting for response data` no OpenCode
* **Causa:**
  1. **No macOS:** O motor de pseudo-terminal (PTY) em Python sofre de uma limitação do backend `kqueue` do Darwin/BSD: quando o subprocesso filho encerra e fecha o lado escravo do PTY, o descritor mestre não sinaliza o evento EOF (fim de arquivo), fazendo com que leitores assíncronos fiquem aguardando indefinidamente em bloqueio.
  2. **No Windows:** Em pipes anônimos sem drenagem concorrente, o Antigravity envia diagnósticos para `stderr`. Quando o buffer de 4 KB do Windows satura, o processo entra em deadlock esperando espaço no buffer enquanto o leitor espera por `stdout`.
  3. **No Cliente OpenCode:** O `@ai-sdk/openai-compatible` possui um timer estrito aguardando o primeiro evento de resposta SSE. Qualquer atraso na inicialização do processo local ou pausas prolongadas durante raciocínio profundo causavam o encerramento da conexão.
* **Solução:**
  1. O OpenAGY migrou para **pipes assíncronos universais (`asyncio.subprocess.PIPE`) com leitura sem buffer (128 bytes)**, eliminando por completo o PTY e garantindo detecção instantânea de EOF no macOS, Linux e Windows.
  2. Drenagem concorrente de `stderr` em segundo plano para evitar saturação de buffers.
  3. Emissão instantânea de chunk inicial de handshake (`role: "assistant"`) em < 5 ms, reiniciando o relógio de timeout do OpenCode.
  4. Emissão periódica de pings de keep-alive (`: ping\n\n`) via Server-Sent Events durante etapas de raciocínio profundo.
  5. Configuração automática de tempos limite estendidos (`timeout: 600000`, `headerTimeout: 600000`, `chunkTimeout: 900000`) em `opencode.json`.

---

## 📄 Licença

Distribuído sob a licença MIT. Consulte o arquivo `LICENSE` para mais informações.
