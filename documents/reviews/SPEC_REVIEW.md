# Revue de SPEC.md — revue 3

Troisième et dernière revue complète de [SPEC.md](../SPEC.md), faite le
2026-11-17 sur la spec telle qu'elle est après la revue 2. Les revues
précédentes (tous leurs points sont traités ou abandonnés) sont archivées
dans [SPEC_REVIEW_1.md](SPEC_REVIEW_1.md) et
[SPEC_REVIEW_2.md](SPEC_REVIEW_2.md).

**Revue close le 2026-11-17** : tous ses points sont traités ou
abandonnés, et la spec a le statut « agreed ».

Approche demandée pour cette revue :

- la spec doit rester haut niveau ;
- la revue n'ouvre pas de nouvelle dimension de design ni de code : un
  point se règle en corrigeant, en complétant ou en allégeant le texte
  existant, jamais en ajoutant un mécanisme.

Ce que la revue fait donc :

- Elle ne soulève ni les sujets que la spec ne traite pas, ni les cas
  limites qui demanderaient un nouveau mécanisme. Elle ne revient pas
  sur les décisions des revues 1 et 2.
- Elle signale aussi les passages qui descendent au niveau du code
  (partie B).
- Les numéros repartent de 1 : « A1 » ici n'est le « A1 » ni de la
  revue 1 ni de la revue 2.
- Les références sont les identifiants de règles et les sections de la
  spec (pas de numéros de ligne : ils bougent).
- Seule la spec a été lue : le code est hors périmètre.
- Chaque point donne le constat, sa conséquence, et la question à
  trancher. Aucune décision n'est prise ici.

Statuts : ✅ traité (décision appliquée dans la spec) · ⏳ ouvert ·
❌ abandonné.

## Vue d'ensemble

| Partie | Points | Ouverts |
|---|---|---|
| A. Contradictions | 1 | 0 |
| B. Niveau de détail | 2 | 0 |
| C. Mineurs | 3 | 0 |

Vérifié par script, sans anomalie : 225 règles, numérotation sans trou ni
doublon dans chaque préfixe ; tous les renvois vers une règle ou une
section existent ; tous les liens du sommaire pointent sur un titre.

Relus sans contradiction trouvée : les machines à états (état de la
source, confirmation de requête, gestion des réglages, état de l'entité,
phases) entre elles et avec leurs règles. Les scénarios relus donnent
chacun un seul résultat : démarrage, retour d'`UNUSABLE`, takeover de
mode et de réglage, mode étranger, découverte d'une source et d'un mode,
`heat_cool` bi-source, monitoring.

## A. Contradictions

- ✅ **A1. Cibles réglées avant leur découverte : Home Assistant refuse
  l'appel.** ENT-CAP-4, ENT-FEAT-5 et ENT-TGT-7 disent que l'utilisateur
  peut régler les cibles d'un mode qui n'en montre pas (mode pas encore
  découvert, source sans cible) « through the service, which does not
  depend on what is shown » : elles sont gardées, puis envoyées à la
  découverte. Mais ENT-FEAT-3 ne déclare `TARGET_TEMPERATURE` que si un
  mode configuré montre une cible simple, et `TARGET_TEMPERATURE_RANGE`
  que si un mode montre low/high. Or Home Assistant vérifie lui-même,
  avant d'appeler l'entité, comme il le fait pour la plage et
  low > high (ENT-TGT-7) et pour les options fan/swing (ENT-FAN-4) :
  `set_temperature` avec `temperature` est refusé si l'entité ne déclare
  pas `TARGET_TEMPERATURE`, et avec `target_temp_low` / `target_temp_high`
  si elle ne déclare pas `TARGET_TEMPERATURE_RANGE`.

  Conséquence : sur une entrée neuve, tant qu'aucun mode à cible simple
  n'est découvert, `temperature` est refusé, contrairement à ce que
  promettent ENT-CAP-4 et ENT-FEAT-5. Une entrée avec le seul `heat`
  n'accepte aucune cible avant le premier fonctionnement en `heat`. De
  même, `target_temp_low` en `cool` (ENT-TGT-7) est refusé tant
  qu'aucun mode ne montre low/high. Un `heat_cool` bi-source suffit
  pour low/high : il les montre toujours (ENT-FEAT-5).

  À décider : accepter la limite et l'écrire (les cibles se règlent dès
  que l'entité déclare la fonction ; avant, ENT-TGT-10 les prend sur les
  sources), ou garder la promesse, ce qui change ENT-FEAT-3 (fonctions
  déclarées autrement que par ce que les modes montrent) ?

  Décision : accepter la limite et l'écrire, comme pour fan/swing
  (ENT-FAN-4 : on ne règle que ce qui est découvert). ENT-FEAT-3 ne
  change pas. Appliqué :
  - ENT-TGT-7, premier point : refusés aussi `temperature` sans
    `TARGET_TEMPERATURE` déclaré, et `target_temp_low` /
    `target_temp_high` sans `TARGET_TEMPERATURE_RANGE` (ENT-FEAT-3),
    contrôle fait par Home Assistant avant l'appel. Donc, sur une entrée
    neuve, `temperature` est refusé jusqu'à la découverte d'un mode à
    cible simple, low/high jusqu'à celle d'un mode qui les montre (un
    `heat_cool` bi-source les montre toujours) ; d'ici là, les cibles
    sont celles prises sur les sources (ENT-TGT-10) ;
  - ENT-TGT-7, `temperature` dans un mode qui n'en montre pas : « as
    long as the entity declares `TARGET_TEMPERATURE` (another mode shows
    one) » ;
  - ENT-CAP-4 : « through the service, when the entity declares the
    feature » ;
  - ENT-FEAT-5 : le service ne dépend pas de ce que ce mode montre,
    seulement des fonctions de l'entité (ENT-FEAT-3, ENT-TGT-7).

