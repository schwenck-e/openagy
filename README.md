# OpenAGY Bridge 🌉

Ponte local e multiplataforma de alta performance que conecta o **OpenCode** à sua sessão autenticada do **Google Antigravity (`agy`)**, permitindo utilizar as cotas e modelos avançados do Antigravity no OpenCode como se fosse um provedor padrão compatível com a API da OpenAI.

---

## 📑 Sumário

- [Arquitetura & Fluxo de Execução](#-arquitetura--fluxo-de-execução)
- [Segurança & Prevenção de Banimento](#-segurança--prevenção-de-banimento)
- [Compatibilidade Multiplataforma](#-compatibilidade-multiplataforma)
- [Modelos Disponíveis](#-modelos-disponíveis)
- [Pré-requisitos](#-pré-requisitos)
- [Guia Completo de Instalação e Inicialização](#-guia-completo-de-instalação-e-inicialização)
  - [Passo 0: Clonar o Repositório](#passo-0-clonar-o-repositório)
  - [🐧 Linux](#-linux)
  - [🪟 Windows (CMD & PowerShell)](#-windows)
  - [🍎 macOS](#-macos)
- [🛠️ Script de Configuração Manual (`setup_opencode.py`)](#️-script-de-configuração-manual-setup_opencodepy)
  - [Quando executar manualmente?](#quando-executar-manualmente)
  - [Comandos de execução avulsa](#comandos-de-execução-avulsa)
  - [Parâmetros suportados](#parâmetros-suportados)
- [Estrutura do Arquivo `opencode.json`](#-estrutura-do-arquivo-opencodejson)
- [Suporte a Chamadas de Ferramentas (Tool Calling)](#-suporte-a-chamadas-de-ferramentas-tool-calling)
- [Variáveis de Ambiente & Parâmetros da Ponte](#-variáveis-de-ambiente--parâmetros-da-ponte)
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
│  - Prompt Budgeting     │  - Proteção contra limites de buffer do SO
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

> **Nota Técnica para Windows:** A ponte conta com **Prompt Budgeting** inteligente e priorização de `agy.exe` nativo para contornar o limite de tamanho de linha de comando do Windows (`WinError 206`), garantindo que chats extensos e ferramentas não causem travamentos.

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

1. **Python 3.10 ou superior** instalado e adicionado ao PATH do sistema.
2. **Google Antigravity CLI (`agy`)** instalado e autenticado na máquina (`agy` funcional no terminal).
3. **OpenCode** instalado na máquina.

---

## 🚀 Guia Completo de Instalação e Inicialização

### Passo 0: Clonar o Repositório

Em qualquer sistema operacional, abra o terminal e clone o repositório:

```bash
git clone https://github.com/schwenck-e/openagy.git
cd openagy
```

---

### 🐧 Linux

#### 1. Instalar pacotes base (se necessário):
Em distribuições baseadas em Debian ou Ubuntu, certifique-se de que o pacote do ambiente virtual está instalado:
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip
```

#### 2. Executar a instalação automatizada:
```bash
chmod +x install.sh run.sh
./install.sh
```
*O script criará o ambiente virtual (`venv`), instalará as dependências (`fastapi`, `uvicorn`, `httpx`) e executará o `setup_opencode.py` automaticamente.*

#### 3. Iniciar a ponte:
```bash
./run.sh
```

---

### 🪟 Windows

Você pode utilizar tanto o **Prompt de Comando clássico (CMD)** quanto o **PowerShell**:

#### Opção A: Via Prompt de Comando (CMD)

1. **Instalação e configuração automatizada:**
```cmd
install.bat
```

2. **Iniciar a ponte:**
```cmd
run.bat
```

---

#### Opção B: Via PowerShell

1. **Permitir execução de scripts locais (se necessário):**
Caso o PowerShell bloqueie a execução de scripts `.ps1`, habilite para a sessão atual:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

2. **Instalação e configuração automatizada:**
```powershell
.\install.ps1
```

3. **Iniciar a ponte:**
```powershell
.\run.ps1
```

---

### 🍎 macOS

1. **Executar a instalação automatizada:**
```bash
chmod +x install.sh run.sh
./install.sh
```

2. **Iniciar a ponte:**
```bash
./run.sh
```

---

## 🛠️ Script de Configuração Manual (`setup_opencode.py`)

O repositório inclui o script utilitário independente [`setup_opencode.py`](setup_opencode.py). Ele é responsável por conectar a ponte ao OpenCode e configurar as permissões do Antigravity.

### Quando executar manualmente?

Você deve executar o `setup_opencode.py` manualmente se:
* **Você atualizou ou reinstalou o OpenCode** e as configurações do provedor foram sobrescritas.
* **Os modelos `openagy/...` não aparecem** no seletor de modelos do OpenCode após a instalação.
* **Você alterou a porta ou a chave da ponte** (por exemplo, iniciou a ponte na porta `9000` ou definiu uma chave customizada).
* **Você quer reconfigurar o OpenCode sem recriar o ambiente virtual** ou reinstalar pacotes.
* **O OpenCode está em um diretório não padrão** e você precisa passar `--config <caminho>`.
* **Ocorreu o erro de permissão headless do `jetski`**, para forçar a autorização de comandos em `~/.gemini/antigravity-cli/settings.json`.

---

### Comandos de execução avulsa

Certifique-se de estar na pasta do projeto e com o Python ativo:

#### No Linux / macOS:
```bash
# Executar com configurações padrão (porta 8080, chave openagy-key):
python3 setup_opencode.py

# Ou utilizando o Python do ambiente virtual criado:
venv/bin/python setup_opencode.py
```

#### No Windows (CMD):
```cmd
# Com Python no PATH:
python setup_opencode.py

# Ou utilizando o ambiente virtual:
venv\Scripts\python.exe setup_opencode.py
```

#### No Windows (PowerShell):
```powershell
# Com Python no PATH:
python setup_opencode.py

# Ou utilizando o ambiente virtual:
.\venv\Scripts\python.exe setup_opencode.py
```

---

### Parâmetros suportados

O script aceita parâmetros opcionais de linha de comando:

| Parâmetro | Padrão | Descrição | Exemplo de Uso |
| :--- | :--- | :--- | :--- |
| `--port` | `8080` | Porta TCP onde a ponte OpenAGY está escutando | `python setup_opencode.py --port 9000` |
| `--key` | `openagy-key` | Chave de API exigida para autorizar chamadas | `python setup_opencode.py --key minha-chave` |
| `--config` | *(Automático)* | Caminho explícito para o arquivo `opencode.json` | `python setup_opencode.py --config /path/to/opencode.json` |

---

## ⚙️ Estrutura do Arquivo `opencode.json`

O script [`setup_opencode.py`](setup_opencode.py) atualiza o arquivo `opencode.json` de forma segura:
* Cria um backup com carimbo de data/hora (`opencode.json.bak-<timestamp>`).
* Preserva o `$schema` oficial do OpenCode.
* Mantém intactos quaisquer servidores MCP (como `zrq-engine`) e outros provedores pré-existentes.
* Remove a chave raiz legada `model` se inválida, evitando erros de validação no OpenCode.

Formato registrado no provedor:

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
1. O OpenAGY formata as especificações das ferramentas nas instruções de sistema do modelo com JSON compacto.
2. O modelo emite blocos estruturados de chamada de função (`tool_call`).
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

## 🔧 Variáveis de Ambiente & Parâmetros da Ponte

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

---

## 🔍 Validação e Diagnóstico Local

### 1. Testar o Antigravity Local diretamente:
```bash
python3 test_local_agy.py
# No Windows:
python test_local_agy.py
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
* **Causa:** O arquivo `opencode.json` não foi atualizado ou o OpenCode estava aberto durante a instalação.
* **Solução:**
  1. Feche completamente o OpenCode.
  2. Execute o script de configuração avulso:
     * Linux/macOS: `python3 setup_opencode.py`
     * Windows: `python setup_opencode.py`
  3. Abra o OpenCode novamente. Os modelos aparecerão agrupados sob **OpenAGY**.

### 3. `[WinError 206] O nome do arquivo ou a extensão é muito grande` no Windows
* **Causa:** O Windows limita a linha de comando a 8.191 caracteres para `.cmd` e a 32.767 para `.exe`.
* **Solução:** A versão mais recente implementa **Prompt Budgeting** e priorização de `agy.exe`. Atualize o repositório com `git pull` e reinicie a ponte.

### 4. Erro de execução de script no PowerShell (`ExecutionPolicy`)
* **Causa:** Política de segurança padrão do Windows bloqueando scripts `.ps1`.
* **Solução:** Execute no PowerShell antes de rodar os scripts:
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  ```
  Ou utilize o script em lote clássico: `install.bat` e `run.bat`.

### 5. `Error: no output produced — a tool required the "command" permission`
* **Causa:** O `jetski` do Antigravity bloqueou a execução de uma ferramenta em modo headless.
* **Solução:** Execute `python setup_opencode.py` (ou `python3 setup_opencode.py`). Ele insere automaticamente as regras permissivas em `~/.gemini/antigravity-cli/settings.json`.

---

## 📄 Licença

Distribuído sob a licença MIT. Consulte o arquivo `LICENSE` para mais informações.
