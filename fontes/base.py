"""
Base do sistema de fontes de cotacao.

Cada fonte (site/API) vira um modulo em fontes/ que expoe:
    FONTE  -> nome legivel da fonte (str)
    coletar() -> (lista_de_Cotacao, dict_indicadores)

O scraper.py junta as cotacoes de TODAS as fontes e consolida por praca.
Assim, adicionar uma nova fonte (ex.: uma API no futuro) = criar 1 arquivo.
"""

import re
import unicodedata
from dataclasses import dataclass

# Siglas de estado validas (para descobrir a regiao de cada praca).
UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}


@dataclass
class Cotacao:
    """Um preco de um produto, numa praca, vindo de uma fonte."""
    produto: str            # "milho" | "soja" | "sorgo" ...
    municipio: str          # "Sorriso"
    uf: str                 # "MT" | "N/D"
    preco_sc: float         # preco por saca
    peso_saca: int          # kg por saca (60 para graos)
    variacao: str = ""      # "-1,92" (texto, como no site)
    fonte: str = ""         # "Noticias Agricolas"
    fonte_detalhe: str = ""  # entidade que cotou: "Cotrijal", "Sindicato"...
    data: str = ""          # data da cotacao, se houver

    @property
    def preco_kg(self) -> float:
        return round(self.preco_sc / self.peso_saca, 4)

    @property
    def chave(self):
        """Identifica a praca de forma estavel (uf + municipio sem acento)."""
        return (self.uf, _slug(self.municipio))


def _slug(texto: str) -> str:
    """'São Gabriel' -> 'saogabriel' (para agrupar a mesma praca)."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", sem_acento.lower())


def parse_preco(texto: str):
    """'1.234,56' (formato BR) -> 1234.56. Retorna None se nao der."""
    limpo = texto.strip().replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def extrair_uf(texto: str):
    """Acha a UF dentro de um nome de praca ('Sorriso/MT' -> 'MT')."""
    for m in re.finditer(r"\b([A-Z]{2})\b", texto):
        if m.group(1) in UFS:
            return m.group(1)
    return None


def separar_praca(nome: str):
    """
    Quebra 'Nao-Me-Toque/RS (Cotrijal)' em:
        municipio = 'Nao-Me-Toque'
        uf        = 'RS'
        detalhe   = 'Cotrijal'  (a entidade que cotou)
    """
    detalhes = re.findall(r"\(([^)]*)\)", nome)
    detalhe = " / ".join(d.strip() for d in detalhes if d.strip())

    sem_par = re.sub(r"\([^)]*\)", "", nome).strip()
    uf = extrair_uf(sem_par)

    m = re.match(r"^(.*?)/\s*[A-Z]{2}\b", sem_par)
    if m:
        municipio = m.group(1).strip()
    elif uf:
        municipio = re.sub(r"\b" + uf + r"\b\s*$", "", sem_par).strip()
    else:
        municipio = sem_par
    municipio = municipio.strip(" -/") or sem_par

    return municipio, (uf or "N/D"), detalhe
