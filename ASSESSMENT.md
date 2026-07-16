# Assessment — Painel de Cotações Agro

**Data:** 16/07/2026
**Produção:** https://painel-cotacoes.onrender.com
**Repositório:** https://github.com/SheldonTcooper/painel-cotacoes
**Responsável:** Rômulo (projeto solo)

---

## 1. O que é

Painel web público de cotações de **milho, soja e sorgo** por praça (município),
com filtro por estado, busca, detalhamento por fonte e calculadora de
frete/margem para decidir onde vale a pena vender.

O problema que resolve: sites de cotação mostram o preço, mas não cruzam
fontes nem descontam o custo logístico. O painel consolida múltiplas fontes
por praça e simula o lucro após frete (km, diesel, autonomia, ida e volta).

## 2. Estado atual (verificado em 16/07/2026)

| Métrica | Valor |
|---|---|
| Fontes ativas | 2 (Notícias Agrícolas + CONAB dados abertos) |
| Cotações por ciclo | ~166 |
| Praças de milho | ~91 |
| Estados cobertos | 27 (todas as UFs) |
| Praças com 2+ fontes | ~7 (milho e soja) |
| Tempo de coleta completa | ~2 s (com cache CONAB aquecido) |

Funcional e estável em produção. Sem histórico, sem testes automatizados
(ver seção 6).

## 3. Arquitetura

```
navegador ──poll 30s──> Flask (/api/cotacoes)
                          │
                          ▼
                     scraper.py ── cache 2 min, coleta síncrona sob demanda
                          │         (locks: 1 coleta por vez; demais servem cache)
                          ▼
                     fontes/ (plugáveis: FONTE + coletar())
                       ├─ noticias_agricolas.py  requests+BS4, diário, por praça
                       └─ conab.py               CSV público semanal, cache 6 h
                          │
                          ▼
                     consolidação por (produto, UF, slug-município)
                       mediana · min · max · spread · n_fontes
```

Pontos-chave do desenho:

- **Coleta síncrona sob demanda** (sem thread de fundo): threads não rodavam
  de forma confiável sob gunicorn no Render. A 1ª requisição com cache velho
  coleta; as concorrentes recebem o cache atual (lock não-bloqueante).
- **Fontes plugáveis**: cada fonte é um módulo com `FONTE` e
  `coletar() -> (lista_de_Cotacao, dict_indicadores)`, registrado em
  `fontes/__init__.py`. Adicionar fonte = 1 arquivo, zero mudança no resto.
- **Consolidação por mediana**: robusta a outlier. Caso real: Campo Grande/MS
  tem NA a R$ 48,00 e CONAB atacado a R$ 106,80 — o consolidado fica em
  R$ 48,00 e o spread (±58,80) fica exposto na interface em vez de escondido.
- **Fuso horário**: o servidor (Render) roda em UTC; o frontend formata o
  timestamp epoch (`atualizado_ts`) no fuso do navegador de cada visitante.

## 4. Fontes de dados — avaliação completa

### Ativas

| Fonte | Método | Frequência | Cobertura | Observações |
|---|---|---|---|---|
| Notícias Agrícolas | scraping HTTP (requests+BS4, sem navegador) | diária | praças com entidade cotante (cooperativa/sindicato) | parser identifica tabelas pelo cabeçalho, não por CSS — resiste a mudanças cosméticas |
| CONAB dados abertos | arquivo público `PrecosSemanalMunicipio.txt` (CSV latin-1, ~26 MB) | semanal | ~76 municípios, 27 UFs | oficial (governo); cache local de 6 h; variação calculada vs semana anterior |

### Avaliadas e descartadas (com motivo)

| Fonte | Motivo do descarte |
|---|---|
| CEPEA/ESALQ (site) | Cloudflare bloqueia robôs |
| CEPEA via Ipeadata (API OData) | séries de grãos mensais, estaduais e majoritariamente inativas — não serve para painel "ao vivo" |
| CONAB (site de consulta) | reCAPTCHA — mas o **arquivo de dados abertos** contorna isso legitimamente |
| Canal Rural | Cloudflare |
| Agrolink | preço renderizado como imagem (exigiria OCR) |

### Ressalvas de qualidade dos dados

- **Nível de comercialização**: a pesquisa CONAB de *preço ao produtor* parou
  de ser publicada em jan/2026; hoje só o *atacado* está corrente. O coletor
  aceita os dois níveis e o filtro de idade (30 dias) decide — se a pesquisa
  de produtor voltar, reaparece sem mudança de código. O nível fica visível
  no detalhe de cada cotação.
