# Tests manuels

Une configuration Home Assistant pour tester l'intégration à la main : des
sources `climate` virtuelles, et un tableau de bord par cas de test, avec ses
scénarios. Chaque scénario cite les règles de la spec qu'il montre.

```text
dev/manual/
  config/
    configuration.yaml            config HA de dev, entités testées en YAML
    packages/sources_<cas>.yaml   sources virtuelles d'un cas et leurs aides
    dashboards/<cas>.yaml         un tableau de bord par cas
  link_config.sh                  relie ces fichiers à un dossier de config HA
```

## Installation

1. Relier la config du dépôt :

   ```bash
   dev/manual/link_config.sh ~/ha-dev/config
   ```

   Le script crée des liens vers `configuration.yaml`, `packages/`,
   `dashboards/` et `custom_components/adaptative_climate`. Un fichier existant
   est d'abord renommé en `.bak`. Une modification faite dans le dépôt compte au
   prochain redémarrage (au rafraîchissement de la page pour un tableau de bord).
2. Vérifier puis démarrer Home Assistant :

   ```bash
   cd ~/ha-dev && .venv/bin/hass --script check_config -c config
   ```

## Sources virtuelles

Ce sont des `climate` de l'intégration
[Template](https://www.home-assistant.io/integrations/template/), pilotées par
des aides : rien à installer. Chaque cas a ses propres sources (suffixe
`_<cas>` : `climate.heat_virtuel_mono`, `input_select.mode_heat_mono`...) :
tester un cas ne touche jamais un autre.

La carte d'une source montre son état et ses aides :

| Aide | Effet |
|---|---|
| *Mode*, *Consigne* (*basse*, *haute*), *Fan*, *Swing* | ce que la source montre ; les modifier, c'est agir sur l'appareil (télécommande) |
| *Température* | sa température courante |
| *Disponible* | coupé : la source est `unavailable` |
| *Inconnu* | allumé : la source est `unknown` |
| *Obéit au mode* | coupé : les demandes de mode sont reçues mais pas appliquées |
| *Délai avant d'obéir* | secondes avant d'appliquer un mode demandé |
| *Applique les réglages* | coupé : consigne, fan et swing reçus mais pas appliqués |
| *Offre ...* | coupé : la source n'offre plus que `off` (mode servi perdu) |
| *Fan actif*, *Swing actif* | coupé : la source n'a plus ce réglage (liste vide) |
| *Fan sans ...* | allumé : une option de fan disparaît de la liste |

Les booléens reviennent à leur valeur de départ à chaque redémarrage. Les
consignes, la plage (`min`/`max`) et le pas d'une source sont fixes : un
changement de plage se teste dans les tests automatiques. **Remettre les
sources à zéro** (vue *Sources*) remet tout à zéro pour son cas ; elle ne
touche pas la mémoire des entités testées.

Les cas avec capteur ont un `sensor.capteur_piece_<cas>`, piloté par
*Température capteur* et *Capteur disponible*.

## Cas de test

| Tableau de bord | Entités | Sources |
|---|---|---|
| *Tests mono-mode* | une par type de mode : HEAT (avec `max_temp`), COOL (pas de 1, fan, swing), DESHUM (sans consigne), FAN_ONLY, AUTO, HEAT_COOL (basse/haute), OFFSET (offset 2 en heat et dry), TRV (capteur externe) | une source par entité |
| *Tests bi-source* | BI : `heat_cool` sur un radiateur et une clim, capteur de la pièce | RADIATEUR (offre aussi `fan_only`, mode étranger), CLIM |
| *Tests multi-sources* | MULTI : un mode par source, `sync_modes` heat/cool/dry, options écrites différemment selon la source | HEAT, COOL, DRY, FAN_ONLY, AUTO, capteur |
| *Tests source unique* | ALL : tous les modes sur une source | ALL |
| *Tests monitoring* | SURV (délais courts) et FANTOME (source qui n'existe pas) | RADIATEUR, CLIM, capteur |
| *Tests manuels* | *Adaptative Manuel*, créée depuis l'interface | HEAT, COOL, DRY, FAN_ONLY, AUTO, ALL, capteur, température externe |

Les délais des entités sont courts pour les tests (monitoring 30 s à 1 min au
lieu de 15 min) : voir `configuration.yaml`.

Partir de **Remettre les sources à zéro** avant un cas. Les scénarios d'une
vue se suivent : un scénario peut compter sur le précédent (un mode déjà
découvert, par exemple).

## Quand le comportement change

Un changement de comportement met à jour les scénarios concernés (et en ajoute
un pour le nouveau comportement) : chercher dans `dashboards/` le mode, l'option
ou la règle touchés. Vérifier ensuite que le YAML se charge (`check_config`, et
un rafraîchissement du tableau de bord).
