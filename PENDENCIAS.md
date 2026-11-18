# Pendências — Sistema de Auditoria Fiscal OCR (`Sistema-Auditoria-Fiscal-OCR`)

Este documento separa o escopo técnico implementado e verificado das melhorias opcionais e dependências externas de produção/validação em campo.

---

## 1. Concluído e Verificado (Engenharia & Pipeline)
- [x] **API REST & Segurança (`src/doc_audit/api.py`, `security.py`):** Autenticação por `X-API-Key`, validação binária de uploads (JPG/PNG/PDF), deduplicação por hash SHA-256, exportação JSON/CSV, correção manual com histórico e exclusão.
- [x] **Fila Assíncrona & Persistência (`tasks.py`, `worker.py`, `models.py`):** Processamento Celery/Redis, modelos SQLAlchemy, migrações Alembic e rotina de retenção (Celery Beat, 90 dias).
- [x] **Pré-processamento, OCR e QR Code (`preprocessing.py`, `ocr.py`):** Renderização PDF a 300 DPI, redução de ruído, limiarização adaptativa/Otsu, correção de inclinação, Tesseract em português e prioridade de chave fiscal via QR Code.
- [x] **Parsers & Auditoria Fiscal (`parsers.py`, `validation.py`, `auditing.py`):** Validação de CPF, CNPJ, chave fiscal de 44 dígitos (módulo 11), aritmética em `Decimal` (tolerância R$ 0,05) e fila de revisão `NEEDS_REVIEW`.
- [x] **Dataset Sintético & Benchmarks (`samples/synthetic/`, `scripts/`):** 50 recibos sintéticos versionados, avaliação comparativa de acurácia (`evaluate_accuracy.py`) e teste de carga (`load_test.py`).
- [x] **Qualidade & CI (`.github/workflows/ci.yml`):**
  - `ruff check .` e `ruff format --check .` (100% em conformidade).
  - `mypy src scripts` (0 erros em 21 arquivos).
  - `pytest --cov=doc_audit` (`45/45` testes passando, 82% de cobertura).
  - Pipeline CI com job `quality` e `compose-integration` (Docker Compose + Postgres + Redis + Tesseract).

---

## 2. Melhorias Futuras Opcionais (Backlog Técnico)
- [ ] **Extração de Métricas Granulares para Prometheus:** Expor tempos individuais de pré-processamento, OCR e auditoria como histogramas `/metrics` (atualmente registrados em JSON nos logs estruturados).
- [ ] **Suporte a NFC-e / NF-e via XML Direto:** Parser complementar caso o cliente envie o XML fiscal em conjunto com o PDF do DANFE.

---

## 3. Dependências Externas (Dados Reais & Hardware de Produção)
- [ ] **Avaliação de Acurácia em Documentos Reais Anonimizados:** Os 50 recibos sintéticos validam o pipeline técnico; as metas finais de acurácia OCR precisam ser aferidas em amostra real anonimizada de cupons térmicos e notas escaneadas.
- [ ] **Teste de Carga em Host Alvo (4 vCPU):** Medições locais executadas com 100 documentos sintéticos; validação final de throughput recomendada na infraestrutura de destino.
- [ ] **Chave de API e Ambiente Docker (`API_KEY`, PostgreSQL, Redis):** Configuração de segredos definitivos em `.env` no deploy produtivo.
