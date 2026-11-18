# Sistema de Auditoria Fiscal OCR (`DocAudit-OCR`)

API local-first para receber cupons fiscais, recibos e notas em imagem ou PDF, executar OCR em português (Tesseract + OpenCV) e auditar os dados extraídos. Este repositório contém a implementação descrita em [DocAudit-OCR Documento de Requisitos e Especificações.pdf](./DocAudit-OCR%20Documento%20de%20Requisitos%20e%20Especifica%C3%A7%C3%B5es.pdf) (ver também [PENDENCIAS.md](PENDENCIAS.md)).

## Situação da implementação

| Área | Situação |
|---|---|
| API REST, chave de API e OpenAPI | Implementados |
| Upload JPG, PNG e PDF, limite de tamanho, assinatura e duplicidade | Implementados |
| Fila Celery/Redis, worker, estados, retentativas e persistência | Implementados |
| PostgreSQL, modelos e migração Alembic | Implementados |
| Renderização PDF a 300 DPI | Implementada |
| Pré-processamento, OCR, QR Code e extração inicial | Implementados |
| Validação fiscal, auditoria aritmética e encaminhamento para revisão | Implementados |
| Correção manual com histórico, exportação e exclusão | Implementadas |
| Métricas, logs estruturados e rotina de retenção | Implementados em sua forma inicial |
| Testes automatizados | Testes unitários e de integração local; o CI também valida o pipeline com Redis, PostgreSQL e Tesseract reais |
| Dataset de desenvolvimento | 50 recibos sintéticos gerados e versionados, incluindo casos de revisão; não substituem documentos reais anonimizados |
| Metas reais de acurácia OCR | Pendentes: precisam ser medidas também em amostra representativa de documentos reais anonimizados |
| Execução integral dos containers e validação com Tesseract real | Validada localmente com PostgreSQL, Redis e Tesseract; também automatizada no CI |
| Teste de carga e medição de desempenho no hardware-alvo | 100 documentos sintéticos medidos localmente; o resultado no host de referência de 4 vCPU ainda está pendente |
| CI para testes, Ruff, mypy, integração Compose e relatórios OCR sintéticos | Implementada configuração em GitHub Actions |

O projeto está em estágio de MVP inicial. Os testes automatizados verificam componentes e fluxos controlados; eles não substituem a avaliação do OCR com um conjunto representativo de documentos reais anonimizados.

## O que está implementado

### Fluxo de processamento

1. A API recebe o arquivo, aplica o limite de tamanho e valida a assinatura binária. A extensão e o `Content-Type` enviados pelo cliente não são tratados como prova do formato.
2. O sistema calcula o SHA-256, rejeita duplicidade e armazena o arquivo usando um UUID, sem confiar no nome recebido.
3. O endpoint responde `202 Accepted` com `document_id` e estado `PENDING`, e envia o trabalho para Celery por Redis.
4. O worker converte cada página de PDF em imagem a 300 DPI, aplica escala de cinza, ampliação, redução de ruído, limiarização adaptativa e correção de inclinação.
5. Tesseract em português extrai o texto e confiança por linha; OpenCV tenta decodificar o QR Code. Uma chave de acesso encontrada no QR prevalece sobre a chave detectada pelo OCR.
6. Parsers extraem CNPJ, CPF, data, total, chave de acesso e itens. Validadores conferem dígitos verificadores, intervalo de data e valores monetários em `Decimal`.
7. A auditoria compara a soma dos itens ao total, registra inconsistências e encaminha campos ausentes, inválidos ou com confiança baixa para `NEEDS_REVIEW`.
8. Extração, itens, auditoria e documento são persistidos no banco.

O processamento de PDFs é consolidado em um registro de documento e uma extração. O limite padrão é 20 páginas por PDF.

### API

