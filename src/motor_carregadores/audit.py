"""Validação estrutural e protocolo antes do treino; nenhum ajuste ao Motor 1."""
import sys
sys.dont_write_bytecode=True
if __package__ in (None,''):
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from motor_carregadores.features import *
def audit():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    raw=pd.read_csv(SOURCE);data=validate_frame(raw)
    assert data.index.equals(pd.date_range('2026-01-01','2026-07-01',freq='15min',inclusive='left'))
    assert not raw.isna().any().any() and np.isfinite(raw.drop(columns='timestamp')).all().all()
    for c,expected in [('hora',data.index.hour),('dia_semana',data.index.dayofweek),('fim_de_semana',(data.index.dayofweek>=5).astype(int)),('mes',data.index.month)]: assert np.array_equal(data[c],expected)
    # Session data is audited structurally; never enters training features.
    sessions=pd.read_csv(ROOT/'data/sessoes_carregadores_6_meses.csv')
    assert sessions.session_id.is_unique
    counts=pd.to_datetime(sessions.hora_chegada).dt.floor('15min').value_counts().reindex(data.index,fill_value=0)
    assert np.array_equal(counts,data.carros_chegando)
    assert abs(sessions.energia_entregue_kwh.sum()-data.energia_entregue_kwh.sum())<.001
    audit={'rows':len(data),'columns':list(raw),'first':str(data.index[0]),'last':str(data.index[-1]),'interval_minutes':15,
        'duplicates':0,'missing_values':0,'continuous':True,'source_sha256':digest(SOURCE),'sessions_rows':len(sessions),'session_arrivals_and_energy_match':True,
        'maxima':{c:float(data[c].max()) for c in VARIABLES},
        'semantics':{'timestamp':'start of last observed interval; available at t+15min',
        'power':'mean requested power from connected vehicles with outstanding energy; excludes queue and abandoned demand; no controller in this simulation',
        'occupancy':'maximum connected within interval, not average','queue':'maximum queue within interval, limit 3',
        'independence':'June held out for Motor 2 fitting and selection. Entire synthetic dataset previously inspected for generation/structural validation; not globally unseen or real-world validation.'}}
    write_json(OUTPUT/'dataset_validation.json',audit)
    preserved=[]
    for folder in ['src/motor_consumo','models/consumo_predio','outputs/motor_consumo','data']:
        preserved.extend(p for p in (ROOT/folder).rglob('*') if p.is_file())
    preserved.append(ROOT/'requirements.txt')
    write_json(OUTPUT/'preservation_before.json',{str(p.relative_to(ROOT)):digest(p) for p in preserved})
    write_json(OUTPUT/'protocol.json',{'models':5,'architecture':'global direct multi-horizon, all 48 horizons stacked',
        'power':'residual over unrounded four-week target-slot mean; fixed architecture, compare but do not switch on June',
        'counts':'Poisson; expected fractional counts; limits 4/6/3','queue_risk':'binary logloss, unweighted, no probability calibration',
        'threshold':'maximum F1 on May only, grid .05 to .95 in .01 increments; ties choose smaller threshold',
        'training':'Jan-Apr, early stopping on May only, 250 maximum rounds, 25 patience, no search',
        'splits':'same origins for all horizons, remove 48 end origins per partition, 28-day initial history required',
        'test':'June once after freezing; no tuning after test','production_example_origin':'2026-06-15 07:45',
        'timestamp_convention':'h=1 target is t+15min, equal to issuance when t is start of last observed interval'})
    print(json.dumps(audit,ensure_ascii=False,indent=2))
if __name__=='__main__': audit()
