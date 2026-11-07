import pandas as pd, numpy as np, re
K=r"^([A-Z]{3})\.[A-Z]{2}\.([A-Z]{2})\.(\d{6})"
s=pd.read_csv("dados/siga-empreendimentos-geracao.csv",sep=";",encoding="utf-16",dtype=str)
s["lat"]=pd.to_numeric(s.NumLatitude.str.replace(",","."),errors="coerce"); s["lon"]=pd.to_numeric(s.NumLongitude.str.replace(",","."),errors="coerce")
k=s.CodCEG.str.extract(K); s["core"]=k[0]+"."+k[1]+"."+k[2]
s=s.dropna(subset=["lat","lon","core"]); s=s[(s.lat.between(-34,6))&(s.lon.between(-74,-34))]
sc=s.groupby("core")[["lat","lon"]].mean()
R=pd.read_csv("br_usinas.csv"); k=R.ceg.astype(str).str.extract(K); R["core"]=k[0]+"."+k[1]+"."+k[2]
R=R.merge(sc,left_on="core",right_index=True,how="left"); R["pos"]=np.where(R.lat.notna(),"ceg","")
BB={"BA":(-18.4,-8.5,-46.7,-37.3),"RN":(-6.99,-4.8,-38.6,-34.9),"CE":(-7.9,-2.7,-41.5,-37.2),"PI":(-10.95,-2.7,-45.99,-40.3),"PE":(-9.5,-7.3,-41.4,-34.8),"PB":(-8.3,-6.0,-38.8,-34.7),"MA":(-10.3,-1.0,-48.8,-41.8),"RS":(-33.8,-27.0,-57.7,-49.6),"SC":(-29.4,-25.9,-53.9,-48.3),"MG":(-22.95,-14.2,-51.1,-39.8),"SP":(-25.4,-19.7,-53.2,-44.1)}
def fora(r):
    b=BB.get(r.uf); return pd.notna(r.lat) and b is not None and not (b[0]<=r.lat<=b[1] and b[2]<=r.lon<=b[3])
bad=R.apply(fora,axis=1); print("coordenada fora da UF no SIGA:",R.loc[bad,"nome"].tolist())
R.loc[bad,["lat","lon"]]=np.nan; R.loc[bad,"pos"]="corrigida"
g=R[R.lat.notna()].groupby("conj")[["lat","lon"]].mean()
m=R.lat.isna()&R.conj.isin(g.index); R.loc[m,["lat","lon"]]=g.loc[R.loc[m,"conj"]].values; R.loc[m&(R.pos==""),"pos"]="conjunto"
def base(x): return re.sub(r"[\s\-]*(\d+|[IVXL]+)$","",str(x).strip()).strip().lower()
R["base"]=R.nome.map(base)
g2=R[R.lat.notna()].groupby(["uf","base"])[["lat","lon"]].mean()
m=R.lat.isna(); keys=list(zip(R.loc[m,"uf"],R.loc[m,"base"])); ok=[kk in g2.index for kk in keys]; idx=R.index[m][ok]
if len(idx): R.loc[idx,["lat","lon"]]=g2.loc[[kk for kk,o in zip(keys,ok) if o]].values; R.loc[idx,"pos"]="complexo"
rng=np.random.default_rng(7); cu=R[R.lat.notna()].groupby("uf")[["lat","lon"]].median()
for i in R.index[R.lat.isna()]:
    uf=R.at[i,"uf"]; R.loc[i,["lat","lon"]]=[cu.loc[uf,"lat"]+rng.normal(0,.3),cu.loc[uf,"lon"]+rng.normal(0,.3)]; R.at[i,"pos"]="aproximada"
print(R.pos.value_counts().to_dict(), "fora restantes:",R.apply(fora,axis=1).sum(), len(R))
print(R[R.nome=="Delfina III"][["lat","lon","pos"]].to_dict("records"))
R.to_csv("br_usinas_geo.csv",index=False)
