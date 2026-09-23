"""
Garimpo Automático — Achado Bom
Busca ofertas de itens do lar no Mercado Livre, filtra por desconto e
reputação do vendedor, e publica as novidades no canal do Telegram.

Roda via GitHub Actions (agendado). Veja o checklist "Garimpo Automático"
pra contexto completo de como isso foi montado.
"""

import json
import os
import pathlib
import sys
import time

import requests

# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------

# Palavras-chave do nicho "itens do lar" — edite essa lista à vontade,
# sem precisar mexer no resto do script.
KEYWORDS = [
    "panela",
    "jogo de panelas",
    "air fryer",
    "liquidificador",
    "ventilador",
    "aspirador de po",
    "organizador de armario",
    "jogo de cama",
    "toalha de banho",
    "cortina",
    "tapete sala",
    "luminaria",
    "potes hermeticos cozinha",
    "cesto organizador",
    "edredom",
    "travesseiro",
]

DISCOUNT_MIN = 0.40  # 40% de desconto mínimo sobre o preço original
TRUSTED_POWER_SELLER_STATUS = {"platinum", "gold"}  # MercadoLíder Gold/Platinum
ITEMS_PER_KEYWORD = 50
SENT_ITEM_TTL_DAYS = 30  # depois disso, um item pode ser reenviado se aparecer de novo

REDIRECT_URI = "https://httpbin.org/get"  # o mesmo usado pra gerar o refresh_token

STATE_DIR = pathlib.Path("state")
TOKENS_FILE = STATE_DIR / "ml_tokens.json"
SENT_FILE = STATE_DIR / "sent_items.json"

ML_CLIENT_ID = os.environ["ML_CLIENT_ID"]
ML_CLIENT_SECRET = os.environ["ML_CLIENT_SECRET"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ML_AFFILIATE_ID = os.environ.get("ML_AFFILIATE_ID", "").strip()  # opcional


# --------------------------------------------------------------------------
# Tokens do Mercado Livre (o refresh_token é rotativo: a cada uso, o
# Mercado Livre devolve um refresh_token novo e invalida o antigo — por
# isso guardamos o estado em arquivo, não só nos Secrets do GitHub)
# --------------------------------------------------------------------------

def load_tokens():
    STATE_DIR.mkdir(exist_ok=True)
    if TOKENS_FILE.exists():
        return json.loads(TOKENS_FILE.read_text())
    # primeira execução: usa os valores que vieram dos Secrets
    return {
        "refresh_token": os.environ["ML_REFRESH_TOKEN"],
        "access_token": os.environ.get("ML_ACCESS_TOKEN", ""),
    }


def save_tokens(tokens):
    STATE_DIR.mkdir(exist_ok=True)
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2, ensure_ascii=False))


def refresh_access_token(tokens):
    resp = requests.post(
        "https://api.mercadolibre.com/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": ML_CLIENT_ID,
            "client_secret": ML_CLIENT_SECRET,
            "refresh_token": tokens["refresh_token"],
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"Falha ao renovar o token do Mercado Livre: {resp.status_code} {resp.text}")
        resp.raise_for_status()
    data = resp.json()
    new_tokens = {
        "access_token": data["access_token"],
        # se o ML não mandar um refresh_token novo, mantém o atual
        "refresh_token": data.get("refresh_token", tokens["refresh_token"]),
    }
    save_tokens(new_tokens)
    return new_tokens


# --------------------------------------------------------------------------
# Controle de duplicados
# --------------------------------------------------------------------------

def load_sent():
    if SENT_FILE.exists():
        return json.loads(SENT_FILE.read_text())
    return {}


def save_sent(sent):
    cutoff = time.time() - SENT_ITEM_TTL_DAYS * 24 * 3600
    pruned = {item_id: ts for item_id, ts in sent.items() if ts > cutoff}
    STATE_DIR.mkdir(exist_ok=True)
    SENT_FILE.write_text(json.dumps(pruned, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------
# Mercado Livre: busca e reputação do vendedor
# --------------------------------------------------------------------------

def search_items(access_token, query):
    resp = requests.get(
        "https://api.mercadolibre.com/sites/MLB/search",
        params={"q": query, "limit": ITEMS_PER_KEYWORD},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if not resp.ok:
        print(f"Busca por '{query}' falhou: {resp.status_code} {resp.text[:300]}")
        return []
    return resp.json().get("results", [])


def is_trusted_seller(seller_id, access_token, cache):
    if seller_id in cache:
        return cache[seller_id]
    resp = requests.get(
        f"https://api.mercadolibre.com/users/{seller_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    trusted = False
    if resp.ok:
        reputation = resp.json().get("seller_reputation") or {}
        trusted = reputation.get("power_seller_status") in TRUSTED_POWER_SELLER_STATUS
    cache[seller_id] = trusted
    return trusted


def affiliate_link(url):
    """Troca o link comum por um link de afiliado, se o programa estiver
    configurado. Sem ML_AFFILIATE_ID, devolve o link direto do produto."""
    if not ML_AFFILIATE_ID:
        return url
    # TODO: ajustar aqui assim que o cadastro em afiliados.mercadolivre.com.br
    # for aprovado — o formato exato do link de afiliado depende da
    # ferramenta que o programa disponibilizar (encurtador próprio, etc.).
    return url


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------

def fmt_brl(value):
    """1234.5 -> '1.234,50' (separador de milhar . e decimal ,)."""
    inteiro, centavos = f"{value:,.2f}".split(".")
    inteiro = inteiro.replace(",", ".")
    return f"{inteiro},{centavos}"


def send_to_telegram(item, discount_pct):
    price = item["price"]
    original_price = item["original_price"]
    link = affiliate_link(item.get("permalink", ""))

    text = (
        f"{item['title']}\n\n"
        f"De R${fmt_brl(original_price)} | Por R${fmt_brl(price)} \U0001F4B0  (-{discount_pct:.0f}%)\n\n"
        f"\U0001F6D2 Achado no Mercado Livre\n"
        f"\U0001F449 {link}\n\n"
        f"\U0001F4B0 Link de afiliado"
    )

    thumbnail = item.get("thumbnail", "").replace("http://", "https://")

    if thumbnail:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": text, "photo": thumbnail},
            timeout=30,
        )
    else:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=30,
        )

    if not resp.ok:
        print(f"Falha ao postar no Telegram: {resp.status_code} {resp.text[:300]}")
    return resp.ok


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    tokens = load_tokens()
    tokens = refresh_access_token(tokens)
    access_token = tokens["access_token"]

    sent = load_sent()
    seller_cache = {}
    posted = 0
    checked = 0

    for keyword in KEYWORDS:
        for item in search_items(access_token, keyword):
            checked += 1
            item_id = item.get("id")
            if not item_id or item_id in sent:
                continue

            price = item.get("price")
            original_price = item.get("original_price")
            if not price or not original_price or original_price <= price:
                continue  # sem desconto real, ignora

            discount = (original_price - price) / original_price
            if discount < DISCOUNT_MIN:
                continue

            seller_id = (item.get("seller") or {}).get("id")
            if not seller_id or not is_trusted_seller(seller_id, access_token, seller_cache):
                continue

            if send_to_telegram(item, discount * 100):
                sent[item_id] = time.time()
                posted += 1
                time.sleep(2)  # evita mandar tudo de uma vez de rajada

    save_sent(sent)
    print(f"Itens verificados: {checked} | Ofertas novas postadas: {posted}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # garante que o erro aparece claro no log do Actions
        print(f"Erro fatal: {exc}", file=sys.stderr)
        raise
