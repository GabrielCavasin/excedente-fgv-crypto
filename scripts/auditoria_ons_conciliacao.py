"""Auditoria do pipeline corrigido (pipeline.py), lendo os mesmos parquet do ONS.
Gera: log de ingestao por arquivo, duplicidades, cobertura da razao, conciliacao mensal
(nosso corte 'oficial' x GNR apurada do proprio ONS no dataset por conjunto), por fonte, UF e razao."""
import glob, os, re, json, sys
import pandas as pd, numpy as np
sys.path.insert(0, ".")
import pipeline as P
OUT = "auditoria"
INI, FIM = pd.Timestamp("2025-01-01"), pd.Timestamp("2026-11-01")
L = pd.read_csv(f"{OUT}/1_log_ingestao.csv")
# 2) GNR apurada do ONS por conjunto (referencia oficial do proprio ONS)
fr = []
for p in sorted(glob.glob("dados/ons_conj/*.parquet")):
    c = pd.read_parquet(p, columns=["id_subsistema", "id_estado", "id_ons", "din_instante", "cod_razaorestricao", "val_geracaonaorealizadaapurada"])
    c = c[c.id_subsistema == "NE"]; c["fonte"] = "eolica" if "EOLICA" in p else "solar"; fr.append(c)
C = pd.concat(fr); dupc = int(C.duplicated(["id_ons", "din_instante"]).sum()); C = C.drop_duplicates(["id_ons", "din_instante"])
C["mes"] = C.din_instante.dt.to_period("M").astype(str)
gnr = (C.groupby(["mes", "fonte"]).val_geracaonaorealizadaapurada.sum() * 0.5 / 1e6).rename("TWh_GNR_apurada_ONS_conjuntos")
# 3) nosso corte (cache do pipeline, mesma leitura)
df = pd.read_parquet("dados/cache_ne.parquet")
df["corte_of"], _ = P.calcular_corte(df, "oficial")
df["mes"] = df.instante.dt.to_period("M").astype(str)
dup = int(df.duplicated(["usina", "instante"]).sum())
cob_razao = float(df.razao.astype(str).ne("").mean())
nos = (df.groupby(["mes", "fonte"], observed=True).corte_of.sum() * 0.5 / 1e6).rename("TWh_nosso_corte_oficial")
gap_total = (df.groupby(["mes", "fonte"], observed=True).gap.sum() * 0.5 / 1e6).rename("TWh_toda_diferenca_positiva")
M = pd.concat([nos, gnr, gap_total], axis=1).reset_index()
M["diferenca_pct"] = (M.TWh_nosso_corte_oficial / M.TWh_GNR_apurada_ONS_conjuntos - 1) * 100
M.to_csv(f"{OUT}/2_conciliacao_mensal.csv", index=False)
por = (df[df.instante >= "2025-11-01"].assign(r=df.razao.astype(str).replace("", "sem razao"))
       .groupby(["fonte", "estado", "r"], observed=True).corte_of.sum() * 0.5 / 1e6).rename("TWh").reset_index()
por = por[por.TWh > 0]; por.to_csv(f"{OUT}/3_corte_por_fonte_uf_razao_nov25_out26.csv", index=False)
def soma(m0, m1, col): x = M[(M.mes >= m0) & (M.mes <= m1)]; return round(float(x[col].sum()), 2)
meta = dict(linhas_brutas=int(L.linhas_brutas.sum()), linhas_validas=int(L.linhas_validas.sum()),
            pct_removido_sem_ref=round(100 * L.sem_referencia_ou_verificada.sum() / max(L.linhas_validas.sum() + L.sem_referencia_ou_verificada.sum(), 1), 2),
            duplicadas_detalhe=int(L.duplicadas_usina_instante.sum()), duplicadas_cache=dup, duplicadas_conjunto=dupc,
            fracao_intervalos_com_razao=round(cob_razao, 4), usinas_cache=int(df.usina.nunique()),
            usinas_por_fonte=df.groupby("fonte", observed=True).usina.nunique().to_dict(),
            usinas_por_uf=df.groupby("estado", observed=True).usina.nunique().to_dict(),
            jan_ago_2026_nosso=soma("2026-01", "2026-08", "TWh_nosso_corte_oficial"),
            jan_ago_2026_GNR_ONS=soma("2026-01", "2026-08", "TWh_GNR_apurada_ONS_conjuntos"),
            nov25_out26_nosso=soma("2025-11", "2026-10", "TWh_nosso_corte_oficial"),
            nov25_out26_GNR_ONS=soma("2025-11", "2026-10", "TWh_GNR_apurada_ONS_conjuntos"),
            ano_2026_ate_out_nosso=soma("2026-01", "2026-10", "TWh_nosso_corte_oficial"))
json.dump(meta, open(f"{OUT}/0_resumo_auditoria.json", "w"), indent=2, ensure_ascii=False, default=str)
print(json.dumps(meta, indent=2, ensure_ascii=False, default=str)); print(M.round(3).to_string(index=False))
