# Revue de SPEC.md

Liste des points relevés à la revue de [SPEC.md](../SPEC.md), mise à jour au fur
et à mesure qu'ils sont traités. Les références sont les identifiants de
règles et les sections de la spec (pas de numéros de ligne : ils bougent).

Statuts : ✅ traité (décision appliquée dans la spec) · ⏳ ouvert ·
❌ abandonné.

## A. Contradictions

- ✅ **A1. Nouvelle requête pendant une confirmation.** Décision : en
  `CONFIRMING(r)` / `RETRY_WAIT(r)`, une requête pour un autre état est
  toujours envoyée, sans comparer avec l'état montré ; le timer de
  confirmation est réarmé ; à sa fin, si l'entité source montre `r`, la
  requête est confirmée sans monitoring. Appliqué : SRC-STATE-2, SRC-REQ-5,
  SRC-REQ-6, diagramme §1.2.4, MON-SRC-3.
- ✅ **A2. Phase stockée.** Décision : toute entrée dans `ON(heat_cool)`
  passe par `wanted(entering)` ; sans température de référence : source
  heat/cool qui tourne, sinon phase stockée, sinon `heat`. La phase stockée
  est oubliée quand on quitte `heat_cool`. Appliqué : ENT-WANT-1 et son
  diagramme, ENT-PHASE-1, ENT-INIT-4.
- ✅ **A3. Cible hors plage.** Décision : l'utilisateur ne peut pas sortir de
  la plage (demande hors de la plage montrée refusée) ; une valeur prise à
  la source (takeover) peut l'être. Appliqué : ENT-TGT-3, ENT-RANGE-5,
  ENT-TGT-7. Suite : sur une modification des capacités (découverte ou mise
  à jour du pas / de la plage), l'entité reprend la main sur toutes les
  cibles gardées, takeover compris (pas d'indicateur d'origine). Appliqué :
  ENT-TGT-4 (nouvelle), ENT-CAP-6, ENT-TGT-9.
- ✅ **A4. Fan/swing réglé sans option montrée.** Décision : distinction
  capacité / valeurs. Capacité non découverte : non affichée, commande
  refusée. Capacité découverte : affichée (éventuellement vide), seules les
  valeurs découvertes sont affichées et acceptées. `OFF` inchangé
  (ENT-FAN-3). Appliqué : ENT-FAN-4, ENT-CAP-4, ENT-CAP-6, ENT-SET-1.
- ✅ **A5. Valeur fan/swing affichée en `ON(m)`.** Décision : l'entité
  affiche sa valeur gardée (comme pour les cibles). À la première
  utilisation d'un mode, les fan/swing sans valeur gardée sont suivis tout
  de suite, y compris pendant `SETTLE(m)` (la stabilisation ne protège que
  les réglages envoyés). Appliqué : ENT-FANV-8, SRC-SET-5, SRC-SET-11,
  SRC-SET-12, ENT-FANV-5, ENT-CAP-6, diagramme §1.2.5, §1.1.2.
- ✅ **A6. Garde du changement de mode (mode non offert par une source
  disponible).** Décision : une source qui n'offre pas un mode servi est
  `UNUSABLE` (+ Repairs issue) ; une source qui sert plusieurs modes est
  bloquée pour tous. Configuration : refusée si la source expose ses modes
  sans le mode servi (à la création / modification seulement) ; acceptée
  si elle ne les expose pas. Appliqué : glossaire, §1.2.1
  (`served_mode_lost`, `served_modes_back`), diagramme §1.2.3.1,
  SRC-STATE-1/6/7/8, SRC-ON-1, SRC-UNUS-1 (nouvelle, §1.2.3.5),
  ENT-HVAC-2/3/5, ENT-TYPE-4, ENT-TYPE-8.
  - ✅ Repairs issue pour une source acceptée sans vérification : levé
    seulement si, une fois vue, elle n'offre pas le mode (ENT-HVAC-5). Pas
    d'issue « non vérifié » à l'acceptation (cas courant, rien à réparer ;
    une source jamais vue est `UNDISCOVERED`, son mode est refusé). Le cas
    d'une source qui n'apparaît jamais est traité en B1.
- ✅ **A7. Mode étranger et resynchronisation.** Décision : un mode étranger
  est toléré jusqu'au prochain `apply` / `follow` de l'entité (changement de
  mode utilisateur, takeover d'une autre source, changement de phase,
  démarrage / rechargement), qui éteint toute source non `OFF`. Au retour
  d'indisponibilité, la source renvoie son état stocké : le mode étranger
  si aucun `apply` / `follow` n'a eu lieu, sinon `off`. Appliqué :
  ENT-STATE-5, SRC-STATE-7.

## B. Trous

