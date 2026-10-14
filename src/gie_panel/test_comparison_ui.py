import json,unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from gie_panel.client import Client
from gie_panel.comparison import OUT
ROOT=Path(__file__).resolve().parents[2]

class ComparisonUI(unittest.TestCase):
    def test_house_button_all_periods_and_return(self):
        fixtures=json.loads((ROOT/'reports/panel/v1/runtime/ui_fixtures.json').read_text())
        result=json.loads((OUT/'result.json').read_text(encoding='utf-8'))
        def call(client,path,body=None):
            if path=='/v1/stations':return [dict(config=dict(station_id=s)) for s in fixtures]
            sid=path.split('/')[2]
            if path.endswith('/catalog'):return fixtures[sid]['catalog']
            if '/replay?' in path:return fixtures[sid]['response']
            if path.endswith('/comparison'):return dict(status='complete',result=result)
            if '/alerts' in path or path.endswith('/events'):return []
            raise AssertionError(path)
        with patch.object(Client,'call',call):
            app=AppTest.from_file(str(ROOT/'src/gie_panel/app.py'),default_timeout=45).run()
            self.assertFalse(any(x.label=='Comparar baterias' for x in app.sidebar.button))
            app.sidebar.selectbox[0].select('DEMO_CASA_001').run()
            next(x for x in app.sidebar.button if x.label=='Comparar baterias').click().run()
            for period in result['periods']:
                next(x for x in app.selectbox if x.label=='Período da comparação').select(period).run()
                self.assertFalse(app.exception,list(app.exception));self.assertTrue(any('Rede com bateria'==x.label for x in app.metric))
            next(x for x in app.sidebar.button if x.label=='Voltar ao painel energético').click().run()
            self.assertFalse(app.exception);self.assertTrue(any(x.value=='Sem bateria instalada' for x in app.info))

if __name__=='__main__':unittest.main()
