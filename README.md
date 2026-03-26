# HWMONIT

HWMONIT é uma stack Docker para monitoramento de OLTs Huawei, responsável por coletar, processar e disponibilizar métricas operacionais por meio de API, facilitando integrações com plataformas como Zabbix e Grafana.

---

## Visão geral

O projeto foi criado para suprir informações de monitoramento que normalmente não estão disponíveis via SNMP de forma prática ou granular.

Com o HWMONIT, é possível centralizar a coleta dessas informações e disponibilizá-las de forma estruturada para consumo por sistemas externos.

---

## Funcionalidades

- Coleta de informações diretamente das OLTs Huawei
- Processamento e consolidação dos dados coletados
- Disponibilização dos dados via API HTTP
- Integração com Zabbix
- Suporte à visualização em Grafana
- Execução em containers Docker
- Organização da solução em serviços independentes

---

## Métricas disponíveis

Entre as métricas que podem ser coletadas e disponibilizadas, estão:

- Total de ONTs/ONUs por PON
- Total de ONTs/ONUs por SLOT
- ONTs/ONUs online por PON
- ONTs/ONUs online por SLOT
- ONTs/ONUs offline por PON
- ONTs/ONUs offline por SLOT
- ONTs/ONUs com LOS por PON
- ONTs/ONUs com LOS por SLOT
- Média de RX das ONTs/ONUs por PON
- Média de RX das ONTs/ONUs por SLOT

---

## Arquitetura

A stack é composta por múltiplos serviços, cada um com uma função específica:

- **collector**: realiza a coleta de dados nas OLTs Huawei
- **api**: disponibiliza os dados coletados via API
- **orchestrator**: realiza orquestrações auxiliares da stack
- **housekeeper**: executa rotinas de manutenção e limpeza
- **mysql**: armazena os dados processados

### Fluxo resumido

```text
OLT Huawei -> Collector -> MySQL -> API -> Zabbix / Grafana / outros consumidores
```

---

## Tecnologias utilizadas

- Python
- Docker
- Docker Compose
- MySQL
- API HTTP
- Integração com Zabbix

---

## Requisitos

Ambiente homologado:

- Ubuntu 24.04
- Docker Engine
- Docker Compose Plugin
- Git

---

## Instalação

### 1. Preparando o ambiente

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker $USER
newgrp docker
```

---

### 2. Clonando o projeto

```bash
git clone https://github.com/GlaucoRibeiro89/HWMONIT.git
cd HWMONIT
```

---

### 3. Ajustando o arquivo `.env`

Para o funcionamento básico da stack, as seções mais importantes são as do **collector** e do **Zabbix**.

Exemplo:

```env
########################################
# COLLECTOR
########################################
OLT_PORT=22
OLT_USER=SEU_USUARIO
OLT_PASS=SUA_SENHA

########################################
# ZABBIX
########################################
ZABBIX_URL=http://SEU-ZABBIX/zabbix/api_jsonrpc.php
ZABBIX_API_TOKEN=SEU_TOKEN
ZABBIX_OLT_GROUP_ID=SEU_ID_GRUPO
```

### Descrição das variáveis

#### Collector
- `OLT_PORT`: porta SSH utilizada pelas OLTs
- `OLT_USER`: usuário SSH das OLTs
- `OLT_PASS`: senha SSH das OLTs

#### Zabbix
- `ZABBIX_URL`: URL da API do Zabbix
- `ZABBIX_API_TOKEN`: token da API do Zabbix
- `ZABBIX_OLT_GROUP_ID`: ID do grupo onde estão cadastradas as OLTs que serão monitoradas

> Sugestão: crie um grupo específico no Zabbix, como `HWMONIT`, para facilitar a organização.

---

## Configuração no Zabbix

Para utilização com o Zabbix:

1. Crie ou defina um grupo para as OLTs que serão monitoradas
2. Identifique o ID desse grupo
3. Configure esse ID no arquivo `.env`
4. Importe e aplique os templates necessários

---

## Subindo a stack

```bash
docker compose build
docker compose up -d
```

Para verificar se os containers estão em execução:

```bash
docker ps
```

---

## Estrutura do projeto

```text
HWMONIT/
├── api/
├── collector/
├── docker/
├── housekeeper/
├── initdb/
├── orchestrator/
├── requirements/
├── .env
└── docker-compose.yml
```

---

## Exemplo de uso da API

Exemplo de consulta ao resumo de uma OLT:

```bash
curl "http://SEU_IP_OU_HOST:PORTA/api/v1/summary/olt?ip=192.168.255.255"
```

Exemplo de resposta:

```json
{
  "ip": "1192.168.255.255",
  "summary": {
    "ont_total": 864,
    "ont_online": 830,
    "ont_offline": 34,
    "ont_loss": 5,
    "avg_dbm": -20.14
  },
  "slots": [
    {
      "slot_path": "0/1",
      "frame": "0",
      "slot": "1",
      "ont_total": 548,
      "ont_online": 530,
      "ont_offline": 17,
      "ont_loss": 2,
      "avg_dbm": -18.33
    }
  ],
  "pons": [
    {
      "port": "0/1/0",
      "frame": "0",
      "slot": "1",
      "pon": "0",
      "ont_total": 32,
      "ont_online": 31,
      "ont_offline": 1,
      "ont_loss": 0,
      "avg_dbm": -19.10
    }
  ]
}
```


Exemplo de consulta de ONT:

```bash
curl "http://SEU_IP_OU_HOST:PORTA/api/v1/ont/by-serial?serial=48575443XXXXXXX&ip=192.168.255.255"
```

Exemplo de resposta:

```json
{
  "ip": "192.168.255.255",
  "serial": "48575443XXXXXXX",
  "port": "0/1/7",
  "status": 1,
  "status_text": "online",
  "last_down_cause": 5,
  "last_down_cause_text": "LOS",
  "rx_power_dbm": -19.42
}

Mapeamentos aplicados:

status
offline = 0
online = 1
outros = -1
last_down_cause
contém Dying = 0
contém LOS = 5
outros = -5

```
---

## Comandos úteis

### Visualizar logs

```bash
docker compose logs -f
```

Logs por serviço:

```bash
docker compose logs -f hwmonit_api
docker compose logs -f hwmonit_collector
docker compose logs -f hwmonit_housekeeper
docker compose logs -f hwmonit_orchestrator
```

### Verificar se o Docker inicia no boot

```bash
systemctl is-enabled docker
```

### Verificar uso de recursos dos containers

```bash
docker stats
```

### Listar containers em execução

```bash
docker ps
```

### Parar a stack

```bash
docker compose down
```

### Recriar a stack após alterações

```bash
docker compose up -d --build
```

---

## Possíveis aplicações

- Monitoramento avançado de OLTs Huawei
- Integração com Zabbix para discovery e triggers
- Alimentação de dashboards no Grafana
- Consolidação de métricas que não estão disponíveis via SNMP
- Apoio a troubleshooting operacional

---

## Observações

- O projeto foi homologado em Ubuntu 24.04
- O correto funcionamento depende do acesso da stack às OLTs e ao Zabbix
- Algumas métricas dependem diretamente do retorno dos dados coletados nos equipamentos

---

## Licença

Este projeto está licenciado sob a licença **MIT**.

Isso significa que ele pode ser utilizado, copiado, modificado e distribuído livremente, inclusive para fins comerciais, desde que o aviso de copyright e a licença sejam mantidos.