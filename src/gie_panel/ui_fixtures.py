"""Export real saved API display payloads for UI-only regression (no optimization)."""
import json
from gie_panel.data import *
from gie_multistation.registry import registry
from gie_provisioning.examples import fixture

if __name__=='__main__':
    configs=registry();configs[NEW]=dict(station_id=NEW,kind='baseline',technical=fixture())
    out={}
    for sid,cfg in configs.items():
        cat=catalog(sid);frames=replay(sid,cat[0]['id'],json.dumps(cfg))
        out[sid]=dict(catalog=dict(scenarios=cat,equipment=equipment(cfg)),response=dict(view=display(frames[0],cfg,'REPLAY',[history_row(frames[0])]),cycle=1,process='replay',mode='REPLAY',model='Artefatos salvos'))
    path=ROOT/'reports/panel/v1/runtime/ui_fixtures.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out),encoding='utf-8')
