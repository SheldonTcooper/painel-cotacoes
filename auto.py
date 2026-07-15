"""
Coletor de cotacoes agricolas + calculo de frete.

Fonte: Noticias Agricolas (https://www.noticiasagricolas.com.br/cotacoes/)
    -> aqui o PRECO vem como TEXTO e pode ser usado no calculo.

Por que nao o Agrolink?
    O Agrolink renderiza o preco como IMAGEM de fundo (PNG com nome
    embaralhado), justamente para impedir robos de ler o valor. Da para
    pegar a tabela, mas o preco vem sempre vazio. Por isso trocamos a fonte.

Requisitos:
    pip install selenium
    (Selenium 4+ baixa o ChromeDriver sozinho via Selenium Manager)
"""

from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ---------------------------------------------------------------------------
# 1) CONFIGURACAO -- mude aqui o que quiser
# ---------------------------------------------------------------------------

# Escolha o produto: basta trocar esta linha.
PRODUTO = "milho"

# Catalogo: produto -> (URL da cotacao, peso da saca em kg).
# Graos no Brasil sao cotados em saca de 60 kg.
PRODUTOS = {
    "milho": ("https://www.noticiasagricolas.com.br/cotacoes/milho", 60),
    "soja":  ("https://www.noticiasagricolas.com.br/cotacoes/soja", 60),
    "trigo": ("https://www.noticiasagricolas.com.br/cotacoes/trigo", 60),
    "cafe":  ("https://www.noticiasagricolas.com.br/cotacoes/cafe", 60),
    "boi":   ("https://www.noticiasagricolas.com.br/cotacoes/boi-gordo", 15),  # @ (arroba)
}

# Dados da carga / logistica (ajuste conforme sua realidade)
producao_kilos = 8000          # kg de produto na carga
valor_diesel = 6.0             # R$ por litro de diesel
autonomia_caminhao = 5.0       # km rodados por litro
distancia_km = 450.0           # distancia ate o destino (so ida), em km
ida_e_volta = True             # True = caminhao volta vazio (conta o dobro)
local_producao = "Vale do Sao Francisco - PE"

# Preco por kg: por padrao e calculado automaticamente a partir do site.
# Se quiser fixar um valor manual, coloque um numero aqui (ex.: 2.0);
# deixe None para usar a media das pracas coletadas.
preco_kilo_manual = None


# ---------------------------------------------------------------------------
# Outras fontes possiveis (referencia)
# ---------------------------------------------------------------------------
#   - CEPEA/ESALQ .... https://www.cepea.esalq.usp.br/br  (indicador de referencia;
#                      costuma bloquear robos)
#   - CONAB .......... https://www.conab.gov.br/  (governo: precos e safras)
#   - Scot Consultoria https://www.scotconsultoria.com.br/
#   - Canal Rural .... https://www.canalrural.com.br/cotacoes/
#   - B3 (futuros) ... https://www.b3.com.br/


# ---------------------------------------------------------------------------
# 2) UTILITARIOS
# ---------------------------------------------------------------------------

def parse_preco(texto):
    """Converte '1.234,56' (formato BR) em 1234.56. Retorna None se falhar."""
    limpo = texto.strip().replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def coletar_tabelas(driver, url):
    """Abre o site, espera as tabelas e devolve todas com seus cabecalhos/linhas."""
    driver.get(url)
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//table"))
    )
    tabelas = []
    for tabela in driver.find_elements(By.XPATH, "//table"):
        ths = [t.text.strip() for t in tabela.find_elements(By.XPATH, ".//th")]
        linhas = []
        for tr in tabela.find_elements(By.XPATH, ".//tbody/tr"):
            celulas = [td.text.strip() for td in tr.find_elements(By.XPATH, "./td")]
            if any(celulas):
                linhas.append(celulas)
        if ths and linhas:
            tabelas.append((ths, linhas))
    return tabelas


def achar_tabela_pracas(tabelas):
    """Retorna a tabela (ths, linhas) cujo cabecalho tem 'Praca' + 'Preco'."""
    for ths, linhas in tabelas:
        cab = " ".join(ths).lower()
        if "praça" in cab and "preço" in cab:
            return ths, linhas
    return None


