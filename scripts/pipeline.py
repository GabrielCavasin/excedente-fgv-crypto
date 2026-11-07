"""
Analise semi-horaria da viabilidade da mineracao flexivel de bitcoin com energia
renovavel restringida (curtailment) no Nordeste do Brasil.

Versao corrigida do pipeline original (evidencia_original/pipeline_original.py).
Mudancas em CORRECOES.md. Resumo:
  - le os parquet reais do ONS (detalhe por usina + conjunto, que traz a razao)
  - referencia = coalesce(val_geracaoreferenciafinal, val_geracaoestimada)
  - duas definicoes de corte: "oficial" (equivale a GNRa do ONS) e "conservador"
  - janela economica de 12 meses completos, para nao distorcer a sazonalidade
  - cenario pos-halving e utilizacao de equilibrio coerente com o VPL
  - modo censo: todas as usinas do Nordeste, sem previsao

Uso:
  python pipeline.py --ons "dados/ons/*.parquet" --conj "dados/ons_conj/*.parquet" \
      --hashprice dados/hashprice.csv --corte-teste 2026-05-01 --saida resultados
"""
import argparse, glob, json, os, re, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.simplefilter("ignore")

PARAM = dict(
    capacidades_mw=[1, 5, 10],
    latencias_min=[0, 5, 15, 30],
    asics={"S19j XP": dict(jth=21.5, usd_th=6.0), "S19 Pro": dict(jth=29.5, usd_th=3.0)},
    infra_usd_mw=250_000, vida_hw=4, vida_infra=8,
    om_var=0.08, om_fixo_brl_mw_ano=120_000, pis_cofins=0.0925, ir=0.34,
    preco_energia_brl_mwh=60.0, taxa_desconto=0.20, cambio=5.20,
    standby_falso_positivo=0.05,
    razoes_incluidas=None,
    # Premissa: projeto inicia em jan/2027; halving em abr/2028 corta o subsidio pela metade.
    # Multiplicadores anuais sobre o hashprice da janela, com preco e dificuldade constantes.
    perfil_halving=[1.0, 0.6462, 0.5, 0.5],
)
CENARIOS_HP = {"x0.8": [0.8] * 4, "x1.0": [1.0] * 4, "x1.2": [1.2] * 4, "pos_halving": PARAM["perfil_halving"]}
NORDESTE = "NE"
ORIGENS_OK = {"Curva", "Irradiância"}


# ---------------------------------------------------------------- leitura ONS
def _mes(p):
    m = re.search(r"(\d{4})_(\d{2})", os.path.basename(p))
    return f"{m.group(1)}_{m.group(2)}"


def ler_conjunto(caminhos):
    cols = ["id_ons", "din_instante", "val_geracao", "val_geracaolimitada", "val_geracaoreferencia",
            "cod_razaorestricao", "val_geracaonaorealizadaapurada", "id_subsistema"]
    fr = []
    for p in caminhos:
        d = pd.read_parquet(p, columns=cols)
        d = d[d.id_subsistema == NORDESTE].drop(columns="id_subsistema")
        d["mes"] = _mes(p)
        fr.append(d)
    c = pd.concat(fr, ignore_index=True).drop_duplicates(["id_ons", "din_instante"])
    c["vinculante"] = c.val_geracaolimitada.notna() & (c.val_geracaolimitada < c.val_geracaoreferencia) \
        & (c.val_geracaonaorealizadaapurada.fillna(0) > 0)
    return c[["id_ons", "din_instante", "cod_razaorestricao", "vinculante", "val_geracaonaorealizadaapurada"]]


