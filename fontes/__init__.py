"""
Registro de fontes de cotacao.

COLETORES = lista de modulos ativos. Cada um precisa expor:
    FONTE (str)  e  coletar() -> (lista_de_Cotacao, dict_indicadores)

>>> COMO ADICIONAR UMA NOVA FONTE (ex.: uma API oficial no futuro) <<<
    1. Crie fontes/minha_fonte.py com FONTE e coletar().
       (coletar() faz o request/parse e devolve as Cotacao no formato padrao.)
    2. Importe e adicione em COLETORES abaixo.
    Pronto: o scraper passa a consolidar essa fonte junto com as demais.

Fontes mapeadas mas ainda NAO ativas (precisam de API/acesso especial):
    - CEPEA/ESALQ ...... indicador de referencia; site bloqueia robos (Cloudflare)
                         e as series no Ipeadata sao mensais/inativas.
    - Canal Rural ...... bloqueado (Cloudflare).
    - Agrolink ......... preco publicado como imagem (exigiria OCR).
"""

from . import conab, noticias_agricolas

COLETORES = [
    noticias_agricolas,  # scraping (precos diarios por praca)
    conab,               # dados abertos oficiais (semanal, por municipio)
    # cepea,             # <- plugar quando houver acesso/API
]
