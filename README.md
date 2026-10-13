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
| **Linux** | Bash, Zsh, Sh | Pseudo-terminal (PTY) de baixa latência | `~/.local/bin`, `/usr/local/bin`, `/usr/bin`, `PATH` | `$XDG_CONFIG_HOME/opencode/` ou `~/.config/opencode/` |
| **Windows** | CMD, PowerShell | Pipes assíncronos (`asyncio.subprocess.PIPE`) | `agy.exe`, `agy.cmd`, `%LOCALAPPDATA%`, `%USERPROFILE%\.local\bin` | `%APPDATA%\opencode\` ou `%USERPROFILE%\.config\opencode\` |
| **macOS** | Zsh, Bash | Pseudo-terminal (PTY) de baixa latência | `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin` | `~/.config/opencode/` |

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

```bash
# 1. Clone o repositório
git clone https://github.com/schwenck-e/openagy.git
cd openagy

# 2. Execute a instalação automática
chmod +x install.sh run.sh
./install.sh

# 3. Inicie o servidor da ponte
./run.sh
```

---

### 🪟 Windows

Você pode usar o **Prompt de Comando (CMD)** ou o **PowerShell**:

#### Opção A: Prompt de Comando (CMD)
```cmd
git clone https://github.com/schwenck-e/openagy.git
cd openagy
install.bat
run.bat
```

#### Opção B: PowerShell
```powershell
git clone https://github.com/schwenck-e/openagy.git
cd openagy
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
.\run.ps1
```

> **Dica Windows:** Caso prefira configurar o OpenCode manualmente sem reinstalar dependências, execute a qualquer momento:
> ```cmd
> python setup_opencode.py
> ```

---

### 🍎 macOS

```bash
git clone https://github.com/schwenck-e/openagy.git
cd openagy
chmod +x install.sh run.sh
./install.sh
./run.sh
```

---

## ⚙️ Estrutura de Configuração no OpenCode

O script de instalação e o utilitário `setup_opencode.py` atualizam automaticamente seu `opencode.json` (preservando comentários, schemas e servidores MCP existentes, como `zrq-engine`). 

Caso queira inspecionar ou configurar manualmente, o bloco registrado é:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "openagy": {
      "name": "OpenAGY",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://127.0.0.1:8080/v1",
        "apiKey": "openagy-key",
        "timeout": 600000,
        "headerTimeout": 600000,
        "chunkTimeout": 900000
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

O OpenAGY traduz as definições de ferramentas padrão enviadas pelo OpenCode no protocolo OpenAI para as instruções nativas compreendidas pelo Antigravity:

1. **Injeção de Esquema:** Ferramentas passadas em `tools` são injetadas nas instruções de sistema do modelo.
2. **Reconhecimento de Bloco:** Quando o modelo decide invocar uma ferramenta, ele emite um bloco estruturado ````tool_call { ... } ````.
3. **Tradução OpenAI:** A ponte intercepta a resposta, monta o objeto `tool_calls` padrão da OpenAI com `call_id` e dispara o evento com `finish_reason: "tool_calls"`.
4. **Alimentação de Resultados:** As respostas retornadas pelo OpenCode sob a role `tool` são reintroduzidas no contexto da conversa em turnos subsequentes.

---

## 🔧 Variáveis de Ambiente & Parâmetros de Inicialização

A ponte pode ser customizada através de variáveis de ambiente no arquivo `.env` ou passadas no shell:

| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `OPENAGY_HOST` | `127.0.0.1` | Endereço IP em que a ponte escuta requisições. |
| `OPENAGY_PORT` | `8080` | Porta local da API OpenAI-compatível. |
| `OPENAGY_API_KEY` | `openagy-key` | Chave de API exigida para autorização das requisições. |
| `OPENAGY_REQUIRE_KEY` | `false` | Se `true`, valida estritamente o Bearer Token. Se `false`, aceita requisições locais. |
| `OPENAGY_AGY_BIN` | *(auto-detectado)* | Caminho explícito para o executável `agy` ou `agy.exe`. |
| `OPENAGY_LOG_LEVEL` | `INFO` | Nível de verbosidade do log (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## 🔍 Validação e Diagnóstico Local

Após iniciar a ponte, você pode testar a integridade dos serviços pelo terminal:

### 1. Teste de Conexão Rápida:
```bash
curl http://127.0.0.1:8080/
```

### 2. Resposta esperada:
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
  1. No Windows e em pipes assíncronos, o Antigravity direciona logs e diagnósticos para `stderr`. Se o canal de `stderr` não for drenado em paralelo com o `stdout`, o buffer de pipe do Windows (4 KB) satura, travando o processo em deadlock.
  2. O cliente do OpenCode (`@ai-sdk/openai-compatible`) espera os primeiros dados de resposta (SSE) rapidamente. Caso o modelo demore para aquecer ou realize raciocínio profundo, o cliente encerra a conexão por inatividade.
* **Solução:**
  1. O OpenAGY drena o `stderr` de forma concorrente em uma tarefa assíncrona dedicada, eliminando qualquer risco de deadlock de buffer de pipe.
  2. A ponte emite imediatamente um chunk inicial de handshake (`role: "assistant"`) em < 5 ms, reiniciando o relógio de timeout do cliente.
  3. Durante raciocínio profundo ou pausas na geração, a ponte emite pings periódicos (`: ping\n\n`) via Server-Sent Events para manter os sockets HTTP e conexões Node/Undici ativas.
  4. O script `setup_opencode.py` configura automaticamente tempos limite estendidos (`timeout`, `headerTimeout`, `chunkTimeout`) no `opencode.json`.

---

## 📄 Licença

Distribuído sob a licença MIT. Consulte o arquivo `LICENSE` para mais informações.
