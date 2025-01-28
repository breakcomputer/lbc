import asyncio
import json
import requests
from pathlib import Path
from undetected_playwright.async_api import async_playwright

LEBONCOIN_SEARCH_URL = "https://www.leboncoin.fr/recherche?category=2&fuel=2&price=min-3500&mileage=min-250000&sort=time"
DISCORD_WEBHOOK_URL = ""

DB_FILE = Path("database.json")
KEYWORDS_FILE = Path("keywords.txt")

def lire_keywords():
    """Lit les mots-clés depuis le fichier keywords.txt."""
    if not KEYWORDS_FILE.exists():
        print(f"Fichier {KEYWORDS_FILE} introuvable. Veuillez le créer et y ajouter des mots-clés, un par ligne.")
        return []
    with KEYWORDS_FILE.open("r", encoding="utf-8") as f:
        return [line.strip().lower() for line in f if line.strip()]

def envoyer_vers_discord(titre, prix, annee, kilometrage, lien):
    """Envoie l'annonce sur Discord via un webhook."""
    try:
        embed = {
            "title": titre,
            "description": (
                f"**Prix** : {prix}\n"
                f"**Année** : {annee}\n"
                f"**Kilométrage** : {kilometrage}\n\n"
                f"[Voir l'annonce]({lien})"
            ),
            "color": 0x7289DA,
        }
        data = {
            "content": "Nouvelle annonce trouvée !",
            "embeds": [embed],
        }
        response = requests.post(DISCORD_WEBHOOK_URL, json=data)
        response.raise_for_status()
        print("Annonce envoyée à Discord avec succès.")
    except requests.RequestException as e:
        print(f"Erreur lors de l'envoi à Discord : {e}")

async def main():
    """Relance la page de recherche toutes les 20 secondes après avoir fini de traiter les annonces."""
    keywords = lire_keywords()
    if not keywords:
        print("Aucun mot-clé trouvé. Le script s'arrête.")
        return

    # Lecture (ou création) de la base de données locale
    if DB_FILE.exists():
        with DB_FILE.open("r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = []

    async with async_playwright() as p:
        args = ["--disable-blink-features=AutomationControlled"]
        browser = await p.chromium.launch(headless=False, args=args)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        try:
            while True:  # Boucle infinie
                try:
                    print("Navigation vers la page de recherche...")
                    await page.goto(LEBONCOIN_SEARCH_URL, timeout=60000)
                    await page.wait_for_selector("a[data-test-id='ad']", timeout=60000)

                    # Récupération de toutes les annonces
                    annonces = await page.query_selector_all("a[data-test-id='ad']")
                    print(f"Nombre total d'annonces trouvées : {len(annonces)}")

                    for annonce in annonces:
                        try:
                            # Titre
                            titre_elem = await annonce.query_selector("p[data-qa-id='aditem_title']")
                            if not titre_elem:
                                continue
                            titre = await titre_elem.inner_text()

                            # Vérifie si le titre contient l'un des mots-clés
                            if not any(keyword in titre.lower() for keyword in keywords):
                                continue

                            # Lien
                            lien = await annonce.get_attribute("href")
                            if not lien:
                                continue
                            lien_complet = f"https://www.leboncoin.fr{lien}"

                            # Prix
                            prix_elem = await annonce.query_selector("p[data-test-id='price']")
                            prix = await prix_elem.inner_text() if prix_elem else "Non spécifié"

                            # Année et kilométrage
                            divs = await annonce.query_selector_all("div.relative.h-full.whitespace-nowrap")
                            if len(divs) >= 2:
                                # Année
                                annee_elem = await divs[0].query_selector("p:last-child")
                                annee = await annee_elem.inner_text() if annee_elem else "Non spécifiée"

                                # Kilométrage
                                km_elem = await divs[1].query_selector("p:last-child")
                                kilometrage = await km_elem.inner_text() if km_elem else "Non spécifié"
                            else:
                                annee = "Non spécifiée"
                                kilometrage = "Non spécifié"

                            # Vérifie si déjà présent dans la DB
                            if lien_complet in db:
                                continue

                            # Ajout dans la DB et envoi Discord
                            db.append(lien_complet)
                            envoyer_vers_discord(titre, prix, annee, kilometrage, lien_complet)

                            print(f"Nouvelle annonce ajoutée : {titre} | {prix} | {annee} | {kilometrage}")
                        except Exception as e:
                            print(f"Erreur de traitement d'une annonce : {e}")

                    # Sauvegarde de la DB
                    with DB_FILE.open("w", encoding="utf-8") as f:
                        json.dump(db, f, ensure_ascii=False, indent=4)

                    print("Terminé pour cette boucle. Relance de la recherche dans 20 secondes...")
                    await asyncio.sleep(20)

                except Exception as e:
                    print(f"Erreur lors de la navigation ou du parsing : {e}")
                    await asyncio.sleep(20)

        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
