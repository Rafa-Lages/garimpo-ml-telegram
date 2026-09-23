# Garimpo Automático — Achado Bom

Busca ofertas de itens do lar no Mercado Livre (desconto ≥ 40%, vendedor
MercadoLíder Gold/Platinum) e publica automaticamente no canal do Telegram
**Achado Bom**, a cada 6 horas, via GitHub Actions.

## Arquivos

- `garimpo.py` — o script de curadoria e publicação.
- `requirements.txt` — dependências Python (só `requests`).
- `.github/workflows/garimpo.yml` — o agendamento (GitHub Actions).
- `state/` — criado automaticamente na primeira execução; guarda os tokens
  renovados do Mercado Livre e a lista de ofertas já enviadas (pra nunca
  repetir). Não apague essa pasta.

## Como subir isso pro seu repositório

No GitHub, na página do repositório: **Add file → Upload files**, e arrasta
os três arquivos/pastas (`garimpo.py`, `requirements.txt`, `.github/`)
mantendo essa mesma estrutura. Se o GitHub não deixar arrastar a pasta
`.github/workflows/garimpo.yml` diretamente, cria esse arquivo por
**Add file → Create new file** e digita o caminho completo
`.github/workflows/garimpo.yml` no campo do nome — o GitHub cria as pastas
sozinho.

## Como testar

Depois de subir os arquivos e com os 6 Secrets já cadastrados
(`ML_CLIENT_ID`, `ML_CLIENT_SECRET`, `ML_ACCESS_TOKEN`, `ML_REFRESH_TOKEN`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`):

1. Aba **Actions** do repositório.
2. Clica no workflow **Garimpo Automático**.
3. **Run workflow** → **Run workflow** de novo pra confirmar.
4. Acompanha o log — se der certo, aparece "Ofertas novas postadas: N" no
   final, e as ofertas chegam no canal.

## Ajustar o nicho

A lista de palavras-chave está no topo de `garimpo.py`, na variável
`KEYWORDS`. Edita, adiciona ou remove termos à vontade — não precisa mexer
em mais nada.

## Sobre o refresh_token

O Mercado Livre invalida o `refresh_token` antigo toda vez que ele é usado
e devolve um novo. Por isso o script guarda o token atualizado em
`state/ml_tokens.json` (commitado de volta no repositório a cada execução)
em vez de depender só do valor original salvo nos Secrets — que só serve
pra primeira execução.
