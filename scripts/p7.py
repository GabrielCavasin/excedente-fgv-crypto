import pandas as pd, numpy as np, copy, sys, json, datetime as dt
sys.path.insert(0,"."); import pipeline as P
# fator 2028 por dias, halving estimado: bloco 840.000 em 20/04/2024 + 210.000 blocos x 10 min
h=dt.date(2024,4,20)+dt.timedelta(minutes=210000*10); print("halving estimado",h)
d0=(h-dt.date(2028,1,1)).days; f=(d0+0.5*(366-d0))/366; print("dias antes",d0,"fator",round(f,4))
def base(path):
    E=pd.read_csv(path); return E[(E.asic=="S19j XP")&(E.latencia_min==5)&(E.cenario_hp=="x1.0")].copy()
OF=base("resultados/censo_oficial/economia_por_usina.csv"); EN=base("resultados/censo_oficial_ENE/economia_por_usina.csv")
C={"Base":({},6),"Combinado":(dict(infra_usd_mw=125000,taxa_desconto=.12),3),"Combinado + energia grátis":(dict(infra_usd_mw=125000,taxa_desconto=.12,preco_energia_brl_mwh=0.),3)}
def cnt(b,k,usd,mult,em=1.0):
    p=copy.deepcopy(P.PARAM); p.update(k); a=dict(p["asics"]["S19j XP"]); a["usd_th"]=usd; o={}
    for cap in (1,5,10):
        x=b[b.cap_mw==cap]; v=np.array([P.economia(r.energia_mwh_ano*em,r.receita_brl_mwh,p["preco_energia_brl_mwh"],cap,a,mult,p)["vpl"] for r in x.itertuples()]); o[cap]=int((v>0).sum())
    return o
out={}
for nm,(k,usd) in C.items():
    for fl,m in [("0,67 (v6)",[1,.67,.5,.5]),(f"{f:.3f} (por dias)",[1,f,.5,.5]),("0,64",[1,.64,.5,.5])]:
        out[(nm,"fator "+fl)]=cnt(OF,k,usd,m)
    out[(nm,"fator por dias, só ENE")]=cnt(EN,k,usd,[1,f,.5,.5])
    out[(nm,"disponibilidade 90%")]=cnt(OF,k,usd,[1,f,.5,.5],em=.9)
    out[(nm,"captura 80%")]=cnt(OF,k,usd,[1,f,.5,.5],em=.8)
    out[(nm,"captura 120%")]=cnt(OF,k,usd,[1,f,.5,.5],em=1.2)
    out[(nm,"padrão 2024 (ilustrativo)")]=cnt(OF,k,usd,[1,f*0+0.6855 if False else (d0/366*1+(366-d0)/366*.556),.52,.49])
    out[(nm,"sem halving")]=cnt(OF,k,usd,[1,1,1,1])
for k,v in out.items(): print(k,v)
json.dump({" | ".join(k):v for k,v in out.items()}|{"fator_2028":f,"halving_est":str(h)},open("p7.json","w"),ensure_ascii=False)
