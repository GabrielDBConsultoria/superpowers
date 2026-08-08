# Inventário Rotativo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mobile-first PWA for rotating stock inventory with barcode scanning, manual entry, ERP staging reads, `inventario` schema writes, and admin export — branded as Xodó Inventário.

**Architecture:** React PWA (`InventarioRotativo.Web`) talks to ASP.NET Core 8 API (`InventarioRotativo.Api`) over HTTPS/JWT. API reads `stg_erp.*` (read-only) and writes `inventario.*` (users, classification, counts, filters). Barcode `{OPP}.{pro_codigo}` resolves via `ordemproducao` join.

**Tech Stack:** React 19 + Vite + TypeScript + CSS Modules + html5-qrcode | ASP.NET Core 8 + EF Core + SQL Server | xUnit + Vitest

**Spec:** `docs/superpowers/specs/2026-08-08-inventario-rotativo-design.md`

**Design reference:** `https://github.com/GabrielDBConsultoria/cockpit-web` — copy `shared/design-tokens/tokens.css`, `tokens.json`, `src/assets/logo-xodo.png`

## Global Constraints

- Azure SQL: `stg_erp` read-only; `inventario` read/write
- Barcode format: `{OPP_NUMERO}.{pro_codigo}` e.g. `45120.12122` (OP finalizada com produção; `45197` é status E e fica fora)
- Barcode scan OP eligibility: `OPP_STATUS = 'F'`, `opp_qtdeproduz > 0`, last 30 days via `COALESCE(opp_dtini, OPP_DTEMIS)`; only `pro_ativo=1` and `unp_ativo=1`
- Default quantity on scan: `1` (one whole label unit)
- Roles: `Operador` | `Admin` (JWT claims)
- UI: CSS Modules + Xodó tokens — no Tailwind, no shadcn
- Operator screens: max-width ~560px, touch targets min 48px
- App title: **Xodó Inventário**
- Error messages in Portuguese (exact strings from spec)
- Export columns: código, descrição, unidade contada, quantidade contada, unidade estoque, quantidade estoque (via `qtd × unp_fatestoque`), lote, validade, OP, operador, data/hora
- Out of scope: EAN-13, offline sync, ERP API, modifying `stg_erp` from import in MVP (staging updated externally)

---

## File Map

```
inventario-rotativo/
├── InventarioRotativo.Api/
│   ├── Program.cs
│   ├── appsettings.json
│   ├── Data/AppDbContext.cs
│   ├── Data/Migrations/
│   ├── Entities/          # inventario schema entities
│   ├── Entities/Stg/      # stg_erp read-only entities (no tracking writes)
│   ├── Services/
│   │   ├── BarcodeParser.cs
│   │   ├── ContagemService.cs
│   │   ├── FiltroService.cs
│   │   ├── ExportacaoService.cs
│   │   └── AuthService.cs
│   ├── Controllers/
│   └── Tests/
│       └── InventarioRotativo.Api.Tests/
├── InventarioRotativo.Web/
│   ├── shared/design-tokens/tokens.css
│   ├── src/
│   │   ├── main.tsx
│   │   ├── index.css
│   │   ├── assets/logo-xodo.png
│   │   ├── lib/apiClient.ts
│   │   ├── lib/auth.tsx
│   │   ├── lib/barcodeParser.ts
│   │   ├── components/Topbar.tsx
│   │   ├── screens/
│   │   │   ├── Login.tsx
│   │   │   ├── Filtros.tsx
│   │   │   ├── Contagem.tsx
│   │   │   ├── Confirmacao.tsx
│   │   │   ├── BuscaManual.tsx
│   │   │   └── admin/
│   │   │       ├── Classificacao.tsx
│   │   │       └── Exportacao.tsx
│   │   └── routes.tsx
│   └── vite.config.ts
└── README.md
```

---

## Chunk 1: API Foundation

