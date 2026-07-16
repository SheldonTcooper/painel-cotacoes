"""
Orquestrador de coleta.

Roda TODAS as fontes registradas em fontes/COLETORES, junta as cotacoes e
CONSOLIDA por praca: para cada municipio/UF calcula o valor de mercado
(mediana entre as fontes), a amplitude (min-max) e quantas fontes cotaram.

A coleta roda DIRETO na requisicao (sincrona), com cache: se o cache esta
fresco, devolve na hora; se esta velho, coleta antes de responder. Nao depende
de threads em segundo plano (que nao executam de forma confiavel sob gunicorn).
"""

import threading
import time
from datetime import datetime
from statistics import median

from fontes import COLETORES

# Por quanto tempo o cache e' considerado fresco (segundos).
INTERVALO_COLETA = 120

# Ordem em que os produtos aparecem no painel.
ORDEM_PRODUTOS = ["milho", "soja", "sorgo"]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_lock = threading.Lock()          # protege o dicionario _cache
_scrape_lock = threading.Lock()   # garante 1 coleta por vez
_cache = {
    "status": "carregando",     # carregando | ok | erro
    "atualizado_em": None,
    "atualizado_ts": None,      # epoch da ultima coleta (controle interno)
    "erro": None,
    "fontes_ativas": [],
    "ordem_produtos": ORDEM_PRODUTOS,
    "produtos": {},
    "estados": [],
}


def _resolver_uf(grupos):
    """Funde pracas sem UF ('N/D') com a praca de mesmo municipio quando so'
    existe UMA candidata com UF definida. Ex.: o Noticias Agricolas as vezes
    publica 'Dourados' sem UF; se a CONAB tem 'Dourados/MS' (e nenhum outro
    estado tem Dourados), as duas viram a mesma praca."""
    com_uf = {}  # (produto, slug) -> [ufs]
    for (produto, uf, slug) in grupos:
        if uf != "N/D":
            com_uf.setdefault((produto, slug), []).append(uf)

    for chave in [k for k in grupos if k[1] == "N/D"]:
        produto, _nd, slug = chave
        candidatas = com_uf.get((produto, slug), [])
        if len(candidatas) == 1:
            grupos[(produto, candidatas[0], slug)].extend(grupos.pop(chave))
    return grupos


def _consolidar(cotacoes, indicadores):
    """Agrupa cotacoes por (produto, praca) e calcula o valor consolidado."""
    grupos = {}
    for c in cotacoes:
        grupos.setdefault((c.produto,) + c.chave, []).append(c)
    grupos = _resolver_uf(grupos)

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
    """Uma rodada: coleta de todas as fontes e atualiza o cache. SINCRONA."""
    print("[scraper] iniciando ciclo de coleta...", flush=True)
    todas = []
    indicadores = {}
    fontes_ok = []
    erros = []
    for modulo in COLETORES:
        nome = getattr(modulo, "FONTE", str(modulo))
        try:
            cotacoes, indics = modulo.coletar()
            todas.extend(cotacoes)
            for prod, ind in indics.items():
                indicadores.setdefault(prod, ind)
            if cotacoes:
                fontes_ok.append(nome)
            print(f"[scraper] {nome}: {len(cotacoes)} cotacoes", flush=True)
        except Exception as e:  # noqa: BLE001
            erros.append(f"{nome}: {type(e).__name__}: {e}")
            print(f"[fonte falhou] {nome}: {type(e).__name__}: {e}", flush=True)

    produtos, estados = _consolidar(todas, indicadores)

    with _lock:
        _cache["atualizado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        _cache["atualizado_ts"] = time.time()
        _cache["produtos"] = produtos
        _cache["estados"] = estados
        _cache["fontes_ativas"] = fontes_ok
        if todas:
            _cache["status"] = "ok"
            _cache["erro"] = None
        else:
            _cache["status"] = "erro"
            _cache["erro"] = "; ".join(erros) or "Nenhuma cotação coletada."
    print(f"[scraper] ciclo terminou: {len(todas)} cotacoes no total", flush=True)


def _precisa_atualizar():
    ts = _cache.get("atualizado_ts")
    return ts is None or (time.time() - ts) > INTERVALO_COLETA


def _atualizar_se_preciso():
    """Coleta (sincrona) se o cache estiver velho. SEM threads de fundo."""
    if not _precisa_atualizar():
        return
    # non-blocking: se ja tem uma requisicao coletando, os demais devolvem o
    # cache atual em vez de esperar. Como nao ha thread de fundo, a 1a
    # requisicao SEMPRE consegue a trava e coleta de verdade.
    if not _scrape_lock.acquire(blocking=False):
        return
    try:
        if _precisa_atualizar():  # confere de novo apos pegar a trava
            _ciclo_coleta()
    except Exception as e:  # noqa: BLE001
        with _lock:
            if not _cache["produtos"]:
                _cache["status"] = "erro"
                _cache["erro"] = f"{type(e).__name__}: {e}"
    finally:
        _scrape_lock.release()


def iniciar():
    """Mantido por compatibilidade. NAO usa thread de fundo de proposito:
    threads nao rodam de forma confiavel sob gunicorn e travavam a coleta.
    A coleta acontece sob demanda em get_dados()."""
    print("[scraper] coleta sob demanda (sem thread de fundo)", flush=True)


def get_dados():
    """Via UNICA: coleta sob demanda (sincrona) e devolve o cache."""
    _atualizar_se_preciso()
    with _lock:
        return dict(_cache)
