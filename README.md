# 📡 WP Infra | NOC — Network Operations Center Monitor

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688?style=flat-square&logo=fastapi&logoColor=white)
![WebSocket](https://img.shields.io/badge/WebSocket-Real--time-E6E6E6?style=flat-square)
![asyncio](https://img.shields.io/badge/asyncio-Concurrency-blue?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square)
![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=flat-square&logo=github-actions&logoColor=white)

> Sistema automatizado e concorrente desenvolvido em Python para monitorar a disponibilidade, latência e status de servidores distribuídos em múltiplas unidades físicas da **WP Infra**.

---

## 🎯 O Problema

Empresas com filiais distribuídas geograficamente sofrem com **pontos cegos na rede**. A queda de um link de internet ou a degradação de um servidor na filial muitas vezes só é percebida quando colaboradores já estão parados — gerando prejuízo operacional, chamados de suporte reativos e SLAs comprometidos.

## 💡 A Solução

Desenvolvemos um *probe* assíncrono que realiza verificações contínuas de **ICMP (ping)** e **TCP (porta)** em todas as filiais simultaneamente, registrando logs estruturados e alimentando um **dashboard centralizado em tempo real** via WebSocket.

O resultado é visibilidade operacional imediata: o time de TI identifica uma queda em segundos, antes que o usuário final perceba.

---

## 🖥️ Dashboard

> *Dark mode minimalista para operação 24/7 sem fadiga visual*

```
┌─────────────────────────────────────────────────────────────┐
│  WP INFRA  |  CENTRAL DE MONITORAMENTO — NOC   ● CONECTADO  │
│  6 TOTAL   6 ONLINE   0 OFFLINE   0 DEGRADADO   74 ms MÉD  │
├──────────────────┬──────────────────┬───────────────────────┤
│ SÃO PAULO — HQ   │ RIO DE JANEIRO   │ BELO HORIZONTE        │
│ Firewall         │ Servidor DNS     │ Gateway Core          │
│ 8.8.8.8          │ 1.1.1.1:53       │ 8.8.4.4               │
│ ● ONLINE  83ms   │ ● ONLINE  16ms   │ ● ONLINE  61ms        │
│ [sparkline ~~~]  │ [sparkline ~~~]  │ [sparkline ~~~]       │
│ 100%      agora  │ 100%      agora  │ 100%      agora       │
└──────────────────┴──────────────────┴───────────────────────┘
```

---

## 🛠️ Arquitetura e Stack Tecnológica

### Stack

| Camada | Tecnologia | Justificativa |
|---|---|---|
| **Backend** | Python 3.10+, FastAPI | ASGI nativo, suporte a WebSocket, tipagem forte |
| **Concorrência** | `asyncio` | I/O não-bloqueante: 100 alvos com custo de 1 thread |
| **Tempo real** | WebSocket (RFC 6455) | Push do servidor para o cliente sem polling |
| **Frontend** | HTML5 + CSS3 + JS ES6+ | Zero dependências, máxima portabilidade |
| **Servidor** | Uvicorn (ASGI) | Performance de produção com suporte a WebSocket |

### Modelo de Concorrência

```
MonitoringEngine
  ├── asyncio.Task → IcmpMonitor → host: 8.8.8.8    ┐
  ├── asyncio.Task → TcpMonitor  → host: 1.1.1.1:53  │ rodam em paralelo
  ├── asyncio.Task → IcmpMonitor → host: 8.8.4.4     │ no mesmo event loop
  ├── asyncio.Task → IcmpMonitor → host: 9.9.9.9     │ sem criar threads
  ├── asyncio.Task → TcpMonitor  → host: 208.67.x.x  │
  └── asyncio.Task → TcpMonitor  → host: 1.0.0.1:53  ┘
```

Cada alvo tem seu **loop persistente independente**. Um timeout em um alvo não bloqueia os demais.

---

## 📐 Arquitetura de Software — Clean Architecture

As dependências sempre apontam para dentro. A camada `core` não conhece FastAPI, nem repositórios, nem nada além de si mesma.

```
┌──────────────────────────────────────────────────────────┐
│  API  (FastAPI, WebSocket, Rotas HTTP)                   │
│  ↓ depende de                                            │
│  REPOSITÓRIOS  (StatusRepository, LogRepository)         │
│  ↓ depende de                                            │
│  SERVIÇOS  (IcmpMonitor, TcpMonitor, MonitoringEngine)   │
│  ↓ depende de                                            │
│  CORE  (Entities, Enums, Exceptions)                     │
│  ← zero dependências externas                            │
└──────────────────────────────────────────────────────────┘
```

---

## 📊 Estruturas de Dados e Complexidade (Big-O)

Uma das decisões mais importantes de qualquer sistema de monitoramento é **como armazenar e consultar estado**. Cada estrutura foi escolhida por sua complexidade de operações críticas.

| Estrutura | Onde é usada | Operação crítica | Big-O | Por que não lista? |
|---|---|---|---|---|
| `dict[str, MonitorResult]` | `StatusRepository` | `get(id)` / `update(id)` | **O(1)** | `list` exige scan O(n) por ID |
| `dict[str, MonitorTarget]` | `MonitoringEngine._targets` | `register` / `lookup` | **O(1)** | idem |
| `dict[str, asyncio.Task]` | `MonitoringEngine._tasks` | `cancel(id)` | **O(1)** | idem |
| `deque(maxlen=2000)` | `LogRepository` | `append` + evicção automática | **O(1)** | `list.pop(0)` desloca n elementos → O(n) |
| `set[WebSocket]` | `WebSocketManager` | `add` / `discard` | **O(1)** | `list` exige O(n) para checar duplicatas |

### Por que `deque` é crítico no LogRepository?

```python
# ❌ list — evicção manual é O(n)
log = []
log.append(result)
if len(log) > 2000:
    log.pop(0)          # desloca 2000 elementos na memória

# ✅ deque — evicção automática O(1)
from collections import deque
log = deque(maxlen=2000)
log.append(result)      # se cheio, remove o mais antigo em O(1)
```

---

## 🔷 Princípios SOLID Aplicados

| Princípio | Implementação no código |
|---|---|
| **S** — Responsabilidade Única | `IcmpMonitor` só executa ping. `TcpMonitor` só testa porta. `MonitoringEngine` só orquestra. Nenhum faz duas coisas. |
| **O** — Aberto/Fechado | Para adicionar um `HttpMonitor`, basta criar `class HttpMonitor(BaseMonitor)`. Nenhuma linha existente precisa mudar. |
| **L** — Substituição de Liskov | `IcmpMonitor` e `TcpMonitor` são permutáveis onde `BaseMonitor` é esperado — o `MonitoringEngine` não sabe qual é qual. |
| **I** — Segregação de Interface | `BaseMonitor` expõe apenas `check(target) → MonitorResult`. Nenhum monitor é forçado a implementar o que não usa. |
| **D** — Inversão de Dependência | `MonitoringEngine` depende de `BaseMonitor` (abstração). As implementações concretas são injetadas via `dict[MonitorType, BaseMonitor]`. |

---

## 🚀 Como Executar

### Pré-requisitos

- Python **3.10** ou superior
- pip

### 1. Clone o repositório

```bash
git clone https://github.com/wpinfra/wpinfra-noc-monitoramento.git
cd wpinfra-noc-monitoramento
```

### 2. Instale as dependências

```bash
# Produção
pip install -r requirements.txt

# Desenvolvimento + testes
pip install -r requirements.txt -r requirements-dev.txt
```

### 3. Configure os alvos

Edite `config.json` com os IPs reais das filiais:

```json
{
  "targets": [
    {
      "id":               "sp-fw-01",
      "name":             "Firewall Principal",
      "host":             "192.168.1.1",
      "branch":           "São Paulo — HQ",
      "monitor_type":     "ICMP",
      "interval_seconds": 30,
      "timeout_seconds":  5
    },
    {
      "id":               "rj-app-01",
      "name":             "Servidor de Aplicação",
      "host":             "192.168.2.10",
      "branch":           "Rio de Janeiro",
      "monitor_type":     "TCP",
      "port":             443,
      "interval_seconds": 30,
      "timeout_seconds":  5
    }
  ]
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | `string` | Identificador único do alvo |
| `name` | `string` | Nome legível exibido no dashboard |
| `host` | `string` | IP ou hostname |
| `branch` | `string` | Nome da filial |
| `monitor_type` | `"ICMP"` \| `"TCP"` | Tipo de sonda |
| `port` | `int` | Obrigatório para `monitor_type: "TCP"` |
| `interval_seconds` | `int` | Intervalo entre verificações (padrão: `30`) |
| `timeout_seconds` | `int` | Timeout da sonda (padrão: `5`) |

### 4. Execute

```bash
python main.py
```

Acesse **http://localhost:8000**

**Windows:** duplo clique em `run.bat`

---

## 🌐 API Reference

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/` | Dashboard HTML |
| `GET` | `/api/targets` | Lista todos os alvos configurados |
| `GET` | `/api/status` | Status atual + summary de todos os alvos |
| `GET` | `/api/logs?n=50` | Últimos N eventos do log circular |
| `GET` | `/api/history` | Histórico de latência por alvo (para sparklines) |
| `GET` | `/api/health` | Health check do servidor |
| `WS`  | `/ws` | Stream de eventos em tempo real |

### Payload WebSocket

```json
{
  "event": "monitor_result",
  "data": {
    "target_id":        "sp-fw-01",
    "status":           "ONLINE",
    "response_time_ms": 83.23,
    "timestamp":        "2024-01-15T14:16:05.123456",
    "error_message":    null
  }
}
```

### Status possíveis

| Status | Condição |
|---|---|
| `ONLINE` | Respondeu dentro do limiar de latência |
| `DEGRADED` | Respondeu, mas latência acima do limiar (ICMP: >200ms / TCP: >500ms) |
| `OFFLINE` | Sem resposta, timeout ou conexão recusada |
| `UNKNOWN` | Ainda não verificado desde o início do serviço |

---

## 📁 Estrutura do Projeto

```
wpinfra-noc-monitoramento/
├── .github/workflows/ci.yml    # Pipeline CI (lint + testes)
├── backend/
│   ├── core/                   # Entidades, enums e exceções (sem dependências)
│   ├── services/               # Monitors e engine de concorrência
│   ├── repositories/           # Armazenamento em memória
│   └── api/                    # Rotas HTTP, WebSocket
├── frontend/                   # Dashboard SPA (HTML + CSS + JS)
├── tests/
│   ├── unit/                   # Testes isolados por módulo
│   └── integration/            # Testes de API com cliente HTTP
├── docs/
│   ├── architecture.md         # Decisões arquiteturais (ADR)
│   └── api.md                  # Referência completa da API
├── config.json                 # Alvos de monitoramento
├── main.py                     # Entry point e composição de dependências
├── requirements.txt            # Dependências de produção
├── requirements-dev.txt        # Dependências de desenvolvimento
└── .env.example                # Template de variáveis de ambiente
```

---

## 🧪 Testes

```bash
# Rodar todos os testes
pytest tests/ -v

# Apenas unitários
pytest tests/unit/ -v

# Com cobertura
pytest tests/ --cov=backend --cov-report=term-missing
```

---

## 🗺️ Roadmap

- [x] Monitoramento ICMP (ping) multi-alvo com asyncio
- [x] Monitoramento TCP de porta
- [x] Dashboard em tempo real via WebSocket
- [x] Sparklines de latência com gradient fill (SVG puro)
- [x] Indicadores de uptime % e latência média
- [x] Toast notifications para incidentes
- [x] Log de eventos circular em memória
- [ ] Persistência em banco de dados (SQLite / PostgreSQL)
- [ ] Alertas por e-mail / webhook (Microsoft Teams, Slack)
- [ ] Autenticação no dashboard (JWT)
- [ ] Monitor HTTP com verificação de status code e tempo de resposta
- [ ] Exportação de relatórios em PDF
- [ ] Deploy com Docker + docker-compose

---

## 👤 Sobre o Projeto

Desenvolvido como **Projeto 1** do portfólio de soluções de infraestrutura inteligente da **WP Infra** — empresa especializada em infraestrutura de TI com unidades distribuídas pelo Brasil.

O projeto demonstra aplicação prática de princípios acadêmicos de Engenharia de Software (SOLID, Clean Architecture, análise de complexidade Big-O) em um contexto corporativo real.

---

## 📄 Licença

MIT — livre para uso, modificação e distribuição.
