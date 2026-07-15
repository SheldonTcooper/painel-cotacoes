"""
Orquestrador de coleta.

Roda TODAS as fontes registradas em fontes/COLETORES, junta as cotacoes e
CONSOLIDA por praca: para cada municipio/UF calcula o valor de mercado
(mediana entre as fontes), a amplitude (min-max) e quantas fontes cotaram.

A coleta acontece de duas formas (redundancia proposital):
  - numa thread periodica em segundo plano (iniciar());
  - sob demanda, disparada pela 1a requisicao (caso a thread nao rode no host).
Cada coleta tem um TETO DE TEMPO rigido para nunca travar em "carregando".
"""

import threading
import time
from datetime import datetime
from statistics import median

from fontes import COLETORES

# De quanto em quanto tempo re-coletar (segundos).
INTERVALO_COLETA = 120

# Teto de tempo por fonte (segundos). Se estourar, a fonte e' abandonada.
COLETA_TIMEOUT = 30

# Ordem em que os produtos aparecem no painel.
ORDEM_PRODUTOS = ["milho", "soja", "sorgo"]


# ---------------------------------------------------------------------------
# Cache compartilhado com o Flask
# ---------------------------------------------------------------------------
_lock = threading.Lock()
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


def _run_com_timeout(func, timeout):
    """Executa func() numa thread e ABANDONA se passar de `timeout` segundos."""
    caixa = {}

    def alvo():
        try:
            caixa["v"] = func()
        except Exception as e:  # noqa: BLE001
            caixa["e"] = e

    t = threading.Thread(target=alvo, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"coleta excedeu {timeout}s (host provavelmente bloqueado)")
    if "e" in caixa:
        raise caixa["e"]
    return caixa["v"]


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
    """Uma rodada: coleta de todas as fontes (com teto de tempo) e atualiza o cache."""
    print("[scraper] iniciando ciclo de coleta...", flush=True)
    todas = []
    indicadores = {}
    fontes_ok = []
    erros = []
    for modulo in COLETORES:
        nome = getattr(modulo, "FONTE", str(modulo))
        try:
            cotacoes, indics = _run_com_timeout(modulo.coletar, COLETA_TIMEOUT)
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


def _coletar_seguro():
    """Roda um ciclo protegido por lock (evita coletas simultaneas)."""
    if not _scrape_lock.acquire(blocking=False):
        return  # ja tem uma coleta rolando
    try:
        _ciclo_coleta()
    except Exception as e:  # noqa: BLE001
        with _lock:
            if not _cache["produtos"]:
                _cache["status"] = "erro"
                _cache["erro"] = f"{type(e).__name__}: {e}"
    finally:
        _scrape_lock.release()


def _loop():
    while True:
        _coletar_seguro()
        time.sleep(INTERVALO_COLETA)


def iniciar():
    print("[scraper] thread de coleta iniciada", flush=True)
    threading.Thread(target=_loop, daemon=True).start()


def _precisa_atualizar():
    ts = _cache.get("atualizado_ts")
    return ts is None or (time.time() - ts) > INTERVALO_COLETA


def get_dados():
    """Devolve o cache. Se estiver velho/vazio, dispara uma coleta em 2o plano."""
    if _precisa_atualizar() and not _scrape_lock.locked():
        threading.Thread(target=_coletar_seguro, daemon=True).start()
    with _lock:
        return dict(_cache)