### Task 1: Scaffold API project and app schema migration

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Api/` (dotnet new webapi)
- Create: `inventario-rotativo/InventarioRotativo.Api/Data/AppDbContext.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Entities/*.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Data/Migrations/001_CreateAppSchema.sql`

**Interfaces:**
- Produces: `AppDbContext` with DbSets: `Usuario`, `Grupo`, `Subgrupo`, `ProdutoClassificacao`, `Contagem`, `OperadorFiltro`
- Produces: SQL migration creating `app` schema tables per spec

- [ ] **Step 1: Create solution and API project**

```bash
cd inventario-rotativo
dotnet new sln -n InventarioRotativo
dotnet new webapi -n InventarioRotativo.Api -o InventarioRotativo.Api --use-controllers
dotnet sln add InventarioRotativo.Api/InventarioRotativo.Api.csproj
cd InventarioRotativo.Api
dotnet add package Microsoft.EntityFrameworkCore.SqlServer
dotnet add package Microsoft.EntityFrameworkCore.Design
dotnet add package BCrypt.Net-Next
dotnet add package Microsoft.AspNetCore.Authentication.JwtBearer
```

- [ ] **Step 2: Define entity `Usuario`**

```csharp
// Entities/Usuario.cs
namespace InventarioRotativo.Api.Entities;

public class Usuario
{
    public int Id { get; set; }
    public string Login { get; set; } = "";
    public string SenhaHash { get; set; } = "";
    public string Nome { get; set; } = "";
    public string Perfil { get; set; } = "Operador"; // Operador | Admin
    public bool Ativo { get; set; } = true;
    public DateTime CriadoEm { get; set; }
}
```

- [ ] **Step 3: Define remaining app entities** (`Grupo`, `Subgrupo`, `ProdutoClassificacao`, `Contagem`, `OperadorFiltro`) matching spec columns exactly

- [ ] **Step 4: Configure `AppDbContext`**

```csharp
protected override void OnModelCreating(ModelBuilder modelBuilder)
{
    modelBuilder.HasDefaultSchema("app");
    modelBuilder.Entity<Usuario>().ToTable("usuario");
    modelBuilder.Entity<Usuario>().HasIndex(u => u.Login).IsUnique();
    // ... map all tables to spec column names (snake_case in DB via column attributes)
}
```

- [ ] **Step 5: Add SQL migration script** `Data/Migrations/001_CreateAppSchema.sql` with CREATE TABLE statements from spec

- [ ] **Step 6: Seed dev admin user** in `Data/DbSeeder.cs`:

```csharp
// login: admin / senha: admin123 (dev only)
BCrypt.Net.BCrypt.HashPassword("admin123")
```

- [ ] **Step 7: Commit**

```bash
git add inventario-rotativo/
git commit -m "feat(api): scaffold InventarioRotativo.Api with app schema entities"
```

---

### Task 2: Staging ERP read-only entities

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Api/Entities/Stg/StgProduto.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Entities/Stg/StgUnidade.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Entities/Stg/StgUnidadePro.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Entities/Stg/StgOrdemProducao.cs`
- Modify: `inventario-rotativo/InventarioRotativo.Api/Data/AppDbContext.cs`

**Interfaces:**
- Consumes: `AppDbContext` from Task 1
- Produces: DbSets `StgProdutos`, `StgUnidades`, `StgUnidadePros`, `StgOrdemProducoes` mapped to `stg_erp.stg_bancoxodo__*` with `.ToTable(..., "stg_erp").HasNoKey()` or proper keys (`pro_codigo`, composite keys)

- [ ] **Step 1: Map `StgProduto`** — columns: `pro_codigo`, `pro_desc`, `pro_descres`, `pro_tpicodigo`, `pro_ativo`

- [ ] **Step 2: Map `StgOrdemProducao`** — columns: `OPP_NUMERO`, `opp_procodigo`, `opp_numlote`, `opp_dtvenc`, `opp_unpunidade`, `opp_unpquant`

- [ ] **Step 3: Map `StgUnidade` and `StgUnidadePro`**

- [ ] **Step 4: Mark staging entities read-only** — override `SaveChanges` to throw if any `Stg*` entity is Added/Modified/Deleted

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(api): add read-only stg_erp entity mappings"
```

---

### Task 3: Barcode parser (TDD)

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Api/Services/BarcodeParser.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api.Tests/BarcodeParserTests.cs`

**Interfaces:**
- Produces: `BarcodeParser.Parse(string barcode) → BarcodeParseResult`
- `BarcodeParseResult`: `{ bool Success, int? OppNumero, int? ProCodigo, string? ErrorMessage }`

- [ ] **Step 1: Write failing tests**

```csharp
[Theory]
[InlineData("48335.12122", 48335, 12122)]
[InlineData("1.5", 1, 5)]
public void Parse_ValidBarcode_ReturnsOppAndProCodigo(string input, int opp, int pro)
{
    var result = BarcodeParser.Parse(input);
    Assert.True(result.Success);
    Assert.Equal(opp, result.OppNumero);
    Assert.Equal(pro, result.ProCodigo);
}

[Theory]
[InlineData("")]
[InlineData("abc")]
[InlineData("48335")]
[InlineData(".12122")]
public void Parse_InvalidBarcode_ReturnsError(string input)
{
    var result = BarcodeParser.Parse(input);
    Assert.False(result.Success);
    Assert.Equal("Formato não reconhecido", result.ErrorMessage);
}
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd inventario-rotativo/InventarioRotativo.Api.Tests
dotnet test --filter BarcodeParser
```

- [ ] **Step 3: Implement parser**

```csharp
public static class BarcodeParser
{
    private static readonly Regex Pattern = new(@"^(\d+)\.(\d+)$", RegexOptions.Compiled);

    public static BarcodeParseResult Parse(string barcode)
    {
        if (string.IsNullOrWhiteSpace(barcode))
            return BarcodeParseResult.Fail("Formato não reconhecido");

        var match = Pattern.Match(barcode.Trim());
        if (!match.Success)
            return BarcodeParseResult.Fail("Formato não reconhecido");

        return BarcodeParseResult.Ok(
            int.Parse(match.Groups[1].Value),
            int.Parse(match.Groups[2].Value));
    }
}
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(api): add barcode parser with tests"
```

---

### Task 4: JWT authentication

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Api/Services/AuthService.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Controllers/AuthController.cs`
- Modify: `inventario-rotativo/InventarioRotativo.Api/Program.cs`

**Interfaces:**
- Produces: `POST /api/v1/auth/login` → `{ token, nome, perfil }`
- Produces: `GET /api/v1/auth/me` → `{ id, login, nome, perfil }`
- JWT claim: `perfil` = `Operador` | `Admin`

- [ ] **Step 1: Configure JWT in `Program.cs`** (issuer, audience, secret from `appsettings.json`)

- [ ] **Step 2: Implement `AuthService.Login(login, senha)`** — BCrypt verify, return JWT

- [ ] **Step 3: Implement `AuthController`**

- [ ] **Step 4: Add `[Authorize(Roles = "Admin")]` policy helper**

- [ ] **Step 5: Integration test** — login with seed admin returns 200 + token

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(api): add JWT auth with Operador/Admin roles"
```

---

## Chunk 2: Core API — Contagem & Filtros

### Task 5: Operator filters (persistent)

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Api/Services/FiltroService.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Controllers/FiltrosController.cs`

**Interfaces:**
- Produces: `GET /api/v1/filtros` → `{ tiposItem: string[], gruposId: int[], subgruposId: int[] }`
- Produces: `PUT /api/v1/filtros` — body same shape, upserts `inventario.operador_filtro`
- Produces: `DELETE /api/v1/filtros` — clears arrays

- [ ] **Step 1: Serialize/deserialize JSON arrays** in `OperadorFiltro` entity (`tipos_item`, `grupos_id`, `subgrupos_id`)

- [ ] **Step 2: Implement GET/PUT/DELETE** scoped to authenticated user id

- [ ] **Step 3: Test** — PUT then GET returns same filters

- [ ] **Step 4: Commit**

---

### Task 6: Scan resolution and count submission

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Api/Services/ContagemService.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Controllers/ContagemController.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Dtos/ContagemDtos.cs`

**Interfaces:**
- Consumes: `BarcodeParser.Parse`, `FiltroService.GetFiltros`, staging entities
- Produces: `POST /api/v1/contagem/scan` body `{ barcode: string }` → preview DTO:

```json
{
  "proCodigo": 12122,
  "descricao": "PÃO DE QUEIJO...",
  "unidade": "PAL",
  "lote": "180526",
  "validade": "2026-08-16",
  "quantidadePadrao": 1,
  "oppNumero": 45120
}
```

- Produces: `POST /api/v1/contagem` body:

```json
{
  "proCodigo": 12122,
  "oppNumero": 45120,
  "unidade": "KG",
  "lote": "180526",
  "validade": "2026-08-16",
  "quantidade": 1,
  "origem": "scan"
}
```

- Produces: `GET /api/v1/contagem/recentes` → last 5 for current operador

- [ ] **Step 1: Implement `ResolveScan(barcode, operadorId)`**
  1. Parse barcode
  2. Query produto (`pro_ativo = 1`) → else "Produto inativo"
  3. Query `ordemproducao` by OPP_NUMERO + opp_procodigo AND `OPP_STATUS = 'F'` AND `opp_qtdeproduz > 0` AND `COALESCE(opp_dtini, OPP_DTEMIS) >= DATEADD(month, -1, today)` → else "Ordem de produção não encontrada"
  4. Query `unidadepro` (`unp_ativo = 1`, unit from OP) — join `unidade` (`UND_ATIVO = 1`)
  5. Validate against operador filters (tipo/grupo/subgrupo) → else "Produto não pertence à seleção atual"
  6. Return preview with `quantidadePadrao: 1`, lote and validade from OP

- [ ] **Step 2: Implement `SubmitContagem(dto, operadorId)`** — snapshot current filters into row

- [ ] **Step 3: Write integration tests** for each error message (exact Portuguese strings)

- [ ] **Step 4: Commit**

---

### Task 7: Manual product search

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Api/Controllers/ProdutosController.cs`

**Interfaces:**
- Produces: `GET /api/v1/produtos?q={term}` → filtered list `{ proCodigo, descricao }`
- Produces: `GET /api/v1/produtos/{codigo}/unidades` → `{ unidade, descricao, quantidade }[]`
- Both respect operador's active filters via join on `produto_classificacao`

- [ ] **Step 1: Search** — `pro_codigo` exact match OR `pro_desc`/`pro_descres` contains `q`, `pro_ativo=1`

- [ ] **Step 2: Filter by tipo/grupo/subgrupo** from operador_filtro

- [ ] **Step 3: Unidades endpoint** — join `unidadepro` + `unidade`, `unp_ativo=1`

- [ ] **Step 4: Commit**

---

## Chunk 3: Admin API

### Task 8: Grupo, subgrupo, classificação

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Api/Controllers/GruposController.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Controllers/ClassificacaoController.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Controllers/TiposItemController.cs`

**Interfaces:**
- Produces: CRUD grupos/subgrupos (Admin only)
- Produces: `GET /api/v1/classificacao?semClassificar=true`
- Produces: `PUT /api/v1/classificacao/{proCodigo}` body `{ grupoId, subgrupoId }`
- Produces: `GET /api/v1/tipos-item` — distinct `pro_tpicodigo` from staging

- [ ] **Step 1: Implement grupo/subgrupo endpoints**

- [ ] **Step 2: List unclassified products** — produtos in stg without `produto_classificacao` row

- [ ] **Step 3: Assign classification** with `atualizado_por` = admin user id

- [ ] **Step 4: Commit**

---

### Task 9: Exportação CSV/Excel

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Api/Services/ExportacaoService.cs`
- Create: `inventario-rotativo/InventarioRotativo.Api/Controllers/ExportacaoController.cs`
- Add package: `ClosedXML` (Excel)

**Interfaces:**
- Produces: `GET /api/v1/exportacao?de=2026-08-01&ate=2026-08-08&formato=csv|xlsx`
- Columns: Código produto, Descrição, Unidade contada, Quantidade contada, Unidade estoque, Quantidade estoque, Lote, Validade, OP, Operador, Data/hora

- [ ] **Step 1: Query contagem** joined with produto + usuario + unidadepro where `registrado_em` between de/ate (inclusive, end of day)

- [ ] **Step 2: Compute stock conversion** — `quantidade_estoque = quantidade × unp_fatestoque` for counted unit; stock unit from `unp_padestoque = 1`

- [ ] **Step 3: Generate CSV** with UTF-8 BOM for Excel compatibility

- [ ] **Step 4: Generate XLSX** via ClosedXML

- [ ] **Step 5: Test** — seed 2 contagens (e.g. 1 PAL and 1 FD for product 12122), export shows 600 KG and 10 KG

- [ ] **Step 6: Commit**

---

## Chunk 4: React PWA Foundation

### Task 10: Scaffold Web + Xodó design tokens

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Web/` (vite react-ts)
- Copy from cockpit-web: `shared/design-tokens/tokens.css`, `tokens.json`, `src/assets/logo-xodo.png`
- Create: `inventario-rotativo/InventarioRotativo.Web/src/index.css`
- Create: `inventario-rotativo/InventarioRotativo.Web/src/components/Topbar.tsx` + `.module.css`

**Interfaces:**
- Produces: running dev server with Xodó yellow topbar, logo, title "Xodó Inventário"

- [ ] **Step 1: Create Vite project**

```bash
cd inventario-rotativo
npm create vite@latest InventarioRotativo.Web -- --template react-ts
cd InventarioRotativo.Web
npm install react-router-dom html5-qrcode
```

- [ ] **Step 2: Copy design tokens and logo** from cockpit-web clone

- [ ] **Step 3: `index.css`** — import tokens, body defaults (match cockpit-web `src/index.css`)

- [ ] **Step 4: Build `Topbar`** — yellow bar, white logo pill, "Xodó Inventário" title (adapt from cockpit-web `Topbar.jsx`)

- [ ] **Step 5: Commit**

---

### Task 11: Auth flow (frontend)

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Web/src/lib/apiClient.ts`
- Create: `inventario-rotativo/InventarioRotativo.Web/src/lib/auth.tsx`
- Create: `inventario-rotativo/InventarioRotativo.Web/src/screens/Login.tsx` + `.module.css`
- Create: `inventario-rotativo/InventarioRotativo.Web/src/routes.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- Produces: `AuthProvider`, `useAuth()`, JWT in `localStorage`, `apiClient` attaches `Authorization` header

- [ ] **Step 1: `apiClient.ts`** — base URL from `VITE_API_URL`, fetch wrapper

- [ ] **Step 2: `auth.tsx`** — login/logout, persist token, redirect by perfil

- [ ] **Step 3: `Login.tsx`** — username/password form, min-height 48px inputs, primary button

- [ ] **Step 4: Protected routes** — Operador → `/contagem`, Admin → `/admin` (or shared contagem + admin menu)

- [ ] **Step 5: Commit**

---

## Chunk 5: Operator Screens

### Task 12: Filtros screen

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Web/src/screens/Filtros.tsx` + `.module.css`

**Interfaces:**
- Consumes: `GET /tipos-item`, `GET /grupos`, `GET /subgrupos`, `GET/PUT/DELETE /filtros`
- Produces: multi-select UI, "Aplicar" saves, "Limpar tudo" clears

- [ ] **Step 1: Load catalog options and current filters on mount**

- [ ] **Step 2: Multi-select chips** for tipo/grupo/subgrupo

- [ ] **Step 3: Apply → PUT filtros → navigate to `/contagem`**

- [ ] **Step 4: Commit**

---

### Task 13: Contagem + barcode scanner

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Web/src/screens/Contagem.tsx` + `.module.css`
- Create: `inventario-rotativo/InventarioRotativo.Web/src/components/BarcodeScanner.tsx`

**Interfaces:**
- Consumes: `POST /contagem/scan`, `GET /contagem/recentes`, `GET /filtros`
- Produces: scan button opens camera via `html5-qrcode`, on scan → navigate to `/confirmacao` with preview state

- [ ] **Step 1: Filter badge** at top (summary of active filters, tap → `/filtros`)

- [ ] **Step 2: `BarcodeScanner`** — rear camera, onSuccess callback with decoded string

- [ ] **Step 3: Call scan API**, handle errors with `--color-status-critical` alert box

- [ ] **Step 4: Recent counts list** (last 5)

- [ ] **Step 5: Commit**

---

### Task 14: Confirmação + manual entry

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Web/src/screens/Confirmacao.tsx` + `.module.css`
- Create: `inventario-rotativo/InventarioRotativo.Web/src/screens/BuscaManual.tsx` + `.module.css`
- Create: `inventario-rotativo/InventarioRotativo.Web/src/lib/barcodeParser.ts` (client-side validation only)

**Interfaces:**
- Consumes: `POST /contagem`, `GET /produtos`, `GET /produtos/{codigo}/unidades`
- Produces: confirmation form (editable quantidade), submit → success toast → `/contagem`
- Manual flow: search → pick product → pick unit → enter lote/validade/qtd → same confirmation

- [ ] **Step 1: `Confirmacao.tsx`** — display all fields, quantidade default 1, submit POST

- [ ] **Step 2: `BuscaManual.tsx`** — search input, product list, unit selector, lote/validade inputs

- [ ] **Step 3: Date input** for validade (DD/MM/YYYY display, ISO to API)

- [ ] **Step 4: Commit**

---

## Chunk 6: Admin Screens

### Task 15: Admin layout + classificação

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Web/src/screens/admin/AdminLayout.tsx` + sidebar
- Create: `inventario-rotativo/InventarioRotativo.Web/src/screens/admin/Classificacao.tsx` + `.module.css`

**Interfaces:**
- Consumes: classification + grupo/subgrupo APIs
- Produces: dark sidebar `#1A1A1A`, list unclassified products, assign grupo/subgrupo dropdowns

- [ ] **Step 1: Admin layout** with sidebar nav: Classificação, Exportação

- [ ] **Step 2: Classificação screen** — filter `semClassificar=true`, inline assign

- [ ] **Step 3: Grupo/subgrupo create** — simple modal or inline form

- [ ] **Step 4: Commit**

---

### Task 16: Exportação screen

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Web/src/screens/admin/Exportacao.tsx` + `.module.css`

**Interfaces:**
- Consumes: `GET /exportacao?de=&ate=&formato=`
- Produces: date range pickers, preview table, download CSV/Excel buttons

- [ ] **Step 1: Date inputs** (de/até)

- [ ] **Step 2: Preview** — fetch and display first 20 rows in table

- [ ] **Step 3: Download** — blob download from API response

- [ ] **Step 4: Commit**

---

## Chunk 7: PWA & Polish

### Task 17: PWA manifest and README

**Files:**
- Create: `inventario-rotativo/InventarioRotativo.Web/public/manifest.json`
- Modify: `inventario-rotativo/InventarioRotativo.Web/index.html`
- Create: `inventario-rotativo/README.md`

- [ ] **Step 1: Web manifest** — name "Xodó Inventário", theme_color `#F4B122`, display standalone

- [ ] **Step 2: Meta viewport** — mobile-friendly, apple-touch-icon

- [ ] **Step 3: README** — setup instructions, env vars (`VITE_API_URL`, connection string), dev seed credentials

- [ ] **Step 4: Commit**

```bash
git commit -m "docs: add inventario-rotativo README and PWA manifest"
```

---

## Spec Coverage Checklist

| Spec requirement | Task |
|-----------------|------|
| Barcode parse `48335.12122` | Task 3, 6 |
| OP → lote/validade | Task 6 |
| Default qty = 1 | Task 6, 14 |
| Persistent filters | Task 5, 12 |
| Multi-operator simultaneous | Task 6 (no session lock) |
| JWT Operador/Admin | Task 4, 11 |
| Manual entry | Task 7, 14 |
| Grupo/subgrupo classification | Task 8, 15 |
| Export by date range | Task 9, 16 |
| Xodó design tokens | Task 10 |
| stg_erp read-only | Task 2 |
| app schema tables | Task 1 |
| Portuguese error messages | Task 6 tests |

**Deferred (out of scope):** CSV import UI (staging managed externally), offline mode, EAN-13

---

## Manual E2E Verification (final)

- [ ] Login as operador on mobile browser
- [ ] Set filters (tipo + grupo + subgrupo)
- [ ] Scan test barcode → confirmation shows correct lote/validade/unidade
- [ ] Submit count → appears in recentes
- [ ] Manual search flow works
- [ ] Login as admin → classify product → export date range CSV
