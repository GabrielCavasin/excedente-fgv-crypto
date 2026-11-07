import pandas as pd, numpy as np, copy, json, sys
sys.path.insert(0,".")
import pipeline as P
E=pd.read_csv("resultados/censo_oficial/economia_por_usina.csv")
S=pd.read_csv("resultados/censo_oficial/usinas_selecionadas.csv")
b=E[(E.asic=="S19j XP")&(E.latencia_min==5)&(E.cenario_hp=="x1.0")].copy()
b=b.merge(S[["usina","nome"]],on="usina",how="left")
A=P.PARAM["asics"]["S19j XP"]
b["hp_medio_ponderado"]=b.receita_brl_mwh*A["jth"]*0.024/P.PARAM["cambio"]
def vpl(row,s,mult,p=P.PARAM):
    a=p["asics"]["S19j XP"]; return P.economia(row.energia_mwh_ano,row.receita_brl_mwh*s,p["preco_energia_brl_mwh"],row.cap_mw,a,mult,p)["vpl"]
def hp_eq(row,mult):
    lo,hi=0.05,60
    if row.energia_mwh_ano<=0: return np.nan
    for _ in range(45):
        m=(lo+hi)/2
        lo,hi=(m,hi) if vpl(row,m,mult)<0 else (lo,m)
    return m*row.hp_medio_ponderado
b["hp_eq_sem_halving"]=[hp_eq(r,[1]*4) for r in b.itertuples()]
b["hp_eq_com_halving"]=[hp_eq(r,P.PARAM["perfil_halving"]) for r in b.itertuples()]
b.to_csv("usinas_painel.csv",index=False)
pct=b.groupby(["fonte","cap_mw"]).utilizacao_obtida.quantile([.1,.25,.5,.75,.9]).unstack()
pct["max"]=b.groupby(["fonte","cap_mw"]).utilizacao_obtida.max(); pct["n"]=b.groupby(["fonte","cap_mw"]).usina.nunique()
pct["n_45"]=b[b.utilizacao_obtida>=.45].groupby(["fonte","cap_mw"]).usina.nunique()
allp=b.groupby("cap_mw").utilizacao_obtida.quantile([.1,.25,.5,.75,.9]).unstack(); allp["max"]=b.groupby("cap_mw").utilizacao_obtida.max(); allp["n_45"]=b[b.utilizacao_obtida>=.45].groupby("cap_mw").usina.nunique()
print((pct*1).round(3)); print(allp.round(3))
print(b.groupby("cap_mw")[["hp_eq_sem_halving","hp_eq_com_halving"]].describe(percentiles=[.5]).round(1).T)
# contagem por cenario com halving
cen={"Base":{}, "Taxa 15%":dict(taxa_desconto=.15),"Taxa 12%":dict(taxa_desconto=.12),"S19j XP usado US$3/TH":dict(asic_usd=3),
"Infra US$125 mil/MW":dict(infra_usd_mw=125000),"Energia R$30":dict(preco_energia_brl_mwh=30.),"Energia R$0":dict(preco_energia_brl_mwh=0.),
"Câmbio 5,46":dict(cambio=5.46),"Hashprice +20%":dict(hp=1.2),"Usado + infra 125 + 12%":dict(asic_usd=3,infra_usd_mw=125000,taxa_desconto=.12),
"Usado + infra 125 + 12% + energia R$0":dict(asic_usd=3,infra_usd_mw=125000,taxa_desconto=.12,preco_energia_brl_mwh=0.)}
out=[]
for nome,k in cen.items():
    p=copy.deepcopy(P.PARAM); s=k.get("hp",1.0)
    for kk,v in k.items():
        if kk in p: p[kk]=v
    a=dict(p["asics"]["S19j XP"]); 
    if "asic_usd" in k: a["usd_th"]=k["asic_usd"]
    fx=p["cambio"]/P.PARAM["cambio"]
    for hv,mult in [("sem",[1]*4),("com",p["perfil_halving"])]:
        v=np.array([P.economia(r.energia_mwh_ano,r.receita_brl_mwh*s*fx,p["preco_energia_brl_mwh"],r.cap_mw,a,mult,p)["vpl"] for r in b.itertuples()])
        row={"cenario":nome,"halving":hv}
        for cap in (1,5,10): row[f"{cap} MW"]=int((v[(b.cap_mw==cap).values]>0).sum())
        out.append(row)
C=pd.DataFrame(out); C.to_csv("contagem_cenarios.csv",index=False); print(C.to_string(index=False))
json.dump(dict(pct=pct.reset_index().to_dict("records"),allp=allp.reset_index().to_dict("records")),open("dist.json","w"),default=float)
