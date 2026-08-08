# Inventário Rotativo — Design Spec

Web application for rotating stock inventory (cycle counting). Operators count stock via barcode labels or manual entry. Admins import ERP data, classify products, and export count reports.

## Problem Statement

Warehouse operators need to quickly count stock during rotating inventory cycles. Each product label encodes a production order and product code. The operator must segment counts by item type, group, and subgroup, submit one count per scan, and admins must export results for a date range.

## Constraints

- Product, unit, and production order data already exists in Azure SQL (`stg_erp` schema, read-only for the app), populated by external ETL — **no admin CSV import in MVP**.
- Item type comes from ERP (`pro_tpicodigo`, string); group and subgroup are classified in the app (separate from ERP `grupopro`/`subgrupopro` staging tables).
- App does **not** move stock — it records counts and exports data for ERP import.
- Multiple operators work simultaneously with persistent filter selections.
- Mobile-first: operators use phone/tablet camera for barcode scanning.
- Two roles: Operador (count) and Admin (import, classify, export).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Celular / Tablet (PWA React)                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐ │
│  │ Operador │  │  Admin   │  │ Câmera (html5-qrcode)│ │
│  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘ │
└───────┼─────────────┼─────────────────────┼─────────────┘
        │             │                     │
        └─────────────┴──── HTTPS / JWT ──────┘
                              │
                    ┌─────────▼─────────┐
                    │  ASP.NET Core API │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │    Azure SQL      │
                    │  stg_erp (read)   │
                    │ inventario (r/w)  │
                    └───────────────────┘