- ✅ **B1. `UNDISCOVERED`.**
  - ✅ `NO_SOURCE` : décision, il couvre `UNUSABLE` et `UNDISCOVERED`
    (« no source available »). Appliqué : mots de §1.3.2 (« becomes
    available », « no source available »), diagramme §1.3.2.1,
    ENT-STATE-6, §1.3.2.6, MON-SRC-1.
  - ✅ Requêtes : décision, une source `UNDISCOVERED` ne reçoit aucune
    requête (ses modes sont refusés ; pas besoin de l'éteindre, elle
    entre en `OFF` à la découverte). Un changement de configuration met
    l'entité en `OFF` (mode stocké `off`, phase oubliée). Appliqué :
    `apply` / `follow` et `apply(p)`, SRC-STATE-8, ENT-INIT-2, ENT-INIT-4.
  - ✅ Bi-source : couvert par la décision précédente. Appliqué : une
    phase dont la source est `UNDISCOVERED` n'est jamais choisie à
    l'entrée (ENT-WANT-1 et son diagramme), ni prise par un changement
    de phase (ENT-WANT-3 et son diagramme, ENT-PHASE-7). Seul
    `UNDISCOVERED` bloque le changement de phase : vers une source
    `UNUSABLE`, la phase change et passe en `WAITING_PHASE(p')`
    (diagramme de phase, ENT-PHASE-5). La découverte d'une source de
    phase compte comme un « new reading », pour que le changement bloqué
    puisse se faire (définition de « new reading », ENT-PHASE-2) ; gardes de `resume`
    (« every source of m UNDISCOVERED », « no source of m available, one
    UNUSABLE ») ; `ON → WAITING` et ENT-PHASE-6 en « no phase source
    available ».
  - ✅ Monitoring : décision, une source `UNDISCOVERED` est signalée après
    `monitoring_duration`, quel que soit le mode stocké (`OFF` compris).
    `UNUSABLE` inchangé (immédiat, jamais en `off`), avec son explication.
    Appliqué : MON-SRC-5 (nouvelle), tableau §4.2, MON-SRC-2, §4.1,
    `monitoring_duration` (§3.1.5).
- ✅ **B2. `resume`.** Le mode stocké qui n'est plus configuré
  (ENT-INIT-4) manquait dans les gardes. Résolu par B1 : un changement de
  configuration met l'entité en `OFF`, le mode stocké est donc toujours
  configuré. (Le mode stocké que la source n'offre plus est couvert par
  A6 : source `UNUSABLE` → `WAITING(m)`.)
- ✅ **B3. SRC-DATA-6.** Une liste qui gagne et perd des items à la fois
  n'était pas traitée. `supported_features` qui perd un bit était un
  « nouveau nombre » stocké tout de suite, alors que c'est une disparition
  de capacité. Rédaction clarifiée : une valeur faite d'items (liste,
  `supported_features`) est comparée item par item ; un item ajouté est
  stocké tout de suite, chaque item retiré a sa propre confirmation.
  Appliqué : SRC-DATA-6, en-tête de la confirmation de retrait,
  SRC-DATA-10.
- ✅ **B4. Options en `OFF`** (ENT-FAN-3). « Every configured mode in
  sync_modes » était impossible dès qu'il y a un `heat_cool` bi-source,
  qui est ignoré dans `sync_modes` (ENT-FAN-7). Décision : le `heat_cool`
  bi-source est exclu de la condition. Appliqué : ENT-FAN-3 (ENT-FAN-4,
  ENT-FANV-8 et ENT-FANV-9 y renvoient).
- ✅ **B5. Bi-source, non dit.**
  - ✅ Ce que chaque phase envoie : la cible de son mode, comme en `heat` /
    `cool` (low à la source heat, high à la source cool). Appliqué :
    ENT-TGT-8.
  - ✅ Question liée : une source `heat` ou `cool` était classée « with
    low/high » dès qu'elle déclarait les deux features et offrait
    `heat_cool`. Décision : branche « offers `heat_cool` » retirée, seul
    `low_high_seen` (par mode) compte (`heat_cool` et `auto` peuvent
    utiliser low/high). Appliqué : ENT-FEAT-2.
  - ✅ Offset / external sensor : généralisé, sans effet pour un mode sans
    entité source propre (non configuré, ou `heat_cool` bi-source).
    Appliqué : CFG-SENS-1 (nouvelle, §3.1.3), tableau §3.1.3.
  - ✅ Plage : du min de la phase heat au max de la phase cool. Appliqué :
    ENT-RANGE-1.
  - ✅ Référence en `OFF` après un `heat_cool` bi-source : les deux sources,
    comme en `ON(heat_cool)` (le plus simple : même calcul, la phase est
    oubliée en `OFF`). Appliqué : ENT-REF-2.
  - ✅ Source de phase mise en `heat_cool` : mode étranger (pas de source
    `heat_cool` dans la configuration). Appliqué : mots de §1.3.1
    (served / foreign), ENT-TYPE-9.
