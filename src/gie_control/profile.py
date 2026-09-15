"""Read the official profile and check it against the frozen policy."""
from pathlib import Path
from dataclasses import asdict
import json
from motor_gerenciamento_v2.config import Config

ROOT = Path(__file__).resolve().parents[2]
PROFILE = 'Commercial_HighAutonomy_V2'

def load_profile(root=None):
    path = Path(root or ROOT) / 'site_profiles' / (PROFILE + '.json')
    profile = json.loads(path.read_text(encoding='utf-8'))
    cfg = Config().validate()
    mapping = {'solar_dc_kwp': 'pv_installed_kwp', 'solar_ac_kw': 'pv_ac_max_kw',
               **{k:k for k in ('battery_capacity_kwh','battery_charge_max_kw','battery_discharge_max_kw',
                  'soc_min_pct','soc_max_pct','ev_max_kw','grid_import_max_kw','grid_export_max_kw',
                  'charge_efficiency','discharge_efficiency')}}
    for key, field in mapping.items():
        if profile[key] != getattr(cfg,field):
            raise ValueError(f'Profile differs from frozen V2: {key}')
    if profile['name'] != PROFILE or profile['operational_reserve'] is not None or profile['strategic_soc_target'] is not None:
        raise ValueError('Unsupported profile policy')
    return profile, cfg
