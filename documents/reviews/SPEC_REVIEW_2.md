# Revue de SPEC.md — revue 2

Deuxième revue complète de [SPEC.md](../SPEC.md), faite le 2026-11-14 sur la
spec telle qu'elle est après la première revue. La première revue (tous ses
points sont traités ou abandonnés) est archivée dans
[SPEC_REVIEW_1.md](SPEC_REVIEW_1.md).

- Les numéros repartent de 1 : « A1 » ici n'est pas le « A1 » de la revue 1.
- Les références sont les identifiants de règles et les sections de la spec
  (pas de numéros de ligne : ils bougent).
- Seule la spec a été lue : le code est hors périmètre.
- Chaque point donne le constat, sa conséquence, et la question à trancher.
  Aucune décision n'est prise ici.
- Les noms ont changé le 2026-11-15 : les fonctions de la source (`Sd`
  → `Sdsm`, `Ss` → `Sstm`, `Sc` → `Smrc`, `Sr` → `Ssrm` ; « stored data
  management » devient « data storage management », « request
  confirmation » devient « mode request confirmation ») et la forme des
  événements (`XtY_name` devient `X=>Y_name` : `SdtSs_restored` devient
  `Sdsm=>Sstm_restored`, `ACtS_request` devient `AC=>S_request`). La
  revue utilise les nouveaux noms, même pour les points traités avant,
  sauf le constat de D1, qui porte sur les anciens.
- Avec B2, SRC-REQ-3 et SRC-REQ-10 sont devenues SRC-SET-14 et
  SRC-SET-13, et les SRC-REQ suivantes ont été renumérotées (SRC-REQ-4
  devient SRC-REQ-3, etc.) : la revue utilise les nouveaux numéros.
- Avec D2 (2026-11-17), `Sdsm=>Sstm_data_available` est devenu
  `Sdsm=>Sstm_discovered`, les états de la confirmation de retrait
  `KEPT` / `CONFIRMING` sont devenus `STORED` / `REMOVING`, et §5.4 « First
  use of a mode » est devenue « Discovery of a mode ». La revue utilise
  les nouveaux noms, sauf le constat de D2, qui porte sur les anciens
  mots.
- Avec D3 (2026-11-17), ENT-TYPE-1 à ENT-TYPE-4 sont passées en §3.1.2
  (ENT-TYPE-1 → CFG-MODE-1, ENT-TYPE-3 → CFG-MODE-2, ENT-TYPE-2 →
  CFG-MODE-4, ENT-TYPE-4 → CFG-MODE-5), ENT-TYPE-5 à ENT-TYPE-9 sont
  devenues ENT-TYPE-1 à ENT-TYPE-5, et CFG-SENS-1 à CFG-SENS-3 sont
  devenues CFG-SENS-3 à CFG-SENS-5. La revue utilise les nouveaux
  numéros, sauf le constat de D3.
- Avec D4 (2026-11-17), SRC-UNDISC-1, SRC-UNUS-1, ENT-WAIT-1 sont
  devenues SRC-UNDISC-2, SRC-UNUS-2, ENT-WAIT-2 ; ENT-NOSRC-1 et -2 sont
  devenues ENT-NOSRC-2 et -3 ; MON-ENT-1 est devenue MON-SENS-4. La revue
  utilise les nouveaux numéros, sauf le constat de D4.
- Avec F8 (2026-11-17), trois durées ont changé de nom
  (`capability_rem_confirmation` → `removal_confirmation_timer`,
  `external_sensor_resend` → `external_sensor_resend_timer`,
  `monitoring_duration` → `monitoring_delay_timer`) et §3.1.3
  « Temperature sensor » est devenue « Temperature readings ». La revue
  utilise les nouveaux noms, sauf le constat de F8.

Statuts : ✅ traité (décision appliquée dans la spec) · ⏳ ouvert ·
❌ abandonné.

## Vue d'ensemble

| Partie | Points | Ouverts |
|---|---|---|
| A. Contradictions | 6 | 0 |
| B. Trous | 14 | 0 |
| C. Canaux et acteurs manquants | 4 | 0 |
| D. Références et termes | 5 | 0 |
| F. Mineurs | 9 | 0 |

(La lettre E, « écarts avec le code » dans la revue 1, n'est pas reprise.)

Les points qui touchent les machines à états, à voir en premier car
d'autres en dépendent : A1, B1, B2, B7, C1, C2, C4. Le fan/swing synchronisé
forme un second groupe : A2, A4, B8, B11.

Vérifié par script, sans anomalie : 186 règles, numérotation sans trou ni
doublon dans chaque préfixe ; tous les renvois vers une règle ou une
section existent ; tous les liens du sommaire pointent sur un titre. Les
renvois ont aussi été relus à la lecture : aucun ne pointe sur une règle
sans rapport.

## A. Contradictions

- ✅ **A1. Source `UNUSABLE` par mode perdu : la confirmation de requête
  n'est pas prévenue.** SRC-STATE-6 dit que `Sdsm=>Sstm_served_mode_lost` fait
  passer la source en `UNUSABLE` « even during a mode request confirmation,
  which ends », et §1.2.3.5 dit que rien n'est envoyé à l'entité source en
  `UNUSABLE`. Mais dans le diagramme de §1.2.4, la confirmation ne
  s'arrête que sur `SE=>S_unavailable` / `SE=>S_unknown`.
  `Sdsm=>Sstm_served_mode_lost` va de `Sdsm` à `Sstm` ; `Ssrm` est prévenue
  (`Sstm=>Ssrm_unusable`), `Smrc` ne reçoit rien.

  Conséquence. Cas probable : l'appareil n'offre plus `heat`, la requête
  `heat` n'est donc pas suivie, la source est en `RETRY_WAIT(heat)` ; le
  retrait de `heat` est confirmé, la source passe en `UNUSABLE`. Mais
  `Smrc_retry_timeout` renvoie `heat` à chaque `request_retry_timer`, et
  « source out of sync » reste levé. En `SETTLE(m)`, `Smrc_settle_timeout`
  envoie `Smrc=>Ssrm_settle_end`, et `Ssrm` peut renvoyer des réglages (cette
  ligne du tableau de §1.2.5 n'a pas de condition d'état). Au retour,
  `Sstm=>Smrc_back(m)` arrive dans un état autre que `IDLE`, sans transition.

  À décider : comment `Smrc` apprend l'entrée en `UNUSABLE` (un événement
  de `Sstm` vers `Smrc`, comme `Sstm=>Ssrm_unusable` pour `Ssrm`, qui remplacerait
  aussi les transitions sur `SE=>S_unavailable` / `SE=>S_unknown`).

  Décision : un événement envoyé à plusieurs fonctions de la source prend
  `x` comme destinataire. `Sdsm=>Sstm_served_mode_lost` devient
  `Sdsm=>Sx_served_mode_lost`, reçu par `Sstm` et `Smrc` ; la confirmation
  (`CONFIRMING`, `RETRY_WAIT`, `SETTLE`) s'arrête sur `SE=>S_unavailable` /
  `SE=>S_unknown` / `Sdsm=>Sx_served_mode_lost`. Appliqué : convention de
  nommage (§1.1.2), tableau de §1.2.1, diagrammes de §1.2.3.1 et §1.2.4,
  SRC-STATE-6, SRC-REQ-1, SRC-SET-14, SRC-REQ-7, tableau du monitoring,
  MON-SRC-3.

- ✅ **A2. Valeur fan/swing montrée quand la valeur n'est pas partagée.**
  ENT-FANV-3 : dans une mémoire partagée, une valeur offerte par certains
  modes seulement « can still be chosen and sent, but it is not
  remembered: the shared memory keeps its previous value ». ENT-FANV-8 :
  en `ON(m)`, l'entité montre « the value remembered for m ».

  Conséquence : l'utilisateur choisit `turbo` en `cool` (synchronisé) ;
  l'appareil tourne en `turbo`, la source garde `turbo` (pas de « setting
  not applied »), et la carte montre l'ancienne valeur (`high`). Même
  chose pour un `turbo` mis à la télécommande (ENT-FANV-4 : « the source
  wins », mais rien n'est retenu).

  Les deux synchronisations ne se comportent pas pareil, alors que
  ENT-FAN-8 annonce « the same principle » : avec `sync_modes`, toutes
  les options de `m` sont montrées en `ON(m)` (ENT-FAN-3), donc une
  valeur non partagée peut être choisie ; avec `bi_source_sync`, seules
  les options partagées sont montrées, donc elle ne peut pas l'être.

  À décider : ce que l'entité montre pour une valeur non partagée (une
  valeur courante du mode, distincte de la mémoire partagée ?), ou ne
  plus proposer les valeurs non partagées, comme avec `bi_source_sync`.

  Décision : seules les valeurs partagées sont retenues ; dans un mode qui
  offre des valeurs non partagées, elles sont montrées et peuvent être
  choisies (utilisateur ou takeover) ; une valeur non partagée choisie est
  envoyée et montrée, sans être retenue ni sauvegardée (perdue au prochain
  `AC.apply` : autre mode, changement de phase, redémarrage).
  `bi_source_sync` suit le même principe que `sync_modes` : toutes les
  options de la phase courante sont montrées. Appliqué : ENT-FAN-3,
  ENT-FAN-8, ENT-FANV-3, ENT-FANV-8, `bi_source_sync` en §3.1.7.

- ✅ **A3. « Source unusable » : source de phase arrêtée pour la saison.**
  MON-SRC-2 justifie de ne rien signaler en `OFF` par « a device unplugged
  for the season (a radiator in summer, an AC at the breaker in winter)
  is normal », et ajoute « for the same reason, in ON(m) only the sources
  of m are reported ». Mais MON-SRC-1 signale « either phase source of a
  bi-source heat_cool (WAITING_PHASE(p), or the other phase source) ».

  Conséquence : en `ON(heat_cool)` bi-source (radiateur + clim, le cas
  principal), la clim coupée au disjoncteur en hiver est une source du
  mode : elle est signalée après `monitoring_delay_timer`, et
  `monitoring_sources` reste allumé des mois. C'est ce que MON-SRC-2
  veut éviter.

  À décider : l'autre source de phase est-elle signalée toujours, ou
  seulement quand la phase la demande (`WAITING_PHASE(p)`) ?

  Décision : par cohérence avec MON-SRC-2, en `ON(heat_cool)` seule la
  source de la phase demandée est signalée (la source de `p` en
  `WAITING_PHASE(p)`). En `WAITING(heat_cool)` et `NO_SOURCE`, il n'y a
  pas de phase : toutes les sources de phase `UNUSABLE` sont signalées,
  comme pour un mode ; une source arrêtée pour la saison ne l'est alors
  que tant que l'autre n'est pas disponible non plus. Appliqué : tableau
  de §4.2, MON-SRC-1, MON-SRC-2.

- ✅ **A4. `sync_modes` : options en `OFF` contre Repairs issue.**
  ENT-FAN-3 : en `OFF`, les options ne sont montrées que si **tous** les
  modes configurés sont dans `sync_modes`. ENT-FAN-7 : un mode
  synchronisé dont la source n'a pas du tout le réglage (« a radiator
  without fan ») est une erreur de configuration, avec warning et Repairs
  issue « removed once the cause is gone » (donc jamais).

  Conséquence : avec un radiateur (`heat`) et une clim (`cool`, `dry`),
  il faut lister `heat` pour avoir les options en `OFF`, ce qui lève une
  issue permanente. Le jugement se fait par réglage (fan, swing, swing
  horizontal) : plusieurs issues possibles pour une installation
  courante.

  Non dit aussi : quand le mode est jugé. « Does not have a setting at
  all » ne peut pas se savoir avant la découverte du mode (ENT-HVAC-5 dit
  « a source never seen is not judged » ; ENT-FAN-7 ne dit rien).

  À décider : un mode sans le réglage est-il une erreur, ou un cas normal
  (ignoré sans issue) ; et à partir de quand il est jugé.

  Décision : la spec est bonne, un mode synchronisé sans le réglage est
  une erreur de configuration. Il est jugé à partir de la découverte du
  mode (à chaque reconstruction des capacités, et au démarrage avec les
  capacités stockées). Un mode pas encore découvert est laissé de côté
  dans le calcul des options partagées jusqu'à sa découverte, qui peut
  les réduire (la mémoire est alors vérifiée, ENT-FANV-3). Appliqué :
  ENT-FAN-6, ENT-FAN-7, ENT-FAN-8.

