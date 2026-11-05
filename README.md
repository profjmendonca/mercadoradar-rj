# MercadoRadar RJ

Aplicativo de consulta a **500 tipos de produtos** e comparação de **promoções verificadas** das redes Guanabara, Assaí, Prezunic, Mundial, Rede Economia e Supermarket.

- Busca tolerante a acentos e pequenos erros de digitação (`feijão`, `feijao`, `feigao`).
- Agrupamento por marca, tipo e preço por quilo/litro/unidade.
- Ofertas somente com fonte e validade informadas.
- Sem preços fictícios. A ausência de promoções é mostrada claramente.
- Coleta de dados ainda **experimental**; cobertura das seis redes **não está pronta**.

## Executar

```sh
pip install -r requirements.txt
uvicorn main:app --reload
```

Abrir http://127.0.0.1:8000 e testar `/api/status` e `/api/products?q=feigao`.

## Publicar gratuitamente

O arquivo `render.yaml` configura o serviço gratuito Python no Render. No painel do Render, escolha **New > Blueprint**, conecte este repositório e implante. O endereço público será criado pelo Render quando o serviço estiver no ar.

Banco SQLite sem disco persistente serve apenas para testes; para armazenar histórico configure PostgreSQL/Supabase em `DATABASE_URL` como segredo no Render.

**Atenção:** não existe integração em tempo real com todas as redes. Nenhuma promoção é inventada para preencher resultados.
