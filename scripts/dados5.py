import pandas as pd, numpy as np, json, copy, sys
sys.path.insert(0,"."); import pipeline as P
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
b=pd.read_csv("usinas_painel.csv"); HPW=35.4377
REF_HP,REF_BTC=36.538,77822
btc=lambda hp: REF_BTC*hp/REF_HP
# hp_eq no cenario combinado (usado+infra125+12%) com halving
p=copy.deepcopy(P.PARAM); p.update(infra_usd_mw=125000,taxa_desconto=.12); a=dict(p["asics"]["S19j XP"]); a["usd_th"]=3
def hpq(r,mult,p,a):
    lo,hi=.05,60
    for _ in range(45):
        m=(lo+hi)/2; v=P.economia(r.energia_mwh_ano,r.receita_brl_mwh*m,p["preco_energia_brl_mwh"],r.cap_mw,a,mult,p)["vpl"]
        lo,hi=(m,hi) if v<0 else (lo,m)
    return m*r.hp_medio_ponderado if r.energia_mwh_ano>0 else np.nan
b["hp_eq_comb_halv"]=[hpq(r,p["perfil_halving"],p,a) for r in b.itertuples()]
b.to_csv("usinas_painel5.csv",index=False)
# grafico 1 dispersao
fig,ax=plt.subplots(figsize=(8,4.4))
for cap,mk in [(1,"o")]:
    for f,c in [("eolica","#1f6fb2"),("solar","#c98a12")]:
        g=b[(b.cap_mw==cap)&(b.fonte==f)]; ax.scatter(g.utilizacao_obtida*100,g.hp_eq_com_halving.clip(upper=2000),s=7,alpha=.55,c=c,label=f"{'Eólica' if f=='eolica' else 'Solar'} (1 MW)")
ax.axhline(HPW,color="#b4442c",ls="--",lw=1.2,label="Hashprice médio observado (US$ 35,4)")
ax.set_yscale("log"); ax.set_ylim(20,2000); ax.set_xlim(0,70); ax.set_yticks([20,35.4,50,100,200,500,1000,2000]); ax.set_yticklabels(["20","35","50","100","200","500","1.000","2.000"])
ax.set_xlabel("Utilização do contêiner de 1 MW (% do ano)",fontsize=8); ax.set_ylabel("Hashprice de equilíbrio com halving (US$/PH/dia)",fontsize=8)
ax.set_title("Cada ponto é uma usina: quanto ela opera e de que hashprice precisa",fontsize=9); ax.legend(fontsize=7,frameon=False); ax.tick_params(labelsize=7)
ax.spines[["top","right"]].set_visible(False); plt.tight_layout(); plt.savefig("g_disp.png",dpi=200); plt.close()
# grafico 2 curva usinas viaveis x BTC
xs=np.arange(40000,400001,2500); fig,ax=plt.subplots(figsize=(8,3.6))
for cap,c in [(1,"#0f7a5c"),(5,"#1f6fb2"),(10,"#6b4fa3")]:
    h=np.sort(b[b.cap_mw==cap].hp_eq_com_halving.values); ax.plot(xs/1000,[np.searchsorted(h,x*REF_HP/REF_BTC,side="right") for x in xs],c=c,lw=1.8,label=f"{cap} MW, premissas base")
h=np.sort(b[b.cap_mw==1].hp_eq_comb_halv.values); ax.plot(xs/1000,[np.searchsorted(h,x*REF_HP/REF_BTC,side="right") for x in xs],c="#0f7a5c",ls="--",lw=1.5,label="1 MW, ASIC usado + infra barata + 12%")
ax.axvline(75.7,color="#b4442c",lw=1); ax.text(78,1080,"BTC em 07/11/2026",fontsize=7,color="#b4442c")
ax.set_xlabel("Preço do bitcoin (US$ mil), dificuldade fixa",fontsize=8); ax.set_ylabel("Usinas com VPL positivo",fontsize=8); ax.set_ylim(0,1200)
ax.set_title("Quantas usinas fecham a conta a cada preço do bitcoin (com halving)",fontsize=9); ax.legend(fontsize=7,frameon=False); ax.tick_params(labelsize=7); ax.spines[["top","right"]].set_visible(False)
plt.tight_layout(); plt.savefig("g_curva.png",dpi=200); plt.close()
# grafico 3 conciliacao mensal
M=pd.read_csv("auditoria/2_conciliacao_mensal.csv").dropna(); M=M.groupby("mes")[["TWh_nosso_corte_oficial","TWh_GNR_apurada_ONS_conjuntos"]].sum()
fig,ax=plt.subplots(figsize=(8,3.2)); x=np.arange(len(M))
ax.bar(x-.2,M.TWh_nosso_corte_oficial,.4,color="#1f6fb2",label="Nosso cálculo, soma por usina"); ax.bar(x+.2,M.TWh_GNR_apurada_ONS_conjuntos,.4,color="#a5a5a5",label="GNR apurada pelo ONS, por conjunto")
ax.set_xticks(x); ax.set_xticklabels([m[2:].replace("-","/") for m in M.index],fontsize=6,rotation=90); ax.set_ylabel("TWh",fontsize=8); ax.tick_params(labelsize=7)
ax.set_title("Conciliação mensal do corte no Nordeste (eólica + solar)",fontsize=9); ax.legend(fontsize=7,frameon=False); ax.spines[["top","right"]].set_visible(False)
plt.tight_layout(); plt.savefig("g_conc.png",dpi=200); plt.close()
# grafico 4 histograma utilizacao 1MW por fonte
fig,ax=plt.subplots(figsize=(8,3)); bins=np.arange(0,66,2.5)
for f,c in [("eolica","#1f6fb2"),("solar","#c98a12")]:
    ax.hist(b[(b.cap_mw==1)&(b.fonte==f)].utilizacao_obtida*100,bins=bins,alpha=.7,color=c,label="Eólica" if f=="eolica" else "Solar")
ax.axvline(61.3,color="#b4442c",ls="--",lw=1); ax.text(54,150,"equilíbrio sem halving ~61%",fontsize=7,color="#b4442c",ha="right")
ax.set_xlabel("Utilização do contêiner de 1 MW (% do ano)",fontsize=8); ax.set_ylabel("Número de usinas",fontsize=8); ax.legend(fontsize=7,frameon=False); ax.tick_params(labelsize=7)
ax.set_title("Distribuição da utilização entre as 1.192 usinas",fontsize=9); ax.spines[["top","right"]].set_visible(False); plt.tight_layout(); plt.savefig("g_hist.png",dpi=200); plt.close()
# top 15
t=b[b.cap_mw==1].nsmallest(15,"hp_eq_com_halving")[["usina","nome","estado","fonte","utilizacao_obtida","energia_mwh_ano","hp_eq_sem_halving","hp_eq_com_halving","hp_eq_comb_halv"]]
t.to_csv("top15.csv",index=False); print(t.round(2).to_string(index=False))
# hp eq distribuicao
print(b.groupby("cap_mw")[["hp_eq_sem_halving","hp_eq_com_halving","hp_eq_comb_halv"]].quantile([.1,.5,.9]).round(1))
print(b.groupby("cap_mw")[["hp_eq_sem_halving","hp_eq_com_halving","hp_eq_comb_halv"]].min().round(1))