- ✅ **B6. Démarrage de HA.** Une entité source chargée après l'intégration
  donne `UNUSABLE` en premier état, donc `WAITING(m)`. MON-SRC-1 signalait
  « at once » : warning + événement à chaque redémarrage. Décision :
  harmonisation, `UNUSABLE` est signalé après `monitoring_duration` comme
  les autres problèmes (absorbe aussi les coupures brèves). Le passage
  bref par `WAITING(m)` au démarrage est gardé (visuel, état juste).
  Appliqué : MON-SRC-1, tableau §4.2, `monitoring_duration` (§3.1.5).
- ✅ **B7. ENT-TGT-9.** Si l'autre cible ne peut pas bouger (bout de plage)
  et que la cible prise « never gives way » : écart cassé, ou l'autre sort
  de sa plage ? (Origine de la cible poussée : sans objet depuis A3, plus
  d'indicateur d'origine.) Décision : la source gagne, l'écart est cassé
  jusqu'au prochain réglage utilisateur ou changement de capacités ; une
  source qui change low et high est prise telle quelle. Appliqué :
  ENT-TGT-9, ENT-TGT-4 (rétablit l'écart : high bouge, sinon low).
  Suite : à l'envoi, chaque cible est ramenée seule dans la plage du mode,
  la paire envoyée pouvait perdre l'écart (plage du mode plus étroite,
  écart cassé, valeur prise hors plage). Décision : l'écart est rétabli
  sur les valeurs envoyées, après la plage (high monte, sinon low
  descend) ; les valeurs gardées ne changent pas. Appliqué : ENT-TGT-8.
- ✅ **B8.** `UtAC_set_mode(m)` en `ON(m)` (même mode) : rien, ou nouvel
  `apply` ? Décision : rien (idempotent : pas d'envoi, pas d'erreur),
  aussi en `WAITING(m)` pour `m` (refusé avec erreur avant) et en `OFF`
  pour `off` (transition absente avant). Appliqué : diagramme §1.3.2.1,
  ENT-STATE-4.
- ✅ **B9. SRC-SET-7.** Le retry à 5 s si le mode change entre-temps.
  La relance est le seul déclencheur d'envoi (`StSE_set_*`) sans les
  conditions des autres (`ON(m)`, pas de confirmation, valeur non montrée),
  et l'état `RETRY` ne traite aucun événement pendant les 5 s.
  - ✅ Clarification préalable de §1.2.5 : renommée « Setting request
    management » ; démarrage (une fois, à `start`, en parallèle de
    §1.2.3 et §1.2.4) ; trois étapes `ACtS_settings` → machine à état →
    `StSE_set_*` ; tableau des déclencheurs d'envoi. Aussi : liste des
    fonctions de §1.2, table des événements. Puis intro reformulée :
    c'est la setting request management qui garde les réglages (en
    mémoire, mode en cours de la source) et les envoie sur des
    événements de l'entité, de la confirmation de requête ou de ses
    timers (colonne « From »).
  - ✅ Décision : l'état `RETRY` est supprimé, la relance devient un timer
    de `STEADY` (comme la resync). Annulé par un changement de mode ou
    l'entrée en `UNUSABLE` ; à son échéance, en `ON(m)` hors
    confirmation, renvoi des réglages gardés non montrés, une seule fois.
    Appliqué : SRC-SET-7. Le diagramme de §1.2.5 (un seul état, illisible)
    est remplacé par un tableau de réactions (Keeping / Sending /
    Following the source entity), qui absorbe le tableau des déclencheurs.

## C. Canaux source → entité manquants

Revu le 2026-11-13 sur l'état actuel de la spec.