def ler_ons(caminhos, conj, inicio, fim):
    fr = []
    for p in sorted(caminhos):
        fonte = "eolica" if "EOLICA" in os.path.basename(p) else "solar"
        d = pd.read_parquet(p, columns=["id_subsistema", "id_estado", "nom_usina", "id_ons", "id_ons_conjuntousina",
                                        "din_instante", "val_geracaoestimada", "val_geracaoverificada",
                                        "val_geracaoreferenciafinal", "nom_origemgeracaoreferencia"])
        d = d[(d.id_subsistema == NORDESTE) & (d.din_instante >= inicio) & (d.din_instante < fim)]
        if d.empty:
            continue
        d["chave"] = d.id_ons_conjuntousina.fillna(d.id_ons)
        d = d.merge(conj, how="left", left_on=["chave", "din_instante"], right_on=["id_ons", "din_instante"],
                    suffixes=("", "_c"))
        ref = d.val_geracaoreferenciafinal.fillna(d.val_geracaoestimada)
        gap = (ref - d.val_geracaoverificada).clip(lower=0)
        o = pd.DataFrame({
            "usina": d.id_ons.astype(str), "nome": d.nom_usina.astype(str), "estado": d.id_estado.astype(str),
            "fonte": fonte, "instante": d.din_instante, "gap": gap.astype("float32"),
            "razao": d.cod_razaorestricao.astype(object).where(d.cod_razaorestricao.notna(), ""),
            "vinculante": d.vinculante.fillna(False).astype(bool),
            "origem_ok": d.nom_origemgeracaoreferencia.isin(ORIGENS_OK),
        })
        fr.append(o.dropna(subset=["gap"]))
    df = pd.concat(fr, ignore_index=True)
    for c in ["usina", "nome", "estado", "fonte", "razao"]:
        df[c] = df[c].astype("category")
    return df


def calcular_corte(df, definicao, razoes=None):
    """oficial: gap apenas onde ha razao registrada (equivale a GNRa).
    conservador: limite vinculante no conjunto, origem confiavel e gap descontado do erro de curva
    da propria usina, medido nos intervalos SEM restricao."""
    tem = df.razao.astype(str).ne("")
    if razoes:
        tem_r = tem & df.razao.astype(str).isin(razoes)
    else:
        tem_r = tem
    if definicao == "oficial":
        return df.gap.where(tem_r, 0.0).astype("float32"), None
    ruido = df.gap.where(~tem).groupby(df.usina, observed=True).transform("mean").fillna(0)
    c = (df.gap - ruido).clip(lower=0).where(tem_r & df.vinculante & df.origem_ok, 0.0)
    return c.astype("float32"), df.gap.where(~tem).groupby(df.usina, observed=True).mean()


def selecionar_usinas(df, inicio, fim, cobertura_min=0.95, n_max=20):
    """Cobertura >= cobertura_min; amostra espalhada pela distribuicao de corte."""
    n = len(pd.date_range(inicio, fim, freq="30min", inclusive="left"))
    g = df.groupby("usina", observed=True)
    t = pd.DataFrame({"cobertura": g.instante.nunique() / n, "corte_mwh": g.corte_mw.sum() * 0.5,
                      "nome": g.nome.first(), "estado": g.estado.first(), "fonte": g.fonte.first()})
    t = t[t.cobertura >= cobertura_min].sort_values("corte_mwh", ascending=False)
    if n_max and len(t) > n_max:
        t = t.iloc[np.unique(np.linspace(0, len(t) - 1, n_max).round().astype(int))]
    return t


def ler_hashprice(caminho):
    df = pd.read_csv(caminho)
    df["data"] = pd.to_datetime(df["data"])
    return df.set_index("data")["hashprice_usd_ph_dia"].sort_index()


# ---------------------------------------------------------------- despacho
def capturavel(corte_mw, cap_mw):
    return np.minimum(corte_mw, cap_mw) * 0.5


def captura_reativa(corte_mw, cap_mw, latencia_min):
    e = capturavel(corte_mw, cap_mw)
    ativo = corte_mw > 0
    inicio = ativo & ~np.r_[False, ativo[:-1]]
    frac = max(0.0, 1 - latencia_min / 30)
    return np.where(inicio, e * frac, e), int(inicio.sum())


def captura_prevista(corte_mw, cap_mw, latencia_min, previsto):
    e = capturavel(corte_mw, cap_mw)
    ativo = corte_mw > 0
    inicio = ativo & ~np.r_[False, ativo[:-1]]
    frac = max(0.0, 1 - latencia_min / 30)
    cap = np.where(inicio & ~previsto, e * frac, e)
    falso = previsto & ~ativo
    desperdicio = falso * cap_mw * PARAM["standby_falso_positivo"] * 0.5
    return cap, desperdicio, int(falso.sum())