- ✅ **A5. Ordre offset / plage à l'envoi d'une cible.** ENT-RANGE-1 : la
  plage d'un mode est le min/max de la source **moins** l'offset (échelle
  de la température de référence) ; ENT-RANGE-4 : l'entité ramène
  « first » la cible dans cette plage. ENT-TGT-8 donne l'ordre inverse :
  plus l'offset, puis « brought into the range of the mode
  (ENT-RANGE-4) ». Tel qu'écrit, une valeur à l'échelle de la source est
  comparée à une plage à l'échelle de la référence.

  Exemple : source 16–30 °C, offset +2, plage du mode 14–28. Cible gardée
  28 : 28 + 2 = 30, ramené dans 14–28, la source reçoit 28 au lieu de 30.

  Deux précisions liées dans ENT-TGT-8 :
  - l'arrondi au pas de la source vient après la plage : il peut en
    faire sortir (de moins d'un pas) quand une limite (`max_temp` +
    offset) n'est pas sur le pas ;
  - « the step of that source » n'est pas défini pour une source sans
    pas (ENT-STEP-1 la compte pour 0,5 °C, mais pour le pas de l'entité).

  À décider : l'ordre (plage puis offset, ou plage exprimée côté source) ;
  le sens de l'arrondi en bout de plage ; le pas d'une source sans pas.

  Décision : la référence est l'entité. Tous les calculs se font à
  son échelle ; ce qui est lu d'une source y est ramené tout de suite
  (moins l'offset), ce qui est envoyé est converti en dernier, à
  l'écriture (plus l'offset, puis pas de la source). En bout de plage,
  l'arrondi se fait vers l'intérieur (jamais hors de `min_temp` /
  `max_temp` de la source). Une source sans pas prend la valeur par
  défaut de Home Assistant, 0,5 °C (1 °F). Appliqué : §3.1.3 (principe),
  ENT-TGT-8, ENT-RANGE-4, ENT-CAP-6, réglages de §1.2.5.

- ✅ **A6. Données `@S` d'une source `UNUSABLE` dont l'entité source est
  utilisable.** §1.1.2 : `temperature@S`, `action@S` et `settings@S`
  valent `None` quand l'entité source « is not usable ». Or une source
  est aussi `UNUSABLE` avec une entité source utilisable (mode servi non
  offert, SRC-UNUS-2) : les données donnent alors des valeurs. ENT-REF-2
  et MON-TEMP-2 disent au contraire qu'une source `UNUSABLE` ne donne pas
  de lecture ; et SRC-STATE-11 / SRC-STATE-12 ne remontent les
  changements qu'en `OFF` / `ON(m)` : la valeur lue ne serait pas suivie.

  À décider : en `UNUSABLE` (et `UNDISCOVERED`), les données valent-elles
  `None` quelle que soit la raison ?

  Décision : `None` en `UNUSABLE` (et `UNDISCOVERED`) quelle que soit la
  raison. Le seul cas en jeu est SRC-UNUS-2 (en `UNDISCOVERED` l'entité
  source n'a jamais été utilisable) : le gain (température affichée,
  écarts surveillés pendant une anomalie rare et déjà signalée) ne vaut
  pas deux comportements d'`UNUSABLE`. ENT-REF-2, MON-TEMP-2,
  SRC-STATE-11 et SRC-STATE-12 étaient déjà cohérents. Appliqué :
  `temperature@S`, `action@S`, `settings@S` en §1.1.2.

## B. Trous

- ✅ **B1. Requête pour l'état déjà en cours, hors confirmation.** Le
  diagramme de §1.2.3.1 a `AC=>S_request(m2)` en `ON(m)`, mais pas
  `AC=>S_request(m)` en `ON(m)`. SRC-STATE-2 ne traite ce cas que pendant
  une confirmation (« A request for r itself changes nothing: the
  confirmation goes on »). SRC-STATE-3 dit qu'une requête « moves the
  state at once to the state asked, and its entry sends it ».

  Le cas arrive à chaque redémarrage : la source est restaurée en
  `ON(m)`, puis `resume` fait `AC.apply(m)`, donc `AC=>S_request(m)` sur
  une source déjà en `ON(m)`. Aussi au retour de `NO_SOURCE`.

  À décider : rien (pas de nouvelle entrée, pas de `Sstm=>Ssrm_mode_changed`,
  réglages gardés), ou nouvelle entrée (vérification de l'entité source,
  retrait des réglages gardés) ?

  Décision : une nouvelle demande de l'état déjà en cours n'a pas
  d'effet : pas de nouvelle entrée, rien d'envoyé, pas de
  `Sstm=>Ssrm_mode_changed`, réglages gardés ; pendant une confirmation, elle
  continue. Appliqué : diagramme de §1.2.3.1 (boucles « ignored » en
  `OFF` et `ON(m)`), SRC-STATE-2, SRC-STATE-3 (règle et exemple du
  redémarrage), tableau de §1.2.1 (`Sstm=>Ssrm_mode_changed`).

- ✅ **B2. Ordre de traitement d'un même événement par des fonctions en
  parallèle.** §1.1.2 : « An event sent to S or AC reaches all its
  functions » ; §0 : chaque machine traite un événement à la fois. Rien
  ne dit dans quel ordre les fonctions traitent le même événement, alors
  que des gardes lisent l'état des autres machines. Cas où l'ordre change
  le résultat :
  - `SE=>S_on(m)` en `CONFIRMING(m)` : `Smrc` confirme et quitte
    `CONFIRMING` ; `Sstm` évalue `[followed]` (« no mode request confirmation
    running »). SRC-STATE-5 dit « the confirmation handles these changes
    first » : si `Sstm` lit ensuite l'état de `Smrc`, la garde est vraie et
    le changement est remonté comme un takeover. La garde doit lire
    l'état d'avant l'événement ;
  - premier `SE=>S_on(m)` d'un mode jamais lancé : `Sdsm` stocke les
    capacités (`S=>AC_capabilities`), `Smrc` entre en `SETTLE(m)` et `Ssrm`
    remonte les fan/swing sans valeur gardée (`S=>AC_settings`,
    SRC-SET-12). Si `S=>AC_settings` part en premier, l'entité reçoit des
    valeurs pour une capacité qu'elle ne connaît pas encore (ENT-FAN-4).
    Même question avec `low_high_seen` (SRC-DATA-8) et des cibles
    low/high prises sur un takeover ;
  - `SE=>S_attributes` en `SETTLE(m)` : `Smrc` peut finir `SETTLE`
    (« settings sent shown ») pendant que `Ssrm` choisit sa réaction selon
    « in SETTLE(m) » ou non ;
  - `U=>AC_set_settings(targets)` en `ON(heat_cool)` : la gestion des
    réglages envoie à la source active (ENT-SET-1), la gestion des phases
    peut changer de phase (ENT-PHASE-2).

  À décider : une règle d'ordre (ordre fixe des fonctions, gardes lues
  sur l'état d'avant l'événement), ou des gardes qui ne lisent pas
  l'autre machine.

  Décision, après avoir déroulé sept cas en diagrammes de séquence :
  - un modèle d'exécution (§1.1.3) : un acteur par source et pour
    l'entité, avec une file externe et une file interne, traitées par
    étapes, la file interne d'abord (EXEC-1) ; ordre par émetteur
    (EXEC-2) ; un stimulus extérieur traité jusqu'au bout avant le
    suivant, quelle que soit son origine (EXEC-3) ; l'entité démarre
    avant ses sources (EXEC-4) ;
  - `Ssrm` a son propre état (`HOLD`, `SETTLE`, `ACTIVE`), changé par ses
    timers et par les événements de `Sstm` et `Smrc` : plus aucune
    condition ne lit une autre machine. `SETTLE` et le settle timer
    passent de `Smrc` à `Ssrm` ;
  - l'entité ne commande ses sources qu'une fois ses files vides, d'après
    ce qu'elle attend de chacune et ce qu'elle lui a déjà envoyé
    (ENT-SEND-1 à 3). Une valeur reprise d'une source dans la même mise à
    jour gagne (ENT-TGT-4) ;
  - les liens entre fonctions de l'entité passent par des événements
    internes (C4).

  Appliqué : §0 (notation), §1.1.2 (codes de l'entité), §1.1.3 (nouvelle),
  §1.2 (fonctions), tableaux de §1.2.1 (`Smrc=>Ssrm_confirmed`,
  `Sstm=>Ssrm_back`, `Sstm=>Ssrm_restored`, `Ssrm_settle_timeout` ;
  `settle_start`, `settle_end`, `Sstm=>Smrc_back` retirés), diagramme et
  texte de §1.2.3.1, SRC-STATE-7, §1.2.4 (sans `SETTLE`, SRC-REQ
  renumérotées), §1.2.5 réécrite (machine d'états, SRC-SET-2, -3, -7,
  -8, -9, -11, nouvelles SRC-SET-13 et -14), §1.3.2.1 (activités et
  ENT-SEND), ENT-TGT-4, §3.1.4, annexe §5 (trois séquences informatives).

- ✅ **B3. Au démarrage, les données stockées ne sont pas comparées à
  l'entité source.** SRC-DATA-4 et l'organigramme de §1.2.2.2 : avec un
  `hvac_modes` stocké valide, les données sont restaurées sans lire
  l'entité source, même utilisable. SRC-DATA-6 ne lit que « on every
  change ».

  Conséquence : ce qui a changé pendant l'arrêt de Home Assistant
  (modes, options, plage ; par exemple après la mise à jour d'une
  intégration) n'est vu qu'au prochain changement de l'entité source. La
  confirmation de retrait ne démarre pas, et `first` juge « every served
  mode offered » sur l'ancien `hvac_modes`. Une entité source qui change
  peu (sans température courante) peut rester longtemps ainsi.

  À décider : à `HA=>S_start`, une entité source utilisable est-elle lue
  comme sur un changement (SRC-DATA-6) ?

  Décision : oui. L'état et les réglages gardés sont restaurés et imposés
  à l'entité source (Home Assistant gagne) ; ce que l'appareil offre
  (`hvac_modes`, capacités, `low_high_seen`) s'observe, et peut avoir
  changé pendant l'arrêt. Après la restauration, une entité source
  utilisable est lue comme sur un changement : un élément ajouté est
  stocké, un élément disparu passe par la confirmation de retrait. Le
  premier état de la source est jugé sur ces données. Appliqué :
  organigramme de §1.2.2.2, SRC-DATA-4, séquence §5.6.

- ✅ **B4. Découverte d'une source : l'entité ne reconstruit pas ses
  capacités.** SRC-DATA-12 : les données qui deviennent disponibles
  (`Sdsm=>Sstm_discovered`) ne sont pas signalées par `S=>AC_capabilities`,
  parce que l'entité reçoit `S=>AC_off` / `S=>AC_unusable`. Mais ENT-CAP-7
  (reconstruction, ENT-TGT-4, réécriture de l'état) ne réagit qu'à
  `S=>AC_capabilities`.

  Conséquence : si l'entité source tourne dans un mode à la découverte
  (entité source chargée après l'intégration, entrée neuve ou données
  perdues), les capacités de ce mode, et peut-être `low_high_seen`, sont
  lues en même temps. Le pas (ENT-STEP-1), les features, la plage et les
  options de l'entité changent sans passer par ENT-CAP-7.

  À décider : lever `S=>AC_capabilities` aussi à la découverte, ou
  appliquer ENT-CAP-7 quand une source sort d'`UNDISCOVERED`.

  Décision : seule la sortie d'`UNDISCOVERED` est concernée. Au
  démarrage, les données disponibles (restaurées ou lues) sont là avant
  le premier état de la source, pendant qu'elle est en `INIT` ; la
  source n'entre alors jamais dans `UNDISCOVERED`. À la sortie
  d'`UNDISCOVERED` (SRC-DATA-6), les données sont lues pour la première
  fois : `Sdsm` envoie `S=>AC_capabilities`. Il l'envoie sur le
  changement de l'entité source lui-même, donc avant `S=>AC_off` /
  `S=>AC_unusable` (EXEC-1, EXEC-2) : l'entité a reconstruit ses
  capacités quand elle voit la source découverte. Appliqué : SRC-DATA-6,
  SRC-DATA-12, §1.2.3.2, tableau des événements (§1.1.2), ENT-CAP-7,
  ENT-TGT-4.

- ✅ **B5. Ce qu'un mode utilise change après coup : rien ne dit quoi
  envoyer.** ENT-CAP-7 traite deux effets d'un changement de capacités :
  pas / plage (ENT-TGT-4) et options (ENT-FANV-3). Pas le changement des
  features d'un mode :
  - `low_high_seen` posé plus tard (ENT-FEAT-2) : un `heat_cool` ou un
    `auto` passe de « single temperature target » (T) à « with
    low/high ». Les low/high de l'entité sont-ils envoyés, ou ceux de la
    source pris ? Tel qu'écrit, cela dépend du moment (takeover hors
    `SETTLE`, ignoré pendant) ;
  - `TARGET_TEMPERATURE` ou un réglage fan/swing qui apparaît dans un
    mode déjà découvert : le réglage n'a jamais été envoyé ;
  - la découverte elle-même : ENT-CAP-6 dit que les cibles « are then
    sent », mais ENT-TGT-4 n'envoie que « a kept target that changed ».
    Une cible déjà dans la plage et sur le pas n'est envoyée par aucune
    règle générale.

  À décider : sur `S=>AC_capabilities` de la source active, l'entité
  renvoie-t-elle les réglages du mode (`AC=>S_settings`, la source
  n'envoyant que ceux non montrés) ; et au passage en low/high, qui
  gagne.

  Décision : l'entité envoie les réglages qui ont changé et les
  nouveaux, avec le mécanisme existant. Sur `S=>AC_capabilities`, les
  réglages attendus de la source active (`expected(S)`) sont recalculés
  avec les nouvelles capacités ; ENT-SEND-3 envoie ce qui diffère de
  `sent(S)`. Un réglage jamais envoyé (découverte du mode, feature qui
  apparaît, low/high après `low_high_seen`) n'est pas dans `sent(S)` :
  il part. « Changé » porte sur la valeur à envoyer (ENT-TGT-8), pas sur
  la valeur gardée. Un fan/swing sans valeur mémorisée n'est pas envoyé
  (ENT-FANV-5). Au passage en low/high, les règles existantes
  tranchent : en `SETTLE` les low/high de l'entité partent, hors
  `SETTLE` ceux de la source arrivent après (EXEC-2) et sont adoptés
  (ENT-TGT-9). Appliqué : ENT-CAP-7, ENT-CAP-6, ENT-TGT-4, tableau des
  événements internes (§1.3.1), paragraphe « Sending to the sources »
  (§1.3.2.1).

- ✅ **B6. Cibles utilisées par mode : tableau incomplet (§1.3.4.3).**
  ENT-FEAT-1 donne trois cas par (source, mode), mais les lignes `heat`
  et `cool` du tableau sont sans condition. Manquent :
  - `heat` / `cool` dont la source est « with low/high » dans ce mode
    (jugé par mode, ENT-FEAT-2) : que montre et qu'envoie l'entité
    (ENT-TGT-8 dit seulement « low, as in the mode heat ») ?
  - `heat` / `cool` dont la source est « without temperature target »
    (un chauffage tout ou rien) ;
  - `dry` avec une source « with low/high » ;
  - un mode pas encore découvert : ENT-CAP-4 dit que l'entité ne montre
    aucune cible pour lui, le tableau dit que `heat` montre
    `temperature`. ENT-CAP-4 dit aussi que les cibles réglées entre-temps
    par l'utilisateur sont gardées : par quel moyen, si aucune n'est
    montrée ?

  À décider : compléter le tableau avec ces cas.

  Décision (prise par Claude, à la demande de l'utilisateur) : le
  tableau a une ligne par (mode, cas de la source), et une colonne
  « Sent as ».
  - `heat` / `cool` d'une source « with low/high » (ENT-FEAT-4) :
    l'entité utilise et montre une seule cible (low en `heat`, high en
    `cool`, en `temperature`). Elle l'envoie en paire, puisque low et
    high vont ensemble (SRC-SET-2) : la cible du mode, avec l'autre
    cible de l'entité. L'écart est appliqué sur l'autre cible, pour
    garder celle du mode (ENT-TGT-8 : en `cool`, low bouge d'abord). Le
    `heat_cool` bi-source envoie à chaque phase comme le mode de la
    phase.
  - « Without temperature target » : aucune cible, rien de montré, rien
    d'envoyé, pour tout mode sauf `fan_only` (déjà sans cible) et
    `heat_cool` bi-source.
  - `dry` « with low/high » : comme `auto` (low, high en
    `target_temp_low` / `target_temp_high`).
  - Mode mono-source pas encore découvert (ENT-FEAT-5) : rien de montré,
    rien d'envoyé ; ENT-CAP-4 garde le dessus sur le tableau. Les cibles
    réglées entre-temps passent par le service (ENT-TGT-7), qui ne
    dépend pas de ce qui est montré : `temperature` règle low en `heat`,
    high en `cool`, T ailleurs. Un `heat_cool` bi-source montre toujours
    low/high, qui choisissent la phase.
  - Conséquence écrite dans ENT-FEAT-3 : les features déclarées suivent
    ce que les modes montrent. Un mode pas encore découvert compte à sa
    découverte.

  Appliqué : tableau de §1.3.4.3, ENT-FEAT-3, ENT-FEAT-4 et ENT-FEAT-5
  (nouvelles), ENT-CAP-4, ENT-CAP-7, ENT-TGT-7, ENT-TGT-8.

- ✅ **B7. `heat_cool` bi-source : `AC.apply(m)` et `WAITING(heat_cool)`.**
  - `AC.apply(m)` (§1.3.2.1) envoie « the phase for a bi-source mode »,
    mais la phase est choisie après, à l'entrée de `ON(heat_cool)`
    (`p := AC.wanted(entering)`), qui fait son propre `AC.apply(p)`. Deux
    `apply` sont décrits pour une seule entrée, et le premier ne connaît
    pas la phase.
  - `resume` vers `WAITING(heat_cool)` fait `AC.apply(m)` : à quelle
    source de phase va la requête (aucune n'est disponible, la phase
    n'est pas choisie) ?
  - En `WAITING(heat_cool)` il n'y a pas de sous-état de phase, mais
    ENT-FAN-3 et ENT-FANV-8 (« the current phase ») et ENT-SET-1 (« sent
    to the active source ») ont besoin d'une phase ou d'une source
    active. Seule ENT-REF-2 traite cet état.

  À décider : `AC.apply(heat_cool)` bi-source se réduit-il à éteindre les
  autres sources, la phase étant appliquée par l'entrée de
  `ON(heat_cool)` ? La phase « courante » en `WAITING(heat_cool)`
  est-elle la phase stockée ?

  Décision, par B2 et C4 : les activités disent ce que l'entité attend de
  chaque source, et l'envoi se fait une fois les files vides
  (ENT-SEND). `AC.apply(heat_cool)` laisse les deux sources de phase à la
  gestion des modes, qui choisit la phase sur `ACstm=>ACmom_entered` et
  fait `AC.apply(p)` : les deux se combinent avant l'envoi, sans requête
  sans phase. En `WAITING(heat_cool)`, la gestion des modes reste en
  `WAITING_PHASE(p)` : la phase courante est `p` (ENT-PHASE-6) ; après
  un redémarrage, elle est en `NO_PHASE`, et la phase est choisie quand
  une source de phase revient. Appliqué : tableau des activités de
  §1.3.2.1, §1.3.3.2.1, ENT-PHASE-6.

- ✅ **B8. Première utilisation d'un mode synchronisé.** ENT-CAP-5 : à la
  première activation, seul le mode est envoyé. SRC-SET-12, ENT-CAP-6 et
  ENT-FANV-5 : la source remonte ses fan/swing et l'entité les adopte.
  C'est écrit pour un mode qui a sa propre mémoire (« the entity has no
  value for it »). Pour un mode de `sync_modes` (ou une phase avec
  `bi_source_sync`), l'entité a une valeur : la valeur partagée.

  Conséquence, tel qu'écrit : rien n'est envoyé, la valeur de l'appareil
  est adoptée et, si tous les modes l'offrent, elle remplace la valeur
  partagée. Le fan choisi en `cool` est remplacé par celui de l'appareil
  à la première utilisation de `dry`.

  À décider : à la découverte d'un mode synchronisé, l'entité
  envoie-t-elle la valeur partagée (comme les cibles, ENT-CAP-6) au lieu
  d'adopter celle de l'appareil ?

  Décision : on distingue la mémoire et ce que montre l'entité source.
  - Tant qu'aucun mode synchronisé n'a été utilisé, la mémoire partagée
    est vide : les découvertes ne changent que les options partagées,
    rien n'est décidé pour la mémoire. Seule exception, une action de
    l'utilisateur : en `OFF`, quand tous les modes sont synchronisés, une
    valeur réglée parmi les options déjà découvertes remplit la mémoire
    (ENT-FANV-9, inchangée).
  - Un mode qui démarre avec une mémoire vide prend la valeur de sa
    source (ENT-FANV-5). C'est le cas du premier mode synchronisé
    utilisé.
  - À chaque découverte, les options partagées sont ajustées
    (ENT-FAN-6), les cibles ramenées dans la plage (ENT-TGT-4), et une
    valeur fan/swing que tous ne proposent plus est retirée de la
    mémoire, au lieu d'être remplacée par celle de la source
    (ENT-FANV-3). Dans le mode courant, elle reste montrée comme une
    valeur non partagée. Rien n'est envoyé.
  - Découverte hors changement de mode : rien de plus.
  - Découverte en changeant de mode (première utilisation) : les
    valeurs mémorisées sont envoyées. La valeur que la source remonte
    avant de les recevoir (SRC-SET-12) n'est pas adoptée : elle va dans
    `sent(S)` seulement (ENT-SEND-2). Une valeur vide prend la source.

  Appliqué : ENT-FANV-3 à ENT-FANV-6, ENT-FANV-8, ENT-CAP-6, ENT-CAP-7,
  ENT-SEND-2, SRC-SET-12, tableau des événements (§1.1.2), intro de
  §5.4.

- ✅ **B9. Fin anticipée de `SETTLE(m)`.** SRC-SET-14 et le diagramme de
  §1.2.4 : `SETTLE` finit plus tôt quand l'entité source montre les
  réglages envoyés (`SE=>S_attributes [settings sent shown]`).
  - Garde à préciser : quand rien n'a été envoyé (tout était déjà
    montré), SRC-SET-6 dit que rien ne finit `SETTLE` plus tôt ; lue
    telle quelle, la garde est pourtant vraie au premier
    `SE=>S_attributes` (un changement de température courante).
  - La fin anticipée retire la protection juste quand un réglage vient
    d'être poussé. Une intégration qui affiche tout de suite la valeur
    envoyée, puis relit l'appareil quelques secondes après, montre
    d'abord la valeur envoyée (fin de `SETTLE`), puis la valeur propre de
    l'appareil (prise pour un takeover). §3.1.4 justifie les 12 s par
    cette relecture tardive (jusqu'à 10 s). La fin sur écho est un choix
    du 2026-11-07 ; la question est de savoir s'il tient avec ces
    intégrations.

  À décider : la garde exacte ; garder ou non la fin anticipée.

  Décision : pas de fin anticipée. `SETTLE(m)` dure toujours
  `settle_timer` : l'écho de la valeur envoyée est justement ce que
  montrent d'abord les intégrations qui relisent l'appareil plus tard.
  La garde disparaît avec. Coût accepté : un réglage changé sur
  l'appareil dans les 12 s qui suivent est ignoré puis remplacé (un
  changement de mode reste suivi, SRC-STATE-5). Appliqué : diagramme de
  §1.2.4 (transition sur `SE=>S_attributes [settings sent shown]`
  retirée), SRC-SET-14, SRC-SET-6 (limitation connue retirée).

- ✅ **B10. « Montre le réglage envoyé » : comparaison des valeurs.**
  Beaucoup de règles comparent ce que l'entité source montre avec ce qui
  a été envoyé (SRC-SET-2, SRC-SET-5, SRC-SET-6, SRC-SET-8, SRC-SET-10,
  SRC-SET-11, MON-SRC-4, garde de fin de `SETTLE`). Pour fan/swing : sans
  la casse (SRC-SET-4). Pour les températures : rien n'est dit.

  Conséquence avec un appareil qui arrondit (21,5 envoyé, 21,7 ou 22
  montré : appareil en °F, précision plus grossière que le pas déclaré) :
  hors `SETTLE`, c'est un takeover, la valeur est adoptée ; pendant
  `SETTLE`, la valeur est ignorée, renvoyée à la fin, puis remontrée
  identique : « setting not applied » (SRC-SET-10), renvoi toutes les
  30 min et problème de monitoring sans fin.

  À décider : une tolérance pour comparer les températures, ou traiter
  comme un takeover une valeur remontrée après un renvoi.

  Décision : une tolérance. Deux températures sont égales si leur écart
  est strictement inférieur à un pas de la source dans ce mode (0,5 °C
  / 1 °F sans pas déclaré, comme ENT-STEP-1). Tout vrai changement fait
  au moins un pas. Le cas °F/°C est couvert : écart jusqu'à 0,33 °C,
  sous un pas de 0,5. Pas de nouvelle constante.
  - Écartée : « le plus grand entre la moitié du pas et 0,5 °C ». Avec
    un pas de 0,5, elle masque un cran de l'utilisateur sur l'appareil
    (si l'égalité est incluse), ou ne couvre pas l'appareil au pas
    menteur (si elle est stricte). Le plancher à 0,5 masque aussi les
    changements d'une source au pas de 0,1 (`generic_thermostat`).
  - L'appareil au pas menteur (0,5 déclaré, entiers acceptés) reste un
    « setting not applied » signalé par le monitoring : aucun écart ne
    le distingue d'un cran de l'utilisateur, et le signalement est
    juste.

  Appliqué : SRC-SET-4 (devient la règle de comparaison, fan/swing et
  températures), SRC-SET-11, MON-SRC-4, `Ssrm.send`.

- ✅ **B11. Mémoire fan/swing non partagée dont la valeur n'est plus
  offerte.** ENT-CAP-7 renvoie à ENT-FANV-3 quand les options changent,
  mais ENT-FANV-3 ne couvre que les mémoires partagées. Pour un mode qui
  a sa propre mémoire : `turbo` retenu, option retirée (SRC-DATA-10) ;
  l'entité montre toujours `turbo` (ENT-FANV-8), la source ne l'envoie
  pas (SRC-SET-4), et rien n'est signalé (MON-SRC-4 juge un réglage
  envoyé).

  À décider : même traitement que la mémoire partagée (remplacée par la
  valeur courante de la source, sinon oubliée) ?

  Décision : même traitement pour la mémoire propre et la mémoire
  partagée (principes homogènes, voir B8). La valeur qui n'est plus
  offerte est retirée : la mémoire est vide pour ce réglage.
  - Le mode courant l'offre encore (un autre mode d'une mémoire
    partagée l'a perdue) : elle reste montrée comme valeur non
    partagée.
  - Le mode courant ne l'offre plus (cas habituel d'une mémoire propre,
    puisque les options d'un mode ne sont jugées que pendant que sa
    source y tourne, SRC-DATA-11) : l'entité prend la valeur que montre
    l'entité source (`settings@S`), la montre, et la mémorise si la
    mémoire peut la garder. Elle devient la valeur attendue de la
    source, qui la garde à la place de la valeur retirée ; rien n'arrive
    à l'appareil, qui la montre déjà.
  - Le mode concerné n'est pas le mode courant : rien n'est envoyé ; le
    prochain démarrage avec cette mémoire vide prend la source.

  Écartée : ne rien montrer jusqu'à ce que la source remonte une valeur
  (le fan resterait vide alors qu'il existe). Appliqué : ENT-FANV-3.

- ✅ **B12. Choix de la phase : cas non couverts.**
  - ENT-PHASE-2 : la phase est vérifiée sur une lecture et sur un
    changement de cible par l'utilisateur. Les cibles changent aussi par
    takeover (ENT-TGT-9) et quand les capacités changent (ENT-TGT-4) : la
    phase attend-elle la lecture suivante, et avec quelle hystérésis ?
  - ENT-WANT-1, à l'entrée : « the target closest to the reference
    temperature ». L'égalité n'est pas traitée (cibles 19 / 24, référence
    21,5).
  - ENT-WANT-1, sans référence : « the heat or cool source already
    running ». Non dit : les deux tournent (après un redémarrage), ou la
    source tourne dans un autre mode que sa phase.

  À décider : ces trois cas.

  Décidé et appliqué :
  - Cas 1 : une reprise de main (ENT-TGT-9) et un changement de
    capacités (ENT-TGT-4) déclenchent la vérification de la phase,
    sans hystérésis comme un changement par l'utilisateur : rare, pas de
    risque d'oscillation. Appliqué : ENT-PHASE-2, ENT-TGT-4, ENT-TGT-9,
    `ACsem=>ACmom_targets_changed` (tableau §1.3.1 et texte §1.3.3.2.1),
    hystérésis et note de §1.3.3.2.2.
  - Cas 2 : égalité → `heat`. Appliqué : ENT-WANT-1, organigramme.

  - Cas 3 : « tourne déjà » se lit sur l'état de la source connu de
    l'entité : `ON` dans le mode de sa phase. Au redémarrage, c'est
    l'état stocké que la source impose (la phase est choisie après la
    prise de main de Home Assistant). Une source dans un autre mode ne
    compte pas. Une seule source au plus tourne dans sa phase : les
    deux sources qui tournent ne peuvent pas arriver. Appliqué :
    ENT-WANT-1, organigramme.

  - Soulevé en traitant le cas 3 : la définition de « mode servi » reste
    liée à la configuration (une entité source configurée pour `dry` qui
    tourne en `dry` est dans un mode servi, quel que soit le mode de
    l'entité). Ajout de l'entrée « Foreign mode » au glossaire (§0), qui
    le précise et renvoie à ENT-STATE-5 et §1.3.1.

- ✅ **B13. Fin de vie d'une entrée.** Le démarrage est spécifié
  (`HA=>S_start`, `HA=>AC_start`), pas la fin : « until the entry unloads »
  apparaît sans événement ni règle. Non dit :
  - ce que deviennent les entités source au déchargement, à l'arrêt de
    Home Assistant et à la suppression de l'entrée (laissées comme elles
    sont ?) ;
  - les timers et les problèmes en cours ;
  - ce que la suppression efface (données stockées des sources et de
    l'entité ; la note sous ENT-FEAT-2 dit que seule la suppression
    efface `low_high_seen`) ;
  - les Repairs issues : seule ENT-HVAC-5 dit qu'elle est retirée au
    déchargement, pas ENT-FAN-7.

  À décider : une section « arrêt » (événements d'arrêt, règles).

  Décision : nouvelle section §1.1.4 « End of an entry », cas rares
  traités au plus simple. Repères pris : une entrée n'est pas déchargée
  quand elle n'est pas affichée (elle tourne côté serveur jusqu'à
  l'arrêt, au rechargement, à la désactivation ou à la suppression) ;
  au redémarrage, Home Assistant lui-même repart de zéro (`for:` des
  automatisations, `delay_on` des templates).
  - Déchargement (END-1, événements `HA=>S_unload`, `HA=>AC_unload`) :
    les appareils restent comme ils sont ; tout ce qui tourne est
    abandonné sans autre action ; rien de plus n'est sauvegardé ; les
    Repairs issues sont retirées ; aucun événement de monitoring
    (`ended`) n'est émis ; Home Assistant met les entités en
    `unavailable`.
  - Démarrage suivant (END-2) : repart de zéro avec les données
    sauvegardées. Rien n'est repris : resynchronisation, nouvelles
    confirmations de retrait, délais de monitoring relancés, Repairs
    issues recréées si leur cause est toujours là.
  - Suppression (END-3) : rien n'est gardé. Toutes les données
    sauvegardées de l'entrée sont effacées (sources et entité), les
    problèmes de monitoring et les Repairs issues retirés, les appareils
    laissés comme ils sont.

  Appliqué : §1.1.4 (END-1 à END-3), sommaire, EXEC-3 (le déchargement
  est un stimulus), tableaux d'événements de §1.2.1 et §1.3.1,
  ENT-HVAC-5, ENT-FAN-7, note sous ENT-FEAT-2, les deux « until the
  entry unloads ».

- ✅ **B14. Retour d'`UNUSABLE` sans réglages gardés : les fan/swing de
  l'appareil passent pour une première utilisation.** Vu en déroulant B2
  (séquence du redémarrage avec une entité source chargée après). Les réglages gardés par
  `Ssrm` ne sont qu'en mémoire (SRC-SET-1) : au démarrage, il n'en a
  aucun tant que l'entité n'a pas envoyé `AC=>S_settings`. SRC-SET-12
  prend « aucune valeur gardée » pour « première utilisation du mode ».

  Le cas : au démarrage, l'entité source n'est pas encore chargée (son
  intégration se charge après), la source est `UNUSABLE` et l'entité en
  `NO_SOURCE`. L'entité source apparaît, l'appareil tourne déjà dans le
  mode stocké `m`. La source revient en `ON(m)` et entre aussitôt en
  `SETTLE(m)` (`Sstm=>Smrc_back`, SRC-STATE-7), sans rien de gardé :
  rien n'est envoyé, et les fan/swing de l'appareil sont remontés
  (`S=>AC_settings`, SRC-SET-12). L'entité sort de `NO_SOURCE` sur
  `S=>AC_usable` et fait `AC.apply(m)` avec sa mémoire, puis reçoit ces
  valeurs et les adopte (ENT-SET-2).

  Conséquence : l'entité montre la valeur de l'appareil, l'appareil
  passe à celle que l'entité vient d'envoyer. Leurs valeurs sont
  échangées, et rien ne le détecte : `Ssrm` garde la valeur envoyée,
  que l'appareil montre. La mémoire de l'entité pour `m` est perdue.

  Ne se produit pas en marche (`Ssrm` garde ses réglages en `UNUSABLE`),
  ni quand une autre source est disponible au démarrage (`resume` fait
  `AC.apply(m)` vers la source `UNUSABLE`, qui garde les réglages), ni
  quand l'appareil ne tourne pas dans `m` (la requête passe par
  `CONFIRMING`, et les réglages arrivent avant `SETTLE`).

  À décider : au retour d'`UNUSABLE`, ne rien remonter à l'entrée de
  `SETTLE(m)` (Home Assistant gagne, SRC-STATE-10 ; les réglages de
  l'entité partent ensuite, protégés par `SETTLE`) ; ou faire dépendre
  SRC-SET-12 d'une vraie première utilisation (mode pas encore
  découvert) ; ou garder les réglages de `Ssrm` à travers les
  redémarrages ?

  Décision : les réglages gardés par `Ssrm` sont sauvegardés avec l'état
  de la source. Après un redémarrage, la source retrouve des réglages
  cohérents avec ceux de l'entité : au retour d'`UNUSABLE`, elle les
  pousse (Home Assistant gagne, SRC-STATE-10) et ne remonte rien ;
  « pas de valeur gardée » veut vraiment dire « l'entité n'a rien
  envoyé » (première utilisation, SRC-SET-12). Si les deux sauvegardes
  divergeaient (arrêt brutal), l'écart ne dure pas : l'entité envoie ses
  réglages à chaque `AC.apply`. Appliqué : tableau de §1.2.2.1 (ligne
  « Kept settings »), SRC-DATA-4, introduction de §1.2.5, SRC-SET-1.

## C. Canaux et acteurs manquants

- ✅ **C1. Monitoring : ses entrées ne sont pas définies.** `M` a un code
  d'acteur (§1.1.2), mais il n'est ni dans la vue d'ensemble (§1.1.1), ni
  dans les fonctions de l'entité ou de la source. Ses seuls événements
  reçus sont `Smrc=>M_out_of_sync_up` / `Smrc=>M_out_of_sync_down` (rangés en
  §1.2.1 sous « between the functions of the source », alors que `M`
  n'en est pas une). Pour les autres problèmes, rien ne dit comment `M`
  est informé, alors que la convention demande un événement nommé :
  - source inutilisable / non découverte (MON-SRC-1, MON-SRC-5) : il
    faut l'état des sources, le mode stocké de l'entité,
    `WAITING_PHASE(p)`, `NO_SOURCE` ; les `S=>AC_*` sont adressés à `AC` ;
  - réglage non appliqué (MON-SRC-4, SRC-SET-9) : c'est `Ssrm` qui a
    l'information, sans événement `Ssrm=>M_*` ;
  - températures (MON-TEMP-5) : `M` lit `temperature@T` et
    `temperature@S` « on every event that can change them », événements
    adressés à `AC` ; les tableaux de données disent « readable to the AC
    entity » ;
  - `M_condition_true` / `M_condition_false` sont des événements
    internes qui ne sont pas des timers, seule forme `X_name` permise par
    §1.1.2.

  À décider : la place de `M` (fonction de l'entité, ou acteur à part,
  un par entrée), ses événements et ses données.

  Décision : `M` est un acteur à part, un par entrée, sans fonctions. Il
  est un puits : il n'envoie rien aux autres acteurs et ne lit aucune
  donnée. Ce n'est pas une fonction de l'entité : il produit d'autres
  entités HA, et son code serait `ACmom`, déjà pris. Chaque problème est
  jugé par l'acteur qui a l'information : la source pour « non
  découverte », « désynchronisée » et « réglage non appliqué » ;
  l'entité pour « inutilisable » et les températures. `M` ne gère que
  le délai, le report et l'affichage. Deux événements génériques,
  `X=>M_up(p)` / `X=>M_down(p)`, remplacent `Smrc=>M_out_of_sync_*` et
  `M_condition_true/false`. Ils sont envoyés en fin de pas, par
  différence, comme ENT-SEND, donc un problème qui naît et finit dans
  le même pas n'est pas envoyé. Au passage, « réglage non appliqué »
  prend fin aussi quand la source quitte `ACTIVE`. Appliqué : §1.1.1,
  §1.1.2, §1.1.3 (EXEC-1), END-2, §1.2, §1.2.1, §1.2.4 (texte et
  diagramme), SRC-SET-9, §1.3, §1.3.1, §4 (intro, colonne « Judged
  by », MON-SRC-4, MON-TEMP-5), §4.4 (MON-SEND-1 à MON-SEND-3,
  diagramme).

- ✅ **C2. État d'une source lu par l'entité.** Les gardes et activités
  de l'entité lisent l'état des sources : « source of m available »,
  « every source of m UNDISCOVERED », « every other source not OFF »,
  « heat or cool source already running ». Cet état n'est pas dans les
  données de la source (§1.1.2) : l'entité doit le déduire des `S=>AC_*`.

  Elle ne le peut pas toujours : une source `UNUSABLE` dès le démarrage
  ne remonte que `S=>AC_unusable`, son état stocké (`OFF` ou `ON(m)`) est
  inconnu. Or `AC.apply` vise « every other source not OFF (UNUSABLE
  included) », et `S=>AC_usable` est décrit comme un retour à un état
  « which the AC entity already knows ». (C'est vrai après le premier
  `AC.apply`, à condition qu'une source `UNUSABLE` d'état inconnu compte
  comme non `OFF`.)

  À décider : une donnée `state@S` (l'état, et l'état stocké en
  `UNUSABLE`), ou la règle « état inconnu = pas `OFF` ».

  En partie réglé par B2 : l'entité garde ce que chaque source a reçu
  d'elle ou lui a remonté (`sent(S)`, ENT-SEND-2), vide au démarrage ;
  elle envoie la différence avec ce qu'elle attend. Une source `UNUSABLE`
  d'état inconnu reçoit donc `off` au premier `AC.apply`. Reste à voir
  les gardes qui lisent l'état des sources.

  Décision : une donnée `state@S`, retenue parce qu'elle est la plus
  simple à coder (une lecture, aucune copie de l'état dans l'entité).
  Elle donne l'état de la source, et en `UNUSABLE` son état stocké.
  Les gardes et les activités de l'entité y lisent l'état des sources.
  Dans ENT-WANT-1, une source `UNUSABLE` « tourne » dans sa phase selon
  son état stocké, celui qu'elle impose à son retour. Appliqué : §1.1.2
  (donnée `state@S`, sens de `S=>AC_usable`), SRC-STATE-7, §1.3.1
  (données lues), ENT-WANT-1.

- ✅ **C3. Entité capteur externe : acteur absent.** ENT-EXT-1 à
  ENT-EXT-5 : l'entité écrit dans des entités capteur externe
  (`number.*` / `input_number.*`), et lit leur unité, leur pas, leur
  plage et leur disponibilité. Cet acteur n'est pas dans la vue
  d'ensemble, n'a pas de code, pas d'événement (l'écriture est un appel
  de service, comme `S=>SE_set_*`), pas de données.

  Trou lié : ENT-EXT-2 n'écrit pas quand l'entité capteur externe est
  indisponible, et rien ne réécrit à son retour. Au démarrage de Home
  Assistant (entité `number` chargée après l'intégration), l'appareil
  peut attendre le prochain changement du capteur ou
  `external_sensor_resend_timer` (15 min), avec un offset déjà forcé à 0
  (ENT-EXT-3).

  À décider : ajouter l'acteur (code, événement d'écriture, données
  lues) ; écrire au retour de l'entité capteur externe ?

  Décision : on ajoute l'acteur, pour être cohérent avec le reste. Son
  code est `XS` (`ES` se confondrait avec `SE`, et `X` sert de nom
  générique), un par entité capteur externe. Ce qu'il apporte :
  - l'événement d'écriture `AC=>XS_set_value(v)`, envoyé tout de suite
    et non en fin de pas ;
  - deux événements en retour, `XS=>AC_usable` et
    `XS=>AC_call_failed` ;
  - une donnée lue, `attributes@XS` (unité, pas, min, max), qui vaut
    `None` quand l'entité n'est pas utilisable ;
  - un nom pour le timer de réécriture, `ACsem_resend_timeout`.

  On écrit au retour : nouvelle règle ENT-EXT-6, qui écrit
  `temperature@T` sur `XS=>AC_usable` si la valeur est valide.
  Appliqué : glossaire, §1.1.1, §1.1.2, EXEC-1, EXEC-3, §1.3.1
  (événements, timers, données lues), ENT-EXT-1, ENT-EXT-2, ENT-EXT-4,
  ENT-EXT-6.

- ✅ **C4. Fonctions de l'entité : ni codes, ni événements entre elles.**
  §1.3 donne quatre fonctions à l'entité : gestion des états (§1.3.2),
  des modes et des phases (§1.3.3), des capacités (§1.3.4) et des
  réglages (§1.3.5). §1.1.2 ne nomme que les fonctions de la source
  (`Sdsm`, `Sstm`, `Smrc`, `Ssrm`). Celles de l'entité n'ont pas de code
  et n'échangent aucun événement : leurs liens sont dans le texte
  (ENT-CAP-7 renvoie à ENT-TGT-4, qui envoie `AC=>S_settings` ; la
  gestion des phases relit les cibles gardées par la gestion des
  réglages). `AC.apply`, `AC.follow` et `AC.wanted` sont préfixées par
  l'entité entière. La règle de §1.1.2 (« a function that must tell
  another one something sends it a named event ») n'est appliquée qu'à
  la source.

  Conséquence : l'ordre de traitement d'un même événement dans l'entité
  ne peut pas s'écrire. Exemple : `U=>AC_set_settings(targets)` en
  `heat_cool` bi-source, que la gestion des réglages et celle des phases
  traitent toutes les deux (B2).

  À décider : un code par fonction, sur le modèle de la source
  (proposition faite en discussion : `ACsta` états, `ACmod` modes et
  phases, `ACcap` capacités, `ACset` réglages), et les événements entre
  ces fonctions.

  Décision : codes `ACstm`, `ACmom`, `ACcam`, `ACsem` (`AC`, les deux
  premières lettres du premier mot, `m`) ; quatre événements internes
  (`ACcam=>ACsem_capabilities_changed(m)`, `ACsem=>ACmom_targets_changed`,
  `ACstm=>ACmom_entered`, `ACstm=>ACmom_left`) ; la gestion des phases
  en machine d'états à part (`NO_PHASE`, `PHASE(p)`, `WAITING_PHASE(p)`) ;
  la température de référence reste une donnée calculée à la lecture ;
  les fonctions décident, l'acteur envoie (ENT-SEND). Une source
  bi-source séparée a été envisagée, puis écartée : deux donneurs
  d'ordres pour une même source physique. Appliqué : §1.1.2, §1.3
  (fonctions), §1.3.1 (événements internes), ENT-STATE-7, §1.3.3.2.1,
  ENT-PHASE-1, ENT-PHASE-2, ENT-PHASE-6, ENT-CAP-7, MON-SRC-1.

## D. Références et termes

- ✅ **D1. Code d'acteur du capteur de température.** La convention
  (§1.1.2) donne `T`. Les événements s'appellent `TStAC_temperature`
  (code `TS`), la donnée `temperature@T`, et la vue d'ensemble « TStAC
  events ». Avec `T`, l'événement serait `TtAC_temperature`. De plus
  `TStAC_` se lit aussi `T` + `StAC_`.

  À décider : `TS` partout (`temperature@TS`), ou `T` partout.

  Décision : `T` partout. Réglé par le passage des noms d'événements de
  `XtY` à `X=>Y` : l'événement devient `T=>AC_temperature`, et la vue
  d'ensemble « T=>AC events ». Le constat ci-dessus garde les anciens
  noms.

- ✅ **D2. Glossaire : termes à plusieurs sens, ou absents.**
  - « available » : les données (SRC-DATA-3), une source (§1.3.1), un
    mode (ENT-HVAC-2), l'entité dans Home Assistant (ENT-OFF-1). Seul
    « usable » est au glossaire.
  - « discovered » : une source (sortie d'`UNDISCOVERED`), un mode
    (jamais lancé, SRC-DATA-1), une capacité (ENT-FAN-4), une valeur.
    « first activation » (ENT-CAP-4, ENT-CAP-5) et « first use of the
    mode » (SRC-SET-12, ENT-FANV-5) désignent-ils la même chose (mode
    jamais lancé / pas de valeur gardée) ?
  - mémoire : « kept » (cibles, réglages de la source), « remembered » /
    « memory » (fan/swing), « stored » (mode, phase, données de la
    source), « saved » (au redémarrage ; `saved_targets` « as kept »).
    On ne sait pas si « kept » veut dire conservé au redémarrage (les
    réglages gardés par la source ne le sont pas).
  - « Request » (glossaire) : « The entity asks a source entity », alors
    que l'entité ne parle jamais à une entité source (§1.1.1) ; et
    « settings request » (SRC-SET-2) n'est pas une requête au sens du
    glossaire.
  - définis hors glossaire (§1.3.1 ou au fil du texte) : active source,
    served / foreign, phase, stored mode, last used mode.

  À décider : compléter le glossaire, et fixer un mot par notion.

  Décision (passe complète faite par Claude, à la demande de
  l'utilisateur) : un mot par notion, défini au glossaire, appliqué dans
  toute la spec. Le glossaire est regroupé par thème (acteurs, états,
  modes, réglages, requêtes, données, exécution) et reprend les mots
  définis ailleurs ; la liste « Words used below » de §1.3.1 y est
  déplacée. Une ligne des conventions renvoie au glossaire.
  - « discovered » : vu une fois sur l'entité source, et stocké. Se dit
    d'une source (`hvac_modes` connu : remplace « data available »,
    `Sdsm=>Sstm_data_available` devient `Sdsm=>Sstm_discovered`), d'un
    mode (sa source y a tourné), d'une capacité, d'une option. « First
    activation » et « first use » disparaissent : « mode not discovered
    yet » / « discovery » pour les capacités, « empty memory » pour
    fan/swing, « the entity sent none » pour les réglages gardés de la
    source (SRC-DATA-4, SRC-SET-12). §5.4 devient « Discovery of a mode ».
  - « available » : seulement une source (`OFF` / `ON(x)`) et un mode
    (sa source disponible). L'entité dans Home Assistant : `unavailable`
    (l'état HA, en code) ou « not `unavailable` » (ENT-OFF-1, ENT-ON-1,
    ENT-WAIT-2, MON-SENS-4). Les températures et lectures : « known ».
    « usable » reste pour les entités HA (source, capteur externe).
  - Mémoire : **stored** = dans les données qui survivent au redémarrage
    (« saved data » devient « stored data » ; `save` les écrit, « saved
    across restarts » en fait partie) ; **kept** = les réglages qu'un
    acteur tient comme référence (cibles de l'entité, réglages gardés de
    la source), tous stockés ; **memory / remembered** = fan/swing de
    l'entité par mode (ENT-SET-1, ENT-FANV-3 et l'intro de §1.2.5
    corrigés en ce sens). Les états `KEPT` / `CONFIRMING` de la
    confirmation de retrait deviennent `STORED` / `REMOVING` (« KEPT »
    heurtait « kept », « CONFIRMING » celui de `Smrc`). Colonne « Kept
    per » de §1.2.2.1 : « Stored per ».
  - « request » : seul, une requête de mode (`AC=>S_request(r)`, `r` =
    « state asked ») ; « setting request » = `AC=>S_settings(s)`, ce qui
    rend cohérents les noms des deux fonctions ; « user request » = appel
    de l'utilisateur (ENT-STATE-4, ENT-CAP-4, ENT-FAN-4, ENT-PHASE-2,
    ENT-TGT-4, -6, -7, MON-SRC-2). SRC-SET-2 ne parle plus de « settings
    request ». Les colonnes « From → To » / « Timer of » donnent le nom
    complet des fonctions (« setting requests » y désignait la fonction).
  - « reading » : la lecture d'une source = température courante moins
    l'offset (ENT-REF-5 en fait la définition ; organigramme de §1.3.5.1,
    ENT-REF-2 et l'offset de §3.1.3 ne retirent plus l'offset une
    seconde fois). « new reading » : l'événement qui peut changer la
    phase (§1.3.3.2.1, diagramme).
  - « setpoint » remplacé par « temperature target » (§1.3.4.3,
    ENT-FEAT-1, §5.8) ; « phase mode » par « the mode of its phase »
    (ENT-TGT-8) ; ENT-FAN-4 parle d'« options » et non de « values ».
  - « step » garde ses deux sens (pas de température, étape d'un
    acteur) : deux entrées au glossaire, le contexte les distingue.

  Appliqué : §0, conventions, §1.1.2, §1.1.4, §1.2.1, §1.2.2 (SRC-DATA-3,
  -4, -6, -10, -12, diagramme de retrait), §1.2.3 (diagramme,
  SRC-STATE-1, -8, -10, §1.2.3.2, §1.2.3.5), §1.2.5 (intro, SRC-SET-1,
  -2), §1.3.1, §1.3.2 (ENT-STATE-4, -8, ENT-INIT-3, ENT-OFF-1, ENT-ON-1,
  ENT-WAIT-2, ENT-NOSRC-2, -3), §1.3.3 (ENT-TYPE-5, CFG-MODE-5, readings,
  ENT-PHASE-2, tableau de §1.3.3.2.2), §1.3.4 (ENT-CAP-4 à -7, §1.3.4.3,
  ENT-FEAT-1, ENT-FAN-4), §1.3.5 (ENT-SET-1, organigramme, ENT-REF-2, -4,
  -5, ENT-TGT-4, -6, -7, -8, -10, ENT-FANV-3, -5), §2 (MON-SENS-4,
  `active_entity_id`), §3.1.3, §3.1.4, §4.2 (tableau, MON-SRC-2), §5.4,
  §5.6, §5.7, §5.8. Vérifié par script : tous les renvois et liens du
  sommaire existent.

