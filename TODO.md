# TODO / suivi du projet

Tenu à jour au fil du travail. Sert de mémoire entre les sessions — avant de dire
qu'une étape est "terminée", vérifier ici qu'il ne reste rien en attente qui y est
rattaché.

## État actuel (2026-08-15)

- Base historique: 108 632+ matchs (ATP/WTA/Challenger H+F, 2021-2026), 4,8M
  statistiques, 7 150+ joueurs, ~1 974 tournois.
- Cotes historiques: ~13 600/~14 700 matchs éligibles (ATP/WTA, ~20 derniers mois).
- Bug finales de qualifs corrigé (voir "Connu et résolu" plus bas) et
  auto-réparé en continu via `daily_sync`.
- Synchronisation automatique en place sur Render (Cron Jobs) : `daily-sync` (6h UTC),
  `upcoming-odds` (7h UTC), `rankings` (lundi 8h UTC) — confirmé fonctionnel.
- API de lecture déployée : `https://tennis-data-platform.onrender.com`
  (`/matches`, `/matches/{id}`, `/tournaments`, `/players`, `/players/{id}`,
  `/players/{id}/form`, `/players/{id}/rankings`, `/players/{id}/h2h/{other_id}`).
- Frontend calendrier/résultats déployé : https://tennis-data-platform-gby1.onrender.com
  (React + Vite + Tailwind, dossier `frontend/`) : liste filtrable + page détail
  (sets, stats, cotes, **comparaison de forme des 2 joueurs**) + pages joueurs (bio,
  classement, indicateurs de forme, historique, recherche), tout en anglais.
- Enrichissement bio joueurs terminé (`scripts/enrich_players.py`) : 4 383 joueurs
  actifs (ATP/WTA/Challenger, 24 derniers mois) ont pays + date de naissance
  (`hand` reste toujours `null`, jamais fourni par le fournisseur).
- Premiers indicateurs analytics (`tennis_data/analytics/form.py`) : win rate
  10/20/30 derniers matchs, fenêtres 3/6/12 mois, par surface, série en cours,
  jours de repos. Paramètre `as_of` dès le départ pour être réutilisable au
  backtesting (étape 14) sans réécriture.
- Repo: https://github.com/rafiksiala/tennis-data-platform

## À faire — bloquant ou à surveiller

- [ ] **Finir le backfill des cotes** : la dernière passe de nettoyage s'est arrêtée sur
      un quota épuisé à 100/1291 matchs restants. À vérifier/relancer
      (`scripts/backfill_odds.py`).
- [x] **CORS restreint** (2026-08-13) : `allow_origins` limité au frontend déployé
      (https://tennis-data-platform-gby1.onrender.com) + dev local. Testé: notre origine
      passe, une origine tierce est bloquée.
- [ ] **Nom de tournoi bizarre observé** : "Brownsburg (Usa) - Qualification" apparaît
      comme *nom de tournoi* (pas comme round) dans l'UI — à vérifier si c'est un vrai
      tournoi de qualification distinct côté fournisseur (plausible) ou un artefact de
      parsing. Vu une seule fois pour l'instant, pas creusé.

## À faire — pas bloquant

- [x] **Enrichissement bio joueurs terminé** (2026-08-13) : 4 383 joueurs actifs
      (ATP+WTA+Challenger). `hand` restera toujours `null` — jamais fourni par le
      fournisseur (confirmé par test). Les joueurs inactifs depuis 24+ mois ou
      nouvellement rencontrés restent à `null` jusqu'à ce qu'on relance le script -
      pas automatisé en continu pour l'instant (contrairement au reste du pipeline).
- [ ] **Drapeaux emoji ne s'affichent pas sur certaines configs Windows** : le code
      pays est bien généré (mapping `frontend/src/lib/countries.ts`), mais le rendu
      graphique dépend des polices du navigateur/OS - affiche le code ISO en texte
      brut ("ES", "GB") au lieu du drapeau sur certaines machines. Pas un bug de notre
      code, rien à faire a priori.
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

## Connu et résolu (pour référence)

- **Finales de qualifs comptées comme vraies finales** : `event_qualification` du
  fournisseur souvent `null` au lieu de `False`/`True`. Corrigé par heuristique
  (la finale la plus tardive d'un tournoi = la vraie) + auto-réparation continue dans
  `daily_sync` (voir `tennis_data/ingest/maintenance.py`). Ce qui ressemblait à des
  "doublons de tournois" (ex: "Wimbledon" vs "ATP Wimbledon") était en fait ça.
- **Fausses "surfaces" de phases Coupe Davis** (2026-08-15) : `tournament_sourface`
  contient parfois un libellé de round ("- Play Offs", "- Preliminary", etc.) au lieu
  d'une vraie surface, découvert en construisant le win rate par surface. Filtre
  positif ajouté à l'ingestion + casse normalisée + nettoyage des données déjà en
  base (voir `tennis_data/ingest/enrich.py`).

## Connu et volontairement laissé de côté

- **ITF non couvert** : décision prise dès le choix du fournisseur (faible valeur
  analytique vs coût d'ingestion). À reconsidérer seulement si besoin d'historique
  pré-carrière de jeunes joueurs Challenger.
- **Point-by-point brut non modélisé relationnellement** : stocké tel quel en JSONB
  (`matches.points_raw`), pas de table dédiée. Volume trop important pour la valeur
  actuelle — à revisiter si un besoin produit précis émerge.

## Prochaine étape

Calendrier + pages joueurs + premiers indicateurs de forme déployés et validés (voir
ci-dessus). Suite possible : enrichir les indicateurs (qualité des adversaires -
nécessite plus d'historique de classement précis, voir limitation ci-dessus -,
tendance/momentum, contexte tournoi/round), ou démarrer la détection de signaux
(étape 13 du plan initial), selon la priorité du moment.

## Repères opérationnels

- Fournisseur: API-Tennis, plan Starter (8 000 req/jour). Suffisant en régime de
  croisière (sync quotidien + cotes + classements ≈ quelques dizaines d'appels/jour),
  mais tout backfill massif ponctuel peut épuiser le quota du jour — normal, pas un bug.
- Base: PostgreSQL sur Render, plan payant (~7$/mois).
- Historique odds réellement exploitable: ~22-23 mois glissants (confirmé par test),
  pas plus loin quel que soit l'effort de backfill.
- Historique matchs réellement exploitable: ~2021+ pour tous les tours suivis.
