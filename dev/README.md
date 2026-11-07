# Tests manuels

Configuration Home Assistant pour tester l'intégration à la main, avec des
entités `climate` virtuelles et un tableau de bord par cas de test.

```text
dev/
  config/
    configuration.yaml            config HA de dev
    packages/sources_<cas>.yaml   sources virtuelles d'un cas et leurs réglages
    dashboards/                   un tableau de bord par cas de test
  link_config.sh                  relie ces fichiers à un dossier de config HA
```

## Installation

1. Relier la config du dépôt :

   ```bash
   dev/link_config.sh ~/ha-dev/config
   ```

   Le script crée des liens symboliques vers `configuration.yaml`, `packages/`,
   `dashboards/` et `custom_components/adaptative_climate`. Un fichier existant
   est d'abord renommé en `.bak`. Toute modification faite dans le dépôt est donc
   prise en compte au prochain redémarrage (ou rafraîchissement de la page pour
   le tableau de bord).
2. Démarrer Home Assistant. Les entités testées sont déclarées dans la section
   `adaptative_climate:` de `configuration.yaml` et créées au démarrage (voir
   [Cas de test](#cas-de-test)).

## Entités virtuelles

| Source | Modes | Réglages |
|:--|:--|:--|
| HEAT Virtuel | off, heat | consigne, fan, swing, swing horizontal |
| COOL Virtuel | off, cool | consigne, fan, swing, swing horizontal |
| DRY Virtuel | off, dry | consigne, fan, swing, swing horizontal |
| FAN_ONLY Virtuel | off, fan_only | consigne, fan, swing, swing horizontal |
| AUTO Virtuel | off, auto | consigne, fan, swing, swing horizontal |
| ALL Virtuel | tous | consigne, consigne basse/haute, fan, swing, swing horizontal |

Dans les cas *multi* et *manuel*, les sources n'écrivent pas leurs options de la
même façon, pour tester la synchronisation sans tenir compte de la casse : HEAT en
capitales (*Auto*, *Off*...) avec une vitesse *Turbo* en plus, DRY en majuscules
(*AUTO*, *LOW*, *HIGH*) sans *medium*, les autres en minuscules.

Les sources sont des `climate` de l'intégration
[Template](https://www.home-assistant.io/integrations/template/) de Home
Assistant : rien à installer.

Chaque tableau de bord a son propre jeu de sources, dans
`packages/sources_<cas>.yaml` (`mono`, `multi`, `unique`, `manuel`) : tester un
cas ne touche jamais les sources d'un autre. Toutes les entités d'un cas portent
le suffixe `_<cas>` (`climate.heat_virtuel_mono`, `input_select.mode_heat_mono`...)
et les climates sont nommés *HEAT Virtuel (mono)*, etc. Le tableau ci-dessus
liste les sources possibles ; chaque cas ne déclare que celles qu'il utilise.

Chaque source a sa propre consigne (`input_number.consigne_<mode>_<cas>`) : on voit
ainsi quelle source reçoit les commandes. Les sources d'un cas lisent la même température de
pièce (`input_number.temperature_courante_<cas>`). L'action (`heating`, `idle`...) est
calculée à partir du mode et de l'écart entre pièce et consigne.

Un interrupteur `input_boolean.dispo_<mode>_<cas>` rend chaque source indisponible.
Il revient à *on* à chaque redémarrage.

Les interrupteurs `input_boolean.fan_actif_<mode>_<cas>`, `swing_actif_<mode>_<cas>` et
`swing_horizontal_actif_<mode>_<cas>` retirent le fan ou un swing d'une source, sans
redémarrer : la source ne propose alors plus aucune option, comme un appareil
qui n'en a pas (un radiateur par exemple). Ils reviennent aussi à *on* à chaque redémarrage.

Le script `script.reset_sources_test_<cas>` remet tout à zéro, pour son cas seulement : sources disponibles
et éteintes, fan et swings actifs (sur leur première option, *auto* et *off*), pièce à 20 °C,
consignes par défaut. Il n'efface pas les réglages mémorisés par les entités testées.

## Cas de test

Chaque cas a son tableau de bord dans la barre latérale. On y trouve
l'entité testée, ses sources avec tous leurs réglages, un résumé de l'état
(la source active est marquée ◀) et la liste des scénarios à dérouler.

| Cas | Entités | Sources | Tableau de bord |
|:--|:--|:--|:--|
| Un mode | `climate.adaptative_heat`, `_cool`, `_dry`, `_fan_only`, `_auto` | la source mono-mode du même mode (`_mono`) | *Tests mono-mode* (une vue par mode) |
| Tous les modes, une source par mode | `climate.adaptative_multi` (heat, cool et dry synchronisés) | les 5 sources mono-mode (`_multi`) | *Tests multi-sources* |
| Tous les modes, une seule source | `climate.adaptative_all` (heat, cool et dry synchronisés) | ALL Virtuel (`_unique`) | *Tests source unique* |
| Manuel | `climate.adaptative_manuel`, créé depuis l'interface | au choix parmi les 6 sources (`_manuel`) | *Tests manuels* (vues *Sources* et *Adaptative*) |

Pour le cas manuel, ajouter un Adaptative Climate depuis *Paramètres > Appareils
et services > Entrées*, le nommer **Adaptative Manuel** et choisir ses sources.
La vue *Sources* donne accès à toutes les sources virtuelles et à leurs réglages.

Partir de **Tout remettre à zéro** avant chaque cas.