- ✅ **D3. Vérifications de la configuration dispersées, en double ou sans
  identifiant.**
  - ENT-TYPE-3 et CFG-MODE-2 disent la même chose ; ENT-TYPE-1 et
    CFG-MODE-1 se recouvrent.
  - ENT-TYPE-2 (au moins un mode) et ENT-TYPE-4 (contrôle des
    `hvac_modes`) sont des vérifications de configuration placées en
    §1.3.3.1.
  - « It needs temperature_sensor (a configuration without it is
    refused) » (§3.1.3) n'a pas d'identifiant.
  - §3 n'a pas de liste des refus, alors que CFG-YAML-5 renvoie à « the
    same checks ».

  À décider : les regrouper en §3.

  Décision (passe complète sur la configuration, à la demande de
  l'utilisateur) : tout ce qui touche la configuration est identifié en
  §3, et le reste de la spec y renvoie.
  - §3 s'ouvre sur ce que la configuration change ailleurs, avec renvois
    : rechargement et passage à `OFF` (ENT-INIT-4), modes listés
    (ENT-HVAC-1, ENT-TYPE-1), source entity retirée (SRC-DATA-9),
    suppression de l'entrée (END-3).
  - §3.1.2 : CFG-MODE-1 (un `<mode>_entity` par mode, une source entity
    pour plusieurs modes : ex-ENT-TYPE-1 fusionnée), CFG-MODE-2 (pas
    d'entité AC : ex-ENT-TYPE-3 fusionnée, avec sa raison), CFG-MODE-3
    (règle du bi-source, sans identifiant jusque-là), CFG-MODE-4 (au
    moins un mode : ex-ENT-TYPE-2), CFG-MODE-5 (contrôle des
    `hvac_modes` : ex-ENT-TYPE-4). §1.3.3.1 renvoie à CFG-MODE-1 à -5, et
    ses règles sont renumérotées ENT-TYPE-1 à -5.
  - §3.1.3 : les deux paragraphes sans identifiant deviennent CFG-SENS-1
    (offset, et le principe de l'échelle de l'entité) et CFG-SENS-2
    (capteur externe : refusé sans `temperature_sensor`, offset 0,
    écrit une fois). Les anciennes CFG-SENS-1 à -3 deviennent -3 à -5.
    Les lignes du tableau renvoient à CFG-SENS-1 / -2 / -3.
  - §3.1.7 : CFG-FAN-1 (`sync_modes` : mode sans source ignoré, erreurs
    jugées en marche, ENT-FAN-7) et CFG-FAN-2 (`bi_source_sync` sans
    `heat_cool` bi-source : sans effet). Le texte du tableau y renvoie.
  - Nouvelle §3.3 « Checks » : CFG-CHECK-1 liste tout ce qui est refusé
    (type ou plage des tableaux, `name` non unique, CFG-MODE-2, -4, -5,
    CFG-SENS-2, -4, -5, CFG-TIMER-1, CFG-LIM-1) et comment ;
    CFG-CHECK-2 ce qui est accepté sans effet ; CFG-CHECK-3 ce qui est
    accepté puis jugé en marche et signalé (ENT-HVAC-5, MON-SRC-5,
    ENT-FAN-7, ENT-FAN-8). CFG-YAML-5 renvoie à §3.3.
  - Renvois ajoutés : CFG-YAML-3 (ENT-INIT-4, END-3), `name` vers
    CFG-YAML-2 ; dans le reste de la spec, les renvois à l'offset et au
    capteur externe pointent sur CFG-SENS-1 / CFG-SENS-2 au lieu de
    §3.1.3 (glossaire, §1.1.1, §1.1.2, SRC-STATE-11, §1.2.5,
    ENT-RANGE-1, ENT-REF-2, ENT-REF-5, ENT-EXT-1, ENT-EXT-3, ENT-TGT-8,
    MON-TEMP-2) ; §1.2.3.5 renvoie à CFG-MODE-5.
  - Laissé ouvert (F3) : `name` unique entre UI et YAML, capteur sans
    unité de température, offset non nul avec un capteur externe, raison
    de CFG-TIMER-1. CFG-CHECK-1 reprend « unique » tel quel.

  Le dernier tiret de D4 (règle du bi-source en §3.1.2) est réglé ici :
  CFG-MODE-3. Vérifié par script : numérotation sans trou ni doublon,
  tous les renvois et liens du sommaire existent.

- ✅ **D4. Énoncés normatifs sans identifiant.** La convention : une règle
  est ce que l'intégration doit faire, et elle a un nom. Sans nom :
  - §1.2.3.2, première puce ; première raison de §1.2.3.5 (seule la
    seconde a SRC-UNUS-1) ;
  - les définitions de `AC.apply` / `AC.follow` (tableau de §1.3.2.1) et
    de `AC.apply(p)` (§1.3.3.2.1) ;
  - §1.3.2.5 (entrée et sortie de `WAITING(m)`), §1.3.2.6 (sortie de
    `NO_SOURCE`) ;
  - la définition des « readings » (§1.3.3.2.1) ;
  - la règle du bi-source en §3.1.2 (réglé par D3 : CFG-MODE-3).

  Par ailleurs MON-ENT-1 est en §2.1 (préfixe `MON`, section des
  entités).

  À décider : lesquels numéroter.

  Décision (passe complète sur toute la spec, à la demande de
  l'utilisateur) : tout énoncé de comportement est une règle numérotée,
  et dans chaque préfixe les numéros montent dans l'ordre du texte. Une
  ligne des conventions dit ce qui n'a pas de numéro : glossaire et
  notation ; tableaux et diagrammes avec leurs légendes, identifiés par
  leur section et les noms qu'ils contiennent (événements, données,
  états, activités, options, attributs) ; introductions qui résument
  avec renvois ; notes, exemples, §5.
  - §1.2.3.2, première puce : SRC-UNDISC-1 (l'ancienne devient -2).
  - §1.2.3.5 : les deux raisons et la phrase « In both cases » deviennent
    SRC-UNUS-1 (entité source non utilisable), SRC-UNUS-2 (mode servi non
    offert, l'ancienne SRC-UNUS-1), SRC-UNUS-3.
  - `AC.apply` / `AC.follow` / `AC.apply(p)` : pas de numéro. Ce sont des
    activités composites, identifiées par leur nom (convention).
  - §1.3.2.5 : entrée et sortie de `WAITING(m)` deviennent ENT-WAIT-1,
    complétée d'après le diagramme (entrée par `resume`, bi-source,
    sortie vers `NO_SOURCE`, `S=>AC_off` d'une source de phase) ; « Shows »
    devient ENT-WAIT-2. §1.3.2.6 : ENT-NOSRC-1 (entrée depuis `INIT` ou
    `OPER`, sortie par `resume`), puis -2 et -3.
  - « new reading » : la définition passe dans ENT-PHASE-2, qui l'utilise,
    avec la note coupée sur le retour d'une source `UNUSABLE` (F1,
    deuxième tiret, réglé au passage). §1.3.3.2.1 renvoie à ENT-PHASE-2.
  - Bi-source en §3.1.2 : déjà réglé par D3 (CFG-MODE-3).
  - MON-ENT-1 passe en §4.1 : MON-SENS-4 ; §2.1 y renvoie.

  Trouvé en plus par la passe :
  - §1.1.2 : les énoncés de comportement sortent de la liste de notation
    et deviennent EVT-1 (événements asynchrones), EVT-2 (pas d'autre
    événement, une fonction prévient l'autre par un événement nommé),
    EVT-3 (lire une donnée ne déclenche rien). « Reaches all its
    functions » renvoie à EXEC-1.
  - §1.2.4 : le paragraphe « out of sync » (jugé par la source depuis C1)
    devient SRC-REQ-9 ; le glossaire, le tableau de §4.2 et MON-SRC-3 y
    renvoient.
  - §1.3.2.1 : « An `UNDISCOVERED` source never gets a request » rejoint
    ENT-SEND-3, qui le disait déjà en partie ; les renvois « (§1.3.2.1) »
    sur ce point pointent sur ENT-SEND-3 (SRC-STATE-8, ENT-INIT-4,
    `AC.apply(p)`, ENT-PHASE-7).
  - §1.3.4 : « dans tout état de l'entité, `INIT` et `NO_SOURCE` compris,
    sans le changer » rejoint ENT-CAP-7 ; l'intro y renvoie.
  - §4 : l'introduction devient MON-ROLE-1 (le monitoring ne juge rien,
    ne lit rien, n'envoie rien).
  - Renvois ajoutés : EXEC-3 vers EVT-1, §1.2.5 « It follows » vers
    SRC-SET-11, intro de §1.2.4 vers SRC-REQ-2, §1.3.3.1 vers CFG-MODE-3,
    hystérésis `h` vers ENT-WANT-3.

  Laissés sans numéro, comme résumés ou légendes : §1.1.1, intros des
  fonctions (§1.2, §1.2.4, §1.2.5, §1.3, §1.3.4), légendes des
  diagrammes (`[followed]`, « check source entity », états de §1.3.3.2.1,
  `h`, machine des problèmes de §4.4), phrases d'état de §1.3.2.3 à
  §1.3.2.6 (F1 en signale deux inexactes). Vérifié par script : 218
  règles, 46 préfixes, numérotation de 1 à n dans l'ordre du texte,
  tous les renvois et liens du sommaire existent.

- ✅ **D5. Événements entre fonctions : absents des diagrammes ou des
  règles.**
  - `Sdsm=>Sx_served_mode_lost` et `Sdsm=>Sstm_served_modes_back` n'apparaissent
    que dans le tableau de §1.2.1 et comme déclencheurs de `Sstm`. Ni le
    diagramme de confirmation de retrait (activité de
    `Sdsm_removal_timeout`), ni SRC-DATA-6 / SRC-DATA-10 ne disent que `Sdsm`
    les envoie.
  - Diagramme de confirmation de retrait : après `Sdsm_removal_timeout` la
    valeur est retirée, mais la transition revient à `STORED`.
  - `Sdsm=>Sstm_discovered` est envoyé pendant la restauration, avant
    que `Sdsm=>Sstm_restored` ne donne son premier état à `Sstm` : personne ne
    le traite (`first` utilise la garde « discovered »).
  - Tableau de §1.2.5 : « otherwise: OFF, mode request confirmation » oublie
    `UNUSABLE` ; la ligne `Smrc=>Ssrm_settle_end` n'a pas de condition d'état
    (voir A1).

  À décider : corrections de forme, après A1.

  Le dernier tiret est réglé par B2 : §1.2.5 est réécrite en machine
  d'états, `UNUSABLE` est dans `HOLD`, `Smrc=>Ssrm_settle_end` n'existe
  plus.

  Décision (passe complète sur les événements, à la demande de
  l'utilisateur) : chaque événement a une seule description, avec les
  renvois vers les règles qui l'envoient et qui le traitent ; tout
  événement employé est décrit, tout événement décrit est employé.
  - Points du constat :
    - `Sdsm` envoie `Sdsm=>Sx_served_mode_lost` à la fin de la
      confirmation de retrait d'un mode servi (SRC-DATA-10, diagramme), et
      `Sdsm=>Sstm_served_modes_back` quand un ajout à `hvac_modes` rend
      tous les modes servis offerts (SRC-DATA-6) ;
    - le diagramme de confirmation de retrait finit sur `[*]` après
      `Sdsm_removal_timeout` (la valeur n'existe plus) ;
    - au démarrage, `Sdsm` n'envoie à `Sstm` que `Sdsm=>Sstm_restored` :
      ni `Sdsm=>Sstm_discovered`, ni `Sdsm=>Sstm_served_modes_back` avant
      lui ; le premier état lit les données (SRC-DATA-4, organigramme de
      §1.2.2.2, tableau de §1.2.1, séquence §5.6 et ses notes
      renumérotées).
  - Une description par événement : §1.1.2 décrit tous les événements
    entre un acteur et l'extérieur (nouveau tableau « Between Home
    Assistant and the actors », les `SE=>S_*` un par un) ; §1.2.1,
    §1.3.1 et §4.4 les listent pour l'acteur avec « See §1.1.2 », et
    décrivent ses événements internes et ses timers. Colonnes harmonisées
    en « From → To ». Le tiret de F8 (événements décrits trois fois avec des
    mots différents) réglée au passage.
  - Ajouts : `HA=>M_start` et `HA=>M_unload` (le monitoring est un
    acteur, il démarre vide et s'arrête au déchargement : END-1, END-2,
    MON-SEND-3) ; tableau des timers du monitoring (`M_delay_timeout`,
    §4.4) ; « appeared in Home Assistant » pour `SE=>S_off` / `SE=>S_on`
    (une entité source chargée après l'intégration, §5.7).
  - Nommage : la convention définit `*` (`S=>SE_set_*`, `S=>AC_*`) et
    `X` comme expéditeur quelconque (`X=>M_up(p)`) ; les `S=>AC_` sans
    `*` sont corrigés (SRC-STATE-3, ENT-STATE-3, ENT-PHASE-3). Les noms
    existants sont gardés : tous suivent `X=>Y_name` ou `X_name_timeout`.
  - Renvois ajoutés dans les tableaux : règles émettrices et
    réceptrices pour `HA=>*`, `U=>AC_*`, `T=>AC_temperature`,
    `AC=>S_*`, `S=>AC_*`, `S=>SE_*`, `SE=>S_call_failed`, `S=>M_up`, et
    pour `Sdsm=>Sstm_restored`, `Sdsm=>Sstm_discovered`,
    `Sdsm=>Sstm_served_modes_back`, `Sstm=>Ssrm_takeover`,
    `Sstm=>Ssrm_unusable`.

  Vérifié par script : chaque nom d'événement employé a exactement une
  description complète ; numérotation et renvois inchangés et valides.

## F. Mineurs

Tous les points de F ont été tranchés le 2026-11-17 sans discussion, à la
demande de l'utilisateur (« je te laisse prendre en compte seul tous ces
éléments mineurs »). Les décisions qui changent un comportement sont
marquées **(comportement)**, pour être relues en premier.

- ✅ **F1. Formulations à corriger.**
  - ENT-TYPE-4 : « Otherwise, a user request for it is refused » suit
    une phrase sur `UNUSABLE` ; « Otherwise » ne renvoie plus à « not
    available ».
  - (Réglé par D4 : la note est passée dans ENT-PHASE-2.) §1.3.3.2.1,
    note « The return of an UNUSABLE source does not » :
    phrase coupée (il manque « count as a reading »), et citation collée
    à la liste.
  - §1.2.3.2 : « moves the source to OFF » ; ou à `UNUSABLE` si un mode
    servi n'est pas offert (SRC-STATE-8).
  - §1.3.2.3 « Every source is asked to be off » et §1.3.2.4 « every
    other source is asked to be off » : sauf une source tolérée dans un
    mode étranger (ENT-STATE-5).
  - SRC-DATA-1, « (source state ON(m)) » : la lecture dépend du mode
    montré par l'entité source, pas de l'état de la source (§1.2 : les
    données stockées « do not depend on the state of the source » ; elles
    sont lues aussi en `UNUSABLE`, SRC-UNUS-2).
  - SRC-SET-3 cite `OFF` et `UNDISCOVERED`, où la source ne reçoit jamais
    de réglages (`AC.apply` envoie la requête d'abord ; aucune requête en
    `UNDISCOVERED`).
  - Ancres `…-new` du sommaire (invisibles).

  Décision : corrections de texte, sans changement de comportement.
  - ENT-TYPE-4 : « when none is, a user request for it is refused »,
    avant la phrase sur `UNUSABLE`.
  - SRC-UNDISC-1 : « to `OFF`, or to `UNUSABLE` if a served source mode
    is not offered (SRC-STATE-8) ».
  - Intro de §1.3.2.3 : toutes les sources sont mises à `off`, sauf une
    source `UNDISCOVERED` (rien ne lui est envoyé, ENT-SEND-3) et une
    source allumée depuis dans un mode étranger (tolérée, ENT-STATE-5).
    §1.3.2.4 renvoie aux mêmes exceptions, et précise qu'en bi-source
    c'est la source de la phase courante qui tourne.
  - SRC-DATA-1 : les capacités d'un mode sont lues quand l'entité source
    montre ce mode, quel que soit l'état de la source (SRC-DATA-6 ; aussi
    en `UNUSABLE`, SRC-UNUS-2).
  - SRC-SET-3 : en `HOLD`, rien n'est envoyé ; les réglages reçus en
    `UNUSABLE` ou pendant une confirmation sont gardés et envoyés à
    l'entrée de `SETTLE`. En `OFF` et `UNDISCOVERED`, la source n'en
    reçoit pas : l'entité n'envoie des réglages qu'à une source à qui
    elle demande un mode, et la requête passe d'abord (ENT-SEND-3), donc
    la source est déjà en `ON(m)` ; rien à une source `UNDISCOVERED`.
  - Ancres : les `<a id="…-new">` sont supprimées, le sommaire pointe sur
    les ancres générées par les titres.

- ✅ **F2. Cibles : précisions.**
  - ENT-TGT-7 refuse une valeur hors de la plage montrée (ENT-RANGE-2) ;
    ENT-RANGE-5 garde la cible dans la plage de la cible. Entre les deux
    (en `OFF`, où la plage montrée couvre tous les modes ; ou
    `target_temp_low` réglé en `cool`), la valeur est-elle ramenée à la
    limite sans erreur ?
  - ENT-TGT-7 avec `hvac_mode` : la plage contrôlée est-elle celle du
    mode courant ou du nouveau ; si le mode est refusé (ENT-STATE-4),
    les cibles sont-elles gardées ?
  - ENT-TGT-10 : « the single target of a source » (laquelle, dans quel
    ordre), « the middle of the range » (quelle plage).
  - ENT-TGT-5 : l'écart s'applique toujours, même quand aucun mode
    configuré ne montre low et high ensemble (`heat`, `cool` et un
    `heat_cool` mono-source à cible unique : régler `cool` à 21 fait
    descendre la cible de `heat`). Voulu ?
  - CFG-LIM-1 : `min_temp` < `max_temp`, mais rien si `max_temp` −
    `min_temp` < `min_gap`, ni pour un mode dont la plage est plus
    étroite que `min_gap` (ENT-TGT-8 ne peut pas rétablir l'écart).

  Vérifié dans Home Assistant 2026.11 (`climate/services.py`) : avant
  d'appeler l'entité, `set_temperature` refuse une valeur hors du
  `min_temp` / `max_temp` montré **maintenant** (même avec un
  `hvac_mode` dans l'appel), et un `target_temp_low` au-dessus de
  `target_temp_high`.

  Décision :
  - ENT-TGT-7, refus : il est fait par Home Assistant, sur la plage de
    l'état courant ; l'entité contrôle la même chose.
  - ENT-TGT-7, entre les deux : une valeur dans la plage montrée mais
    hors de la plage de sa cible est ramenée à la borne la plus proche,
    sans erreur, puis l'écart est appliqué. Cas : `OFF`, low/high réglé
    dans un mode qui montre `temperature`, mode pas encore découvert,
    requête avec `hvac_mode`.
  - ENT-TGT-7 avec `hvac_mode` : si le mode est refusé (ENT-STATE-4),
    toute la requête est refusée, aucune cible n'est gardée.
  - ENT-RANGE-5 : une cible qu'aucun mode n'utilise encore (modes pas
    découverts, ou non configurés) est gardée dans la plage la plus large
    de tous les modes (celle montrée en `OFF`). Ce cas manquait (au
    premier démarrage, aucun mode n'utilise de cible).
  - ENT-TGT-10 réécrite : les cibles manquantes sont prises à l'entrée
    dans `OPER` (depuis `INIT`, ou depuis `NO_SOURCE`), avant `resume`.
    Sources parcourues dans l'ordre des modes (premier mode servi par
    chacune), celles qui ne montrent rien sont sautées. T : la cible
    unique de la première source qui en montre une, sinon le milieu de
    la plage montrée en `OFF` (21 °C avec 7–35 °C). low/high : la source
    `heat_cool` mono-source, sinon la cible unique des sources `heat` /
    `cool`, sinon le low / high de la première source qui en montre,
    sinon T − 1 et T + 1. Les cibles restaurées sont gardées : seules les
    manquantes sont prises (lien avec F8, données partielles).
  - **(comportement)** ENT-TGT-5 : l'écart ne s'applique que si l'entité
    a low/high (un mode configuré les montre, ENT-FEAT-3, comme
    ENT-TGT-11). Sinon low et high sont les cibles indépendantes de
    `heat` et `cool` : régler `cool` à 21 °C laisse `heat` à 22 °C. Une
    source low/high en `heat` ou `cool` reçoit toujours une paire avec
    l'écart (ENT-TGT-8). Quand un mode se met à montrer low/high,
    l'écart est appliqué au changement de capacités (ENT-TGT-4).
    ENT-TGT-6 et ENT-TGT-9 renvoient à ENT-TGT-5.
  - CFG-LIM-1 : avec les deux limites, `max_temp` doit dépasser
    `min_temp` d'au moins `min_gap` (CFG-CHECK-1 suit). Plages trop
    étroites venant des sources : ENT-TGT-5 met low au minimum et high
    au maximum de leurs plages (l'écart est le plus grand possible) ;
    ENT-TGT-8 envoie les deux bornes de la plage du mode.

- ✅ **F3. Configuration : précisions.**
  - `name` « unique » : aussi entre une entrée de l'UI et une entrée
    YAML (CFG-YAML-2 ne parle que du YAML) ? Renommer une entrée YAML
    vaut suppression puis création (données stockées perdues) : à dire.
  - `temperature_sensor` : capteur sans unité, ou dont l'unité n'est pas
    une température.
  - `<mode>_offset` non nul avec un capteur externe : accepté et ignoré,
    ou refusé (CFG-SENS-4 dit seulement « is 0 ») ?
  - CFG-TIMER-1 ne donne pas la raison de la contrainte.

  Décision :
  - Nouvelles CFG-NAME-1 et CFG-NAME-2 (§3.1.1) : `name` est unique entre
    toutes les entrées, UI et YAML ; une entrée YAML dont le nom est pris
    par une entrée de l'UI n'est pas importée (erreur loguée). Renommer
    une entrée YAML la supprime avec ses données stockées et en crée une
    nouvelle, qui part comme à un premier démarrage. CFG-YAML-2 et
    CFG-CHECK-1 y renvoient.
  - Nouvelle CFG-SENS-6 : l'unité de `temperature_sensor` doit être une
    température (°C, °F, K). Une autre unité montrée au contrôle est
    refusée ; sans unité (capteur template), accepté et lu dans l'unité
    de Home Assistant ; en fonctionnement, une unité qui n'est pas une
    température rend la valeur invalide (`temperature@T` `None`,
    ENT-REF-1, MON-TEMP-4).
  - CFG-SENS-2 : un `<mode>_offset` non nul avec un capteur externe sur
    le même mode (avec sa propre entité source) est **refusé**, pour
    qu'un offset ne paraisse jamais réglé alors qu'il est sans effet.
    CFG-CHECK-1 suit.
  - CFG-TIMER-1 : raison ajoutée. L'appareil a
    `request_confirmation_timer` pour suivre une commande ; la renvoyer
    plus tôt ne lui donne pas plus de chances et charge l'appareil (et
    son cloud, souvent limité en débit).

- ✅ **F4. Fan/swing : précisions.**
  - ENT-FAN-2 déclare la feature quand un mode « has options » ;
    ENT-FAN-4 montre le réglage dès que la capacité est découverte,
    « which may be none ».
  - ENT-FAN-4 / ENT-FAN-5 : la demande de l'utilisateur est comparée
    sans la casse. À vérifier : Home Assistant contrôle lui-même la
    valeur contre les `fan_modes` / `swing_modes` montrés (comparaison
    exacte) avant d'appeler l'entité ; une demande `Low` pour `low`
    n'arriverait alors jamais. La comparaison sans la casse ne
    servirait qu'entre l'entité et ses sources.

  Vérifié dans Home Assistant 2026.11 (`climate/entity.py`,
  `_valid_mode_or_raise`) : `set_fan_mode`, `set_swing_mode` et
  `set_swing_horizontal_mode` refusent, avant d'appeler l'entité, une
  valeur qui n'est pas exactement (casse comprise) dans les options
  montrées, et toute valeur quand il n'y a pas d'option.

  Décision :
  - ENT-FAN-2 : la feature est déclarée dès qu'un mode configuré a la
    capacité découverte, même sans option (aligné sur ENT-FAN-4).
  - ENT-FAN-4 : seule une valeur parmi les options montrées peut être
    réglée ; Home Assistant fait ce contrôle lui-même (comparaison
    exacte), l'entité contrôle la même chose.
  - ENT-FAN-5 : la comparaison sans la casse ne sert qu'entre l'entité
    et ses sources (valeur mémorisée et options d'un mode, options
    partagées, valeur rapportée par une source, SRC-SET-4). Ajouté :
    l'entité montre une valeur écrite comme les options qu'elle montre.

- ✅ **F5. Température de référence : précisions.**
  - ENT-REF-2 en `OFF` : « the source of the last used mode ». Si ce
    mode n'est plus configuré (ENT-INIT-4) : ENT-STATE-2 traite le cas
    pour `turn_on`, pas pour ENT-REF-2, ENT-TGT-7, ENT-TGT-11.
  - Organigramme de §1.3.5.1 : « else of the first available source » se
    lit comme un repli quand la dernière source utilisée n'a pas de
    lecture ; le texte ne le prévoit que si aucun mode n'a jamais été
    utilisé.

  Décision :
  - Un dernier mode utilisé qui n'est plus configuré est oublié : tout se
    passe comme si aucun mode n'avait été utilisé (ENT-INIT-4,
    ENT-STATE-2, ENT-DATA-1). `turn_on` demande le premier mode configuré,
    les cibles de `OFF` sont celles de ce mode (ENT-TGT-7, ENT-TGT-11),
    la référence est lue sur la première source disponible (ENT-REF-2).
  - Pas de repli : le texte est gardé, l'organigramme est aligné dessus
    (« or of the first available source if no mode was ever used ») ;
    ENT-REF-2 dit que ce n'est pas un repli (dernière source sans
    lecture → pas de référence, ENT-REF-3). La question bi-source de
    l'organigramme lit aussi le dernier mode utilisé en `OFF`.

- ✅ **F6. Capteur externe : warning répété.** ENT-EXT-2 logue un warning
  à chaque écriture hors plage, donc à chaque changement de température
  et à chaque réécriture, tant que cela dure.

  Décision : ENT-EXT-2 logue un warning quand la valeur sort de la plage
  de l'entité capteur externe, pas à nouveau tant qu'elle reste dehors ;
  la première écriture revenue dans la plage est loguée en info, une
  nouvelle sortie relogue un warning. Les erreurs d'écriture
  (`XS=>AC_call_failed`) restent loguées à chaque fois.

- ✅ **F7. Attributs (§2.2).**
  - `mode_entity_ids` : valeur pour un `heat_cool` bi-source (pas de
    source propre) ?
  - La phase courante n'est visible que par `active_entity_id`, et pas
    du tout quand les deux phases utilisent la même entité source.

  Décision :
  - `mode_entity_ids` ne liste que les modes qui ont leur propre entité
    source (`<mode>_entity`) : un `heat_cool` bi-source n'y est pas (ses
    phases utilisent les sources listées pour `heat` et `cool`).
  - Nouvel attribut `phase` : la phase courante d'un `heat_cool`
    bi-source (`heat` ou `cool`, aussi en `WAITING(heat_cool)`), `None`
    sinon.

- ✅ **F8. Structure du document.**
  - La source a un tableau « Stored data » (§1.2.2.1), pas l'entité : ce
    qu'elle sauve est dispersé (ENT-STATE-1, ENT-STATE-2, ENT-PHASE-1,
    ENT-TGT-2, ENT-FANV-1). Rien ne traite des données perdues ou
    partielles côté entité (SRC-DATA-5 le fait pour la source ;
    ENT-TGT-10 suppose que « pas de cible sauvée » = premier démarrage,
    entité en `OFF`).
  - §4 ne cite pas les Repairs issues (ENT-HVAC-5, ENT-FAN-7,
    ENT-FAN-8), qui signalent aussi des problèmes.
  - (Réglé par D5 : une description par événement en §1.1.2.) Les
    événements sont décrits trois fois (§1.1.2, §1.2.1, §1.3.1),
    avec des mots différents (`AC=>S_request(r)`).
  - §3.1.3 « Temperature sensor » contient aussi les offsets, les
    capteurs externes et `phase_hysteresis` ; les noms des durées n'ont
    pas de forme commune (`*_timer`, `capability_rem_confirmation`,
    `external_sensor_resend`, `monitoring_duration`).

  Décision :
  - Nouvelle section §1.3.6 « Stored data » (sommaire, intro de §1.3,
    glossaire « Stored » et END-3 y renvoient ; END-3 cite aussi le
    dernier mode utilisé) : un tableau (mode, dernier mode utilisé,
    phase, cibles, mémoire fan/swing, avec leurs règles), ENT-DATA-1
    (chaque valeur manquante traitée seule, comme SRC-DATA-4 : mode →
    `off`, dernier mode → aucun, phase → aucune, cible manquante → prise
    des sources par ENT-TGT-10, mémoire → vide) et ENT-DATA-2 (valeur
    invalide écartée et traitée comme manquante ; données de l'entité et
    des sources indépendantes). ENT-INIT-2 renvoie aussi à ENT-DATA-2.
  - §4 : note « Repairs issues » après MON-ROLE-1 : ce sont des problèmes
    de configuration vus en fonctionnement, levés tout de suite par
    l'entité, sans délai, sans allumer de capteur ; une source qui
    n'offre pas un mode servi est aussi `UNUSABLE`, donc peut aussi être
    signalée en « source unusable ».
  - §3.1.3 devient « Temperature readings », avec une phrase d'intro
    (capteur, offsets, capteurs externes, hystérésis de phase) : les
    renvois « §3.1.3 » restent justes.
  - **(comportement : noms d'options)** Toutes les durées configurables
    sont nommées `<quoi>_timer`, en secondes (phrase en tête de §3.1.4) :
    `capability_rem_confirmation` → `removal_confirmation_timer`,
    `external_sensor_resend` → `external_sensor_resend_timer`,
    `monitoring_duration` → `monitoring_delay_timer` (le « délai » d'un
    problème, comme `M_delay_timeout`). Pas de migration
    (pas de rétrocompatibilité pour l'instant).

- ✅ **F9. Événements reçus hors du cas décrit.** ENT-SET-2 ne parle que
  de `S=>AC_settings` « from the active source ». Non dit :
  `S=>AC_settings` d'une autre source (qui tourne dans un mode étranger)
  ou en `OFF` ; les `S=>AC_*` reçus en `INIT` après le premier état de la
  source, et en `NO_SOURCE` hors des sorties. Sans doute ignorés : à
  écrire.

  Décision : ignorés, et écrit.
  - Notation (§0) : un événement que l'état courant ne traite ni par une
    transition ni par une réaction est ignoré par cette machine ; les
    autres fonctions de l'acteur le reçoivent quand même (EXEC-1).
  - ENT-SET-2 : `S=>AC_settings` d'une autre source que la source active
    (source tolérée dans un mode étranger, toute source en `OFF`) est
    ignoré : ni adopté, ni écrit dans `expected(S)` / `sent(S)`.
  - Nouvelle ENT-INIT-5 : en `INIT`, la gestion d'état ne traite que le
    premier état de chaque source. Le démarrage est un seul stimulus
    (EXEC-4), donc aucun autre `S=>AC_*` n'est attendu avant la sortie
    d'`INIT` ; s'il en venait un, il serait ignoré : `resume` lit
    `state@S` et resynchronise. `S=>AC_capabilities` et les capteurs
    externes restent traités par leurs fonctions.
  - Nouvelle ENT-NOSRC-4 : en `NO_SOURCE`, seules les sorties
    (`S=>AC_usable`, `S=>AC_off`) ; une source découverte `UNUSABLE`
    laisse l'entité en `NO_SOURCE` ; une source `UNUSABLE` ou
    `UNDISCOVERED` ne rapporte rien d'autre ; `S=>AC_capabilities` est
    traité par la gestion des capacités.

  Vérifié par script après F : 215 règles, numérotation sans trou ni
  doublon dans chaque préfixe, tous les renvois vers une règle ou une
  section existent, tous les liens du sommaire pointent sur un titre.
