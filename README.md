# ARP 01 — Gestão de frotas logísticas

**Aluna:** Anny Gabrielly Gonçalves de Oliveira · **Matrícula:** 2310019 · **Instituição:** UniEVANGÉLICA · **Disciplina:** Arquiteturas de Sistemas Distribuídos

Projeto individual da ARP 01. **Entidade central:** solicitação de transporte de carga. Um cliente informa origem, destino e peso; o sistema registra a solicitação imediatamente, aloca um veículo de forma assíncrona e permite consultar o resultado. Documentação completa: [docs/documentacao-tecnica.md](docs/documentacao-tecnica.md) e [docs/Documentacao_Basica_ARP01_Gestao_de_Frotas.pdf](docs/Documentacao_Basica_ARP01_Gestao_de_Frotas.pdf).

## Começar em um comando

Instale **Node.js e Python 3.12**. Na pasta do projeto, rode:

```bash
npm run dev
```

Abra **http://localhost:8100**. A tela permite criar solicitações e acompanhar o resultado automaticamente. Não é necessário `npm install`, Docker, criar `.env` nem digitar uma chave: o comando gera o `.env` com uma chave aleatória na primeira execução, inicia os serviços e mantém os dados em `.local-data/`. Para encerrar, pressione `Ctrl+C`. No Windows, o comando usa `py -3` (Python Launcher); se necessário, defina a variável `PYTHON` apontando para sua instalação do Python.

> A API continua autenticada com `X-API-Key` (RF11). A tela obtém automaticamente a chave local de `/dev-config`, rota habilitada apenas em `npm run dev`. O `.env` é ignorado pelo Git; todos os serviços se vinculam a `127.0.0.1` nesse modo. Não exponha o modo de desenvolvimento na internet.

## Execução alternativa com Docker Compose

Pré-requisitos: Docker Engine com Compose. Se você já executou `npm run dev`, o `.env` estará pronto; encerre o modo local antes de iniciar o Compose. Na raiz deste projeto:

```bash
docker compose up --build -d
docker compose ps
```

A porta `8100` fica vinculada apenas a `127.0.0.1`. Os demais serviços, inclusive o broker experimental, só são acessíveis na rede interna do Compose. Aguarde alguns segundos até os serviços terminarem de iniciar. Nesta modalidade, a tela pedirá a chave gerada no `.env` ao criar solicitações. Se preferir usar Compose diretamente sem executar `npm run dev` antes, copie `.env.example` para `.env` e defina `API_KEY` manualmente.

```bash
curl -i http://localhost:8100/health
curl -i -X POST http://localhost:8100/requests \
  -H 'X-API-Key: SUA_CHAVE' -H 'Content-Type: application/json' \
  -d '{"origin":"Anapolis, GO","destination":"Goiania, GO","cargo_kg":480}'
curl -i http://localhost:8100/requests/COLE_O_REQUEST_ID \
  -H 'X-API-Key: SUA_CHAVE'
```

Resposta inicial: `202` e `CREATED`. Repita o GET após alguns segundos: `ASSIGNED` com `vehicle_id`, ou `REJECTED` se não houver veículo disponível. O cadastro inicial contém três veículos (`500`, `1500` e `5000` kg), cada um pode receber somente uma solicitação. Para redefinir os dados de demonstração, `docker compose down -v` remove os volumes **e todos os dados do projeto**.

Logs e evidências:

```bash
docker compose logs --tail=80 gateway requests broker dispatch-a dispatch-b fleet notifications
docker compose exec dispatch-a python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8104/peer-state').read().decode())"
docker compose exec dispatch-b python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8104/peer-state').read().decode())"
docker compose exec broker python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8101/dlq').read().decode())"
```

O script `python3 tests/smoke.py` sobe subprocessos locais isolados sem dependências externas, valida o ciclo completo e os endpoints e os encerra no final. Não rode o teste ao mesmo tempo que `npm run dev`, pois usam as mesmas portas. Veja também [docs/evidencias.md](docs/evidencias.md) para obter prints próprios e [docs/colecao-requisicoes.json](docs/colecao-requisicoes.json) para importar no Postman.

## Rotas públicas

| Método | Rota | Autenticação | Resultado |
|---|---|---|---|
| GET | `/health` | não | 200, saúde do gateway |
| GET | `/` | não | 200, interface web |
| POST | `/requests` | `X-API-Key` | 202, solicitação aceita; 400, dados inválidos; 401, sem chave; 503, dependência indisponível |
| GET | `/requests/{uuid}` | `X-API-Key` | 200, estado; 404, UUID inexistente; 401/503 |

Payload do POST: `{"origin":"Anapolis, GO","destination":"Goiania, GO","cargo_kg":480}`. `origin` e `destination` têm de 2 a 120 caracteres e devem ser distintos; `cargo_kg` é maior que 0 e até 10000. É possível enviar um UUID em `X-Correlation-ID`; na ausência dele, o serviço gera um. Rotas internas de diagnóstico (`/vehicles`, `/notifications/{uuid}`, `/peer-state`, `/dlq`) não são expostas pelo gateway e servem somente à demonstração na rede local.

Ao usar `npm run dev`, `GET /dev-config` fornece a chave local à interface. Essa rota não existe no Docker Compose.

## Limites da implementação didática

O broker foi implementado neste repositório com SQLite e assinaturas fixas para permitir executar e inspecionar o exercício sem bibliotecas extras. É um protótipo de middleware persistente, não substitui RabbitMQ/Kafka em produção. A API key é autenticação mínima; em produção seriam necessários TLS, autorização por usuário, métricas e um broker com alta disponibilidade. Consulte [docs/documentacao-tecnica.md](docs/documentacao-tecnica.md) para as limitações de entrega e de recuperação de falhas.
