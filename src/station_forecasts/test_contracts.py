"""Contract, causal availability and preservation tests without final-test data."""
import unittest,tempfile,shutil
from .core import *
from .predict import Forecaster
from .train import fit
class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items=[]
        for profile in ['posto_24h_v1','residencial_v1']:
            c=config(profile);f=Forecaster(c['station_id']);d=load(c);folder=ROOT/c['dataset_dir']/'monthly'
            raw={k:pd.concat([pd.read_csv(folder/f'{k}_2025-{m:02d}.csv') for m in range(1,10)],ignore_index=True) for k in ['building','ev']}
            n=3000;raw={k:v.iloc[:n].copy() for k,v in raw.items()};issue=dates(raw['building'].timestamp,c['timezone'])[-1]+pd.Timedelta(minutes=15)
            cls.items.append((c,f,d,raw,issue))
    def test_01_contract_48_and_limits(self):
        for c,f,d,r,issue in self.items:
            p=f.predict(r['building'],r['ev'],issue)
            self.assertEqual(len(p),48);self.assertTrue(pd.DatetimeIndex(p.timestamp_previsto).equals(pd.date_range(issue,periods=48,freq='15min')))
            self.assertTrue(np.isfinite(p.drop(columns='timestamp_previsto').to_numpy()).all());self.assertTrue((p.drop(columns='timestamp_previsto')>=0).all().all())
            self.assertTrue(p.potencia_solicitada_alta_kw.between(0,c['ev_limit_kw']).all());self.assertTrue((p.potencia_solicitada_alta_kw>=p.potencia_solicitada_prevista_kw).all())
            self.assertTrue(p.carregadores_ocupados_previstos.between(0,c['n_evse']).all());self.assertTrue(p.probabilidade_fila.between(0,1).all());self.assertTrue(p.probabilidade_recarga.between(0,1).all())
            np.testing.assert_allclose(p.energia_solicitada_prevista_kwh,.25*p.potencia_solicitada_prevista_kw)
    def test_02_insufficient_history(self):
        for c,f,d,r,issue in self.items:
            with self.assertRaises(ValueError):f.predict(r['building'].iloc[-20:],r['ev'].iloc[-20:],issue)
    def test_03_station_isolation(self):
        c,f,d,r,issue=self.items[0];other=self.items[1][3]
        with self.assertRaises(ValueError):f.predict(other['building'],other['ev'],issue)
        self.assertNotEqual(self.items[0][1].folder,self.items[1][1].folder)
    def test_04_timezone(self):
        c,f,d,r,issue=self.items[0]
        with self.assertRaises(ValueError):f.predict(r['building'],r['ev'],issue.tz_localize(None))
        p=f.predict(r['building'],r['ev'],issue);q=f.predict(r['building'],r['ev'],issue.tz_convert('UTC'));pd.testing.assert_frame_equal(p,q)
    def test_05_future_stale_rejected(self):
        c,f,d,r,issue=self.items[0]
        for offset in [-15,15]:
            with self.assertRaises(ValueError):f.predict(r['building'],r['ev'],issue+pd.Timedelta(minutes=offset))
    def test_06_no_future_feature_leak(self):
        for c,f,d,r,issue in self.items:
            pos=5000;x=features(d,c,[pos])[0];changed=d.copy();changed.loc[changed.index[pos+1]:,COLUMNS]=999
            pd.testing.assert_frame_equal(x,features(changed,c,[pos])[0])
            pd.testing.assert_frame_equal(x,features(d.iloc[:pos+1],c,[pos])[0])
    def test_07_unavailable_weather_not_used(self):
        for c,f,d,r,issue in self.items:
            pos=5000;issue=d.index[pos]+pd.Timedelta(minutes=15);x=features(d,c,[pos])[0]
            changed=d.copy();unknown=changed.weather_available_at>issue
            changed.loc[unknown,['temperatura_externa_c','umidade_relativa_pct']]=999
            pd.testing.assert_frame_equal(x,features(changed,c,[pos])[0])
            self.assertTrue((x.weather_age_minutes>=0).all())
    def test_08_bounded_history_exact(self):
        for c,f,d,r,issue in self.items:
            pos=10000;past=d.iloc[pos-MIN_HISTORY+1:pos+1]
            pd.testing.assert_frame_equal(features(d,c,[pos])[0],features(past,c,[len(past)-1])[0])
    def test_09_partition_purge(self):
        for c,f,d,r,issue in self.items:
            for partition in ['train','validation']:
                pos=origins(d,c,partition);o=np.repeat(pos,48);h=np.tile(np.arange(1,49),len(pos))
                end=pd.Timestamp(c['periods'][partition][1],tz=c['timezone'])
                self.assertTrue((d.index[o]+(h+1)*pd.Timedelta(minutes=15)<=end).all())
            self.assertLess(d.index.max(),pd.Timestamp('2025-11-01',tz=c['timezone']))
    def test_10_reload_exact(self):
        for c,f,d,r,issue in self.items:
            q=Forecaster(c['station_id']);pd.testing.assert_frame_equal(f.predict(r['building'],r['ev'],issue),q.predict(r['building'],r['ev'],issue))
    def test_11_physical_input_rejections(self):
        c,f,d,r,issue=self.items[0]
        for col,value in [('potencia_solicitada_kw',1000),('carregadores_ocupados',3),('carros_na_fila',4),('energia_entregue_kwh',999),('carros_chegando',.5)]:
            e=r['ev'].copy();e[col]=e[col].astype(float);e.loc[0,col]=value
            with self.assertRaises(ValueError):f.predict(r['building'],e,issue)
    def test_12_bad_timeline_and_nonfinite(self):
        c,f,d,r,issue=self.items[0]
        for kind in ['duplicate','gap','nan','availability','origin']:
            b=r['building'].copy()
            if kind=='duplicate':b.loc[1,'timestamp']=b.loc[0,'timestamp']
            elif kind=='gap':b=b.iloc[1:]
            elif kind=='nan':b.loc[0,'consumo_predio_kw']=np.nan
            elif kind=='availability':b.loc[0,'available_at']=b.loc[0,'timestamp']
            else:b.loc[0,'origin']='MEASURED'
            with self.assertRaises(ValueError):f.predict(b,r['ev'],issue)
    def test_13_artifact_integrity(self):
        c,f,d,r,issue=self.items[0]
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/c['station_id']/'v1';shutil.copytree(f.folder,target)
            (target/'selection.json').write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError):Forecaster(c['station_id'],model_root=tmp)
        with self.assertRaises(ValueError):Forecaster('../other')
    def test_14_preserve_all_previous_files(self):
        initial=json.loads((REPORT/'preservation_before.json').read_text(encoding='utf-8'))
        for file,expected in initial.items():self.assertEqual(digest(ROOT/file),expected,file)
    def test_15_full_training_seed_reproduction(self):
        for c,f,d,r,issue in self.items:
            x,o,h,t=features(d,c,origins(d,c,'train',4));y=labels(d,o,h)
            xv,ov,hv,tv=features(d,c,origins(d,c,'validation'));yv=labels(d,ov,hv)
            model,constant=fit(x,y[:,0],xv,yv[:,0],'regression',15)
            self.assertIsNone(constant)
            self.assertEqual(model.model_to_string(),(f.folder/'building_15.txt').read_text(encoding='utf-8'))
    def test_16_rare_events_not_zero_selected(self):
        for c,f,d,r,issue in self.items:
            self.assertNotEqual(f.selection['motor2'],'zero')
            self.assertFalse(f.selection['test_used'])
            self.assertFalse(f.freeze['test_accessed'])
    def test_17_no_silent_registry_fallback(self):
        with self.assertRaises(FileNotFoundError):Forecaster('UNKNOWN_STATION')
    def test_18_configurable_limits(self):
        for c,f,d,r,issue in self.items:
            p=bound(np.full((48,7),1000.),c)
            self.assertTrue((p[:,1]<=c['ev_limit_kw']).all());self.assertTrue((p[:,2]<=c['n_evse']).all());self.assertTrue((p[:,4]<=c['queue_limit']).all())
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    write(REPORT/'inference_tests.json',dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),success=result.wasSuccessful()))
    raise SystemExit(not result.wasSuccessful())
