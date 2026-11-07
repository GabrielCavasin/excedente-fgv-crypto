# Projeto Excedente (FGV Crypto)

Energia renovável cortada é suficiente para remunerar a mineração de Bitcoin? Avaliação por usina, com dados semi-horários do ONS, de 1.192 usinas eólicas e solares do Nordeste (censo complementar de 1.517 usinas do Brasil).

- Documento técnico: `docs/Excedente_v7_documento_tecnico.pdf`
- Painel: https://monitor-excedente.vercel.app (código em `monitor/index.html`)

## Resultado principal (contêiner de 1 MW, halving estimado em 17/04/2028)

| Cenário | Todas as razões de corte | Recorte conservador apenas ENE |
|---|---|---|
| Base | 0 | 0 |
| Combinado (ASIC usado US$ 3/TH, infra US$ 125 mil/MW, taxa 12%) | 148 | 0 |
| Combinado + energia grátis | 309 | 0 |

## Ambiente

Python 3.11 ou superior e as versões em `requirements.txt`:

    pip install -r requirements.txt

## Dados de entrada (não versionados por tamanho)

Coloque em `dados/`:

1. `dados/ons/`: RESTRICAO_COFF_EOLICA_DETAIL_AAAA_MM.parquet e RESTRICAO_COFF_FOTOVOLTAICA_DETAIL_AAAA_MM.parquet, jan/2025 a nov/2026, de https://dados.ons.org.br (datasets restricao_coff_eolica_detail e restricao_coff_fotovoltaica_detail).
2. `dados/ons_conj/`: RESTRICAO_COFF_EOLICA_AAAA_MM.parquet e RESTRICAO_COFF_FOTOVOLTAICA_AAAA_MM.parquet (datasets por conjunto).
3. `dados/hashprice.csv`: série diária de hashprice (cópia em `resultados/hashprice_diario.csv`).
4. `dados/siga-empreendimentos-geracao.csv`: cadastro SIGA da ANEEL, usado só para coordenadas.

Os dados usados no estudo foram baixados em 06/11/2026 às 03h12 UTC. O ONS pode revisar dados publicados; os hashes SHA-256 dos 92 arquivos estão em `auditoria/7_hash_arquivos.csv`.

## Como reproduzir

    python scripts/pipeline.py --censo --saida resultados/censo_oficial
    python scripts/pipeline.py --censo --razoes ENE --saida resultados/censo_oficial_ENE
    python scripts/pipeline.py --censo --definicao conservador --saida resultados/censo_conservador
    python scripts/pipeline.py --saida resultados/amostra_oficial
    python scripts/porusina.py
    python scripts/p7.py
    python scripts/br_censo.py && python scripts/br_censo_ene.py && python scripts/geo.py
    python scripts/auditoria_ons_conciliacao.py
    python scripts/previsao_matriz_confusao.py

Rode os scripts a partir da raiz do repositório. A conciliação usa cerca de 6 GB de RAM.

## Auditoria (pasta `auditoria/`)

- `1_log_ingestao.csv` e `8_funil_janela_economica.csv`: linhas por arquivo e motivo de exclusão.
- `2_conciliacao_mensal.csv`: nosso corte contra a GNR apurada pelo ONS, por mês e fonte (2,2% na janela).
- `11_conferencia_manual_intervalos.csv`: 12 intervalos refeitos do arquivo bruto.
- `9_matriz_confusao_previsao.csv`: matriz de confusão da previsão (intervalos de 30 min).

## Premissas principais

S19j XP (21,5 J/TH) a US$ 6/TH; infraestrutura US$ 250 mil/MW; energia R$ 60/MWh; O&M 8% + R$ 120 mil/MW/ano; PIS/COFINS 9,25%; IR/CSLL 34%; taxa 20%; câmbio 5,20; vida de 4 anos (2027 a 2030); receita de 2028 a 64,6% pelo halving. Preços de ASIC e infraestrutura são referências de mercado, não orçamentos.
