# MercadoRadar RJ — Comparador de preços v10

Aplicativo web com **500 categorias de produtos pesquisáveis** e comparação entre preços convencionais e promoções anunciadas por Guanabara, Assaí, Prezunic, Mundial, Rede Economia e Supermarket.

**O catálogo de 500 produtos não é uma lista de 500 preços.** A quantidade de cotações reais disponíveis depende das fontes consultadas. Se não houver um preço verificável, o aplicativo mostra “Sem cotação” e o site oficial da rede, nunca uma estimativa inventada.

## Recursos

- Pesquisa tolerante a acentos e erros comuns: `feijão`, `feijao`, `feigao`, `fejao`.
- Sinônimos: `pasta de dente` = `creme dental`; `extra virgem` = `extravirgem`.
- Preços comuns e promoções; filtro opcional para mostrar somente promoções.
- Organização por tipo, unidade de comparação (kg/l/unidade) e marca.
- Seis redes na tela, com indicação de ausência de cotação e ligação para site oficial.
- Fonte, data de consulta, validade promocional e condições de fidelidade, quando conhecidas.
- Preços não confirmados para filial/CEP são identificados como indicativos.
- Catálogo SQLite de 500 produtos carregado automaticamente no primeiro boot.
- Coletor experimental das 14 categorias de ofertas públicas do Guanabara, acionado por intervalo e sem bloquear a interface.

## Cobertura atual

| Rede | Situação |
|---|---|
| Guanabara | Ofertas iniciais documentadas e coletor experimental de categorias |
| Prezunic | Alguns preços referenciais publicados, ainda sem coleta automática validada |
| Mundial | Algumas ofertas de encarte válido até 18/11/2026, ainda sem coleta automática |
| Assaí | Site oficial consultável, preços dependem da loja; coletor pendente |
| Rede Economia | Encarte online consultável; coletor pendente |
| Supermarket | Ofertas online por período e condições; coletor pendente |

Os dados de exemplo de `data/precos_publicados_2026_11_05.json` provêm de anúncios reais consultados, **não são inventados**, porém **não garantem preço vigente em uma filial**. Cotações comuns com mais de dez dias não entram nos resultados; promoções vencidas também não. O aplicativo não realiza 3.000 consultas em tempo real ao abrir.

## Execução local

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Acesse http://localhost:8000.

Principais endpoints:

- `GET /api/health` — diagnóstico básico
- `GET /api/products?q=pasta%20de%20dente` — catálogo pesquisável
- `GET /api/prices?q=azeite` — preços comuns e ofertas
- `GET /api/prices?q=leite&only_promotions=true` — somente promoções
- `GET /api/offers?q=arroz` — endpoint legado de promoções
- `GET /api/status` — cobertura, situação dos coletores e banco
- `POST /api/admin/prices` — importação autorizada mediante `X-Admin-Token`

## Render gratuito

O repositório inclui `render.yaml`. Para um Web Service:

- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Plano: Free
- Opcional: `ENABLE_COLLECTOR=true`
- Configure `DATABASE_URL` com PostgreSQL externo gratuito para persistência.

**Aviso:** o armazenamento SQLite local do Render gratuito é efêmero. Dados inseridos podem desaparecer ao reiniciar, mas o catálogo e as cotações publicadas são reimportados ao iniciar o servidor. Para histórico e atualizações persistentes é necessário banco externo.

## Testes

```bash
pip install pytest httpx
python -m pytest -q
```

A existência de adaptador não é garantia de que sites não alterem seus formatos ou restrições de acesso. Verifique sempre a informação na página de origem antes de comprar.
