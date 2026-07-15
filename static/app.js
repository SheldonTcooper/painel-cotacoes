// ---------------------------------------------------------------------------
// Estado da interface
// ---------------------------------------------------------------------------
const CORES = { milho: "#fbbf24", soja: "#34d399", sorgo: "#f472b6" };
const COR_PADRAO = "#60a5fa";

let dados = null;                 // ultimo JSON da API
let selecionados = new Set();     // produtos marcados
let expandidos = new Set();       // pracas com detalhe aberto (chave "produto|uf|municipio")
const POLL_MS = 30000;

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------
const fmt = (n, casas = 2) =>
  Number(n).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

function classeVar(txt) {
  if (!txt) return "zero";
  if (txt.includes("-")) return "desce";
  if (/[1-9]/.test(txt)) return "sobe";
  return "zero";
}

function listaProdutos() {
  return (dados && dados.ordem_produtos) ? dados.ordem_produtos.filter(p => dados.produtos[p]) : [];
}

// ---------------------------------------------------------------------------
// Filtros
// ---------------------------------------------------------------------------
function montarChipsProdutos() {
  const box = document.getElementById("filtro-produtos");
  box.innerHTML = "";
  listaProdutos().forEach((p) => {
    const el = document.createElement("div");
    el.className = "chip" + (selecionados.has(p) ? " ativo" : "");
    el.textContent = p;
    el.onclick = () => {
      if (selecionados.has(p)) selecionados.delete(p);
      else selecionados.add(p);
      if (selecionados.size === 0) selecionados.add(p);
      montarChipsProdutos();
      render();
    };
    box.appendChild(el);
  });
}

function preencherUFs() {
  const sel = document.getElementById("filtro-uf");
  const atual = sel.value;
  sel.innerHTML = '<option value="TODOS">Todos os estados</option>';
  (dados.estados || []).forEach((uf) => {
    const o = document.createElement("option");
    o.value = uf; o.textContent = uf;
    sel.appendChild(o);
  });
  sel.value = atual && [...sel.options].some((o) => o.value === atual) ? atual : "TODOS";
}

function pracasFiltradas(produto) {
  const uf = document.getElementById("filtro-uf").value;
  const busca = document.getElementById("busca").value.trim().toLowerCase();
  let lista = (dados.produtos[produto]?.pracas) || [];
  if (uf !== "TODOS") lista = lista.filter((p) => p.uf === uf);
  if (busca) lista = lista.filter((p) => p.municipio.toLowerCase().includes(busca));
  return lista;
}

// ---------------------------------------------------------------------------
// Render dos cards
// ---------------------------------------------------------------------------
function render() {
  if (!dados || !dados.produtos) return;
  const cont = document.getElementById("cards");
  cont.innerHTML = "";

  selecionados = new Set([...selecionados].filter((p) => dados.produtos[p]));
  if (selecionados.size === 0) listaProdutos().forEach((p) => selecionados.add(p));

  listaProdutos().filter((p) => selecionados.has(p)).forEach((produto) => {
    const info = dados.produtos[produto] || {};
    const lista = pracasFiltradas(produto);

    const precos = lista.map((p) => p.preco_sc);
    const media = precos.length ? precos.reduce((a, b) => a + b, 0) / precos.length : 0;
    const min = precos.length ? Math.min(...precos) : 0;
    const max = precos.length ? Math.max(...precos) : 0;

    const ref = info.indicador
      ? `Indicador (${info.indicador.fonte || ""})<br><b>R$ ${info.indicador.valor}</b>`
      : "";

    let linhas = "";
    if (lista.length) {
      lista.forEach((p) => {
        const chave = `${produto}|${p.uf}|${p.municipio}`;
        const aberto = expandidos.has(chave);
        // celula de fonte: se 1 cotacao mostra a entidade; se varias, "N fontes"
        const fonteTxt = p.n_cotacoes > 1
          ? `${p.n_cotacoes} cotações`
          : (p.cotacoes[0]?.detalhe || p.cotacoes[0]?.fonte || "—");
        const spreadTxt = p.spread > 0 ? `<span class="spread">±${fmt(p.spread)}</span>` : "";

        linhas += `
          <tr class="linha" data-chave="${chave}">
            <td>${p.municipio}<span class="praca-uf">${p.uf}</span></td>
            <td class="preco">R$ ${fmt(p.preco_sc)} ${spreadTxt}</td>
            <td class="preco-kg">R$ ${fmt(p.preco_kg, 3)}</td>
            <td class="fonte-cel"><span class="caret">${aberto ? "▾" : "▸"}</span>${fonteTxt}</td>
            <td class="var ${classeVar(p.variacao)}">${p.variacao || "—"}</td>
          </tr>`;

        if (aberto) {
          const itens = p.cotacoes.map((c) => `
            <div class="cot-item">
              <span class="cot-fonte">${c.fonte}${c.detalhe ? " · " + c.detalhe : ""}</span>
              <span class="cot-preco">R$ ${fmt(c.preco_sc)}</span>
              <span class="var ${classeVar(c.variacao)}">${c.variacao || "—"}</span>
            </div>`).join("");
          linhas += `<tr class="detalhe"><td colspan="5"><div class="cot-box">
            <div class="cot-cab">Cotações usadas (consolidado = mediana)</div>${itens}</div></td></tr>`;
        }
      });
    } else {
      linhas = `<tr><td colspan="5" class="vazio">Nenhuma praça para este filtro.</td></tr>`;
    }

    const card = document.createElement("div");
    card.className = "card";
    card.style.borderTop = `3px solid ${CORES[produto] || COR_PADRAO}`;
    card.innerHTML = `
      <div class="card-topo">
        <h3>${produto}</h3>
        <div class="card-ref">${ref}</div>
      </div>
      <div class="card-metricas">
        <div class="metrica"><div class="v">R$ ${fmt(media)}</div><div class="l">média/sc</div></div>
        <div class="metrica"><div class="v">R$ ${fmt(min)}</div><div class="l">mínima</div></div>
        <div class="metrica"><div class="v">R$ ${fmt(max)}</div><div class="l">máxima</div></div>
        <div class="metrica"><div class="v">${lista.length}</div><div class="l">praças</div></div>
      </div>
      <div class="tabela-wrap">
        <table>
          <thead><tr>
            <th>Praça</th><th style="text-align:right">R$/sc</th>
            <th style="text-align:right">R$/kg</th><th>Fonte</th>
            <th style="text-align:right">Var.</th>
          </tr></thead>
          <tbody>${linhas}</tbody>
        </table>
      </div>`;
    cont.appendChild(card);
  });

  // clique para expandir/recolher o detalhe de fontes
  cont.querySelectorAll("tr.linha").forEach((tr) => {
    tr.onclick = () => {
      const k = tr.dataset.chave;
      if (expandidos.has(k)) expandidos.delete(k);
      else expandidos.add(k);
      render();
    };
  });

  calcularFrete();
}