## B. Niveau de détail

- ❌ **B1. Passages qui décrivent le code plutôt que le comportement.**
  Quelques phrases disent comment c'est codé ou testé, pas ce que fait
  l'intégration :
  - EXEC-1, fin : « There is no thread: everything runs in the event
    loop of Home Assistant, with no wait (`await`) during a step. » Le
    comportement voulu est déjà dit juste avant : une étape n'est pas
    interrompue par un autre acteur.
  - ENT-HA-1 : les noms des propriétés que Home Assistant lit selon sa
    version (`native_temperature_unit`, `native_current_temperature`...).
  - ENT-HA-2 : une exigence de test (« The tests run on a version before
    2026.11 and on a version from 2026.11 »), pas un comportement.
  - ENT-HVAC-5 : l'identifiant interne de la Repairs issue
    (`<entry>_<mode>_not_supported`).
  - ENT-EXT-1 : « is kept once when the configuration is read » dit
    comment ; l'effet est la fin de la phrase (chaque valeur n'est écrite
    qu'une fois).

  Conséquence : ces phrases lient la spec à des choix de code ou de test
  ; les retirer ne change rien au comportement attendu.

  À décider : les retirer ou les réduire à leur effet (« une étape ne
  s'interrompt pas », « fonctionne avant et après 2026.11 », « une
  Repairs issue par mode non offert »), ou les garder ?

  Décision : on ne touche rien.