As rotas de documentos requerem o cabeçalho `X-API-Key`. `/health` e `/metrics` são endpoints operacionais públicos. A documentação interativa e o esquema OpenAPI ficam em `/docs` e `/openapi.json`.

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/v1/documents` | Recebe JPG, PNG ou PDF; responde `202` com `document_id` e estado. |
| `GET` | `/api/v1/documents/{id}` | Consulta estado, extração, itens, confiança, correções e auditoria. |
| `GET` | `/api/v1/documents` | Lista com filtros `status`, `cnpj`, `created_from`, `created_to`, `limit` e `offset`. O CNPJ é mascarado na listagem. |
| `PATCH` | `/api/v1/documents/{id}/fields` | Corrige `cnpj`, `cpf`, `issue_datetime`, `total_amount` ou `access_key` e guarda o valor anterior e a data da correção. |
| `GET` | `/api/v1/documents/export?format=json` | Exporta os resultados em JSON; use `format=csv` para CSV. |
| `DELETE` | `/api/v1/documents/{id}` | Exclui o registro e seus dados dependentes, o arquivo e, se presente, o processamento salvo. Responde `204`. |
| `GET` | `/health` | Verificação simples da API. |
| `GET` | `/metrics` | Contagem por estado, falhas e duração média do processamento concluído. |

Estados possíveis: `PENDING`, `PROCESSING`, `DONE`, `FAILED` e `NEEDS_REVIEW`. `DONE` indica auditoria aprovada; extrações que precisam de conferência humana ficam em `NEEDS_REVIEW`.

Erros de upload incluem arquivo vazio (`400`), duplicado (`409`, com referência ao documento existente), arquivo grande (`413`), tipo ou assinatura não aceitos (`415`) e indisponibilidade da fila (`503`). A validação detalhada do conteúdo acontece no worker depois da resposta assíncrona.

### Regras de auditoria implementadas

- Validação de CPF e CNPJ pelos dígitos verificadores.
- Validação da chave fiscal com 44 dígitos e módulo 11.
- Verificação de que o CNPJ embutido na chave coincide com o CNPJ extraído.
- Conversão de valores brasileiros, por exemplo `1.234,56`, para `Decimal("1234.56")`.
- Aprovação aritmética quando a diferença entre total e itens é menor ou igual à tolerância configurada (padrão `R$ 0,05`).
- Encaminhamento para revisão quando campos críticos estão ausentes ou inválidos, há divergência aritmética ou a confiança cai abaixo do limiar.
- O QR Code prevalece sobre a chave encontrada no OCR; divergências são registradas no log.
- A correção manual preserva o texto bruto do OCR e registra o histórico do campo corrigido.

### Persistência e operação

Os modelos e a migração inicial cobrem:

- `documents`: metadados, hash, caminho do arquivo e estado.
- `extractions`: campos reconhecidos, texto bruto, confiança, versão do OCR e dados do QR.
- `items`: descrição, quantidade e valores dos itens.
- `audits`: cálculos, indicadores de validação, problemas encontrados e veredito.
- `corrections`: histórico de correção manual.

O Compose declara serviços separados para API, worker, Celery Beat, Redis e PostgreSQL. O scheduler agenda a exclusão diária de documentos com mais de `RETENTION_DAYS` (90 dias por padrão). As tarefas do worker usam confirmação tardia e até três retentativas com backoff exponencial.

Os logs são emitidos em JSON com `document_id`, etapa e duração. `/metrics` oferece contadores e duração média geral; a duração detalhada de cada etapa está nos logs, não em métricas Prometheus.

## Tecnologias

- Python 3.12
- FastAPI e Pydantic
- Celery e Redis
- PostgreSQL 16, SQLAlchemy e Alembic
- Tesseract com idioma português, `pytesseract`, OpenCV headless, NumPy e PyMuPDF
- pytest, pytest-cov, Ruff e mypy
- Docker Compose

O limite de Python é `>=3.12,<3.13`. A versão de OpenCV está fixada no `pyproject.toml`; a pinagem completa das dependências transitivas e do pacote Tesseract do sistema ainda pode ser refinada.

## Executar com Docker Compose

Pré-requisitos: Docker Desktop com o engine Linux ativo e Docker Compose.

```powershell
Copy-Item .env.example .env
```

Edite `.env` e substitua `API_KEY` por uma chave própria antes de iniciar. Então:

```powershell
docker compose up --build
```

A API ficará disponível em `http://localhost:${API_PORT:-8000}` e o Swagger em `http://localhost:${API_PORT:-8000}/docs`. Se a porta padrão já estiver em uso, ajuste `API_PORT` em `.env`. A primeira inicialização da API aplica a migração do banco.