```

### Projects

| Project | Stack | Deploy |
|---------|-------|--------|
| `InventarioRotativo.Web` | React + Vite + TypeScript + CSS Modules (PWA) | Azure Static Web Apps |
| `InventarioRotativo.Api` | ASP.NET Core 8 + EF Core | Azure App Service |

### Database Access Rules

- `stg_erp.*` — read-only (ERP staging, updated by external ETL)
- `inventario.*` — read/write (users, classification, counts, filters)

## ERP Staging Tables (Read-Only)

### `stg_erp.stg_bancoxodo__produto`

Key columns used by the app:

| Column | Type | Usage |
|--------|------|-------|
| `pro_codigo` | int | Product code (barcode suffix, e.g. 12122) |
| `pro_desc` | nvarchar | Product description for search/display |
| `pro_descres` | nvarchar | Short description |
| `pro_tpicodigo` | nvarchar | Item type (from ERP, e.g. `"04"` — used in filters) |
| `pro_ativo` | int | Active flag |

### `stg_erp.stg_bancoxodo__unidade`

| Column | Type | Usage |
|--------|------|-------|
| `UND_CODIGO` | nvarchar(10) | Unit code (e.g. PAL) |
| `UND_DESC` | nvarchar | Unit description |
| `UND_ATIVO` | int | Active flag |

### `stg_erp.stg_bancoxodo__unidadepro`

| Column | Type | Usage |
|--------|------|-------|
| `unp_procodigo` | int | Product code FK |
| `unp_unidade` | nvarchar(10) | Unit code FK |
| `unp_quantidade` | int | Packaging quantity (often equals `unp_fatestoque`) |
| `unp_fatestoque` | float | Stock conversion factor — multiply counted qty to get stock-base qty |
| `unp_padestoque` | int | `1` = stock base unit (usually KG); `0` = alternate unit |
| `unp_ativo` | int | Active flag — filter `unp_ativo = 1`; watch duplicate unit codes (e.g. KG devolução) |

### `stg_erp.stg_bancoxodo__ordemproducao`

| Column | Type | Usage |
|--------|------|-------|
| `OPP_NUMERO` | int | Production order (barcode prefix, e.g. 48335) |
| `opp_procodigo` | int | Product code |
| `opp_numlote` | nvarchar(15) | Batch/lot number |
| `opp_dtvenc` | date | Expiration date |
| `opp_unpunidade` | nvarchar(10) | Unit on label |
| `opp_unpquant` | int | Unit quantity factor |
| `opp_dtini` | date | Production start — used for "last month" OP window on barcode scans |
| `OPP_DTEMIS` | date | Emission date (fallback if `opp_dtini` is null) |
| `OPP_STATUS` | nvarchar | OP status — barcode scans require `'F'` (finalizada) |
| `opp_qtdeproduz` | float | Quantity produced — barcode scans require `> 0` |
| `opp_inversa` | int | Inverse OP flag — barcode scans require `0` (exclude inversas) |

Updated frequently by external ingestion. App reads only.

## Barcode Format

Labels use a proprietary format, not EAN-13:

```
{OPP_NUMERO}.{pro_codigo_suffix}
Example: 48335.12122
```

- `48335` → `OPP_NUMERO` (PRODUÇÃO on label)
- `12122` → `pro_codigo` as integer (CÓDIGO `012122` on label, leading zero dropped)

### Scan Resolution Flow

Applies only to barcode scans (`origem = 'scan'`). Manual entry does not use OP lookup.

**Active-data rules:** only `pro_ativo = 1` products and `unp_ativo = 1` units.

**OP eligibility (barcode scan only):** production orders must satisfy **all** of:

```sql
OPP_STATUS = 'F'
AND opp_qtdeproduz > 0
AND COALESCE(opp_dtini, OPP_DTEMIS) >= DATEADD(month, -1, CAST(GETDATE() AS date))
```

1. Parse barcode into `opp_numero` and `pro_codigo`
2. Lookup `produto` WHERE `pro_codigo` = pro_codigo AND `pro_ativo` = 1
3. Lookup `ordemproducao` WHERE `OPP_NUMERO` = opp_numero AND `opp_procodigo` = pro_codigo AND OP eligibility above
4. Lookup `unidadepro` WHERE `unp_procodigo` = pro_codigo AND `unp_unidade` = opp_unpunidade AND `unp_ativo` = 1
5. Validate product matches operator's active filters (tipo item, grupo, subgrupo)
6. Return preview: description, unit, lot (`opp_numlote`), expiry (`opp_dtvenc`), default quantity = 1

Default quantity is always 1 whole unit of the label's unit (e.g. 1 pallet). Operator may adjust before submitting.

Labels with an OP older than the window (or not present in staging) cannot resolve lote/validade via scan — operator uses manual entry.

### Error Cases

| Condition | Message |
|-----------|---------|
| Invalid barcode format | "Formato não reconhecido" |
| OP not found (missing, wrong product, outside last-month window, not status F, or zero production) | "Ordem de produção não encontrada" — operator may use manual entry |
| Product outside filters | "Produto não pertence à seleção atual" |
| Inactive product | "Produto inativo" |

## App Schema Tables (New — schema `inventario`)

### `inventario.usuario`

```sql
id            INT IDENTITY PK
login         NVARCHAR(50) UNIQUE NOT NULL
senha_hash    NVARCHAR(256) NOT NULL
nome          NVARCHAR(100) NOT NULL
perfil        NVARCHAR(20) NOT NULL  -- 'Operador' | 'Admin'
ativo         BIT NOT NULL DEFAULT 1
criado_em     DATETIME2 NOT NULL
```

### `inventario.grupo`

```sql
id            INT IDENTITY PK
nome          NVARCHAR(100) NOT NULL
ativo         BIT NOT NULL DEFAULT 1
```

### `inventario.subgrupo`

```sql
id            INT IDENTITY PK
grupo_id      INT FK → inventario.grupo
nome          NVARCHAR(100) NOT NULL
ativo         BIT NOT NULL DEFAULT 1
```

### `inventario.produto_classificacao`

```sql
pro_codigo    INT PK
grupo_id      INT FK → inventario.grupo
subgrupo_id   INT FK → inventario.subgrupo
atualizado_em DATETIME2 NOT NULL
atualizado_por INT FK → inventario.usuario
```

Item type (`pro_tpicodigo`) comes from ERP — no separate app table needed.

### `inventario.contagem`

```sql
id            BIGINT IDENTITY PK
pro_codigo    INT NOT NULL
opp_numero    INT NULL              -- OP from barcode (null if manual)
unidade       NVARCHAR(10) NOT NULL -- unit counted in
lote          NVARCHAR(15) NOT NULL
validade      DATE NOT NULL
quantidade    DECIMAL(18,4) NOT NULL DEFAULT 1
operador_id   INT FK → inventario.usuario NOT NULL
tipo_item     NVARCHAR(10) NULL     -- filter snapshot (pro_tpicodigo)
grupo_id      INT NULL              -- filter snapshot
subgrupo_id   INT NULL              -- filter snapshot
origem        NVARCHAR(10) NOT NULL -- 'scan' | 'manual'
registrado_em DATETIME2 NOT NULL
```

Each operator submission creates one row. Filter values are snapshotted for export traceability. Operator may count in any product unit; export converts to stock base unit.

### `inventario.operador_filtro`

```sql
operador_id   INT PK FK → inventario.usuario
tipos_item    NVARCHAR(MAX) NULL   -- JSON array of pro_tpicodigo
grupos_id     NVARCHAR(MAX) NULL   -- JSON array of grupo_id
subgrupos_id  NVARCHAR(MAX) NULL   -- JSON array of subgrupo_id
atualizado_em DATETIME2 NOT NULL
```

Filters persist across sessions until operator changes or clears them.

## User Roles

| Role | Capabilities |
|------|-------------|
| **Operador** | Login, set filters, scan/manual count, submit counts, view recent counts |
| **Admin** | All Operador capabilities plus: grupo/subgrupo management, product classification, export by date range |

## Screens

### Operador (Mobile-First)

1. **Login** — username + password → JWT
2. **Filtros** — multi-select Tipo de Item / Grupo / Subgrupo; Apply / Clear all; persisted in `inventario.operador_filtro`
3. **Contagem** (main) — scan button, manual search button, last 5 counts summary, filter badge
4. **Confirmação** (after scan or manual) — product, unit, lot, expiry, quantity (default 1); confirm or adjust → submit

### Admin

1. **Classificação** — list unclassified products; assign grupo/subgrupo individually or in batch
2. **Exportação** — date range filter; preview; export CSV or Excel (with stock-unit conversion)

## API Endpoints

Base: `/api/v1`. All routes except login require JWT.

### Auth

| Method | Route | Role | Description |
|--------|-------|------|-------------|
| POST | `/auth/login` | public | Returns JWT + profile |
| GET | `/auth/me` | all | Current user info |

### Operator Filters

| Method | Route | Role | Description |
|--------|-------|------|-------------|
| GET | `/filtros` | Operador | Get saved filters |
| PUT | `/filtros` | Operador | Save/update filters |
| DELETE | `/filtros` | Operador | Clear all filters |

### Counting

| Method | Route | Role | Description |
|--------|-------|------|-------------|
| POST | `/contagem/scan` | Operador | Body: `{ barcode }` → resolve and return preview |
| POST | `/contagem` | Operador | Body: confirmed data → save count |
| GET | `/contagem/recentes` | Operador | Last 5 counts by operator |

### Manual Search

| Method | Route | Role | Description |
|--------|-------|------|-------------|
| GET | `/produtos?q=` | Operador | Search by code or description (respects filters) |
| GET | `/produtos/{codigo}/unidades` | Operador | Product units from unidadepro |

### Classification (Admin)

| Method | Route | Role | Description |
|--------|-------|------|-------------|
| GET | `/grupos` | Admin | List groups |
| POST | `/grupos` | Admin | Create group |
| GET | `/subgrupos?grupoId=` | Admin | List subgroups |
| POST | `/subgrupos` | Admin | Create subgroup |
| GET | `/classificacao?semClassificar=true` | Admin | Unclassified products |
| PUT | `/classificacao/{proCodigo}` | Admin | Assign grupo/subgrupo |

### Export (Admin)

| Method | Route | Role | Description |
|--------|-------|------|-------------|
| GET | `/exportacao?de=&ate=` | Admin | Returns CSV or Excel file |

### Catalogs

| Method | Route | Role | Description |
|--------|-------|------|-------------|
| GET | `/tipos-item` | all | Distinct pro_tpicodigo values |
| GET | `/grupos` | all | Active groups (for filters) |
| GET | `/subgrupos` | all | Active subgroups (for filters) |

## Export Format

Admin exports by date range (start/end). Formats: CSV and Excel.

Operator counts in the unit they choose; export includes both counted values and values converted to the product's stock base unit (`unp_padestoque = 1`).

### Conversion rule

```
quantidade_estoque = quantidade_contada × unp_fatestoque
```

Where `unp_fatestoque` comes from `unidadepro` for the counted unit (`unp_unidade = contagem.unidade`, `unp_ativo = 1`). Stock base unit code comes from the row where `unp_padestoque = 1`.

Example (product 12122): 1 PAL → 600 KG; 1 FD → 10 KG; 1 CX → 20 KG.

| Column | Source |
|--------|--------|
| Código produto | `contagem.pro_codigo` |
| Descrição | `produto.pro_desc` |
| Unidade contada | `contagem.unidade` |
| Quantidade contada | `contagem.quantidade` |
| Unidade estoque | `unidadepro.unp_unidade` where `unp_padestoque = 1` |
| Quantidade estoque | `quantidade × unp_fatestoque` |
| Lote | `contagem.lote` |
| Validade | `contagem.validade` |
| OP | `contagem.opp_numero` |
| Operador | `usuario.nome` |
| Data/hora | `contagem.registrado_em` |

## Manual Entry Flow

When barcode is unavailable:

1. Operator searches product by code or description (filtered by active selection)
2. Selects unit from product's `unidadepro` entries
3. Enters lot, expiry, quantity manually
4. Submits → saved as `origem = 'manual'`, `opp_numero = null`

## Design System (referência: `cockpit-web`)

Visual identity follows the **Xodó** brand design tokens from [cockpit-web](https://github.com/GabrielDBConsultoria/cockpit-web). React is kept; reuse tokens and patterns — do not introduce Tailwind or a new component library for MVP.

### Source files to copy/adapt

| Asset | Path in cockpit-web |
|-------|---------------------|
| Design tokens (CSS) | `shared/design-tokens/tokens.css` |
| Design tokens (JSON) | `shared/design-tokens/tokens.json` |
| Logo | `src/assets/logo-xodo.png` |
| Token import pattern | `src/index.css` (imports tokens, sets body defaults) |

### Color palette (revision 2026-08-01)

| Token | Value | Usage |
|-------|-------|-------|
| `--color-primary` | `#F4B122` | Amarelo Xodó — buttons, highlights, brand |
| `--color-topbar` | `#F4B122` | Header background |
| `--color-sidebar` | `#1A1A1A` | Sidebar background (admin layout) |
| `--color-background` | `#FFFFFF` | Page background |
| `--color-text` | `#1A1A1A` | Primary text |
| `--color-text-muted` | `#666666` | Secondary text |
| `--color-border` | `#E8E8E8` | Borders, inputs |
| `--color-surface` | `#FFFFFF` | Cards |
| `--color-row-hover` | `#FEF3D0` | List/table hover |
| `--color-status-success` | `#008742` | Positive status |
| `--color-status-success-bg` | `#D6F0E3` | Success badge background |
| `--color-status-critical` | `#C01818` | Errors/alerts only (not brand) |
| `--color-status-critical-bg` | `#FAE5E5` | Error badge background |