- **Comparabilidade**: atacado (CONAB) tende a ser estruturalmente mais alto
  que preço de balcão (NA). A mediana + spread exposto mitigam, mas o usuário
  deve olhar o detalhe da praça antes de decidir.
- **Praças sem UF**: o NA às vezes publica a praça sem estado; a consolidação
  funde com a praça de mesmo município quando há uma única candidata com UF.

## 5. Decisões técnicas e justificativas

| Decisão | Alternativa rejeitada | Por quê |
|---|---|---|
| requests + BeautifulSoup | Selenium (versão original em `auto.py`) | navegador headless é pesado/frágil no plano free; o site responde a HTTP simples com headers de navegador |
| coleta síncrona + cache | thread de fundo | thread não roda confiável sob gunicorn (worker forka); bug real de produção resolvido |
| mediana | média | robusta a outlier entre fontes (caso Campo Grande) |
| JS puro no frontend | React | 1 tela, estado simples (2 Sets); framework não paga o custo |
| cache CONAB de 6 h | baixar a cada ciclo | arquivo semanal de 26 MB; baixar a cada 2 min seria desperdício |
| epoch + fuso do navegador | hora formatada no servidor | Render é UTC; cada visitante vê seu próprio fuso |

## 6. Riscos e dívidas conhecidas

Em ordem de prioridade:

1. **Dependência de scraping (NA)** — mudança estrutural no site derruba a
   fonte principal diária. Mitigação existente: parser por cabeçalho,
   falha isolada por produto, endpoint `/api/diag` para diagnóstico remoto.
   Mitigação futura: alerta automático quando `fontes_ativas` encolher.
2. **Sem testes automatizados** — os parsers (`parse_preco`, `separar_praca`,
   identificação de tabelas, parser CONAB) são funções puras; testes com
   fixtures de HTML/CSV salvos seriam baratos e pegariam regressão de layout.
3. **Sem histórico** — o painel só mostra o instante atual. Persistir cada
   ciclo (SQLite bastaria) habilitaria tendência, que é o que o produtor
   mais consome.
4. **Plano free do Render** — hiberna após ~15 min; primeiro acesso lento
   (acordar + coletar). Aceitável para o estágio atual.
5. **Termos de uso** — coleta educada (2 min, sob demanda, headers honestos)
   e CONAB permite uso citando a fonte. NA não tem API/licença explícita;
   risco baixo, mas existe. Não contornamos nenhum bloqueio ativo.
6. **Sorgo com cobertura rala** — poucas praças em ambas as fontes; é
   limitação do mercado, não do código.

## 7. Roadmap sugerido

Curto prazo (maior valor por esforço):
1. Testes dos parsers com fixtures (protege contra o risco nº 1 e 2).
2. Persistência em SQLite + gráfico de tendência por praça.
3. Badge de "idade" da cotação na UI (diária NA vs semanal CONAB).

Médio prazo:
4. Alerta (e-mail/Telegram) quando uma fonte cair ou quando o preço de uma
   praça cruzar um alvo definido pelo usuário.
5. Frete: tabela de custo por eixo/pedágio em vez de só diesel.

Longo prazo:
6. CEPEA se surgir acesso legítimo (indicador de referência de mercado).
7. Múltiplos destinos na calculadora ("para onde vender" automático).

## 8. Runbook (operação)

```bash
# rodar local
pip install -r requirements.txt
py app.py            # http://127.0.0.1:5000

# diagnóstico em produção
curl https://painel-cotacoes.onrender.com/api/diag      # a fonte NA responde?
curl https://painel-cotacoes.onrender.com/api/cotacoes  # status, fontes_ativas, erro

# deploy: push na main -> Render redeploya sozinho (render.yaml)
git push origin main
```

Sinais de problema e onde olhar:

| Sintoma | Causa provável | Onde olhar |
|---|---|---|
| status "erro" no painel | ambas as fontes falharam | `erro` em `/api/cotacoes`; logs do Render |
| só 1 fonte em `fontes_ativas` | NA mudou layout ou CONAB fora do ar | `/api/diag` (NA); baixar o TXT da CONAB manualmente |
| painel lento no 1º acesso | hibernação do plano free + coleta fria | esperado; ~30 s |
| horário estranho | regressão do fuso | frontend deve usar `atualizado_ts`, nunca `atualizado_em` |
