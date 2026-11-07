import glob, os, re, numpy as np, pandas as pd, sys
sys.path.insert(0,"."); import pipeline as P
INI,FIM=pd.Timestamp("2025-11-01"),pd.Timestamp("2026-11-01")
grade=pd.date_range(INI,FIM,freq="30min",inclusive="left"); N=len(grade)
# razao por conjunto (todos os subsistemas)
fr=[]
for p in sorted(glob.glob("dados/ons_conj/*.parquet")):
    m=re.search(r"(\d{4})_(\d{2})",p).groups()
    if not (("2025","11")<=m<=("2026","10")): continue
    d=pd.read_parquet(p,columns=["id_ons","din_instante","cod_razaorestricao","id_subsistema"]); fr.append(d)
C=pd.concat(fr).drop_duplicates(["id_ons","din_instante"]); C=C[C.cod_razaorestricao.notna()][["id_ons","din_instante","cod_razaorestricao"]]
print("conj",len(C))
S={}; META={}; TOT={}
for p in sorted(glob.glob("dados/ons/*.parquet")):
    fonte="eolica" if "EOLICA" in p else "solar"
    d=pd.read_parquet(p,columns=["id_subsistema","id_estado","nom_usina","id_ons","ceg","id_ons_conjuntousina","din_instante","val_geracaoestimada","val_geracaoverificada","val_geracaoreferenciafinal"])
    d=d[(d.din_instante>=INI)&(d.din_instante<FIM)]
    d["chave"]=d.id_ons_conjuntousina.fillna(d.id_ons)
    d=d.merge(C,how="left",left_on=["chave","din_instante"],right_on=["id_ons","din_instante"],suffixes=("","_c"))
    ref=d.val_geracaoreferenciafinal.fillna(d.val_geracaoestimada)
    d["gap"]=(ref-d.val_geracaoverificada); d=d.dropna(subset=["gap"]); d["corte"]=d.gap.clip(lower=0).where(d.cod_razaorestricao.notna(),0.0)
    d=d.dropna(subset=["corte"]).drop_duplicates(["id_ons","din_instante"])
    idx=((d.din_instante-INI)/pd.Timedelta("30min")).astype(int).values
    for (u,),g in d.groupby(["id_ons"]):
        if u not in S:
            S[u]=np.zeros(N,np.float32); META[u]=dict(nome=g.nom_usina.iloc[0],uf=g.id_estado.iloc[0],sub=g.id_subsistema.iloc[0],ceg=g.ceg.iloc[0],fonte=fonte,conj=g.id_ons_conjuntousina.iloc[0]); TOT[u]=0
        ii=idx[g.index.map(d.index.get_loc)] if False else ((g.din_instante-INI)/pd.Timedelta("30min")).astype(int).values
        S[u][ii]=g.corte.values.astype(np.float32); TOT[u]+=len(g)
    print(os.path.basename(p),len(d),len(S),flush=True)
hp=P.ler_hashprice("dados/hashprice.csv"); hpd=hp.reindex(grade.normalize()).ffill().bfill().values
HPW=hp[(hp.index>=INI)&(hp.index<FIM)].mean()
rows=[]
for u,s in S.items():
    cob=TOT[u]/N
    if cob<0.95: continue
    m=META[u]; r=dict(usina=u,**m,cobertura=cob,corte_mwh=float(s.sum()*.5))
    for cap in (1,5,10):
        e,nev=P.captura_reativa(s.astype(float),cap,5); E=e.sum()
        r[f"e{cap}"]=E; r[f"f{cap}"]=((e*hpd).sum()/E/HPW) if E>0 else 1.0
    rows.append(r)
R=pd.DataFrame(rows); R.to_csv("br_usinas.csv",index=False)
print(len(R), R.groupby(["sub","fonte"]).usina.count(), R.groupby("sub").corte_mwh.sum()/1e6)
