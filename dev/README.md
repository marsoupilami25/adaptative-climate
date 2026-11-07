# Tests manuels

Configuration Home Assistant pour tester l'intégration à la main, avec des
entités `climate` virtuelles et un tableau de bord par cas de test.

```text
dev/
  config/
    configuration.yaml            config HA de dev
    packages/sources_virtuelles.yaml   sources virtuelles et leurs réglages
    dashboards/                   un tableau de bord par cas de test
  link_config.sh                  relie ces fichiers à un dossier de config HA
```

## Installation

1. Installer [Climate Template](https://github.com/jcwillox/hass-template-climate)
   (via HACS) dans la config HA de dev.
2. Relier la config du dépôt :

   ```bash
   dev/link_config.sh ~/ha-dev/config
   ```

   Le script crée des liens symboliques vers `configuration.yaml`, `packages/`,
   `dashboards/` et `custom_components/adaptative_climate`. Un fichier existant
   est d'abord renommé en `.bak`. Toute modification faite dans le dépôt est donc
   prise en compte au prochain redémarrage (ou rafraîchissement de la page pour
   le tableau de bord).
3. Démarrer Home Assistant. Les entités testées sont déclarées dans la section
   `adaptative_climate:` de `configuration.yaml` et créées au démarrage (voir
   [Cas de test](#cas-de-test)).

## Entités virtuelles

| Source | Modes | Réglages |
|:--|:--|:--|
| HEAT Virtuel | off, heat | consigne |
| COOL Virtuel | off, cool | consigne, fan, swing |
| DRY Virtuel | off, dry | consigne, fan, swing |
| FAN_ONLY Virtuel | off, fan_only | consigne, fan, swing |
| AUTO Virtuel | off, auto | consigne |
| ALL Virtuel | tous | consigne, consigne basse/haute, fan, swing |

Chaque source a sa propre consigne (`input_number.consigne_<mode>`) : on voit
ainsi quelle source reçoit les commandes. Toutes lisent la même température de
pièce (`input_number.temperature_courante`). L'action (`heating`, `idle`...) est
calculée à partir du mode et de l'écart entre pièce et consigne.

Un interrupteur `input_boolean.dispo_<mode>` rend chaque source indisponible.
Il revient à *on* à chaque redémarrage.

Le script `script.reset_sources_test` remet tout à zéro : sources disponibles
et éteintes, pièce à 20 °C, consignes par défaut.

## Cas de test

Chaque cas a son tableau de bord dans la barre latérale. On y trouve
l'entité testée, ses sources avec tous leurs réglages, un résumé de l'état
(la source active est marquée ◀) et la liste des scénarios à dérouler.

| Cas | Entités | Sources | Tableau de bord |
|:--|:--|:--|:--|
| Un mode | `climate.adaptative_heat`, `_cool`, `_dry`, `_fan_only`, `_auto` | la source mono-mode du même mode | *Tests mono-mode* (une vue par mode) |
| Tous les modes, une source par mode | `climate.adaptative_multi` | les 5 sources mono-mode | *Tests multi-sources* |
| Tous les modes, une seule source | `climate.adaptative_all` | ALL Virtuel | *Tests source unique* |

Les cas 1 et 2 partagent les sources mono-mode : allumer HEAT Virtuel depuis
Adaptative MULTI allume aussi Adaptative HEAT. Partir de **Tout remettre à
zéro** avant chaque cas.
