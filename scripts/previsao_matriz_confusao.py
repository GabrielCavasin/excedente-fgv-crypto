import pandas as pd, numpy as np, sys
sys.path.insert(0,"."); import pipeline as P
sel=pd.read_csv("resultados/amostra_oficial/usinas_selecionadas.csv")
df=pd.read_parquet("dados/cache_ne.parquet",filters=[("usina","in",list(sel.usina.astype(str)))])
df["corte_mw"],_=P.calcular_corte(df,"oficial")
grade=pd.date_range("2025-01-01","2026-11-01",freq="30min",inclusive="left")
rows=[]
for u,g in df.groupby("usina",observed=True):
    s=g.set_index("instante")["corte_mw"].sort_index(); s=s[~s.index.duplicated()].reindex(grade,fill_value=0.0).astype(float)
    res,idx=P.prever(s,pd.Timestamp("2026-05-01")); y=(s.loc[idx]>0).values; anos=len(idx)/(48*365)
    ev=int((y & ~np.r_[False,y[:-1]]).sum())
    for est,r in res.items():
        pr=r["prev"]; tp=int((pr&y).sum()); fp=int((pr&~y).sum()); fn=int((~pr&y).sum()); tn=int((~pr&~y).sum())
        # alarmes por evento: inicios de blocos previstos
        al=int((pr & ~np.r_[False,pr[:-1]]).sum()); alf=0
        # blocos previstos sem nenhum corte real dentro
        blk=np.cumsum(pr & ~np.r_[False,pr[:-1]])*pr
        for b in range(1,blk.max()+1):
            if not y[blk==b].any(): alf+=1
        rows.append(dict(usina=u,estrategia=est,anos=anos,TP=tp,FP=fp,FN=fn,TN=tn,eventos=ev,blocos_alerta=al,blocos_alerta_falsos=alf))
R=pd.DataFrame(rows); R.to_csv("9_matriz_confusao_previsao.csv",index=False)
A=R.groupby("estrategia")[["TP","FP","FN","TN","eventos","blocos_alerta","blocos_alerta_falsos"]].sum()
anos=R.groupby("estrategia").anos.sum()
A["precisao"]=A.TP/(A.TP+A.FP); A["recall"]=A.TP/(A.TP+A.FN)
for c in ["TP","FP","FN","TN","eventos","blocos_alerta","blocos_alerta_falsos"]: A[c+"_por_usina_ano"]=A[c]/anos
print(A.round(3).T.to_string()); print("anos teste por usina",R.anos.iloc[0])
