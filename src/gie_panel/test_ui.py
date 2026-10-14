import json,unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from gie_panel.client import Client,APIError
ROOT=Path(__file__).resolve().parents[2]

class UITests(unittest.TestCase):
    def test_four_real_replay_payloads_and_disconnect(self):
        data=json.loads((ROOT/'reports/panel/v1/runtime/ui_fixtures.json').read_text())
        disconnected=False
        def call(client,path,body=None):
            if disconnected:raise APIError('Sem comunicação com a API. Nenhuma decisão anterior é apresentada como atual.')
            if path=='/v1/stations':return [dict(config=dict(station_id=s)) for s in data]
            sid=path.split('/')[2]
            if path.endswith('/catalog'):return data[sid]['catalog']
            if '/replay?' in path:return data[sid]['response']
            if '/alerts' in path or path.endswith('/events'):return []
            raise AssertionError(path)
        with patch.object(Client,'call',call):
            app=AppTest.from_file(str(ROOT/'src/gie_panel/app.py'),default_timeout=20).run()
            for sid in data:
                app.sidebar.selectbox[0].select(sid).run()
                self.assertFalse(app.exception,list(app.exception))
                content=' '.join(x.value for x in list(app.markdown)+list(app.caption))
                self.assertIn(sid,content)
                if sid=='DEMO_CASA_001':self.assertTrue(any(x.value=='Sem bateria instalada' for x in app.info));self.assertNotIn('BAT_01',content)
                if sid=='DEMO_POSTO_24H_001':self.assertIn('BAT_01',content);self.assertIn('BAT_02',content)
                self.assertTrue(all(len(m.value.split(' ')[0].split('.')[-1])==2 for m in app.metric if m.value!='—'))
            disconnected=True;app.run();self.assertTrue(app.error);self.assertFalse(app.metric)
if __name__=='__main__':unittest.main()
