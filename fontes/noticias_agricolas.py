"""
Fonte: Noticias Agricolas (https://www.noticiasagricolas.com.br/cotacoes/).

Le a tabela de precos por praca de cada produto via HTTP simples (requests) +
BeautifulSoup -- sem navegador. Cada linha vira uma Cotacao, guardando a
entidade que cotou (cooperativa/sindicato/corretora) em fonte_detalhe.
"""

import requests
from bs4 import BeautifulSoup

from .base import Cotacao, parse_preco, separar_praca

FONTE = "Notícias Agrícolas"

PRODUTOS = {
    "milho": ("https://www.noticiasagricolas.com.br/cotacoes/milho", 60),
    "soja":  ("https://www.noticiasagricolas.com.br/cotacoes/soja",  60),
    "sorgo": ("https://www.noticiasagricolas.com.br/cotacoes/sorgo", 60),
}

# Cabecalhos de um navegador real -- ajuda a passar por protecoes (Cloudflare)
# quando a requisicao parte de um servidor (datacenter).
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# (conexao, leitura) em segundos -- tupla garante que NUNCA trava eternamente.
TIMEOUT = (10, 20)


def _get_soup(url):
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def coletar():
    """Retorna (lista_de_Cotacao, dict_indicadores_por_produto)."""
    cotacoes = []
    indicadores = {}

    for produto, (url, peso) in PRODUTOS.items():
        try:
            soup = _get_soup(url)
        except Exception as e:
            print(f"[NA] falha ao coletar {produto}: {type(e).__name__}: {e}", flush=True)
            continue  # esse produto falhou; segue os outros

        for tabela in soup.find_all("table"):
            ths = [th.get_text(strip=True) for th in tabela.find_all("th")]
            cab = " ".join(ths).lower()
            linhas = tabela.find_all("tr")

            # Indicador de referencia: "Data | Valor"
            if produto not in indicadores and "data" in cab and "valor" in cab:
                for tr in linhas:
                    tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                    if len(tds) >= 2 and parse_preco(tds[1]) is not None:
                        indicadores[produto] = {"valor": tds[1], "data": tds[0], "fonte": FONTE}
                        break

            # Tabela de pracas: "Praca | Preco"
            if "praça" in cab and "preço" in cab:
                for tr in linhas:
                    tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                    if len(tds) < 2:
                        continue
                    preco = parse_preco(tds[1])
                    if preco is None:
                        continue
                    municipio, uf, detalhe = separar_praca(tds[0])
                    cotacoes.append(Cotacao(
                        produto=produto,
                        municipio=municipio,
                        uf=uf,
                        preco_sc=round(preco, 2),
                        peso_saca=peso,
                        variacao=tds[2] if len(tds) > 2 else "",
                        fonte=FONTE,
                        fonte_detalhe=detalhe,
                    ))

    return cotacoes, indicadores
