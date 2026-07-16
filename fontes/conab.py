"""
Fonte: CONAB - Dados Abertos (Portal de Informacoes Agropecuarias).

Le o arquivo publico de precos semanais por municipio:
    https://portaldeinformacoes.conab.gov.br/downloads/arquivos/PrecosSemanalMunicipio.txt

E' um CSV (separador ';', encoding latin-1) com TODAS as pesquisas de preco
da CONAB. Filtramos MILHO / SOJA / SORGO GRANIFERO e pegamos, para cada
municipio e nivel de comercializacao, a semana mais recente.

Niveis de comercializacao: o arquivo traz "PREÇO RECEBIDO P/ PRODUTOR" e
"ATACADO". A pesquisa de produtor parou de ser publicada em jan/2026; o
atacado segue semanal. Aceitamos os dois e deixamos o filtro de idade
(MAX_IDADE_DIAS) decidir o que entra -- se a CONAB retomar a pesquisa de
produtor, ela reaparece sozinha. O nivel fica registrado em fonte_detalhe.

O arquivo e' semanal (~26 MB), entao mantemos um cache proprio de algumas
horas: o ciclo do scraper roda a cada 2 min, mas so' baixamos da CONAB
quando o cache local vence.
"""

import time
from datetime import datetime, timedelta

import requests

from .base import Cotacao

FONTE = "CONAB"

URL = ("https://portaldeinformacoes.conab.gov.br/"
       "downloads/arquivos/PrecosSemanalMunicipio.txt")

# nome do produto no arquivo CONAB -> (nome no painel, kg por saca)
PRODUTOS = {
    "MILHO":           ("milho", 60),
    "SOJA":            ("soja",  60),
    "SORGO GRANIFERO": ("sorgo", 60),
}

# Rotulo curto por nivel de comercializacao. O campo vem truncado no
# arquivo ("PREÇO RECEBIDO P/ PR"), por isso o casamento por prefixo.
NIVEIS = {
    "PREÇO RECEBIDO": "produtor",
    "ATACADO": "atacado",
}


def _rotulo_nivel(texto):
    for prefixo, rotulo in NIVEIS.items():
        if texto.startswith(prefixo):
            return rotulo
    return None

# Ignora municipios cuja ultima cotacao e' mais velha que isso.
MAX_IDADE_DIAS = 30

# O arquivo muda 1x por semana; nao ha' motivo para baixar 26 MB a cada
# ciclo de 2 min. Cache local do resultado ja' parseado.
CACHE_TTL = 6 * 3600
TIMEOUT = (10, 120)

_cache = {"ts": 0.0, "resultado": None}


def _parse_fim_semana(texto):
    """'06-07-2026 - 10-07-2026' -> datetime(2026, 7, 10)."""
    fim = texto.split(" - ")[-1].strip()
    return datetime.strptime(fim, "%d-%m-%Y")


def _parse_valor(texto):
    """'1,15' -> 1.15 (R$/kg). Retorna None se nao der."""
    try:
        return float(texto.strip().replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _titulo(nome):
    """'EUCLIDES DA CUNHA' -> 'Euclides da Cunha'."""
    minusculas = {"da", "de", "do", "das", "dos", "e", "d"}
    palavras = nome.title().split()
    return " ".join(
        p.lower() if i > 0 and p.lower() in minusculas else p
        for i, p in enumerate(palavras)
    )


def _separar_municipio(nome):
    """'CHAPECÓ-SC' -> ('Chapecó', 'SC')."""
    nome = nome.strip()
    if len(nome) > 3 and nome[-3] == "-":
        return _titulo(nome[:-3].strip()), nome[-2:]
    return _titulo(nome), "N/D"


def _baixar_e_parsear():
    """Baixa o arquivo da CONAB e devolve a lista de Cotacao consolidavel."""
    resp = requests.get(URL, timeout=TIMEOUT, stream=True)
    resp.raise_for_status()
    resp.encoding = "latin-1"

    # Para cada (produto, municipio, nivel) guardamos as semanas vistas:
    # a mais recente vira a cotacao, a anterior da' a variacao.
    melhores = {}  # (produto, municipio, nivel) -> {fim_semana: (valor_kg, periodo)}

    primeira = True
    for linha in resp.iter_lines(decode_unicode=True):
        if primeira:
            primeira = False
            continue  # cabecalho
        campos = linha.split(";")
        if len(campos) < 13:
            continue

        prod_conab = campos[0].strip()
        if prod_conab not in PRODUTOS:
            continue
        nivel = _rotulo_nivel(campos[11].strip())
        if nivel is None:
            continue

        valor_kg = _parse_valor(campos[12])
        if valor_kg is None or valor_kg <= 0:
            continue
        try:
            fim = _parse_fim_semana(campos[9])
        except ValueError:
            continue

        chave = (prod_conab, campos[3].strip(), nivel)
        semanas = melhores.setdefault(chave, {})
        # se o mesmo municipio/semana repetir, fica a ultima linha
        semanas[fim] = (valor_kg, campos[9].strip())

    limite = datetime.now() - timedelta(days=MAX_IDADE_DIAS)
    cotacoes = []
    for (prod_conab, municipio_uf, nivel), semanas in melhores.items():
        datas = sorted(semanas)
        atual = datas[-1]
        if atual < limite:
            continue  # municipio sem pesquisa recente

        produto, peso = PRODUTOS[prod_conab]
        valor_kg, periodo = semanas[atual]
        municipio, uf = _separar_municipio(municipio_uf)

        variacao = ""
        if len(datas) >= 2:
            anterior_kg = semanas[datas[-2]][0]
            if anterior_kg:
                pct = (valor_kg - anterior_kg) / anterior_kg * 100
                variacao = f"{pct:+.2f}".replace(".", ",")

        cotacoes.append(Cotacao(
            produto=produto,
            municipio=municipio,
            uf=uf,
            preco_sc=round(valor_kg * peso, 2),
            peso_saca=peso,
            variacao=variacao,
            fonte=FONTE,
            fonte_detalhe=f"{nivel} · semana {periodo.split(' - ')[0][:5]}",
            data=atual.strftime("%d/%m/%Y"),
        ))

    return cotacoes


def coletar():
    """Retorna (lista_de_Cotacao, dict_indicadores). Usa cache de CACHE_TTL."""
    agora = time.time()
    if _cache["resultado"] is not None and agora - _cache["ts"] < CACHE_TTL:
        return _cache["resultado"], {}

    cotacoes = _baixar_e_parsear()
    if cotacoes:  # so' substitui o cache se a coleta rendeu algo
        _cache["resultado"] = cotacoes
        _cache["ts"] = agora
    print(f"[CONAB] {len(cotacoes)} cotacoes (arquivo semanal)", flush=True)
    return cotacoes, {}