# ---------------------------------------------------------------- previsao
def features(s):
    """Somente informacao conhecida em D-1."""
    df = pd.DataFrame({"y": (s > 0).astype(int)})
    df["hora"] = s.index.hour + s.index.minute / 60
    df["dow"] = s.index.day_of_week
    df["mes"] = s.index.month
    df["lag48"] = (s.shift(48) > 0).astype(float)
    df["lag336"] = (s.shift(336) > 0).astype(float)
    df["frac_d1"] = (s.shift(48) > 0).astype(float).rolling(48).mean()
    df["hsin"] = np.sin(2 * np.pi * df["hora"] / 24)
    df["hcos"] = np.cos(2 * np.pi * df["hora"] / 24)
    return df.iloc[336:].dropna()


def prever(s, corte_teste, limiar=0.5):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import precision_score, recall_score, brier_score_loss
    df = features(s)
    tr, te = df[df.index < corte_teste], df[df.index >= corte_teste]
    X = ["hsin", "hcos", "dow", "mes", "lag48", "lag336", "frac_d1"]
    res = {}
    persist = te["lag48"].values > 0.5
    res["persistencia"] = dict(prev=persist, precisao=precision_score(te["y"], persist, zero_division=0),
                               recall=recall_score(te["y"], persist, zero_division=0))
    if tr["y"].nunique() == 2 and len(tr) > 500:
        m = LogisticRegression(max_iter=1000, class_weight="balanced").fit(tr[X], tr["y"])
        p = m.predict_proba(te[X])[:, 1]
        res["modelo"] = dict(prev=p >= limiar, precisao=precision_score(te["y"], p >= limiar, zero_division=0),
                             recall=recall_score(te["y"], p >= limiar, zero_division=0),
                             brier=brier_score_loss(te["y"], p))
    return res, te.index


# ---------------------------------------------------------------- economia
def _vpl(energia, receita, preco, cap, hw, infra, mult, p=None):
    p = p or PARAM
    r, n = p["taxa_desconto"], p["vida_hw"]
    depr = hw / p["vida_hw"] + infra / p["vida_infra"]
    v = -(hw + infra)
    for t in range(1, n + 1):
        contrib = receita * mult[t - 1] * (1 - p["pis_cofins"] - p["om_var"]) - preco
        ebitda = energia * contrib - p["om_fixo_brl_mw_ano"] * cap
        v += (ebitda - max(ebitda - depr, 0) * p["ir"]) / (1 + r) ** t
    return v + infra * (p["vida_infra"] - n) / p["vida_infra"] / (1 + r) ** n


def economia(energia_mwh_ano, receita_mwh_brl, preco_energia, cap_mw, asic, mult, p=None):
    p = p or PARAM
    hw = 1e6 / asic["jth"] * asic["usd_th"] * cap_mw * p["cambio"]
    infra = p["infra_usd_mw"] * cap_mw * p["cambio"]
    vpl = _vpl(energia_mwh_ano, receita_mwh_brl, preco_energia, cap_mw, hw, infra, mult, p)
    # utilizacao de equilibrio: a que zera o VPL (coerente com impostos e residual)
    emax = cap_mw * 8760
    if _vpl(emax, receita_mwh_brl, preco_energia, cap_mw, hw, infra, mult, p) < 0:
        ueq = np.inf
    else:
        a, b = 0.0, emax
        for _ in range(30):
            c = (a + b) / 2
            if _vpl(c, receita_mwh_brl, preco_energia, cap_mw, hw, infra, mult, p) < 0:
                a = c
            else:
                b = c
        ueq = b / emax
    contrib1 = receita_mwh_brl * mult[0] * (1 - p["pis_cofins"] - p["om_var"]) - preco_energia
    return dict(contribuicao_brl_mwh=contrib1, vpl=vpl, utilizacao_equilibrio=ueq,
                utilizacao_obtida=energia_mwh_ano / cap_mw / 8760, capex=hw + infra)


