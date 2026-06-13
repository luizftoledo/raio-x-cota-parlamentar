# Raio-X da Cota Parlamentar

Dashboard estática para acompanhar diariamente as despesas da Cota para o Exercício da Atividade Parlamentar (CEAP) dos deputados federais.

## O que ela mostra

- Total gasto no ano até o momento.
- Ranking de parlamentares, partidos, UFs, categorias e fornecedores.
- Maiores documentos individuais, com link para a nota/PDF na Câmara.
- Sinais de atenção para checagem jornalística: documentos altos, concentração em fornecedor, publicidade dominante, possíveis repetidos, limites mensais e pontos fora da curva.
- Filtros por busca textual, partido, UF e categoria.

## Fonte

Os dados vêm do arquivo oficial anual da Câmara:

```text
https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip
```

A documentação oficial informa que esses arquivos são separados por ano e têm atualização diária.

## Rodar localmente

```bash
cd raio-x-cota-parlamentar
python3 scripts/update_ceap.py --year 2026
python3 -m http.server 8000 -d public
```

Depois abra:

```text
http://localhost:8000
```

## Publicar no GitHub Pages

1. Crie um repositório no GitHub e envie esta pasta.
2. Em `Settings > Pages`, escolha `GitHub Actions` como fonte.
3. O workflow `.github/workflows/update-dashboard.yml` vai rodar todo dia às 08:30 UTC e também pode ser acionado manualmente por `workflow_dispatch`.

## Nota metodológica

A Câmara informa que o parlamentar pode apresentar comprovantes em até 90 dias. Por isso, dados do ano corrente podem mudar retroativamente, inclusive valores de meses anteriores.

Os sinais de atenção não são acusações de irregularidade. Eles apenas indicam padrões que merecem checagem.