- ✅ **B2. Le glossaire porte des règles, et des règles sont redites en
  beaucoup d'endroits.**
  - Le glossaire annonce « The rules are in the sections cited », mais
    plusieurs lignes énoncent du comportement : « Served, foreign »
    (l'entité logue, liste dans `foreign_modes`, tolère jusqu'aux
    prochaines requêtes, passe `OFF` si c'est la source active),
    « Takeover » (avec la liste de ce qui n'en est pas),
    « Resynchronization », « Settle time », « Removal confirmation »,
    « Mode request confirmation » (hors synchro).
  - Des règles sont redites, avec d'autres mots, dans beaucoup de
    sections. Exemples :
    - une source `UNDISCOVERED` ne reçoit rien : ENT-SEND-3,
      SRC-STATE-8, SRC-SET-3, ENT-PHASE-7, ENT-INIT-4, tableau des
      activités de §1.3.2.1, §1.3.2.3 ;
    - la source gagne (takeover) : glossaire, SRC-STATE-5,
      SRC-STATE-10, SRC-REQ-8, SRC-SET-11, SRC-SET-13, ENT-STATE-3,
      ENT-TGT-9, ENT-FANV-4 ;
    - le mode étranger toléré : glossaire, ENT-STATE-5, ENT-SEND-2,
      ENT-TYPE-5, SRC-STATE-7, §1.3.2.3.

  Conséquence : aucune contradiction aujourd'hui (relu), mais chaque
  changement doit être reporté partout, sinon deux énoncés divergent
  (c'était le cas de la revue 2, A1 : SRC-STATE-6 contre le diagramme
  de §1.2.4). La longueur rend aussi la vue d'ensemble plus difficile à
  lire.

  À décider : alléger (glossaire = définition et renvoi ; une règle
  énoncée une fois, un renvoi ailleurs), ou garder les redites, qui
  permettent de lire une section seule ?

  Décision : alléger, sans changer le comportement. Ce qui est retiré
  reste énoncé dans la règle citée en renvoi. Appliqué :
  - Glossaire :
    - « Served, foreign » : définition, puis « What the entity does with
      a foreign mode: ENT-STATE-5 » (le log, `foreign_modes` et la
      tolérance sont dans ENT-STATE-5) ;
    - « Takeover » : définition, puis les renvois (SRC-STATE-5 pour le
      mode, SRC-SET-11 pour un réglage ; ENT-STATE-5, ENT-TGT-9,
      ENT-FANV-4 côté entité). La liste de ce qui n'est pas un takeover
      est retirée : elle est dans SRC-STATE-5 et SRC-SET-11 ;
    - « Kept » : « What is sent comes from them; what the source entity
      shows otherwise is a takeover, or a setting not applied » est
      retiré (SRC-SET-10, SRC-SET-11).
    - « Resynchronization », « Settle time », « Removal confirmation »
      et « Mode request confirmation » sont gardées : relues, ce sont
      des définitions d'une phrase avec renvoi.
  - `UNDISCOVERED` ne reçoit rien, énoncé dans ENT-SEND-3 : SRC-STATE-8
    et SRC-SET-3 n'en gardent que le renvoi (le doublon final de
    SRC-SET-3 est retiré). ENT-PHASE-7, ENT-INIT-4, le tableau des
    activités et §1.3.2.3 étaient déjà des renvois courts.
  - Takeover, énoncé dans SRC-STATE-5 et SRC-SET-11 : SRC-REQ-8 ne
    redit plus « the state moves and is reported to the entity ».
    SRC-STATE-10, SRC-SET-13, ENT-STATE-3, ENT-TGT-9 et ENT-FANV-4 sont
    gardées : chacune porte sa propre règle.
  - Mode étranger, énoncé dans ENT-STATE-5 : SRC-STATE-7 n'en garde que
    le renvoi (ce qui est renvoyé au retour d'`UNUSABLE` est dans
    ENT-STATE-5) ; ENT-TYPE-5 dit « handled as in ENT-STATE-5 ».
    ENT-SEND-2 et §1.3.2.3 étaient déjà des renvois courts.

## C. Mineurs

- ✅ **C1. Mots qui varient pour une même notion.**
  - « source temperature(s) » (tableau de §1.3.3.2.2, ENT-REF-6) pour
    ce que le glossaire appelle **reading** (température courante moins
    l'offset).
  - Le problème « Source out of sync » (§4.2, MON-SRC-3) s'appelle
    « mode not followed » dans le tableau de §4.1.
  - Le problème « Setting not applied » (§4.2, MON-SRC-4) s'appelle
    « a setting not shown » dans la colonne « Effect » de
    `monitoring_delay_timer` (§3.1.5).
  - Glossaire, « Function » : « with its own code » veut dire « son
    abréviation » (`Sdsm`, `ACstm`...), mais se lit comme « son propre
    code source ».

  À décider : aligner sur les mots du glossaire et de §4.2 ?

  Décision : aligner. Appliqué :
  - tableau de §1.3.3.2.2 : « both source readings », « one source
    reading » ; ENT-REF-6 : « the mean of the two readings » ;
  - §4.1 : « source out of sync » ;
  - §3.1.5, `monitoring_delay_timer` : « 30 s at least for a setting not
    applied » ;
  - glossaire, « Function » : « with its own abbreviation » ; de même en
    §1.3.1 : « (abbreviations: §1.1.2) ».

- ✅ **C2. Ce qui est montré : trois phrases incomplètes ou trop
  larges.**
  - §2.2, `hvac_action` : « The action of the active source (`None`
    when it has none) ». ENT-OFF-1 donne `off` en `OFF`, ENT-WAIT-2
    `None` en `WAITING(m)`.
  - §2.2, `phase` : « also in `WAITING(heat_cool)`, where it is kept ».
    Après un redémarrage qui reprend directement en `WAITING(heat_cool)`,
    la gestion des modes est en `NO_PHASE` (revue 2, B7) : il n'y a pas
    de phase, donc `phase` vaut `None`, et il n'y a pas d'options
    fan/swing de phase à montrer (ENT-FAN-3, ENT-FANV-8). Cela se
    déduit, mais le texte dit l'inverse.
  - MON-SENS-4 et §2.1 : les capteurs de monitoring sont « never
    `unavailable` », mais END-1 dit qu'ils le deviennent quand l'entrée
    est déchargée (Home Assistant le fait).

  À décider : compléter ces trois phrases, sans changer le comportement
  ?

  Décision : compléter, sans changer le comportement. Appliqué :
  - §2.2, `hvac_action` : « In `ON(m)`, the action of the active source
    (`None` when it has none); `off` in `OFF`; `None` in `WAITING(m)` »,
    avec les renvois ENT-OFF-1, ENT-ON-1, ENT-ON-2, ENT-WAIT-2 ;
  - §2.2, `phase` : gardée en `WAITING(heat_cool)` entré depuis
    `ON(heat_cool)` ; après un redémarrage qui reprend en
    `WAITING(heat_cool)`, `NO_PHASE` : `None` jusqu'au retour d'une
    source de phase ;
  - MON-SENS-4 : jamais `unavailable` « while the entry is loaded » ; au
    déchargement, Home Assistant les rend `unavailable` comme l'entité
    (END-1). §2.1 : « never `unavailable` while the entry is loaded ».

- ✅ **C3. En-tête de la spec.** « Status: **draft**. Baseline written
  from the README and the code, then amended. The code will follow the
  spec once agreed. » Depuis le 2026-11-12, la spec est la seule
  référence : le code n'est plus une base.

  À décider : à la clôture de cette dernière revue, changer le statut
  (par exemple « agreed ») et retirer « from the README and the code » ?

  Décision : clore la revue. En-tête de la spec : « Status: **agreed**
  (2026-11-17, after three reviews). The code will follow the spec. »