# ---------------------------------------------------------------- execucao
def rodar(df, hp, args):
    saida = args.saida
    os.makedirs(saida, exist_ok=True)
    ini_e, fim_e = pd.Timestamp(args.inicio_economia), pd.Timestamp(args.fim)
    if args.censo:
        sel = selecionar_usinas(df[df.instante >= ini_e], ini_e, fim_e, n_max=None)
    else:
        sel = selecionar_usinas(df, pd.Timestamp(args.inicio), fim_e, n_max=args.n)
    sel.to_csv(f"{saida}/usinas_selecionadas.csv")
    grade = pd.date_range(args.inicio, args.fim, freq="30min", inclusive="left")
    grupos = {u: g for u, g in df[df.usina.isin(sel.index)].groupby("usina", observed=True)}
    linhas, previsao = [], []
    for usina in sel.index:
        s = grupos[usina].set_index("instante")["corte_mw"].sort_index()
        s = s[~s.index.duplicated()].reindex(grade, fill_value=0.0).astype(float)
        s_e = s.loc[ini_e:]
        anos = len(s_e) / (48 * 365)
        if not args.censo:
            res, idx_te = prever(s, pd.Timestamp(args.corte_teste))
            s_te = s.loc[idx_te]
            anos_te = len(s_te) / (48 * 365)
        hp_dia = hp.reindex(s_e.index.normalize()).ffill().bfill().values
        for nome, asic in PARAM["asics"].items():
            rec_mwh = hp_dia / (asic["jth"] * 0.024) * PARAM["cambio"]
            for cap in PARAM["capacidades_mw"]:
                teto = capturavel(s_e.values, cap)
                for lat in PARAM["latencias_min"]:
                    e, n_ev = captura_reativa(s_e.values, cap, lat)
                    energia_ano = e.sum() / anos
                    rec_med = (e * rec_mwh).sum() / max(e.sum(), 1e-9) if e.sum() > 0 else rec_mwh.mean()
                    for cen, mult in CENARIOS_HP.items():
                        eco = economia(energia_ano, rec_med, PARAM["preco_energia_brl_mwh"], cap, asic, mult)
                        linhas.append(dict(usina=usina, fonte=sel.fonte[usina], estado=sel.estado[usina], asic=nome,
                                           cap_mw=cap, latencia_min=lat, cenario_hp=cen, eventos_ano=n_ev / anos,
                                           teto_mwh_ano=teto.sum() / anos, energia_mwh_ano=energia_ano,
                                           receita_brl_mwh=rec_med, **eco))
                if nome == "S19j XP" and not args.censo:
                    teto_te = capturavel(s_te.values, cap).sum()
                    for lat in PARAM["latencias_min"][1:]:
                        base_te, n_ev = captura_reativa(s_te.values, cap, lat)
                        for est, r in res.items():
                            capt, desp, nfp = captura_prevista(s_te.values, cap, lat, r["prev"])
                            ganho = (capt.sum() - base_te.sum() - desp.sum()) / anos_te
                            previsao.append(dict(usina=usina, fonte=sel.fonte[usina], cap_mw=cap, latencia_min=lat,
                                                 estrategia=est, precisao=r["precisao"], recall=r["recall"],
                                                 ganho_liquido_mwh_ano=ganho, ganho_pp_utilizacao=ganho / cap / 8760,
                                                 teto_ganho_pp=(teto_te - base_te.sum()) / anos_te / cap / 8760,
                                                 eventos_ano=n_ev / anos_te, falsos_positivos_ano=nfp / anos_te))
    res = pd.DataFrame(linhas)
    prev = pd.DataFrame(previsao)
    res.to_csv(f"{saida}/economia_por_usina.csv", index=False)
    frt = res.groupby(["asic", "cap_mw", "latencia_min", "cenario_hp"]).agg(
        usinas=("usina", "nunique"), usinas_vpl_positivo=("vpl", lambda v: int((v > 0).sum())),
        utilizacao_mediana=("utilizacao_obtida", "median"), utilizacao_p90=("utilizacao_obtida", lambda v: v.quantile(.9)),
        utilizacao_max=("utilizacao_obtida", "max"), utilizacao_equilibrio_mediana=("utilizacao_equilibrio", "median"),
        vpl_mediano=("vpl", "median"), vpl_max=("vpl", "max")).reset_index()
    frt.to_csv(f"{saida}/fronteira_viabilidade.csv", index=False)
    if len(prev):
        prev.to_csv(f"{saida}/ganho_previsao.csv", index=False)
        prev.groupby(["estrategia", "latencia_min", "cap_mw"])[
            ["ganho_pp_utilizacao", "teto_ganho_pp", "precisao", "recall", "eventos_ano", "falsos_positivos_ano"]
        ].median().reset_index().to_csv(f"{saida}/resumo_ganho_previsao.csv", index=False)
    graficos(res, prev, saida)
    with open(f"{saida}/metadados.json", "w") as f:
        json.dump(dict(parametros=PARAM, cenarios_hp=CENARIOS_HP, args=vars(args), n_usinas=len(sel)), f, indent=2, default=str)
    return res, prev, frt


