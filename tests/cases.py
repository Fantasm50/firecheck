"""Synthetic objects from project-spec.md, 8.1 (fictional, for tests and demo only).

Flags not listed are "no". Shared by checklist and scoring tests.
"""

CASE_A = {  # small carpentry workshop
    "name": "Кейс А. Малая столярная мастерская",
    "category": "В2",
    "people_max": 8,
    "workplaces_per_floor": 8,
    "has_dust_collectors": True,
    "has_heating_units": True,
    "uses_oils_paints": True,
    "water_required": "unknown",
}

CASE_B = {  # machine shop of a medium plant
    "name": "Кейс Б. Механический цех среднего завода",
    "category": "В3",
    "people_max": 60,
    "workplaces_per_floor": 30,
    "has_aps": True,
    "has_soue": True,
    "has_indoor_hydrants": True,
    "has_fire_pumps": True,
    "has_external_stairs": True,
    "has_boiler": True,
    "has_heating_units": True,
    "does_hot_work": True,
    "hot_work_on_equipment": True,
    "uses_oils_paints": True,
    "has_design_docs": True,
    "water_required": "yes",
    "aupt_required": "no",  # main rooms are category Г (res. No 1464, app. 3)
}

CASE_C = {  # painting section
    "name": "Кейс В. Окрасочный участок",
    "category": "Б",
    "people_max": 25,
    "workplaces_per_floor": 20,
    "has_aps": True,
    "has_soue": True,
    "has_aupt": True,
    "uses_hazardous_substances": True,
    "uses_oils_paints": True,
    "has_exhaust_deposits": True,
    "has_ignition_protection": True,
    "has_flame_arresters": True,
    "has_fire_dampers": True,
    "has_fire_retardant": True,
    "has_design_docs": True,
    "uses_risk_calc": True,
    "water_required": "yes",
}
