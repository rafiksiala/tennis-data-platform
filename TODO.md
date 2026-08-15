# TODO / suivi du projet

Tenu à jour au fil du travail. Sert de mémoire entre les sessions — avant de dire
qu'une étape est "terminée", vérifier ici qu'il ne reste rien en attente qui y est
rattaché.

## État actuel (2026-08-13)

- Base historique: 108 632+ matchs (ATP/WTA/Challenger H+F, 2021-2026), 4,8M
  statistiques, 7 150+ joueurs, ~1 974 tournois.
- Cotes historiques: ~13 600/~14 700 matchs éligibles (ATP/WTA, ~20 derniers mois).
- Synchronisation automatique en place sur Render (Cron Jobs) : `daily-sync` (6h UTC),
  `upcoming-odds` (7h UTC), `rankings` (lundi 8h UTC) — confirmé fonctionnel.
- API de lecture déployée : `https://tennis-data-platform.onrender.com`
  (`/matches`, `/matches/{id}`, `/tournaments`, `/players/{id}/rankings`,
  `/players/{id}/h2h/{other_id}`).
- Repo: https://github.com/rafiksiala/tennis-data-platform

## À faire — bloquant ou à surveiller

- [ ] **Finir le backfill des cotes** : la dernière passe de nettoyage s'est arrêtée sur
      un quota épuisé à 100/1291 matchs restants. À vérifier/relancer
      (`scripts/backfill_odds.py`).
- [ ] **CORS** : actuellement ouvert à tout le monde (`allow_origins=["*"]` dans
      `api/main.py`). À restreindre à l'origine du frontend une fois déployé.

## À faire — pas bloquant, à traiter avant/pendant l'étape "pages joueurs"

- [ ] **Bio joueurs jamais peuplée** : `country_code`, `birth_date`, `hand` toujours
      `null`. Il faudrait appeler `get_players` (par `player_id` ou `tournament_key`,
      voir contrainte API confirmée par test) pour enrichir progressivement.
- [ ] **Champs tournoi jamais peuplés** : `level`, `country`, `city`, `prize_money`
      toujours `null`. Utile pour des filtres type "Grand Chelem uniquement".
- [ ] **Classement précis à la date du match, historique** : on n'a que la précision
      `weekly` depuis le 2026-08-08 (capture continue). La reconstitution
      `season_approx` pour les matchs antérieurs (via le rang de fin de saison de
      `get_players`) n'a jamais été implémentée — limitation connue depuis le choix du
      fournisseur, toujours vraie.
- [ ] **Pollution résiduelle qualifs sur QF/SF** : seule la reclassification de `F` a été
      corrigée (heuristique "la finale la plus tardive du tournoi"). `QF`/`SF` pourraient
      avoir une pollution similaire mais plus faible (rare que les qualifs aillent
      jusqu'à ce stade) — pas mesuré, pas corrigé.
- [ ] **Ordre du tri `/tournaments`** : trie sur `start_date` qui est toujours `null`
      (tri sans effet réel). Mineur, base petite donc pas de problème de perf, mais
      illogique — à corriger (ex: trier par `season desc, name`) en même temps que le
      remplissage des champs tournoi.

## Connu et volontairement laissé de côté

- **ITF non couvert** : décision prise dès le choix du fournisseur (faible valeur
  analytique vs coût d'ingestion). À reconsidérer seulement si besoin d'historique
  pré-carrière de jeunes joueurs Challenger.
- **Point-by-point brut non modélisé relationnellement** : stocké tel quel en JSONB
  (`matches.points_raw`), pas de table dédiée. Volume trop important pour la valeur
  actuelle — à revisiter si un besoin produit précis émerge.
- **Doublons de tournois liés au nommage** (ex: anciennes observations "Wimbledon" vs
  "ATP Wimbledon") : investigué le 2026-08-13, s'est avéré être le bug qualifs
  ci-dessus, pas un vrai doublon de lignes `tournaments`. Rien à faire ici a priori,
  mais à garder en tête si un cas similaire réapparaît.

## Prochaine étape

Frontend — calendrier/résultats (étape 10 du plan initial). Stack pas encore décidée.

## Repères opérationnels

- Fournisseur: API-Tennis, plan Starter (8 000 req/jour). Suffisant en régime de
  croisière (sync quotidien + cotes + classements ≈ quelques dizaines d'appels/jour),
  mais tout backfill massif ponctuel peut épuiser le quota du jour — normal, pas un bug.
- Base: PostgreSQL sur Render, plan payant (~7$/mois).
- Historique odds réellement exploitable: ~22-23 mois glissants (confirmé par test),
  pas plus loin quel que soit l'effort de backfill.
- Historique matchs réellement exploitable: ~2021+ pour tous les tours suivis.
