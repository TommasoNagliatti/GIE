"""Explicit technical/simulated fixtures; no implied measured values."""
def fixture(sid='NEW_NO_HISTORY'):
    return dict(station_id=sid,timezone='America/Manaus',import_kw=25.,export_kw=3.,
        chargers=[dict(evse_id='E'+str(i),max_kw=float(i+2),minimum_kw=0) for i in range(5)],
        batteries=[],solar=[],inverters=[],circuits=[dict(circuit_id='BRANCH',evse_ids=['E0','E1'],max_kw=4.)],baseline_building_kw=3.)

def sample(technical,t='2026-10-13T00:00:00-04:00',building=3.,solar=0.):
    return dict(issue_time=t,current=dict(station_id=technical['station_id'],observed_at=t,available_at=t,origin='SIMULATED',quality='TRUSTED',building_kw=building,solar_kw=solar,
        demands=[dict(evse_id=e['evse_id'],connected=True,requested_kw=e['max_kw']) for e in technical['chargers']]))