def achar_indicador(tabelas):
    """Retorna a 1a tabela com cabecalho 'Data' + 'Valor' (indicador de referencia)."""
    for ths, linhas in tabelas:
        cab = " ".join(ths).lower()
        if "data" in cab and "valor" in cab:
            return ths, linhas
    return None


# ---------------------------------------------------------------------------
# 3) CALCULO DE FRETE / MARGEM
# ---------------------------------------------------------------------------

def calcular_frete(preco_kilo, origem_preco):
    km_total = distancia_km * (2 if ida_e_volta else 1)
    litros = km_total / autonomia_caminhao
    custo_combustivel = litros * valor_diesel
    receita = producao_kilos * preco_kilo
    lucro = receita - custo_combustivel
    custo_por_kg = custo_combustivel / producao_kilos if producao_kilos else 0

    print("=" * 58)
    print("RESUMO DA CARGA".center(58))
    print("=" * 58)
    print(f"Produto ..............: {PRODUTO}")
    print(f"Origem ...............: {local_producao}")
    print(f"Preco usado ..........: R$ {preco_kilo:.3f}/kg  ({origem_preco})")
    print(f"Distancia ({'ida+volta' if ida_e_volta else 'so ida':9}): {km_total:.0f} km")
    print(f"Diesel gasto .........: {litros:.1f} L  (R$ {custo_combustivel:.2f})")
    print(f"Custo de frete por kg : R$ {custo_por_kg:.3f}")
    print("-" * 58)
    print(f"Receita ({producao_kilos} kg x R$ {preco_kilo:.3f}) : R$ {receita:.2f}")
    print(f"Lucro apos frete .....: R$ {lucro:.2f}")
    print("=" * 58)


# ---------------------------------------------------------------------------
# 4) EXECUCAO
# ---------------------------------------------------------------------------

def main():
    if PRODUTO not in PRODUTOS:
        print(f"Produto '{PRODUTO}' nao cadastrado. Opcoes: {', '.join(PRODUTOS)}")
        return

    url, peso_saca = PRODUTOS[PRODUTO]
    print(f"Buscando cotacao de '{PRODUTO}' em {url} ...\n")

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--log-level=3")
    # options.add_argument("--headless=new")  # descomente p/ rodar sem abrir janela

    driver = webdriver.Chrome(options=options)
    try:
        tabelas = coletar_tabelas(driver, url)
    finally:
        driver.quit()  # sempre fecha o Chrome

    if not tabelas:
        print("Nenhuma tabela encontrada. O layout do site pode ter mudado.")
        return

    # --- Indicador de referencia (preco do dia) ---
    indicador = achar_indicador(tabelas)
    if indicador:
        _, linhas = indicador
        data, valor = linhas[0][0], linhas[0][1]
        print(f"Indicador de referencia: R$ {valor}/saca de {peso_saca}kg  (em {data})\n")

    # --- Precos por praca ---
    precos_kg = []
    pracas = achar_tabela_pracas(tabelas)
    if pracas:
        ths, linhas = pracas
        print(f"PRECOS POR PRACA  ({' | '.join(ths)})")
        print("-" * 58)
        for linha in linhas:
            praca = linha[0]
            preco_sc = parse_preco(linha[1]) if len(linha) > 1 else None
            variacao = linha[2] if len(linha) > 2 else ""
            if preco_sc is not None:
                preco_kg = preco_sc / peso_saca
                precos_kg.append(preco_kg)
                print(f"  {praca:<38} R$ {preco_sc:>7.2f}/sc  ({variacao})")
    else:
        print("Tabela de precos por praca nao encontrada nesta pagina.")

    print()

    # --- Define o preco/kg a usar no frete ---
    if preco_kilo_manual is not None:
        preco_kilo = preco_kilo_manual
        origem = "valor manual"
    elif precos_kg:
        preco_kilo = sum(precos_kg) / len(precos_kg)
        origem = f"media de {len(precos_kg)} pracas / {peso_saca}kg"
    else:
        print("Sem preco disponivel para calcular o frete. Defina 'preco_kilo_manual'.")
        return

    calcular_frete(preco_kilo, origem)


if __name__ == "__main__":
    main()
