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


if __name__ == "__main__":
    # threaded=True: atende varias requisicoes junto com a thread de coleta.
    # use_reloader=False: evita abrir DUAS threads de scraping.
    app.run(host="127.0.0.1", port=5000, debug=False,
            threaded=True, use_reloader=False)
