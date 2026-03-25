# HWMONIT

HWMONIT é uma stack Docker para coleta, processamento e disponibilização de métricas de OLTs Huawei via API, facilitando integrações com plataformas de monitoramento como Zabbix e Grafana.

## Objetivo

Foi criado para gerar informacoes importantes para o monitoramento que nao existem dentro do monitoramento SNMP.

- ONT/ONU total por PON/SLOT
- ONT/ONU online por PON/SLOT
- ONT/ONU offline por PON/SLOT
- ONT/ONU LOS por PON/SLOT
- ONT/ONU RX AVG por PON/SLOT

## Tecnologias utilizadas

- Python


## Instalacao
### Configuração do ambiente
- Homolago em Ubuntu 24

```bash

sudo apt-get update
sudo apt-get install -y ca-certificates curl

sudo apt-get install git

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

### Baixando projeto
```bash

git clone https://github.com/GlaucoRibeiro89/HWMONIT.git

```

### Ajustando .env

- Para o stack funcionar a unica sessao necessaria e a do Zabbix e a collector.

```bash
########################################
# COLLECTOR
########################################
OLT_PORT=22 - porta ssh das suas olts
OLT_USER=SEU-USUARIO - usuario ssh das suas olts
OLT_PASS=SUA-SENHA - senha ssh das suas olts


########################################
# ZABBIX
########################################
ZABBIX_URL=http://SEU-ZABBIX/zabbix/api_jsonrpc.php
ZABBIX_API_TOKEN=SEU-TOKEN - gerado em user/api tokens
ZABBIX_OLT_GROUP_ID=SEU-ID-GRUPO - o ideal é criar um grupo com nome relevante, HWMONIT por exemplo, ao cria-lo capture o id utilizando o html inspect do navegador.
```

### Zabbix
- Aplicar o grupo que será utilizado para busca da olt que deve ser monitorada, pegar o id e aplicar no env
- Aplicar os templates

### Startando o Stack Docker
cd HWMONIT
docker compose build
docker compose up -d

## Estrutura do projeto

```bash
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

## Extras

### LOG's
```bash
docker compose logs -f

docker compose logs -f hwmonit_api
docker compose logs -f hwmonit_collector
docker compose logs -f hwmonit_housekeeper
docker compose logs -f hwmonit_orchestrator

```

### Verificar se o Docker servico docker no boot
```bash
systemctl is-enabled docker
```

### Verificar uso docker
```bash
docker stats
```

### Verificar containers
```bash
docker ps
```