### Typography

| Token | Value |
|-------|-------|
| `--font-family-primary` | `Segoe UI` |
| `--font-family-fallback` | `Arial, Helvetica Neue, sans-serif` |
| `--font-family-body` | primary + fallback stack |

### Layout and component patterns (from cockpit-web operator screens)

- **CSS Modules** per component (e.g. `Contagem.module.css`) — same approach as `modules/paradas/`
- **Operator screens:** max-width ~560px, centered, mobile-first
- **Touch targets:** min-height 48px for inputs and buttons
- **Buttons:** `background: var(--color-primary)`, `border-radius: var(--radius-base)` (4px)
- **Inputs:** border `var(--color-border)`, focus ring via `border-color: var(--color-primary)` + `box-shadow: 0 0 0 2px var(--color-row-hover)`
- **Lists/cards:** `var(--color-surface)` background, hover `var(--color-row-hover)`
- **Header:** yellow topbar (`--color-topbar`) with white logo pill and app title — same pattern as `Topbar.jsx`
- **Alerts/errors:** use `--color-status-critical` tokens, not primary yellow

### Branding in inventário rotativo

- Logo: `logo-xodo.png` in header
- App title suggestion: **"Xodó Inventário"** (parallel to "Xodó Produção" in cockpit-web)
- Operator PWA: single-column flow, no sidebar
- Admin screens: optional sidebar layout (dark `#1A1A1A`) for import/classification/export

