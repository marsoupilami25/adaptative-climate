"""Interface module, no logic: exposes the config flow of config/flows (ARCHITECTURE §11)."""

from .config.flows.config_flow import AdaptativeClimateConfigFlow

__all__ = ["AdaptativeClimateConfigFlow"]
