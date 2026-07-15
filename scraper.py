"""
Orquestrador de coleta.

Roda TODAS as fontes registradas em fontes/COLETORES, junta as cotacoes e
CONSOLIDA por praca: para cada municipio/UF calcula o valor de mercado
(mediana entre as fontes), a amplitude (min-max) e quantas fontes cotaram.

Tudo roda numa thread em segundo plano; o Flask so le o cache.
"""

import threading
import time
from datetime import datetime
from statistics import median

from fontes import COLETORES

# De quanto em quanto tempo re-coletar (segundos).
INTERVALO_COLETA = 120

# Ordem em que os produtos aparecem no painel.
ORDEM_PRODUTOS = ["milho", "soja", "sorgo"]


# ---------------------------------------------------------------------------
# Cache compartilhado com o Flask
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_cache = {
    "status": "carregando",     # carregando | ok | erro
    "atualizado_em": None,
    "erro": None,
    "fontes_ativas": [],
    "ordem_produtos": ORDEM_PRODUTOS,
    "produtos": {},
    "estados": [],
}


def _consolidar(cotacoes, indicadores):
    """Agrupa cotacoes por (produto, praca) e calcula o valor consolidado."""
    grupos = {}
    for c in cotacoes:
        grupos.setdefault((c.produto,) + c.chave, []).append(c)

    produtos = {}
    estados = set()

    for (produto, uf, _slug), lista in grupos.items():
        precos = [c.preco_sc for c in lista]
        peso = lista[0].peso_saca
        valor = round(median(precos), 2)

        entry = {
            "municipio": lista[0].municipio,
            "uf": uf,
            "preco_sc": valor,
            "preco_kg": round(valor / peso, 4),
            "min": round(min(precos), 2),
            "max": round(max(precos), 2),
            "spread": round(max(precos) - min(precos), 2),
            "n_fontes": len({c.fonte for c in lista}),
            "n_cotacoes": len(lista),
            "variacao": lista[0].variacao,
            "cotacoes": [
                {
                    "fonte": c.fonte,
                    "detalhe": c.fonte_detalhe,
                    "preco_sc": c.preco_sc,
                    "variacao": c.variacao,
                }
                for c in sorted(lista, key=lambda x: x.preco_sc)
            ],
        }

        produtos.setdefault(produto, {"pracas": [], "peso_saca": peso})
        produtos[produto]["pracas"].append(entry)
        if uf != "N/D":
            estados.add(uf)

    for produto, dados in produtos.items():
        dados["pracas"].sort(key=lambda e: (e["uf"], e["municipio"]))
        dados["indicador"] = indicadores.get(produto)

    return produtos, sorted(estados)


def _ciclo_coleta():
    """Uma rodada: coleta de todas as fontes e atualiza o cache."""
    todas = []
    indicadores = {}
    fontes_ok = []
    for modulo in COLETORES:
        try:
            cotacoes, indics = modulo.coletar()
            todas.extend(cotacoes)
            # nao sobrescreve um indicador ja existente de outra fonte
            for prod, ind in indics.items():
                indicadores.setdefault(prod, ind)
            if cotacoes:
                fontes_ok.append(modulo.FONTE)
        except Exception as e:
            print(f"[fonte falhou] {getattr(modulo, 'FONTE', modulo)}: {e}")

    produtos, estados = _consolidar(todas, indicadores)

    with _lock:
        _cache["status"] = "ok"
        _cache["atualizado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        _cache["produtos"] = produtos
        _cache["estados"] = estados
        _cache["fontes_ativas"] = fontes_ok
        _cache["erro"] = None


def _loop():
    while True:
        try:
            _ciclo_coleta()
        except Exception as e:
            with _lock:
                _cache["status"] = "erro"
                _cache["erro"] = str(e)
        time.sleep(INTERVALO_COLETA)


def iniciar():
    threading.Thread(target=_loop, daemon=True).start()


def get_dados():
    with _lock:
        return dict(_cache)
