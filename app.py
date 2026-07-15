"""
Servidor web (Flask) do painel de cotacoes.

Rodar:
    py app.py
Depois abra no navegador:  http://127.0.0.1:5000
"""

from flask import Flask, jsonify, render_template

import scraper

app = Flask(__name__)

# Inicia a coleta em segundo plano assim que o servidor sobe.
scraper.iniciar()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/cotacoes")
def api_cotacoes():
    """Devolve os precos ja coletados (cache), em JSON."""
    return jsonify(scraper.get_dados())


@app.route("/api/diag")
def api_diag():
    """Diagnostico: mostra o que o servidor consegue (ou nao) baixar da fonte."""
    import time
    import requests
    from fontes.noticias_agricolas import HEADERS, TIMEOUT

    url = "https://www.noticiasagricolas.com.br/cotacoes/milho"
    t0 = time.time()
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        texto = r.text
        return jsonify({
            "ok": True,
            "status_code": r.status_code,
            "segundos": round(time.time() - t0, 2),
            "tamanho": len(texto),
            "tem_tabela_praca": ("cot-fisicas" in texto) and ("Praça" in texto),
            "servidor_cf": r.headers.get("server", ""),
            "trecho": texto[:400],
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({
            "ok": False,
            "erro": f"{type(e).__name__}: {e}",
            "segundos": round(time.time() - t0, 2),
        })


if __name__ == "__main__":
    # threaded=True: atende varias requisicoes junto com a thread de coleta.
    # use_reloader=False: evita abrir DUAS threads de scraping.
    app.run(host="127.0.0.1", port=5000, debug=False,
            threaded=True, use_reloader=False)
