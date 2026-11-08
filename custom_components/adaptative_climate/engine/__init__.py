"""Engine of the Adaptative Climate entity.

The climate entity (climate.py) is a facade over these parts, from the
lowest layer to the highest:

- model, util, timer: shared definitions, value helpers, one-shot timer
- sources: reads and commands the source climate entities
- profiles: what each mode does with its sources and targets
- phase: the phase (heat or cool) of the combined HEAT_COOL
- settings_memory: fan and swing settings remembered by each mode
- modes: the current mode, its source, switching modes
- targets: the targets kept by the entity, and the gap between them
- target_sync: sends the targets to the sources, takes their changes

Each part keeps its own state and gets what it depends on when built.
Only the entity writes its state; a part that needs it (end of a timer)
gets a callback.
"""