- ✅ **C1. Pas d'événement « capacités changées ».** Décision : nouvel
  événement `StAC_capabilities` (sans paramètre), levé par la gestion des
  données stockées à chaque changement stocké des capacités (`hvac_modes`,
  capacités de mode, `low_high_seen`) : ajout / nouvelle valeur, retrait
  confirmé ; un seul événement par mise à jour de l'entité source ; pas
  levé pour `data_available` (la sortie d'`UNDISCOVERED` est déjà signalée).
  La gestion des capacités de l'entité tourne en parallèle de sa machine
  à états (dit en tête de §1.3.4) : elle traite l'événement dans tous les
  états (`INIT` et `NO_SOURCE` compris), sans changer d'état : relecture
  des capacités, ENT-TGT-4 si pas / plage
  changés, ENT-FANV-3 si options changées, réécriture de son état dans HA
  (sauf `INIT` / `NO_SOURCE`). Appliqué : §1.1.2 (événement, ligne
  `data`), §1.3.1, SRC-DATA-6, SRC-DATA-8, diagramme de confirmation de
  retrait, SRC-DATA-12 (nouvelle), en-tête de §1.3.4, ENT-CAP-6, ENT-CAP-7 (nouvelle),
  ENT-TGT-4, ENT-FANV-3. La valeur courante de la source dont ENT-FANV-3
  a besoin est réglée en C3 (`settings@S`).

  Constat de départ : l'entité lit les
  données de la source « quand il faut » (§1.1.2, ligne `data`), mais
  rien ne lui signale un changement. Or plusieurs règles demandent d'agir
  au moment du changement :
  - ENT-CAP-6 / ENT-TGT-4 : découverte d'un mode, ou mise à jour du
    pas / de la plage (SRC-DATA-6, SRC-DATA-10) → reprise des cibles
    gardées, et envoi (`ACtS_settings`) en `ON(m)` / `WAITING(m)` ;
  - ENT-FANV-3 : une option qui n'est plus offerte par tous les modes
    d'une mémoire partagée → la valeur gardée est remplacée (avec la
    valeur courante de la source : voir C3) ;
  - publication dans Home Assistant de min/max/step, des options
    fan/swing et des features (l'état de l'entité doit être réécrit).

  `data_available` et la fin d'une confirmation de retrait restent
  internes à la source. ENT-HVAC-5 n'est plus concerné depuis A6 :
  l'issue suit `StAC_unusable` / `StAC_usable` (l'entité lit
  `hvac_modes` pour distinguer mode perdu et indisponibilité).