Os valores de usuário e senha do PostgreSQL no Compose são somente para desenvolvimento local; troque-os antes de qualquer implantação compartilhada. Os serviços não devem ser expostos diretamente à Internet sem endurecimento adicional.

### Exemplo de envio no PowerShell

```powershell
curl.exe -X POST http://localhost:8000/api/v1/documents `
  -H "X-API-Key: sua-chave-local" `
  -F "file=@.\cupom.jpg"
```

Consulte o resultado usando o `document_id` retornado:

```powershell
curl.exe http://localhost:8000/api/v1/documents/ID-RETORNADO `
  -H "X-API-Key: sua-chave-local"
```

## Desenvolvimento local

Para processamento real no host, instale também Tesseract 5 com o idioma português e inicie Redis. PostgreSQL pode ser substituído por SQLite para desenvolvimento local; o Compose usa PostgreSQL.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:DATABASE_URL = "sqlite:///./doc_audit.db"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:API_KEY = "chave-local-de-desenvolvimento"
alembic upgrade head
uvicorn doc_audit.main:app --reload --app-dir src
```

Inicie o worker e o scheduler em terminais separados:

```powershell
celery -A doc_audit.worker.celery_app worker --loglevel=INFO
celery -A doc_audit.worker.celery_app beat --loglevel=INFO
```

Configurações disponíveis (também listadas em `.env.example`):

| Variável | Padrão | Uso |
|---|---|---|
| `API_KEY` | `change-this-local-key` | Chave de acesso às rotas de documentos. Altere antes de uso compartilhado. |
| `API_PORT` | `8000` | Porta local publicada pelo Compose. |
| `DATABASE_URL` | `sqlite:///./doc_audit.db` | URL SQLAlchemy. No Compose, aponta para PostgreSQL. |
| `REDIS_URL` | `redis://localhost:6379/0` | Broker e backend de resultados Celery. |
| `UPLOAD_DIR` | `./data/uploads` | Armazenamento dos arquivos originais. |
| `PROCESSED_DIR` | `./data/processed` | Destino das imagens processadas quando habilitado. |
| `MAX_UPLOAD_BYTES` | `10485760` | Tamanho máximo por upload (10 MiB). |
| `MAX_IMAGE_PIXELS` | `20000000` | Limite de pixels decodificados por página para restringir imagens desproporcionais. |
| `MAX_PDF_PAGES` | `20` | Número máximo de páginas do PDF. |
| `AUDIT_TOLERANCE` | `0.05` | Tolerância monetária da auditoria. |
| `MIN_FIELD_CONFIDENCE` | `60` | Limiar de confiança do OCR (0 a 100). |
| `SAVE_PREPROCESSED` | `false` | Salva imagens pré-processadas para depuração. |
| `RETENTION_DAYS` | `90` | Prazo de retenção usado pela tarefa agendada. |

## Testes e qualidade

```powershell
pytest --cov=doc_audit --cov-report=term-missing
ruff check .
mypy src scripts
```

A suíte cobre validadores, parsers, limiarização, deskew em rotações de `-15°`, `-5°`, `0°`, `5°` e `15°`, renderização de PDF a 300 DPI, assinaturas de arquivos, autenticação da API, upload, duplicidade, correção manual, auditoria e uma execução simulada do worker.

Na última validação local: 45 testes passaram; cobertura total foi de 82%. O workflow também executa o fluxo com Tesseract real e anexa os relatórios das duas configurações de pré-processamento como artefatos do CI. Os testes unitários continuam simulando a fila/OCR para serem determinísticos.

## Avaliar acurácia do OCR

O avaliador compara texto, campos extraídos, itens e auditoria com ground truth, calculando CER, WER, acurácia por campo e taxa de falso aprovado. O repositório inclui 50 recibos sintéticos em `samples/synthetic`, cada um com imagem e ground truth JSON. Eles ajudam a validar o fluxo e o avaliador, mas não representam a diversidade de layouts, fotografias ou qualidade de documentos fiscais reais. Complemente-os com documentos anonimizados obtidos com autorização antes de tirar conclusões sobre qualidade do produto. Nunca coloque dados pessoais reais no Git.

Para regenerar o conjunto sintético:

```powershell
python scripts/generate_synthetic_dataset.py --output-dir samples/synthetic --count 50
```

Crie um JSON por imagem no diretório do conjunto. Exemplo `samples/test/cupom-001.json`:

```json
{
  "document_id": "cupom-001",
  "image": "cupom-001.png",
  "expected": {
    "raw_text": "texto rotulado do cupom",
    "cnpj": "11.222.333/0001-81",
    "cpf": null,
    "issue_datetime": "2026-03-14T18:42:00",
    "total_amount": "87.90",
    "access_key": null,
    "items": [],
    "should_review": false
  }
}
```

Execute o conjunto sintético com os dois métodos para uma comparação inicial:

```powershell
python scripts/evaluate_accuracy.py --dataset samples/synthetic --threshold adaptive --output accuracy-adaptive.json
python scripts/evaluate_accuracy.py --dataset samples/synthetic --threshold otsu --output accuracy-otsu.json
```

Validação local observada em 50 recibos sintéticos: `adaptive` obteve CER 0,00343, WER 0,02107, acurácia de CNPJ 92%, data/total 100%, itens 80% e nenhum falso aprovado entre 10 casos rotulados para revisão. `otsu` obteve CER 0,00394, WER 0,02606, CNPJ 90%, data/total 100%, itens 80% e também nenhum falso aprovado. Esses números servem apenas para verificar o fluxo com dados sintéticos; não demonstram acurácia em documentos fiscais reais.

Mantenha o conjunto de teste congelado e fora do ajuste dos parâmetros. As metas de qualidade documentadas (por exemplo, acurácia mínima de 90% para campos críticos e falso aprovado abaixo de 2%) só poderão ser confirmadas após coletar e rotular dados adequados e executar essa avaliação.

## Smoke test de integração e carga

Com o Compose ativo, o smoke test envia uma imagem sintética à API e espera que o worker execute OCR e auditoria:

```powershell
python scripts/smoke_test.py --api-url http://localhost:8000 --api-key sua-chave-local
```

Para medir um lote de 100 documentos distintos em imagens de aproximadamente 2 MP:

```powershell
python scripts/generate_synthetic_dataset.py --output-dir samples/load --count 100
python scripts/load_test.py --api-url http://localhost:8000 --api-key sua-chave-local --dataset samples/load --documents 100 --concurrency 4
```

O relatório inclui latência de upload, tempo observado até o estado terminal (inclui fila) nos percentis p50/p95, throughput e contagem por estado. Registre resultados com hardware, versões, configuração/quantidade de workers e commit usados. Isso não substitui medição no host de referência de 4 vCPU.

Medições locais de 100 recibos sintéticos com Tesseract 5.3.0, Docker Engine com 16 CPUs e 15,6 GiB de memória: com concorrência de upload 4, throughput 0,712 documento/s e p95 até estado terminal 10,063 s; com concorrência 2, throughput 0,547 documento/s e p95 9,094 s. A execução com concorrência 4 ultrapassou por pouco a meta de 10 s; use a configuração de 2 apenas como referência preliminar, pois estes números não foram obtidos no hardware-alvo de 4 vCPU.

## Pendências conhecidas

- Substituir/ampliar a amostra sintética por documentos anonimizados, autorizados e representativos; congelar o conjunto de teste e avaliar CER/WER, campos críticos e falso aprovado.
- Executar e registrar um lote de 100 documentos no hardware-alvo de 4 vCPU. `/metrics` fornece a duração média geral; o p95 por documento é medido pelo script de carga.
- Acompanhar a primeira execução do workflow GitHub Actions no repositório remoto; o CI foi adicionado localmente, mas ainda não foi executado no GitHub.
- Ampliar e avaliar o parser heurístico de itens em diferentes layouts; a versão atual reconhece um formato comum de linha de NFC-e, não todos os modelos de cupom.
- Refinar controles operacionais antes de uma implantação compartilhada: segredos e credenciais fora dos padrões locais, proteção de endpoints operacionais, política de mascaramento para CPF e retenção/exclusão auditáveis.
- Expor métricas agregadas consultáveis por etapa; a aplicação já registra durações estruturadas por etapa, e o Tesseract/idioma português estão fixados na imagem Docker.

## Fora do escopo atual

Consulta à SEFAZ, OCR de manuscritos, treinamento de modelos próprios, interface web de revisão e suporte especializado a todos os layouts de NF-e/DANFE permanecem fora deste MVP, conforme o documento de requisitos.