// ---------------------------------------------------------------------------
// Calculadora de frete
// ---------------------------------------------------------------------------
function calcularFrete() {
  const box = document.getElementById("frete-resultado");
  const produto = listaProdutos().find((p) => selecionados.has(p));
  const lista = produto ? pracasFiltradas(produto) : [];
  if (!lista.length) { box.innerHTML = '<div class="res-box"><div class="l">Sem preço para calcular</div></div>'; return; }

  const precoKg = lista.reduce((a, p) => a + p.preco_kg, 0) / lista.length;
  const kg = +document.getElementById("f-kg").value || 0;
  const km = +document.getElementById("f-km").value || 0;
  const diesel = +document.getElementById("f-diesel").value || 0;
  const auton = +document.getElementById("f-auton").value || 1;
  const idaVolta = document.getElementById("f-idavolta").checked;

  const kmTotal = km * (idaVolta ? 2 : 1);
  const litros = kmTotal / auton;
  const custoFrete = litros * diesel;
  const receita = kg * precoKg;
  const lucro = receita - custoFrete;
  const neg = lucro < 0 ? " negativo" : "";
  const uf = document.getElementById("filtro-uf").value;

  box.innerHTML = `
    <div class="res-box"><div class="v">R$ ${fmt(precoKg, 3)}</div><div class="l">preço médio (${produto}${uf !== "TODOS" ? "/" + uf : ""})</div></div>
    <div class="res-box"><div class="v">${fmt(litros, 1)} L</div><div class="l">diesel (${kmTotal} km)</div></div>
    <div class="res-box"><div class="v">R$ ${fmt(custoFrete)}</div><div class="l">custo de frete</div></div>
    <div class="res-box"><div class="v">R$ ${fmt(receita)}</div><div class="l">receita (${kg} kg)</div></div>
    <div class="res-box lucro${neg}"><div class="v">R$ ${fmt(lucro)}</div><div class="l">lucro após frete</div></div>`;
}

// ---------------------------------------------------------------------------
// API + status
// ---------------------------------------------------------------------------
async function atualizar() {
  try {
    const resp = await fetch("/api/cotacoes");
    dados = await resp.json();
  } catch (e) {
    setStatus("erro", "Sem conexão com o servidor");
    return;
  }

  if (dados.status === "carregando") {
    setStatus("carregando", "Coletando cotações… (1ª carga leva ~30s)");
  } else if (dados.status === "erro") {
    setStatus("erro", "Erro na coleta: " + (dados.erro || ""));
  } else {
    setStatus("ok", "Ao vivo");
    document.getElementById("atualizado").textContent = dados.atualizado_em || "—";
    document.getElementById("fontes-ativas").textContent =
      "Fontes: " + ((dados.fontes_ativas || []).join(" · ") || "—");
    if (selecionados.size === 0) listaProdutos().forEach((p) => selecionados.add(p));
    montarChipsProdutos();
    preencherUFs();
    render();
  }
}

function setStatus(cls, txt) {
  document.getElementById("pulso").className = "pulso " + cls;
  document.getElementById("status-txt").textContent = txt;
}

// ---------------------------------------------------------------------------
// Inicializacao
// ---------------------------------------------------------------------------
document.getElementById("filtro-uf").addEventListener("change", render);
document.getElementById("busca").addEventListener("input", render);
["f-kg", "f-km", "f-diesel", "f-auton", "f-idavolta"].forEach((id) =>
  document.getElementById(id).addEventListener("input", calcularFrete));

atualizar();
setInterval(atualizar, POLL_MS);
