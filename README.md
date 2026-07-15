# Painel de Cotações Agro

Painel web em tempo real de cotações de **milho, soja e sorgo** por praça,
com filtro por região (estado), consolidação de preço por praça e calculadora
de frete/margem.

Fonte de dados: **Notícias Agrícolas** (coleta via HTTP, sem navegador).

## Rodar localmente

```bash
pip install -r requirements.txt
py app.py
```
Abra: http://127.0.0.1:5000

## Estrutura

```
app.py               # servidor Flask + API /api/cotacoes
scraper.py           # coleta em segundo plano + consolidação por praça
fontes/              # sistema de fontes plugáveis
  base.py            #   formato padrão (Cotacao) + parsers
  noticias_agricolas.py  # coletor (requests + BeautifulSoup)
  __init__.py        #   registro de fontes ativas
templates/index.html # página
static/style.css     # estilo
static/app.js        # lógica do painel (filtros, tabelas, frete)
auto.py              # script CLI original (versão simples, usa Selenium)
```

## Publicar no Render.com (grátis)

1. Suba este projeto para um repositório no **GitHub**.
2. No [Render](https://render.com) → **New +** → **Web Service** → conecte o repositório.
3. O Render detecta o `render.yaml` automaticamente (Python, plano free).
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --workers 1 --bind 0.0.0.0:$PORT --timeout 120`
4. Clique em **Create Web Service**. Ao final você recebe um link público
   `https://<seu-painel>.onrender.com`.

Observações:
- O plano free "hiberna" após ~15 min sem acesso; o primeiro acesso seguinte
  demora alguns segundos para acordar e recoletar.
- A coleta roda a cada 2 min (ajustável em `scraper.py`, `INTERVALO_COLETA`).

## Adicionar novas fontes (ex.: API oficial no futuro)

Crie um arquivo em `fontes/` expondo `FONTE` e `coletar()` que devolve
`(lista_de_Cotacao, dict_indicadores)`, e registre em `fontes/__init__.py`.
A consolidação por praça passa a incluir a nova fonte automaticamente.
