#!/usr/bin/env python3
"""Build daily CEAP dashboard data from Camara dos Deputados open data."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import statistics
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


SOURCE_URL = "https://www.camara.leg.br/cotas/Ano-{year}.csv.zip"
FUEL_MONTHLY_LIMIT = Decimal("9392.00")
SECURITY_MONTHLY_LIMIT = Decimal("8700.00")
HIGH_VALUE = Decimal("10000.00")
BRL_Q = Decimal("0.01")


def money(value: Decimal | int | float) -> float:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return float(value.quantize(BRL_Q, rounding=ROUND_HALF_UP))


def parse_money(value: str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    text = str(value).strip()
    if not text:
        return Decimal("0")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def parse_date(value: str | None):
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if "T" in text else text[:10], fmt)
        except ValueError:
            continue
    return None


def clean_text(value: str | None, fallback: str = "Sem informação") -> str:
    text = " ".join((value or "").strip().split())
    return text if text else fallback


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def doc_key(row: dict) -> str:
    parts = [
        digits(row.get("txtCNPJCPF")),
        clean_text(row.get("txtFornecedor"), ""),
        clean_text(row.get("txtNumero"), ""),
        clean_text(row.get("datEmissao"), "")[:10],
        f"{row['vlrLiquidoD']:.2f}",
    ]
    return "|".join(parts)


def percentile(values: list[Decimal], p: float) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((len(ordered) * p) / 100) - 1))
    return ordered[index]


def median_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return Decimal(str(statistics.median(values)))


def mad_threshold(values: list[Decimal], multiplier: Decimal = Decimal("3")) -> Decimal:
    med = median_decimal(values)
    deviations = [abs(value - med) for value in values]
    mad = median_decimal(deviations)
    if mad == 0:
        return med * Decimal("2")
    return med + multiplier * mad


def group_sum(rows: list[dict], *keys: str):
    totals = defaultdict(Decimal)
    counts = Counter()
    for row in rows:
        key = tuple(clean_text(row.get(k)) for k in keys)
        totals[key] += row["vlrLiquidoD"]
        counts[key] += 1
    return totals, counts


def top_from_totals(totals, counts=None, limit=20, key_names=None, extra=None):
    items = []
    for key, total in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]:
        if not isinstance(key, tuple):
            key = (key,)
        row = {key_names[i] if key_names else f"key_{i}": key[i] for i in range(len(key))}
        row["total"] = money(total)
        row["count"] = counts.get(key, 0) if counts else 0
        if extra:
            row.update(extra(key, total))
        items.append(row)
    return items


def fetch_rows(year: int) -> tuple[list[dict], str, int]:
    url = SOURCE_URL.format(year=year)
    request = urllib.request.Request(url, headers={"User-Agent": "raio-x-cota-parlamentar/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read()

    with zipfile.ZipFile(io.BytesIO(content)) as zipped:
        csv_name = [name for name in zipped.namelist() if name.lower().endswith(".csv")][0]
        with zipped.open(csv_name) as handle:
            reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig"), delimiter=";")
            rows = []
            for raw in reader:
                row = {key: (value or "").strip() for key, value in raw.items()}
                row["vlrLiquidoD"] = parse_money(row.get("vlrLiquido"))
                row["vlrDocumentoD"] = parse_money(row.get("vlrDocumento"))
                row["emissaoDt"] = parse_date(row.get("datEmissao"))
                row["pagamentoDt"] = parse_date(row.get("datPagamentoRestituicao"))
                row["deputado"] = clean_text(row.get("txNomeParlamentar"))
                row["partido"] = clean_text(row.get("sgPartido"))
                row["uf"] = clean_text(row.get("sgUF"))
                row["categoria"] = clean_text(row.get("txtDescricao"))
                row["fornecedor"] = clean_text(row.get("txtFornecedor"))
                row["cnpjcpf_digits"] = digits(row.get("txtCNPJCPF"))
                rows.append(row)
    return rows, url, len(content)


def build_alerts(rows: list[dict]) -> list[dict]:
    alerts = []

    by_category_values = defaultdict(list)
    for row in rows:
        if row["vlrLiquidoD"] > 0:
            by_category_values[row["categoria"]].append(row["vlrLiquidoD"])
    p99_by_category = {category: percentile(values, 99) for category, values in by_category_values.items()}

    for row in sorted(rows, key=lambda item: item["vlrLiquidoD"], reverse=True):
        threshold = max(p99_by_category.get(row["categoria"], Decimal("0")), HIGH_VALUE)
        if row["vlrLiquidoD"] >= threshold:
            alerts.append(
                {
                    "type": "Documento alto",
                    "severity": "alta" if row["vlrLiquidoD"] >= Decimal("50000") else "media",
                    "title": f"Despesa alta em {row['categoria'].lower()}",
                    "deputy": row["deputado"],
                    "party": row["partido"],
                    "uf": row["uf"],
                    "supplier": row["fornecedor"],
                    "category": row["categoria"],
                    "value": money(row["vlrLiquidoD"]),
                    "date": (row["emissaoDt"].date().isoformat() if row["emissaoDt"] else ""),
                    "detail": "Valor acima do percentil 99 da categoria ou acima de R$ 10 mil.",
                    "url": row.get("urlDocumento", ""),
                }
            )
        if len([a for a in alerts if a["type"] == "Documento alto"]) >= 40:
            break

    duplicate_groups = defaultdict(list)
    for row in rows:
        key = doc_key(row)
        if key.count("|") == 4 and row["vlrLiquidoD"] > 0:
            duplicate_groups[key].append(row)
    for group in sorted(duplicate_groups.values(), key=len, reverse=True):
        deputies = sorted({row["deputado"] for row in group})
        if len(group) > 1 and len(deputies) > 1:
            row = group[0]
            alerts.append(
                {
                    "type": "Documento repetido",
                    "severity": "media",
                    "title": "Mesmo documento aparece para mais de um parlamentar",
                    "deputy": ", ".join(deputies[:4]),
                    "party": "",
                    "uf": "",
                    "supplier": row["fornecedor"],
                    "category": row["categoria"],
                    "value": money(sum(item["vlrLiquidoD"] for item in group)),
                    "date": (row["emissaoDt"].date().isoformat() if row["emissaoDt"] else ""),
                    "detail": f"{len(group)} registros com mesmo fornecedor, documento, data e valor.",
                    "url": row.get("urlDocumento", ""),
                }
            )
        if len([a for a in alerts if a["type"] == "Documento repetido"]) >= 20:
            break

    deputy_totals = defaultdict(Decimal)
    deputy_supplier_totals = defaultdict(Decimal)
    deputy_category_totals = defaultdict(Decimal)
    for row in rows:
        deputy_key = (row["deputado"], row["partido"], row["uf"])
        deputy_totals[deputy_key] += row["vlrLiquidoD"]
        deputy_supplier_totals[deputy_key + (row["fornecedor"],)] += row["vlrLiquidoD"]
        deputy_category_totals[deputy_key + (row["categoria"],)] += row["vlrLiquidoD"]

    for key, total in sorted(deputy_supplier_totals.items(), key=lambda item: item[1], reverse=True):
        deputy_key = key[:3]
        share = total / deputy_totals[deputy_key] if deputy_totals[deputy_key] else Decimal("0")
        if total >= Decimal("30000") and share >= Decimal("0.60"):
            alerts.append(
                {
                    "type": "Concentração em fornecedor",
                    "severity": "media",
                    "title": "Gasto concentrado em um fornecedor",
                    "deputy": key[0],
                    "party": key[1],
                    "uf": key[2],
                    "supplier": key[3],
                    "category": "",
                    "value": money(total),
                    "date": "",
                    "detail": f"{money(share * 100)}% do gasto anual do parlamentar está nesse fornecedor.",
                    "url": "",
                }
            )
        if len([a for a in alerts if a["type"] == "Concentração em fornecedor"]) >= 20:
            break

    for key, total in sorted(deputy_category_totals.items(), key=lambda item: item[1], reverse=True):
        deputy_key = key[:3]
        share = total / deputy_totals[deputy_key] if deputy_totals[deputy_key] else Decimal("0")
        if key[3].startswith("DIVULGAÇÃO") and total >= Decimal("50000") and share >= Decimal("0.70"):
            alerts.append(
                {
                    "type": "Publicidade dominante",
                    "severity": "media",
                    "title": "Divulgação domina os gastos do parlamentar",
                    "deputy": key[0],
                    "party": key[1],
                    "uf": key[2],
                    "supplier": "",
                    "category": key[3],
                    "value": money(total),
                    "date": "",
                    "detail": f"{money(share * 100)}% da cota usada no ano foi para divulgação.",
                    "url": "",
                }
            )
        if len([a for a in alerts if a["type"] == "Publicidade dominante"]) >= 20:
            break

    monthly_category = defaultdict(Decimal)
    for row in rows:
        month = clean_text(row.get("numMes"), "0").zfill(2)
        key = (row["deputado"], row["partido"], row["uf"], row["categoria"], month)
        monthly_category[key] += row["vlrLiquidoD"]
    for key, total in sorted(monthly_category.items(), key=lambda item: item[1], reverse=True):
        limit = None
        if key[3].startswith("COMBUST"):
            limit = FUEL_MONTHLY_LIMIT
        elif key[3].startswith("SERVIÇO DE SEGURANÇA"):
            limit = SECURITY_MONTHLY_LIMIT
        if limit and total > limit:
            alerts.append(
                {
                    "type": "Limite mensal",
                    "severity": "alta",
                    "title": "Categoria passou do limite mensal informado pela Câmara",
                    "deputy": key[0],
                    "party": key[1],
                    "uf": key[2],
                    "supplier": "",
                    "category": key[3],
                    "value": money(total),
                    "date": f"Mês {key[4]}",
                    "detail": f"Total mensal acima de R$ {money(limit):,.2f}. Verificar glosas/parcelas e enquadramento.",
                    "url": "",
                }
            )
        if len([a for a in alerts if a["type"] == "Limite mensal"]) >= 20:
            break

    by_category_deputy = defaultdict(lambda: defaultdict(Decimal))
    for row in rows:
        by_category_deputy[row["categoria"]][(row["deputado"], row["partido"], row["uf"])] += row["vlrLiquidoD"]
    for category, totals in by_category_deputy.items():
        values = list(totals.values())
        threshold = mad_threshold(values)
        for key, total in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:8]:
            if total >= Decimal("30000") and total > threshold:
                alerts.append(
                    {
                        "type": "Fora da curva na categoria",
                        "severity": "baixa",
                        "title": "Parlamentar bem acima dos pares na categoria",
                        "deputy": key[0],
                        "party": key[1],
                        "uf": key[2],
                        "supplier": "",
                        "category": category,
                        "value": money(total),
                        "date": "",
                        "detail": "Total acima de mediana + 3*MAD entre parlamentares da mesma categoria.",
                        "url": "",
                    }
                )

    missing_doc_totals = defaultdict(Decimal)
    for row in rows:
        doc = row["cnpjcpf_digits"]
        if row["vlrLiquidoD"] >= Decimal("5000") and len(doc) not in (11, 14):
            missing_doc_totals[(row["fornecedor"], row["categoria"])] += row["vlrLiquidoD"]
    for key, total in sorted(missing_doc_totals.items(), key=lambda item: item[1], reverse=True)[:15]:
        alerts.append(
            {
                "type": "Documento de fornecedor ausente/incomum",
                "severity": "baixa",
                "title": "Fornecedor com CNPJ/CPF ausente ou fora do padrão",
                "deputy": "",
                "party": "",
                "uf": "",
                "supplier": key[0],
                "category": key[1],
                "value": money(total),
                "date": "",
                "detail": "Soma de registros altos com identificador do fornecedor ausente ou diferente de 11/14 dígitos.",
                "url": "",
            }
        )

    return alerts[:180]


def build_dashboard(rows: list[dict], year: int, source_url: str, source_bytes: int) -> dict:
    rows = [row for row in rows if row["vlrLiquidoD"] != 0]
    dates = [row["emissaoDt"] for row in rows if row["emissaoDt"]]
    total = sum(row["vlrLiquidoD"] for row in rows)

    deputies = {(row["deputado"], row["partido"], row["uf"]) for row in rows if row["deputado"] != "LID.GOV-CD"}
    suppliers = {row["fornecedor"] for row in rows}

    deputy_totals, deputy_counts = group_sum(rows, "deputado", "partido", "uf")
    category_totals, category_counts = group_sum(rows, "categoria")
    party_totals, party_counts = group_sum(rows, "partido")
    uf_totals, uf_counts = group_sum(rows, "uf")
    supplier_totals, supplier_counts = group_sum(rows, "fornecedor", "txtCNPJCPF")

    main_category_by_deputy = {}
    main_supplier_by_deputy = {}
    publicity_by_deputy = defaultdict(Decimal)
    for row in rows:
        dkey = (row["deputado"], row["partido"], row["uf"])
        if row["categoria"].startswith("DIVULGAÇÃO"):
            publicity_by_deputy[dkey] += row["vlrLiquidoD"]

    deputy_category = defaultdict(Decimal)
    deputy_supplier = defaultdict(Decimal)
    for row in rows:
        dkey = (row["deputado"], row["partido"], row["uf"])
        deputy_category[dkey + (row["categoria"],)] += row["vlrLiquidoD"]
        deputy_supplier[dkey + (row["fornecedor"],)] += row["vlrLiquidoD"]
    for key, value in deputy_category.items():
        dkey = key[:3]
        if dkey not in main_category_by_deputy or value > main_category_by_deputy[dkey][1]:
            main_category_by_deputy[dkey] = (key[3], value)
    for key, value in deputy_supplier.items():
        dkey = key[:3]
        if dkey not in main_supplier_by_deputy or value > main_supplier_by_deputy[dkey][1]:
            main_supplier_by_deputy[dkey] = (key[3], value)

    top_deputies = top_from_totals(
        deputy_totals,
        deputy_counts,
        80,
        ["deputy", "party", "uf"],
        lambda key, total: {
            "avg_doc": money(total / deputy_counts[key]) if deputy_counts[key] else 0,
            "main_category": main_category_by_deputy.get(key, ("", Decimal("0")))[0],
            "main_supplier": main_supplier_by_deputy.get(key, ("", Decimal("0")))[0],
            "publicity_share": money((publicity_by_deputy[key] / total * 100) if total else Decimal("0")),
        },
    )

    supplier_deputies = defaultdict(set)
    supplier_parties = defaultdict(set)
    supplier_categories = defaultdict(Counter)
    for row in rows:
        skey = (row["fornecedor"], row.get("txtCNPJCPF", ""))
        supplier_deputies[skey].add(row["deputado"])
        supplier_parties[skey].add(row["partido"])
        supplier_categories[skey][row["categoria"]] += 1

    top_suppliers = top_from_totals(
        supplier_totals,
        supplier_counts,
        80,
        ["supplier", "cnpjcpf"],
        lambda key, total: {
            "deputies": len(supplier_deputies[key]),
            "parties": len(supplier_parties[key]),
            "avg_doc": money(total / supplier_counts[key]) if supplier_counts[key] else 0,
            "main_category": supplier_categories[key].most_common(1)[0][0] if supplier_categories[key] else "",
        },
    )

    top_docs = []
    for row in sorted(rows, key=lambda item: item["vlrLiquidoD"], reverse=True)[:100]:
        top_docs.append(
            {
                "deputy": row["deputado"],
                "party": row["partido"],
                "uf": row["uf"],
                "category": row["categoria"],
                "supplier": row["fornecedor"],
                "cnpjcpf": row.get("txtCNPJCPF", ""),
                "value": money(row["vlrLiquidoD"]),
                "date": row["emissaoDt"].date().isoformat() if row["emissaoDt"] else "",
                "month": int(row.get("numMes") or 0),
                "document": row.get("txtNumero", ""),
                "url": row.get("urlDocumento", ""),
            }
        )

    monthly = defaultdict(Decimal)
    monthly_category = defaultdict(Decimal)
    for row in rows:
        month = int(row.get("numMes") or 0)
        if month:
            monthly[month] += row["vlrLiquidoD"]
            monthly_category[(month, row["categoria"])] += row["vlrLiquidoD"]
    monthly_rows = [{"month": month, "total": money(monthly[month])} for month in sorted(monthly)]
    monthly_category_rows = [
        {"month": month, "category": category, "total": money(value)}
        for (month, category), value in sorted(monthly_category.items())
    ]

    weekday = defaultdict(Decimal)
    for row in rows:
        if row["emissaoDt"]:
            weekday[row["emissaoDt"].weekday()] += row["vlrLiquidoD"]
    weekday_names = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
    weekday_rows = [{"weekday": weekday_names[index], "total": money(weekday[index])} for index in range(7)]

    alerts = build_alerts(rows)
    alert_counts = Counter(alert["type"] for alert in alerts)

    return {
        "meta": {
            "year": year,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_url": source_url,
            "source_bytes": source_bytes,
            "methodology_note": (
                "A Câmara permite apresentação de comprovantes em até 90 dias; "
                "dados do ano corrente podem mudar retroativamente."
            ),
        },
        "summary": {
            "total": money(total),
            "documents": len(rows),
            "deputies": len(deputies),
            "suppliers": len(suppliers),
            "categories": len(category_totals),
            "first_date": min(dates).date().isoformat() if dates else "",
            "last_date": max(dates).date().isoformat() if dates else "",
            "avg_per_deputy": money(total / len(deputies)) if deputies else 0,
            "avg_per_doc": money(total / len(rows)) if rows else 0,
            "alerts": len(alerts),
        },
        "rankings": {
            "deputies": top_deputies,
            "categories": top_from_totals(category_totals, category_counts, 40, ["category"]),
            "suppliers": top_suppliers,
            "parties": top_from_totals(party_totals, party_counts, 40, ["party"]),
            "ufs": top_from_totals(uf_totals, uf_counts, 40, ["uf"]),
            "documents": top_docs,
        },
        "series": {
            "monthly": monthly_rows,
            "monthly_category": monthly_category_rows,
            "weekday": weekday_rows,
        },
        "alerts": alerts,
        "alert_counts": [{"type": key, "count": value} for key, value in alert_counts.most_common()],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--out", type=Path, default=Path("public/data/dashboard.json"))
    parser.add_argument("--raw-out", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    rows, source_url, source_bytes = fetch_rows(args.year)
    args.raw_out.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    dashboard = build_dashboard(rows, args.year, source_url, source_bytes)
    args.out.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Generated {args.out} with {dashboard['summary']['documents']} records "
        f"and R$ {dashboard['summary']['total']:,.2f}."
    )


if __name__ == "__main__":
    main()