def graficos(res, prev, saida):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    b = res.query("latencia_min==5 and cenario_hp=='x1.0' and asic=='S19j XP'")
    fig, ax = plt.subplots(figsize=(8, 5))
    for cap, g in b.groupby("cap_mw"):
        ax.scatter(g["utilizacao_obtida"] * 100, g["vpl"] / 1e6, label=f"{cap} MW", s=18, alpha=.7)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xlabel("Utilização obtida do contêiner (% do ano)")
    ax.set_ylabel("VPL do projeto (R$ milhões)")
    ax.set_title("Viabilidade por usina e capacidade (S19j XP, latência 5 min)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(f"{saida}/vpl_por_usina.png", dpi=150)
    plt.close(fig)
    if len(prev):
        fig, ax = plt.subplots(figsize=(8, 5))
        for est, g in prev.query("cap_mw==10").groupby("estrategia"):
            m = g.groupby("latencia_min")["ganho_pp_utilizacao"].median() * 100
            ax.plot(m.index, m.values, marker="o", label=est)
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_xlabel("Latência do controlador reativo (min)")
        ax.set_ylabel("Ganho líquido mediano (p.p. de utilização)")
        ax.set_title("Ganho da previsão contra reativa realista (10 MW)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(f"{saida}/ganho_previsao.png", dpi=150)
        plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ons", default="dados/ons/*.parquet")
    ap.add_argument("--conj", default="dados/ons_conj/*.parquet")
    ap.add_argument("--hashprice", default="dados/hashprice.csv")
    ap.add_argument("--saida", default="resultados")
    ap.add_argument("--corte-teste", default="2026-05-01")
    ap.add_argument("--inicio", default="2025-01-01")
    ap.add_argument("--inicio-economia", default="2025-11-01")
    ap.add_argument("--fim", default="2026-11-01", help="exclusivo; nov/2026 fica de fora por estar parcial")
    ap.add_argument("--definicao", choices=["oficial", "conservador"], default="oficial")
    ap.add_argument("--razoes", default="", help="ex.: ENE")
    ap.add_argument("--censo", action="store_true", help="todas as usinas NE, sem previsao")
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    cache = "dados/cache_ne.parquet"
    if os.path.exists(cache):
        df = pd.read_parquet(cache)
    else:
        arqs = [p for p in glob.glob(a.ons)]
        conj = ler_conjunto(glob.glob(a.conj))
        df = ler_ons(arqs, conj, pd.Timestamp(a.inicio), pd.Timestamp(a.fim))
        df.to_parquet(cache)
    razoes = [x for x in a.razoes.split(",") if x] or PARAM["razoes_incluidas"]
    df["corte_mw"], ruido = calcular_corte(df, a.definicao, razoes)
    hp = ler_hashprice(a.hashprice)
    res, prev, fr = rodar(df, hp, a)
    print(a.saida, res.usina.nunique(), "usinas;", "MWh corte janela:",
          round(df.loc[df.instante >= pd.Timestamp(a.inicio_economia), "corte_mw"].sum() * .5))
    print(fr.query("latencia_min==5 and cenario_hp in ['x1.0','pos_halving']").round(3).to_string(index=False))