- ✅ **C2. `hvac_action` : l'entité n'avait aucun moyen de le connaître.**
  La source ne le gardait pas et aucun `StAC_*` ne le portait ; l'entité
  ne lit jamais l'entité source (§1.1.1). Décision :
  - lecture à la demande à travers la source, sans stockage : la valeur
    que l'entité source montre à ce moment, `None` si elle n'en a pas ou
    n'est pas utilisable ;
  - les changements (`SEtS_attributes`, `SEtS_on(m)`, `SEtS_off`) sont
    relayés par la source en `OFF` / `ON(m)` : `StAC_action(a)` ;
  - l'entité lit la valeur quand la source active change ou revient
    (entrée en `ON(m)`, changement de phase, retour de la source de
    phase d'`UNUSABLE`), puis suit `StAC_action` de la source active
    seulement ;
  - montrée telle quelle, aussi pendant une confirmation de requête et
    `SETTLE(m)` (même si c'est encore l'action de l'ancien mode) ;
  - entité source sans `hvac_action` → `None` dans l'entité (la card HA
    affiche alors le mode à la place de l'action, vérifié dans le code du
    frontend).

  Appliqué : §1.1.2 (événement `StAC_action(a)`, ligne `action`), §1.3.1,
  SRC-STATE-12 (nouvelle), ENT-ON-1, ENT-ON-2 (nouvelle), §2.2.

- ✅ **C3. Valeurs courantes d'une source hors takeover.**
  `StAC_settings` n'existe qu'en `ON(m)`, sur un changement (ou en
  `SETTLE(m)` pour les fan/swing sans valeur gardée, SRC-SET-12).

  Décision générale : distinguer **événements** et **données**. Un
  événement `XtY_nom` déclenche quelque chose chez `Y`. Une donnée
  `nom@X` est une valeur que `X` rend lisible : on la lit en la nommant,
  quand on en a besoin, sans événement. Données de la source :
  `capabilities@S` (données stockées), `action@S` (`hvac_action`
  actuel), `settings@S` (réglages montrés par l'entité source, quel que
  soit l'état de la source). Appliqué : §1.1.2 (renommée « Events and
  data », convention, tableau des données ; lignes `data` / `action`
  retirées des tableaux d'événements), sommaire, §1.3.1, SRC-STATE-12,
  ENT-CAP-1, ENT-CAP-7, ENT-ON-2, `StAC_capabilities`.
  - ✅ ENT-TGT-10 (premières cibles) a besoin des cibles de sources `OFF`.
    Résolu : lecture de `settings@S`. Branche « source active » retirée
    (au premier démarrage l'entité est forcément en `OFF`). Les low/high
    d'une source `heat_cool` sont lus dans `settings@S` s'ils sont
    montrés.
  - ✅ Quel offset retirer pour une source qui sert plusieurs modes ?
    Décision : erreur de configuration, une entité source n'a qu'un
    offset ; les modes qu'elle sert doivent avoir le même (un mode avec
    capteur externe compte pour 0), sinon la configuration est refusée.
    Étendu au capteur externe : les options d'une même source doivent
    être cohérentes, même `<mode>_external_sensor` pour tous ses modes
    (ou aucun). Appliqué : §3.1.3 (textes sur l'offset et le capteur
    externe), CFG-SENS-2 (nouvelle), MON-TEMP-2 (une lecture par entité
    source, cas « offsets différents » retiré), ENT-TGT-10, ENT-EXT-1
    (une écriture par capteur externe, pas par mode).
  - ✅ ENT-FANV-3 : « replaced by the current value of the source » —
    valeur que l'entité n'avait pas hors `StAC_settings`, source non
    désignée. Résolu : la valeur actuelle de la source dont les options
    ont changé (`settings@S`).
- ✅ **C4. Absence de valeur et valeurs initiales.**
  Constat : `TStAC_temperature` ne portait qu'une valeur valide, alors
  que ENT-REF-2, ENT-EXT-5 et MON-TEMP-4 doivent savoir que le capteur
  est devenu invalide ; on ne savait pas si un `current_temperature`
  disparu était remonté ; les événements étant des changements, une
  valeur stable n'était jamais connue (démarrage, découverte, retour
  d'`UNUSABLE`). Décision, avec la convention événements / données de
  C3 :
  - nouvelles données `temperature@T` (valeur du capteur, `None` si non
    valide) et `temperature@S` (`current_temperature` montrée, `None` si
    absente ou source non utilisable), non stockées ;
  - les événements portent aussi la disparition :
    `TStAC_temperature(None)`, `StAC_temperature(None)` ;
  - l'entité et le monitoring lisent les données à chaque calcul, refait
    sur chaque événement qui peut le changer (valeur changée, entrée en
    `OPER`, changement de mode ou de phase, source disponible ou
    `UNUSABLE`) : une valeur stable est lue tout de suite ;
  - capteurs externes : écriture de `temperature@T` dès `start` s'il est
    valide.

  Appliqué : §1.1.2 (`TStAC_temperature`, `StAC_temperature`, tableaux
  des données du capteur et de la source), §1.3.1, SRC-STATE-11,
  ENT-REF-1, ENT-REF-2, ENT-REF-7 (nouvelle), ENT-EXT-1, ENT-EXT-4,
  ENT-EXT-5, §3.1.3 (`temperature_sensor`), MON-TEMP-1, MON-TEMP-2,
  MON-TEMP-4, MON-TEMP-5 (nouvelle).

## D. Références et termes

- ✅ **D1. Numérotation des règles.** `SET-x` (§1.2.5) n'avait pas de
  numéro, et ENT-TGT-13 était placée avant ENT-TGT-4. Décision : règles
  renumérotées dans l'ordre du document, chaque préfixe sans trou ;
  renvois mis à jour dans la spec et dans cette revue (les numéros cités
  plus haut sont les nouveaux). Changements : `SET-x` → SRC-SET-6, et
  SRC-SET-6…11 → SRC-SET-7…12 ; ENT-TGT-13 → ENT-TGT-4, et
  ENT-TGT-4…12 → ENT-TGT-5…13. Les autres règles gardent leur numéro.
  Vérification de tous les renvois (règles et sections) ; corrigés :
  - SRC-STATE-7 (renvoi sur le nouvel envoi à la fin du settle) : SRC-SET-5 →
    SRC-SET-5, SRC-SET-6 ;
  - ENT-STATE-5 (« `resume` makes an `apply` ») : SRC-STATE-10 →
    ENT-INIT-1, ENT-INIT-4 ;
  - ENT-CAP-6 (7–35 °C d'un mode non découvert) : ENT-RANGE-1 →
    ENT-CAP-4, qui le définit ;
  - §3.1.1, option `name` : « (§4.1) » → §3.2 (point D3).
- ✅ **D2.** Avant ENT-PHASE-6 (« Leaving: both phase sources UNUSABLE ») :
  renvoi « (ENT-PHASE-5) » → ENT-PHASE-6 (corrigé avec B1).
- ✅ **D3.** §3.1.1, option `name` : « (§4.1) » → §3.2 (corrigé avec D1).
- ✅ **D4.** §1.2.2.1, ligne « State » : « mode management » (fonction de
  l'entité, §1.3.3) → state management (SRC-STATE-9). Aussi : « the last
  usable state » était inexact, une requête reçue en `UNUSABLE` devient
  l'état stocké (SRC-STATE-4). Appliqué : ligne « State » de §1.2.2.1.
- ✅ **D5.** `next_mode` (ENT-SET-1) : remplacé (A4).
- ✅ **D6.** « mode order » et « first configured mode » : jamais définis.
  Décision : l'ordre de l'enum `HVACMode` de Home Assistant (`off`,
  `heat`, `cool`, `heat_cool`, `auto`, `dry`, `fan_only`), mono- ou
  bi-source. Appliqué :
  glossaire (§0), ENT-HVAC-1 (liste des modes dans cet ordre) ; utilisé
  par ENT-STATE-2, ENT-INIT-4, ENT-REF-2, ENT-FAN-6.
- ✅ **D7.** « request confirmation » : inclut `RETRY_WAIT` dans SRC-SET-3, pas dans
  SRC-STATE-5 ni SRC-STATE-10 (SRC-REQ-9 suit les changements en
  `RETRY_WAIT`). Décision : « request confirmation running » =
  `CONFIRMING` ou `RETRY_WAIT` (comme en §1.2.5), défini en tête de
  §1.2.4. SRC-STATE-5 réécrite : le seul changement de mode de l'entité
  source non suivi est celui qui ne montre pas `r` en `CONFIRMING(r)` ;
  en `RETRY_WAIT(r)` et `SETTLE(m)`, takeover. SRC-STATE-10 : takeover en
  `OFF` / `ON(m)` sauf en `CONFIRMING(r)`.
- ✅ **D8.** « offered » : ENT-CAP-3 (la source l'offre) contre ENT-HVAC-1
  (configuré). Décision : « offer » réservé à la source (ce que montre
  l'entité source) ; pour l'entité, « listed » (dans `hvac_modes`) et
  « available ». Appliqué : ENT-CAP-3 (un mode non découvert est
  disponible, ENT-HVAC-2), ENT-HVAC-1, titre de §1.3.4.2 « Modes listed »
  et sommaire, tableau de §1.3.3.1 (« not listed »).
- ✅ **D9.** « usable » appliqué aux sources (ENT-TYPE-8, ENT-STATE-7, diagramme de
  phase) alors que §1.3.1 définit « available ». Décision :
  « usable » réservé aux entités source (glossaire) ; pour une source,
  « available » (§1.3.1) ou `UNUSABLE`. Appliqué : ENT-STATE-7,
  ENT-TYPE-8, ENT-HVAC-3, `PHASE(p)` et gardes du diagramme de phase,
  ENT-REF-2 et son diagramme (« first available source »), ENT-REF-3,
  ENT-TGT-10, §1.2.3.5, SRC-STATE-9, SRC-ON-1, glossaire (« Served
  modes »).
- ✅ **D10.** `StAC_settings` en §1.1.2 : décrit maintenant aussi la remontée en
  `SETTLE` (A5).
- ✅ **D11.** Doublons : ENT-PHASE-3 / ENT-PHASE-5 ; ENT-TYPE-5 / ENT-INIT-4.
  Décision : ENT-PHASE-5 fusionnée dans ENT-PHASE-3 (le changement de
  phase est un `apply(p)`, chaque source confirme sa requête) ;
  ENT-TYPE-5 supprimée (ENT-INIT-4 la couvre ; la nouvelle ENT-TYPE-5,
  ex-6, y renvoie).
  Renumérotation : ENT-PHASE-6…8 → ENT-PHASE-5…7, ENT-TYPE-6…10 →
  ENT-TYPE-5…9 ; renvois mis à jour dans la spec et cette revue (les
  numéros cités ailleurs sont les nouveaux).
- ✅ **D12.** Forme : SRC-STATE-3 et SRC-REQ-3 coupées en puces au milieu des
  phrases ; sommaire sans §1.2.2.1 à §1.2.2.3 ; marqueurs ❓ / ⚠ / ✅ des
  conventions plus utilisés. Appliqué : SRC-STATE-3 et SRC-REQ-3
  réécrites ; SRC-DATA-4 et SRC-SET-1 réindentées (espaces de fin
  retirés) ; §1.2.2.1 à §1.2.2.3 ajoutées au sommaire, « : » retirés des
  titres de §1.2.2.2 et §1.2.2.3 ; trois lignes de marqueurs retirées
  des conventions.
- ✅ **D13.** ENT-TGT-13 placée avant ENT-TGT-4 (numérotation hors ordre).
  Résolu par D1 : elle est devenue ENT-TGT-4.
- ✅ **D14. Événements sans préfixe.** La convention `XtY_nom` (émetteur →
  récepteur, §1.1.2) n'est pas suivie partout. Événements sans préfixe
  relevés dans la spec :

  | Événement | Où | Émetteur | Récepteur |
  |---|---|---|---|
  | `start` | §1.2.1, §1.2.5, §1.3.2.1 | Home Assistant (mise en place de l'entrée) | source, entité |
  | `restored` | §1.2.1 | gestion des données stockées | machine à états de la source |
  | `data_available` | §1.2.1 | gestion des données stockées | machine à états de la source |
  | `served_mode_lost` | §1.2.1 | gestion des données stockées | machine à états de la source |
  | `served_modes_back` | §1.2.1 | gestion des données stockées | machine à états de la source |
  | `change`, « source entity leaves the mode » | confirmation de retrait (§1.2.2.3) | entité source (alias de `SEtS_*`) | gestion des données stockées |
  | `timeout` | confirmation de retrait | son timer | gestion des données stockées |
  | `send(r)`, `send(r2)` | §1.2.4 | machine à états de la source | confirmation de requête |
  | `confirm timeout`, `retry timeout` | §1.2.4 | ses timers | confirmation de requête |
  | `settle timeout` | §1.2.4, §1.2.5 | timer de la confirmation de requête | confirmation de requête, gestion des réglages |
  | « back from UNUSABLE in ON(m)… » | §1.2.4 | machine à états de la source | confirmation de requête |
  | `StSE_set_hvac_mode failed`, `StSE_set_* failed` | §1.2.4, §1.2.5 | entité source (erreur d'appel) | confirmation de requête, gestion des réglages |
  | « entry of SETTLE(m) », « mode change », « the source enters UNUSABLE » | tableau §1.2.5 | confirmation de requête, machine à états de la source | gestion des réglages |
  | `resync timeout`, `send retry timeout` | §1.2.5 | ses timers | gestion des réglages |
  | « every source has reported its first state », « a source becomes available » | §1.3.2.1 | dérivés des `StAC_*` | machine à états de l'entité |
  | « enter ON(heat_cool) », « new reading » | §1.3.3.2 | dérivés (entrée d'état, `TStAC_*` / `StAC_*`) | gestion des phases |
  | « condition true / false », « lasted its delay » | §4.4 | monitoring | cycle de vie d'un problème |

  Il faut un préfixe aussi pour les échanges entre fonctions d'une même
  source ou de l'entité, et pour les timers. Les événements dérivés
  (alias, conditions sur plusieurs événements) sont à nommer ou à
  remplacer par la liste des événements qu'ils couvrent.

  Décision : codes d'acteurs étendus (`HA` Home Assistant ; fonctions de
  la source `Sd`, `Ss`, `Sc`, `Sr` ; `M` monitoring) ; un événement
  envoyé à `S` ou `AC` atteint toutes ses fonctions ; timers
  `X_name_timeout` (événement de `X` à lui-même) ; plus d'alias : les
  conditions deviennent des gardes sur de vrais événements, et une
  fonction qui doit prévenir une autre lui envoie un événement nommé.
  Correspondance : `start` → `HAtS_start` / `HAtAC_start` ; `restored`,
  `data_available`, `served_mode_lost`, `served_modes_back` →
  `SdtSs_*` ; `change` / « leaves the mode » → les `SEtS_*` avec garde ;
  `timeout` → `Sd_removal_timeout` ; `send(r)` → `SstSc_send(r)` ;
  « back from UNUSABLE… » → `SstSc_back(m)` ; timers →
  `Sc_confirm_timeout`, `Sc_retry_timeout`, `Sc_settle_timeout`,
  `Sr_resync_timeout`, `Sr_send_retry_timeout` ; pour §1.2.5 :
  `SctSr_settle_start`, `SctSr_settle_end`, `SstSr_mode_changed(x)`
  (requête de l'entité) et `SstSr_takeover(x)` (changement de l'entité
  source suivi), `SstSr_unusable` ; `StSE_set_* failed` →
  `SEtS_call_failed(c)` ; « every source has reported… » et « a source
  becomes available » → `StAC_*` avec garde ; « new reading » → la
  liste `TStAC_temperature`, `StAC_temperature`, `StAC_off` (« readings »,
  définies sous le diagramme de phase) ; « enter ON(heat_cool) » →
  transition initiale sans déclencheur ; §4.4 → `M_condition_true`,
  `M_condition_false`, `M_delay_timeout`. Appliqué : §1.1.2
  (convention, `SEtS_call_failed`), §1.2.1 (tableaux : événements, entre
  fonctions, timers), diagrammes de restauration, de confirmation de
  retrait, de la source, de la confirmation de requête, de l'entité, de
  phase et de §4.4 ; tableau de §1.2.5 ; §1.3.1 (`HAtAC_start`) ; textes
  qui citaient ces événements.
- ✅ **D15. Activités sans préfixe.** Les activités nommées des transitions
  n'ont pas de préfixe qui dise qui les fait :
  - entité (§1.3.2.1, §1.3.3.2) : `apply(m)`, `apply(off)`, `apply(p)`,
    `follow(S)` ; calcul de phase `wanted(entering)` (ENT-WANT-1) ;
  - activités écrites en clair dans les diagrammes : `log`, `store r`,
    `save`, `monitoring up` / `monitoring down`, `start` / `cancel` /
    `restart … timer`, « send the kept settings again ».

  À définir : la forme du préfixe (propriétaire de l'activité), et
  lesquelles nommer (les activités composées comme `apply` / `follow`
  au moins).

  Décision : trois sortes d'activités, définies dans la notation des
  diagrammes (§0). Envoi d'un événement : son nom (déjà préfixé, D14).
  Activité composée `X.name` (propriétaire `X`) : `AC.apply(m)`,
  `AC.apply(off)`, `AC.follow(S)`, `AC.apply(p)`, et le calcul
  `AC.wanted` / `AC.wanted(entering)`. Action élémentaire sur la machine
  qui l'écrit, sans préfixe, vocabulaire fixé : `start` / `cancel` /
  `restart T`, `x := v`, `store x`, `save`, `log`. `monitoring up` /
  `monitoring down` → événements `SctM_out_of_sync_up` /
  `SctM_out_of_sync_down` (ajoutés au tableau des événements entre
  fonctions de §1.2.1). `followed (SRC-STATE-5)` retiré des activités
  de §1.2.4 : garde `[followed]` sur les transitions `SEtS_off` /
  `SEtS_on` de la machine de la source, définie sous son diagramme.
  Appliqué : §0, §1.2.1, §1.2.3.1, §1.2.4, §1.3.2.1, §1.3.3.2, et les
  textes qui citaient ces activités.

## E. Écarts avec le code

- ❌ Abandonné : le code est hors périmètre, la spec est la seule référence
  (`min_phase_duration`, limite d'écriture du capteur externe).

## F. Mineurs

- ✅ **F1.** ENT-TYPE-4 : conséquence d'un échec de la vérification (A6).
- ✅ **F2.** MON-SRC-1 : le tableau dit « a source of the stored mode », la puce dit
  « every source, in NO_SOURCE ». Décision : la puce suit le tableau, en
  `NO_SOURCE` seules les sources du mode stocké sont signalées (aucune
  en `off`, MON-SRC-2). Appliqué : MON-SRC-1.
- ✅ **F3.** Durées en dur (5 s retry d'envoi, 30 min resync, 30 s minimum de
  MON-SRC-4) alors que les autres sont en §3.1.4. Décision : restent
  fixes (marges internes), regroupées avec leur justification dans
  CFG-TIMER-2 (§3.1.4).
- ✅ **F4.** Défauts « °C (unit of Home Assistant) » : que valent 1, 2, ±10 en °F ?
  Décision : options dans l'unité de Home Assistant ; distinction
  température / écart de température ; valeurs °F d'un écart = °C × 1,8
  arrondi au °F entier. Appliqué : CFG-UNIT-1 (§3.1), tableaux de §3.1.3,
  §3.1.5, §3.1.6 (offsets ±18 °F, `phase_hysteresis` 2 °F,
  `monitoring_gap` 4 °F, `min_gap` 2 °F).
- ✅ **F5.** `monitoring_duration` : la colonne « Effect » ne citait que MON-SRC-4,
  MON-TEMP l'utilise aussi. Corrigé avec B1 et B6 (MON-SRC-1, MON-SRC-4,
  MON-SRC-5, MON-TEMP-1, MON-TEMP-4).
- ✅ **F6.** SRC-DATA-5 : `hvac_modes` corrompu mais état stocké présent, quelle
  branche de la restauration ? Décision : chaque donnée manquante ou
  corrompue est traitée seule. Sans `hvac_modes` : l'état et les
  capacités sont restaurés, `hvac_modes` est lu sur l'entité source si
  elle est utilisable, sinon données non disponibles jusqu'à la
  première lecture. Sans état : `OFF`. Appliqué : diagramme de §1.2.2.2,
  SRC-DATA-4, SRC-DATA-5, SRC-STATE-1.
- ✅ **F7.** Pas d'entité qui devient plus grossier : les cibles gardées sont-elles
  réarrondies ? (Couvert en partie par ENT-TGT-4 si le changement de pas
  vient d'une modification des capacités.) Décision : oui, réarrondies.
  Le pas ne change qu'avec les capacités (ENT-TGT-4) ou entre deux
  démarrages (source ajoutée ou retirée par un changement de
  configuration). Appliqué : ENT-TGT-4 s'applique aussi à la sortie
  d'`INIT` ; renvoi dans ENT-INIT-1.
- ✅ **F8.** Deux entrées qui partagent la même entité source : non traité.
  Décision : autorisé ; la vérification de la configuration contrôle la
  cohérence des offsets et du capteur externe entre entrées ; une entité
  AC comme source est refusée ; un capteur externe nommé par plusieurs
  modes n'est retenu qu'une fois (une seule écriture par valeur).
  Appliqué : CFG-MODE-1, CFG-MODE-2 (§3.1.2), CFG-SENS-3 (§3.1.3),
  ENT-EXT-1 ; s'applique aussi au YAML (CFG-YAML-5).
  Abandonné : deux entrées qui partagent une entité source avec capteur
  externe, et des `temperature_sensor` différents, y écrivent chacune
  leur valeur. Pas de cas d'usage réel (elles se disputent déjà mode et
  réglages) ; noté sous CFG-SENS-3.
- ✅ **F9.** ENT-HA-1 (renommage `native_*` en 2026.11) : non vérifié.
  Confirmé par l'utilisateur (déjà en place dans le code) ; spec
  inchangée.
