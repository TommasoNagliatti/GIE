"""Real worker tests of first-step persistence, current demand and safe blocking."""
import json,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from gie_multistation.api import create_app

HOUSE='DEMO_CASA_001';POST='DEMO_POSTO_24H_001'

class RuntimeTests(unittest.TestCase):
    def test_committed_state_survives_crash_and_service_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            token='local-test-only-'+'x'*32;headers={'Authorization':'Bearer '+token}
            app=create_app({token:[HOUSE,POST]},directory)
            with TestClient(app) as client:
                def send(s,op,body={}):return client.post('/v1/stations/'+s+'/'+op,headers=headers,json=body)
                for sid in [HOUSE,POST]:self.assertEqual(send(sid,'initialize').status_code,200)
                body={'issue_time':'2025-11-01T00:00:00-03:00','current':{'building_kw':1.,'solar_kw':0.,'demands':[{'evse_id':'EVSE_01','connected':True,'requested_kw':7.}]}}
                r=send(HOUSE,'cycle',body);self.assertEqual(r.status_code,200,r.text)
                self.assertAlmostEqual(r.json()['state']['numeric_state']['ev_served_kw'],7.,delta=5e-5)
                hstate=r.json()['simulation_state']
                p=send(POST,'cycle',{'issue_time':body['issue_time']});self.assertEqual(p.status_code,200,p.text)
                saved=p.json()['simulation_state'];self.assertEqual(saved['cycles'],1)
                proc=app.state.manager.slots[POST]['process'];proc.terminate();proc.join(5)
                restored=send(POST,'restart');self.assertEqual(restored.status_code,200,restored.text)
                self.assertEqual(restored.json()['simulation_state'],saved)
                self.assertEqual(send(POST,'cycle',{'issue_time':body['issue_time']}).status_code,422)
                self.assertEqual(send(POST,'cycle',{'issue_time':'2025-11-01T00:30:00-03:00'}).status_code,422)
                self.assertEqual(client.get('/v1/stations/'+HOUSE+'/state',headers=headers).json()['simulation_state'],hstate)
                body['issue_time']='2025-11-01T00:15:00-03:00';body['current']['building_kw']=100.
                blocked=send(HOUSE,'cycle',body);self.assertEqual(blocked.status_code,200,blocked.text)
                self.assertFalse(blocked.json()['state']['execution_allowed'])
                self.assertEqual(blocked.json()['simulation_state'],hstate)
                body['current']['building_kw']=1.;body['current']['demands'][0]['vehicle_max_kw']=3.
                retried=send(HOUSE,'cycle',body);self.assertEqual(retried.status_code,200,retried.text)
                self.assertAlmostEqual(retried.json()['state']['numeric_state']['ev_served_kw'],3.,delta=5e-5)
                final=retried.json()['simulation_state'];self.assertEqual(final['cycles'],2)
                self.assertFalse(retried.json()['hardware_commands_sent'])
            with TestClient(create_app({token:[HOUSE,POST]},directory)) as client:
                r=client.post('/v1/stations/'+HOUSE+'/initialize',headers=headers,json={})
                self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['simulation_state'],final)
            checkpoint=Path(directory)/HOUSE/'energy_state_v3.json'
            corrupt=json.loads(checkpoint.read_text());corrupt['station_id']=POST
            checkpoint.write_text(json.dumps(corrupt))
            with TestClient(create_app({token:[HOUSE,POST]},directory)) as client:
                r=client.post('/v1/stations/'+HOUSE+'/initialize',headers=headers,json={})
                self.assertEqual(r.status_code,503,r.text)

if __name__=='__main__':unittest.main(verbosity=2)