## Deployment

| Component | Azure Service |
|-----------|---------------|
| API | App Service (.NET 8) |
| PWA | Static Web Apps |
| Database | Azure SQL (existing) |
| Secrets | Key Vault (connection string, JWT secret) |

## Testing Strategy

- **API integration tests:** barcode parser, filter validation, count persistence, export generation
- **Frontend component tests:** barcode parser, confirmation form
- **Manual E2E:** full scan flow on mobile device with camera

## Out of Scope (YAGNI)

- Admin CSV import of ERP data (staging updated by external ETL)
- Direct ERP API integration
- EAN-13 barcode support (proprietary format only)
- Offline mode / sync queue
- Supervisor role (only Operador and Admin)
- Export by grupo/subgrupo filter (date range only)
- Modifying `stg_erp` data from the app (read-only)

## Azure Data Validation (2026-08-08)

Validated against `dwxodo.database.windows.net` / `dwxodo` via `inventario-rotativo/scripts/analyze-stg-erp.py`. Full output: `inventario-rotativo/scripts/analysis-results-2026-08-08.json`.

| Finding | Detail |
|---------|--------|
| `stg_erp` tables | 41+ `stg_bancoxodo__*` tables including produto, unidade, unidadepro, ordemproducao, grupopro, subgrupopro |
| Product 12122 | PÃO DE QUEIJO TRADICIONAL PCT 1KG; `pro_tpicodigo = "04"`; active |
| Units 12122 | KG (base, `unp_padestoque=1`), CX/20, FD/10, PAL/600, PCT/1; duplicate KG rows for devolução — use `unp_ativo=1` |
| Label OP 48335 | **Not in staging** — for scan tests use a finished OP e.g. `45120.12122` (status F, `opp_qtdeproduz > 0`, lote `180526`) |
| Stock base unit | All active products have exactly one `unp_padestoque=1` row |
| Conversion | For most products `unp_quantidade ≈ unp_fatestoque`; export uses `unp_fatestoque`. Edge case: product 550 PAL has quantidade=540, fatestoque=600 |
