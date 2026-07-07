# ⚖️ RPA Core — Captura Genérica de Intimações Judiciais

**Sistema RPA multi-tenant, 100% configurável, para captura e classificação de intimações em portais da justiça.**

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Pydantic](https://img.shields.io/badge/pydantic-v2-ff69b4)](https://docs.pydantic.dev/latest/)
[![Selenium](https://img.shields.io/badge/selenium-4.15%2B-green)](https://www.selenium.dev/)
[![LangChain](https://img.shields.io/badge/langchain-0.1%2B-orange)](https://www.langchain.com/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

---

## 📖 Índice

- [Visão Geral](#-visão-geral)
- [Arquitetura](#-arquitetura)
- [Fluxo de Execução](#-fluxo-de-execução)
- [Estrutura de Pastas](#-estrutura-de-pastas)
- [Stack Tecnológica](#-stack-tecnológica)
- [Instalação](#-instalação)
- [Configuração](#-configuração)
- [Uso](#-uso)
- [Criando um Novo Plugin](#-criando-um-novo-plugin)
- [Classificação (De-Para)](#-classificação-de-para)
- [Segurança](#-segurança)
- [Docker](#-docker)
- [Testes](#-testes)
- [Logs & Debug](#-logs--debug)
- [Roadmap](#-roadmap)

---

## 🎯 Visão Geral

O **RPA Core** automatiza o processo de consulta de intimações judiciais em múltiplos portais (PJE, E-SAJ, Tucujuris, Diários Oficiais, etc.), para múltiplos escritórios de advocacia simultaneamente, com **zero código específico por cliente**.

### Princípios Fundamentais

| Princípio | Descrição |
|---|---|
| **100% Genérico** | Nenhum nome de cliente, escritório ou portal está hardcoded |
| **Multi-Tenant** | Um único código-base atende N clientes (`--client-id`) |
| **Config-Driven** | Comportamento definido em JSON externo |
| **Headless** | Roda em terminal/serviço, sem interface gráfica |
| **IA como Aprimoramento** | LLM é opcional — se falhar, fallback para classificação manual |
| **Resiliente** | Erro em um portal não derruba a execução inteira |

### Saída

Uma **planilha Excel unificada** (`data/output/<client_id>/intimacoes_YYYY-MM-DD.xlsx`) com 19 colunas padronizadas, enviada por e-mail ao final da execução.

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI (main.py)                          │
│              argparse: --client-id, --no-headless           │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   RPAOrchestrator                            │
│   Pipeline: config → plugins → classify → Excel → email     │
└──────┬──────────┬──────────┬──────────────┬─────────────────┘
       │          │          │              │
┌──────▼──┐ ┌─────▼───┐ ┌───▼──────┐ ┌─────▼──────┐
│ Config  │ │ Plugins │ │Classifier│ │ ExcelWriter │
│ Manager │ │(Adapters│ │(Hybrid)  │ │ (Pandas)    │
│ (JSON)  │ │ Selenium│ │Regex→LLM │ │             │
└─────────┘ └─────────┘ └──────────┘ └─────────────┘
```

### Padrão Hexagonal (Ports & Adapters)

```
┌──────────────────────────────────────┐
│           DOMAIN (models.py)         │
│  Advogado, ClienteConfig,            │
│  IntimacaoRecord, PortalType         │
└────────────────┬─────────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼────┐ ┌─────▼────┐ ┌────▼─────┐
│ PORT   │ │  PORT    │ │  PORT    │
│Portal  │ │Classifier│ │Output    │
│Plugin  │ │          │ │Writer    │
│(ABC)   │ │(ABC)     │ │(ABC)     │
└───┬────┘ └─────┬────┘ └────┬─────┘
    │            │            │
┌───▼────────┐ ┌─▼──────────┐ ┌▼──────────┐
│ ADAPTERS   │ │ ADAPTERS   │ │ ADAPTERS  │
│ Portal A   │ │ Hybrid     │ │ Excel     │
│ Portal B   │ │ Classifier │ │ Writer    │
│ Portal C   │ │ (Regex+LLM)│ │ (Pandas)  │
│ (Selenium) │ │            │ │           │
└────────────┘ └────────────┘ └───────────┘
```

---

## 🔄 Fluxo de Execução

Cada execução do RPA segue esta pipeline:

```
1. INIT        main.py carrega --client-id e o JSON correspondente
       │
2. CONFIG      ClienteConfig.load() → cache em memória
       │
3. ORCHESTRATE Para cada Advogado × Portal ativo:
       │
       ├─ 3a. AUTH       authenticate() → login, 2FA, certificado
       ├─ 3b. FETCH      fetch_intimations() → lista de dicts brutos
       ├─ 3c. PROCESS    process_intimation() → IntimacaoRecord
       └─ 3d. ACTION     take_action() → Tomar Ciência / Ignorar
       │
4. CLASSIFY    HybridClassifier em todos os registros (concorrente)
       │         Regex (keyword match) → LLM (DeepSeek/GPT) → MANUAL
       │
5. WRITE       ExcelWriter → data/output/<client_id>/intimacoes_<data>.xlsx
       │
6. NOTIFY      SMTP → anexa planilha e envia para emails_destino
```

---

## 📁 Estrutura de Pastas

```
rpa_core/
├── src/
│   ├── main.py                      # Entrypoint CLI
│   ├── orchestrator.py              # Pipeline principal
│   ├── config_manager.py            # Carregador de JSONs (com cache)
│   ├── models.py                    # Pydantic v2: todos os modelos
│   │
│   ├── interfaces/                  # 🔌 Ports (contratos abstratos)
│   │   ├── portal_plugin.py         #   ABC para plugins de portal
│   │   ├── classifier.py            #   ABC para classificadores
│   │   └── output_writer.py         #   ABC para persistência
│   │
│   ├── plugins/                     # 🔧 Adapters (implementações)
│   │   ├── base_selenium_plugin.py  #   Helpers: waits, retry, screenshots
│   │   ├── portal_a_plugin.py       #   Demo: Books to Scrape
│   │   ├── portal_b_plugin.py       #   Template: PJE/CNJ (certificado)
│   │   └── portal_c_pdf_plugin.py   #   Template: DJE (PDF)
│   │
│   ├── services/                    # 🧠 Lógica de negócio
│   │   ├── classifier_service.py    #   Hybrid: Regex → LLM → Manual
│   │   ├── llm_client.py            #   LangChain (DeepSeek/OpenAI/Azure)
│   │   └── excel_writer.py          #   Pandas + openpyxl formatado
│   │
│   ├── security/                    # 🔐 Credenciais
│   │   ├── credential_vault.py      #   Keyring → .env fallback
│   │   └── certificate_handler.py   #   Certificados .pfx/A3
│   │
│   ├── utils/                       # 🛠️ Utilitários
│   │   ├── logger.py                #   JSON lines + rotação diária
│   │   ├── pdf_parser.py            #   pdfplumber + PyPDF2
│   │   └── email_2fa_handler.py     #   IMAP polling para 2FA
│   │
│   └── configs/                     # ⚙️ Configs dos clientes
│       └── cliente_exemplo.json     #   Template 100% genérico
│
├── tests/
│   ├── test_models.py               # 14 testes de validação Pydantic
│   └── test_classifier.py           # 11 testes do classificador híbrido
│
├── data/
│   ├── output/                      # Planilhas geradas
│   └── logs/                        # Logs JSON + screenshots de erro
│
├── certs/                           # Certificados digitais (.pfx)
├── requirements.txt                 # Dependências com versões fixas
├── docker-compose.yml               # Selenium Grid 4 + App
├── Dockerfile                       # Python 3.12-slim
├── pyproject.toml                   # Config pytest
├── .env                             # Variáveis de ambiente (template)
└── .gitignore
```

---

## 🧰 Stack Tecnológica

| Camada | Tecnologia | Versão |
|---|---|---|
| **Linguagem** | Python | 3.10+ |
| **Modelos** | Pydantic | 2.5+ |
| **Web Scraping** | Selenium + WebDriverWait | 4.15+ |
| **IA / LLM** | LangChain + ChatOpenAI | 0.1+ |
| **Excel** | Pandas + OpenPyXL | 2.1+ / 3.1+ |
| **PDF** | pdfplumber → PyPDF2 fallback | 0.10+ / 3.0+ |
| **Credenciais** | keyring → python-dotenv | 24+ / 1.0+ |
| **Resiliência** | tenacity (exponential backoff) | 8.2+ |
| **Testes** | pytest + pytest-asyncio | 8.0+ |
| **Container** | Docker + Selenium Grid 4 | — |

---

## 🚀 Instalação

```bash
# 1. Clone o repositório
git clone <repo-url>
cd bot-advocacia

# 2. Crie o ambiente virtual
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure o .env
cp .env .env.local
# Edite .env.local com suas chaves (DeepSeek, email, etc.)
```

---

## ⚙️ Configuração

### 1. Variáveis de Ambiente (`.env`)

```bash
# LLM — DeepSeek (recomendado, mais barato e melhor em português)
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.0

# Email — senha de app para IMAP (captura 2FA) e SMTP (envio de relatórios)
EMAIL_APP_PASSWORD=your-app-password

# Vault fallback — senhas quando keyring não está disponível
SENHA_PORTAL_A=sua-senha
CERT_PASSWORD_MARIA=sua-senha-certificado
SMTP_APP_PASSWORD=sua-senha-smtp
```

### 2. Configuração do Cliente (`src/configs/cliente_exemplo.json`)

```jsonc
{
  "client_id": "meu_escritorio",        // identificador único
  "nome_escritorio": "Meu Escritório",
  "use_ai_classifier": true,             // habilitar IA para classificação

  "advogados": [
    {
      "nome": "Dr. Silva",
      "usuario": "dr.silva",             // null se usa certificado
      "senha_ref": "VAULT:SENHA_PORTAL", // referência para o CredentialVault
      "certificado_path": null,          // ou "certs/dr-silva.pfx"
      "email_2fa": "dr.silva@email.com"  // null se portal não pede 2FA
    }
  ],

  "portais_ativos": ["portal_a", "portal_b"],

  "emails_destino": ["relatorios@escritorio.com"],

  // Regras de classificação: palavra-chave → categoria
  "classification_rules": {
    "execução": "Execução",
    "tutela": "Tutela Antecipada",
    "recurso": "Recurso",
    "embargos": "Embargos",
    "sentença": "Sentença"
    // ... adicione quantas quiser
  }
}
```

### 3. Prioridade de Credenciais

```
1. Windows Credential Manager  (keyring → target="rpa_core", username=<senha_ref>)
2. Variáveis de Ambiente       (.env → <senha_ref>)
3. Erro                        (KeyError — execução interrompida)
```

---

## 🖥️ Uso

```bash
# Ativar ambiente virtual
source venv/bin/activate

# Execução headless (padrão)
python -m src.main --client-id cliente_exemplo

# Com navegador visível (debug)
python -m src.main --client-id cliente_exemplo --no-headless

# Usando Selenium Grid remoto
python -m src.main --client-id cliente_exemplo --remote-selenium http://localhost:4444

# Listar clientes disponíveis
python -m src.main --list-clients

# Via variável de ambiente
CLIENT_ID=cliente_exemplo python -m src.main
```

### Saída esperada

```
20:06:19 | INFO | main | RPA Core starting — client=cliente_exemplo
20:06:20 | INFO | orchestrator | Pipeline started | lawyers=1 | portals=1
20:06:21 | INFO | orchestrator | → João Silva | portal_a | authenticating …
20:06:22 | INFO | portal_a | ✅ Books to Scrape carregado com sucesso.
20:06:22 | INFO | portal_a | 📚 Extraídos 20 livros da página.
20:06:22 | INFO | orchestrator | → João Silva | portal_a | fetched 20 raw records
20:06:23 | INFO | orchestrator | Pipeline finished | records=20 | elapsed=2.1s
20:06:23 | INFO | main | ✓ Done — data/output/cliente_exemplo/intimacoes_2026-07-06.xlsx
```

---

## 🔌 Criando um Novo Plugin

Para adicionar um novo portal (ex: E-SAJ, Projudi, etc.):

### Passo 1 — Criar a classe

```python
# src/plugins/portal_esaj_plugin.py
from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType

class ESAJPlugin(PortalPlugin):

    @property
    def portal_type(self) -> PortalType:
        return PortalType.PORTAL_EXTRA   # ou adicione um novo no enum

    @property
    def portal_name(self) -> str:
        return "E-SAJ"

    def __init__(self, headless: bool = True, remote_url: str | None = None):
        self.headless = headless
        self.remote_url = remote_url
        # ...

    async def authenticate(self, advogado, config) -> bool:
        # Login no E-SAJ
        ...

    async def fetch_intimations(self, advogado, data_ref) -> list[dict]:
        # Extrair intimações
        ...

    async def process_intimation(self, raw, advogado) -> IntimacaoRecord:
        # Mapear para o modelo canônico
        ...

    async def take_action(self, record, advogado) -> None:
        # Clicar em "Tomar Ciência"
        ...

    async def cleanup(self) -> None:
        # Fechar driver
        ...
```

### Passo 2 — Registrar no orquestrador

```python
# src/orchestrator.py — adicione ao PLUGIN_REGISTRY
PLUGIN_REGISTRY[PortalType.PORTAL_EXTRA] = "src.plugins.portal_esaj_plugin.ESAJPlugin"
```

### Passo 3 — Ativar na config do cliente

```json
{
  "portais_ativos": ["portal_a", "portal_b", "portal_extra"]
}
```

### Regras para plugins

| Regra | Detalhe |
|---|---|
| **Waits explícitos** | `WebDriverWait` com timeout 30s. **Nunca** `time.sleep()` |
| **Selectors robustos** | Prefira `By.XPATH` ou `By.CSS_SELECTOR` |
| **Headless** | Use `self.headless` — nunca hardcode |
| **2FA** | Use `Email2FAHandler.wait_for_code()` |
| **Erro → screenshot** | `base_selenium_plugin` já salva em `data/logs/` |
| **Retry** | Use o decorator `@retry_on_transient` do `base_selenium_plugin` |

---

## 🧠 Classificação (De-Para)

O `HybridClassifier` opera em 3 estágios:

```
1. REGEX (custo zero)
   ├─ Itera as classification_rules do JSON
   ├─ keyword in texto.lower() → match exato
   └─ Confiança: 1.0

2. LLM (opcional, se use_ai_classifier=true)
   ├─ Envia prompt com lista de categorias
   ├─ Valida que resposta é uma categoria conhecida
   └─ Confiança: ai_fallback_threshold (default 0.8)

3. FALLBACK
   └─ Retorna "CLASSIFICACAO_MANUAL" / 0.0
      O analista revisa depois na planilha
```

### Provedores LLM suportados

| Prioridade | Provedor | Variável |
|---|---|---|
| 1 | **DeepSeek** | `LLM_API_KEY` |
| 2 | Azure OpenAI | `AZURE_OPENAI_API_KEY` |
| 3 | OpenAI | `OPENAI_API_KEY` |

Se nenhuma chave for configurada → classificação somente por regex (sem IA).

---

## 🔐 Segurança

### Credential Vault

```
┌──────────────────────────────┐
│ 1. Windows Credential Manager │  ← keyring (produção)
│    target: "rpa_core"         │
│    username: <senha_ref>      │
├──────────────────────────────┤
│ 2. Environment Variables      │  ← .env (dev/fallback)
│    <senha_ref>=<valor>        │
├──────────────────────────────┤
│ 3. KeyError                   │  ← execução interrompida
└──────────────────────────────┘
```

### Certificados Digitais

```python
from src.security.certificate_handler import CertificateHandler

cert = CertificateHandler.load(
    "certs/advogado.pfx",
    password_ref="VAULT:CERT_PASSWORD"
)

# Para Selenium: configure o perfil Chrome com o certificado
# Para requests: cert.create_ssl_context()
# Para extrair PEM: cert.extract_to_pem()
```

---

## 🐳 Docker

### Subir Selenium Grid + Rodar RPA

```bash
# 1. Iniciar o Grid
docker compose up -d selenium-hub chrome-node

# 2. Rodar o RPA (one-shot)
docker compose run --rm rpa --client-id cliente_exemplo

# 3. Ou tudo junto
CLIENT_ID=cliente_exemplo docker compose up

# 4. Parar tudo
docker compose down
```

### Serviços no `docker-compose.yml`

| Serviço | Porta | Descrição |
|---|---|---|
| `selenium-hub` | 4444 | Selenium Grid Hub |
| `chrome-node` | 5900 | Chrome + VNC (debug visual) |
| `rpa` | — | App Python (executa e sai) |

---

## 🧪 Testes

```bash
# Todos os testes
pytest

# Apenas modelos
pytest tests/test_models.py -v

# Apenas classificador
pytest tests/test_classifier.py -v

# Com coverage
pytest --cov=src --cov-report=term-missing
```

### Cobertura atual

| Arquivo | Testes |
|---|---|
| `test_models.py` | 14 testes — validação Pydantic, bounds, load/cache, enums |
| `test_classifier.py` | 11 testes — regex, LLM fallback, AI disabled, mock |

### Teste rápido de conectividade LLM

```bash
python test_deepseek.py
# ✅ Conexão bem-sucedida! Resposta: OK
```

---

## 📊 Logs & Debug

### Formato

Logs usam **JSON lines** para ingestão em ELK / Splunk / Datadog:

```json
{"ts": "2026-07-06T20:06:19.123Z", "level": "INFO", "logger": "orchestrator",
 "msg": "Pipeline finished | records=20 | elapsed=2.1s | output=data/output/..."}
```

### Localização

| Artefato | Caminho |
|---|---|
| Logs diários | `data/logs/execution_YYYY-MM-DD.log` |
| Screenshots de erro | `data/logs/screenshot_error_YYYYMMDD_HHMMSS.png` |
| Planilhas | `data/output/<client_id>/intimacoes_YYYY-MM-DD.xlsx` |

### Rotação

- **Tamanho máximo:** 10 MiB por arquivo
- **Backups:** 30 arquivos mantidos
- **Console:** nível INFO (stderr, formato legível)
- **Arquivo:** nível DEBUG (JSON)

---

## 🗺️ Roadmap

- [ ] Plugin E-SAJ (São Paulo)
- [ ] Plugin Projudi (Paraná)
- [ ] Plugin Tucujuris (Amapá)
- [ ] Plugin DJE Nacional (CNJ)
- [ ] Suporte a captcha via 2Captcha/AntiCaptcha
- [ ] Agendamento via Cron / APScheduler
- [ ] Dashboard web para revisão de classificações manuais
- [ ] Integração com Slack/Teams para notificações
- [ ] Export CSV e PDF além do Excel
- [ ] Modo replay (reprocessar screenshots/logs offline)

---

## 📄 Licença

MIT — veja o arquivo [LICENSE](LICENSE) (se disponível).

---

**Feito com ☕ e Python. 100% genérico, 0% hardcoded.**
