#!/usr/bin/env python3
"""Análise do stg_erp no dwxodo — requer az login + ODBC Driver 18."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys

import pyodbc

SQL_COPT_SS_ACCESS_TOKEN = 1256
SUBSCRIPTION = os.environ.get("COCKPIT_AZURE_SUBSCRIPTION", "DataOpsXodo")
SERVER = os.environ.get("COCKPIT_AZURE_SQL_SERVER", "dwxodo.database.windows.net")
DATABASE = os.environ.get("COCKPIT_AZURE_SQL_DATABASE", "dwxodo")


def get_token() -> str:
    result = subprocess.run(
        [
            "az",
            "account",
            "get-access-token",
            "--subscription",
            SUBSCRIPTION,
            "--resource",
            "https://database.windows.net/",
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    token = (result.stdout or "").strip()
    if result.returncode != 0 or not token:
        raise RuntimeError(f"az login required: {result.stderr.strip()}")
    return token


def connect() -> pyodbc.Connection:
    token = get_token()
    token_bytes = token.encode("utf-16-le")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SERVER},1433;"
        f"DATABASE={DATABASE};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=60;"
    )
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})


QUERIES: dict[str, str] = {
    "1_stg_tables": """
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'stg_erp'
          AND TABLE_NAME LIKE '%bancoxodo%'
        ORDER BY TABLE_NAME
    """,
    "2_produto_12122": """
        SELECT pro_codigo, pro_desc, pro_descres, pro_tpicodigo, pro_ativo
        FROM stg_erp.stg_bancoxodo__produto
        WHERE pro_codigo = 12122
    """,
    "3_unidades_12122": """
        SELECT unp_procodigo, unp_unidade, unp_quantidade, unp_fatestoque,
               unp_padestoque, unp_DescEmb, unp_ativo
        FROM stg_erp.stg_bancoxodo__unidadepro
        WHERE unp_procodigo = 12122
        ORDER BY unp_padestoque DESC, unp_unidade
    """,
    "4_op_48335": """
        SELECT OPP_NUMERO, opp_procodigo, opp_numlote, opp_dtvenc,
               opp_unpunidade, opp_unpquant, opp_qtdeordem, opp_qtdeproduz
        FROM stg_erp.stg_bancoxodo__ordemproducao
        WHERE OPP_NUMERO = 48335 AND opp_procodigo = 12122
    """,
    "5_multi_unidade_top30": """
        SELECT TOP 30 p.pro_codigo, p.pro_descres,
               COUNT(*) AS qtd_unidades,
               SUM(CASE WHEN u.unp_padestoque = 1 THEN 1 ELSE 0 END) AS tem_unidade_estoque
        FROM stg_erp.stg_bancoxodo__produto p
        JOIN stg_erp.stg_bancoxodo__unidadepro u ON u.unp_procodigo = p.pro_codigo
        WHERE p.pro_ativo = 1 AND u.unp_ativo = 1
        GROUP BY p.pro_codigo, p.pro_descres
        HAVING COUNT(*) > 1
        ORDER BY qtd_unidades DESC
    """,
    "6_razao_qtd_fat": """
        SELECT TOP 50 unp_procodigo, unp_unidade, unp_quantidade, unp_fatestoque,
               unp_padestoque,
               CAST(unp_quantidade AS float) / NULLIF(unp_fatestoque, 0) AS razao_qtd_fat
        FROM stg_erp.stg_bancoxodo__unidadepro
        WHERE unp_ativo = 1 AND unp_padestoque = 0
        ORDER BY unp_procodigo, unp_unidade
    """,
    "7_sem_unidade_estoque": """
        SELECT TOP 20 p.pro_codigo, p.pro_descres
        FROM stg_erp.stg_bancoxodo__produto p
        WHERE p.pro_ativo = 1
          AND NOT EXISTS (
            SELECT 1 FROM stg_erp.stg_bancoxodo__unidadepro u
            WHERE u.unp_procodigo = p.pro_codigo
              AND u.unp_padestoque = 1 AND u.unp_ativo = 1
          )
    """,
    "8_unidade_base_amostra": """
        SELECT TOP 20 u.unp_procodigo, p.pro_descres, u.unp_unidade,
               u.unp_quantidade, u.unp_fatestoque
        FROM stg_erp.stg_bancoxodo__unidadepro u
        JOIN stg_erp.stg_bancoxodo__produto p ON p.pro_codigo = u.unp_procodigo
        WHERE u.unp_padestoque = 1 AND u.unp_ativo = 1 AND p.pro_ativo = 1
        ORDER BY u.unp_procodigo
    """,
}


def run_query(cursor: pyodbc.Cursor, sql: str) -> list[dict]:
    cursor.execute(sql)
    if cursor.description is None:
        return []
    cols = [c[0] for c in cursor.description]
    rows = []
    for row in cursor.fetchall():
        rows.append({cols[i]: row[i] for i in range(len(cols))})
    return rows


def main() -> int:
    results: dict[str, list[dict]] = {}
    with connect() as conn:
        cur = conn.cursor()
        for name, sql in QUERIES.items():
            try:
                results[name] = run_query(cur, sql)
            except Exception as exc:  # noqa: BLE001
                results[name] = [{"error": str(exc)}]

    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
