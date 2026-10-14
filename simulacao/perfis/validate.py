"""Independent contract/physics checks, negative cases and deterministic replays."""
import argparse,json,subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
import pandas as pd
from loads import ROOT,INDEX,PROFILES,LOADS,schedules
from ev import simulate
from generate import DATA,REPO,sha,save_json


def annual_contract(a,station):
    idx=pd.DatetimeIndex(pd.to_datetime(a['timestamp'])).tz_convert('America/Sao_Paulo')
    assert idx.equals(INDEX),'annual timeline'
    assert a['station_id'].eq(station).all(),'station isolation'
    assert a['origin'].eq('SIMULATED').all(),'provenance'
    assert pd.DatetimeIndex(pd.to_datetime(a['available_at'],format='mixed')).tz_convert('America/Sao_Paulo').equals(idx+pd.Timedelta(minutes=15)),'availability'
    assert np.isfinite(a.select_dtypes('number').to_numpy()).all(),'nonfinite'

class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames={p:{n:pd.read_csv(DATA/p/(n+'.csv'),keep_default_na=False) for n in ['building','ev','energy','sessions','equipment_events','training_split_plan']} for p in PROFILES}
        cls.manifests={p:json.loads((DATA/p/'manifest.json').read_text(encoding='utf-8')) for p in PROFILES}

    def test_01_annual_timelines_provenance(self):
        for p,c in PROFILES.items():
            for n in ['building','ev','energy','training_split_plan']:
                with self.subTest(profile=p,series=n):annual_contract(self.frames[p][n],c['station_id'])

    def test_02_no_nonfinite_negative_powers(self):
        for p,frames in self.frames.items():
            for name,a in frames.items():
                self.assertTrue(np.isfinite(a.select_dtypes('number').to_numpy()).all())
                for key in a:
                    if key.endswith(('_kw','_kwh')):self.assertTrue((a[key]>=-1e-9).all(),(p,name,key))

    def test_03_building_energy(self):
        for p,f in self.frames.items():
            b=f['building'];np.testing.assert_allclose(b.consumo_predio_kw*.25,b.consumo_predio_kwh,atol=1e-9)
            np.testing.assert_allclose(b[['cooling_kwh','hvac_fan_kwh','heating_kwh','scheduled_kwh']].sum(axis=1),b.consumo_predio_kwh,atol=1e-8)
            self.assertTrue((b.heating_kwh==0).all(),'No electric space heating assumption')

    def test_04_monthly_physical_ranges(self):
        for p,c in PROFILES.items():
            b=self.frames[p]['building'].set_axis(INDEX)
            monthly=b.consumo_predio_kwh.resample('MS').sum()
            self.assertTrue(monthly.between(*c['expected_range']).all(),monthly.to_dict())
            self.assertGreater(b.consumo_predio_kw.min(),0)

    def test_05_ev_power_capacity_and_energy(self):
        for p,c in PROFILES.items():
            a=self.frames[p]['ev'];np.testing.assert_allclose(a.potencia_entregue_kw*.25,a.energia_entregue_kwh,atol=1e-9)
            self.assertTrue((a.potencia_entregue_kw<=a.potencia_solicitada_kw+1e-9).all())
            self.assertLessEqual(a.potencia_solicitada_kw.max(),c['n_evse']*c['evse_kw']+1e-9)
            cols=[]
            for i in range(1,c['n_evse']+1):
                key=f'evse_{i:02d}_kw';cols.append(key)
                for kind in ['available','occupied']:
                    self.assertTrue((a[key]<=c['evse_kw']*a[f'evse_{i:02d}_{kind}_fraction']+1e-8).all())
            np.testing.assert_allclose(a[cols].sum(axis=1),a.potencia_entregue_kw,atol=1e-9)

    def test_06_occupancy(self):
        for p,c in PROFILES.items():
            a=self.frames[p]['ev']
            self.assertTrue(a.carregadores_ocupados.between(0,c['n_evse']).all())
            np.testing.assert_array_equal(a.carregadores_ocupados,a.carros_conectados)
            np.testing.assert_allclose(a.ocupacao_pct,a.carregadores_ocupados*100/c['n_evse'])
            self.assertTrue((a.ocupacao_media_pct<=a.ocupacao_pct+1e-8).all())
            self.assertTrue(a.carros_na_fila.between(0,3).all())
            for key in ['carregadores_ocupados','carros_conectados','carros_chegando','carros_na_fila']:self.assertTrue((a[key]%1==0).all())

    def test_07_sessions_soc_energy_identity(self):
        all_ids=[]
        for p,c in PROFILES.items():
            s=self.frames[p]['sessions'];self.assertTrue(s.station_id.eq(c['station_id']).all());self.assertTrue(s.origin.eq('SIMULATED').all())
            self.assertTrue(s.session_id.is_unique);all_ids.extend(s.session_id)
            self.assertTrue((s.delivered_ac_kwh<=s.requested_ac_kwh+1e-8).all())
            self.assertTrue(s.soc_initial.between(0,1).all());self.assertTrue(s.soc_target.between(0,1).all())
            np.testing.assert_allclose(s.soc_final,s.soc_initial+s.delivered_ac_kwh*.92/s.capacity_kwh,atol=1e-9)
            self.assertTrue((s.soc_final<=s.soc_target+1e-8).all())
            self.assertAlmostEqual(s.delivered_ac_kwh.sum(),self.frames[p]['ev'].energia_entregue_kwh.sum(),places=6)
            np.testing.assert_allclose(s.unmet_ac_kwh,s.requested_ac_kwh-s.delivered_ac_kwh,atol=1e-8)
        self.assertEqual(len(set(all_ids)),len(all_ids))

    def test_08_reconstruct_occupancy_arrivals_queue(self):
        for p,c in PROFILES.items():
            s=self.frames[p]['sessions'];a=self.frames[p]['ev'];size=len(INDEX)*15
            delta=np.zeros((size+1,c['n_evse']),dtype=int);queue=np.zeros(size+1,dtype=int);arr=np.zeros(size,dtype=int)
            for row in s.itertuples():
                arr[row.arrival_minute]+=1
                queue_end=row.start_minute if row.start_minute>=0 else row.end_minute
                queue[row.arrival_minute]+=1;queue[queue_end]-=1
                if row.start_minute<0:continue
                i=int(row.evse_id[-2:])-1
                self.assertGreaterEqual(row.start_minute,row.arrival_minute);self.assertGreater(row.end_minute,row.start_minute)
                delta[row.start_minute,i]+=1;delta[row.end_minute,i]-=1
                self.assertEqual(row.wait_minutes,row.start_minute-row.arrival_minute)
            occ=delta.cumsum(axis=0)[:-1];self.assertTrue(((occ>=0)&(occ<=1)).all(),'EVSE overlap')
            np.testing.assert_array_equal(occ.sum(axis=1).reshape(-1,15).max(axis=1),a.carregadores_ocupados)
            np.testing.assert_allclose(occ.sum(axis=1).reshape(-1,15).mean(axis=1)*100/c['n_evse'],a.ocupacao_media_pct,atol=1e-8)
            np.testing.assert_array_equal(arr.reshape(-1,15).sum(axis=1),a.carros_chegando)
            np.testing.assert_array_equal(queue.cumsum()[:-1].reshape(-1,15).max(axis=1),a.carros_na_fila)

    def test_09_independent_minute_energy_replay(self):
        for p,c in PROFILES.items():
            size=len(INDEX)*15;available=np.ones((size,c['n_evse']),dtype=bool);f=self.frames[p]
            for row in f['equipment_events'].itertuples():available[row.start_minute:row.end_minute,int(row.evse_id[-2:])-1]=False
            power=np.zeros_like(available,dtype=float)
            for row in f['sessions'].itertuples():
                if row.start_minute<0:continue
                i=int(row.evse_id[-2:])-1;energy=0.;outage=0
                for t in range(row.start_minute,row.end_minute):
                    if not available[t,i]:outage+=1;continue
                    soc=row.soc_initial+energy*.92/row.capacity_kwh
                    acceptance=row.vehicle_max_kw*(1 if soc<=.8 else max(.3,1-(soc-.8)*4))
                    delivered=min(c['evse_kw'],acceptance,max(0,row.requested_ac_kwh-energy)*60)
                    energy+=delivered/60;power[t,i]+=delivered
                self.assertAlmostEqual(energy,row.delivered_ac_kwh,places=7)
                self.assertEqual(outage,row.outage_minutes)
            np.testing.assert_allclose(power.sum(axis=1).reshape(-1,15).mean(axis=1),f['ev'].potencia_entregue_kw,atol=1e-7)

    def test_10_solar_equipment_envelopes(self):
        for p,c in PROFILES.items():
            a=self.frames[p]['energy'];e=self.manifests[p]['equipment']
            self.assertTrue(a.pv_generation_ac_kw.between(0,c['inverter_kw']).all())
            self.assertTrue((a.loc[a.ghi_w_m2==0,'pv_generation_ac_kw']==0).all())
            np.testing.assert_allclose(a.pv_generation_ac_kwh,a.pv_generation_ac_kw*.25,atol=1e-9)
            if e['optional_battery_template']:
                opt=e['optional_battery_template'];self.assertLessEqual(opt['discharge_kw']/opt['eta_discharge'],opt['min_voltage_v']*opt['max_current_a']/1000)
            self.assertEqual(len(e['evse']),c['n_evse']);self.assertEqual(len(e['batteries']),2 if c['n_evse']==2 else 0)
            for bat in e['batteries']:
                self.assertLessEqual(bat['charge_kw'],bat['min_voltage_v']*bat['inverter_input_current_a']/1000)
                self.assertLessEqual(bat['discharge_kw']/bat['eta_discharge'],bat['min_voltage_v']*bat['inverter_input_current_a']/1000)
                self.assertTrue(bat['soc_min']<=bat['soc_initial']<=bat['soc_max'])
            self.assertEqual(self.manifests[p]['battery_dispatch'] if 'battery_dispatch' in self.manifests[p] else e['battery_dispatch'],'NOT_SIMULATED')
            self.assertFalse(any('soc' in col.lower() for col in a))
            self.assertTrue((self.frames[p]['building'].consumo_predio_kw+self.frames[p]['ev'].potencia_entregue_kw<=e['grid']['import_kw']).all())

    def test_11_residential_frequency(self):
        f=self.frames['residencial_v1'];arr=f['ev'].set_axis(INDEX).carros_chegando.resample('MS').sum()
        self.assertTrue(arr.isin([3,4]).all());self.assertEqual(len(f['sessions']),42)
        self.assertTrue(f['sessions'].requested_ac_kwh.between(10,25).all())
        self.assertGreater((f['ev'].potencia_entregue_kw==0).mean(),.95)
        self.assertEqual(f['ev'].carros_na_fila.max(),0)

    def test_12_station_continuity_and_variation(self):
        for p,f in self.frames.items():
            b=f['building'].set_axis(INDEX);daily=b.consumo_predio_kwh.resample('D').sum()
            self.assertGreater(daily.std(),.1)
            self.assertGreater(daily.groupby(daily.index.dayofweek).mean().std(),.005)
            self.assertGreater(daily.groupby(daily.index.month).mean().std(),.03)
            self.assertGreater((f['ev'].potencia_entregue_kw==0).sum(),100)
        f=self.frames['posto_24h_v1'];self.assertGreater(f['ev'].carros_na_fila.max(),0)
        self.assertGreater(f['ev'].loc[INDEX.hour<6,'carros_chegando'].sum(),0)
        self.assertGreater(f['sessions'].outage_minutes.sum(),0)

    def test_13_monthly_shards_exact(self):
        for p,c in PROFILES.items():
            for name in ['building','ev','energy']:
                pieces=[]
                for month in range(1,13):
                    path=DATA/p/'monthly'/f'{name}_2025-{month:02d}.csv'
                    a=pd.read_csv(path,keep_default_na=False);self.assertLess(len(a),10000);self.assertLess(path.stat().st_size,8*1024*1024);pieces.append(a)
                pd.testing.assert_frame_equal(pd.concat(pieces,ignore_index=True),self.frames[p][name])

    def test_14_future_horizon_boundaries(self):
        for p,f in self.frames.items():
            a=f['training_split_plan'];issue=pd.to_datetime(a.issue_time);end=pd.to_datetime(a.last_target_end)
            self.assertTrue(((end-issue)==pd.Timedelta(hours=12)).all())
            for name,bound in [('train','2025-09-01'),('validation','2025-11-01'),('test','2026-01-01')]:
                mask=a.partition.eq(name);eligible=a.eligible_horizon48
                self.assertEqual(int((mask&~eligible).sum()),48)
                self.assertTrue((end[mask&eligible]<=pd.Timestamp(bound,tz='America/Sao_Paulo')).all())
            self.assertEqual(int((~a.eligible_motor2_history).sum()),2688)

    def test_15_weather_availability(self):
        for f in self.frames.values():
            for name in ['building','energy']:
                a=f[name];wa=pd.DatetimeIndex(pd.to_datetime(a.weather_available_at)).tz_convert('America/Sao_Paulo')
                self.assertTrue(wa.equals(INDEX.floor('h')+pd.Timedelta(hours=1)))
                self.assertTrue((wa>=pd.DatetimeIndex(pd.to_datetime(a.available_at))).all())

    def test_16_reproducible_schedules_and_ev(self):
        for p in PROFILES:
            load=schedules(p)[list(LOADS[p])]
            saved=pd.read_csv(ROOT/p/'scheduled_loads_kw.csv',index_col=0)
            np.testing.assert_allclose(load.to_numpy(),saved.to_numpy(),atol=1e-9)
            ev,s,fault=simulate(p)
            np.testing.assert_allclose(ev.to_numpy(),self.frames[p]['ev'][ev.columns].to_numpy(),atol=1e-9)
            # Compare every session field, including reasons and timestamps.
            saved=self.frames[p]['sessions']
            for col in s:
                if pd.api.types.is_numeric_dtype(s[col]):np.testing.assert_allclose(s[col],saved[col],atol=1e-9)
                else:self.assertEqual(s[col].tolist(),saved[col].tolist())

    def test_17_hashes_originals_and_artifacts(self):
        baseline=json.loads((ROOT/'baseline.json').read_text())
        for file,digest in baseline['files'].items():self.assertEqual(sha(REPO/file),digest,file)
        for p,manifest in self.manifests.items():
            for file,digest in manifest['outputs_sha256'].items():self.assertEqual(sha(DATA/p/file),digest,file)
            for file,digest in manifest['inputs_sha256'].items():self.assertEqual(sha(REPO/file),digest,file)

    def test_18_negative_contract_cases(self):
        a=self.frames['residencial_v1']['building'];station=PROFILES['residencial_v1']['station_id']
        for change in ['gap','duplicate','nonfinite','station','origin','availability']:
            b=a.copy()
            if change=='gap':b=b.iloc[:-1]
            elif change=='duplicate':b.loc[1,'timestamp']=b.loc[0,'timestamp']
            elif change=='nonfinite':b.loc[0,'consumo_predio_kw']=np.inf
            elif change=='station':b.loc[0,'station_id']='OTHER'
            elif change=='origin':b.loc[0,'origin']='MEASURED'
            else:b.loc[0,'available_at']=b.loc[0,'timestamp']
            with self.subTest(change=change),self.assertRaises(AssertionError):annual_contract(b,station)

    def test_19_energyplus_execution(self):
        for p in PROFILES:
            txt=(DATA/p/'energyplus_errors.txt').read_text()
            self.assertIn('EnergyPlus Completed Successfully',txt)
            self.assertNotIn('** Severe **',txt);self.assertNotIn('** Fatal **',txt)
            self.assertNotIn('out of range',txt)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--energyplus');args=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DatasetTests))
    replay={}
    if args.energyplus and result.wasSuccessful():
        for p in PROFILES:
            with tempfile.TemporaryDirectory(prefix='gie_reproduce_') as tmp:
                run=subprocess.run([args.energyplus,'-w',str(next((ROOT/'weather').glob('*.epw'))),'-d',tmp,str(ROOT/p/'building.idf')],cwd=ROOT/p,capture_output=True,text=True)
                run.check_returncode()
                files=['eplusout.csv','eplusmtr.csv']
                replay[p]={name:sha(Path(tmp)/name)==sha(ROOT/p/'run'/name) for name in files}
                assert all(replay[p].values()),replay
    baseline=json.loads((ROOT/'baseline.json').read_text());frozen=json.loads((REPO/'docs/release/frozen_manifest.json').read_text())
    preserved={k:sha(REPO/k)==v for k,v in baseline['files'].items()}
    frozen_mismatch=[k for k,v in frozen.items() if not (REPO/k).is_file() or sha(REPO/k)!=v]
    summary={}
    for p in PROFILES:
        b=DatasetTests.frames[p]['building'];e=DatasetTests.frames[p]['ev'];s=DatasetTests.frames[p]['sessions'];monthly=b.set_axis(INDEX).consumo_predio_kwh.resample('MS').sum()
        summary[p]=dict(rows=len(b),building_annual_kwh=float(b.consumo_predio_kwh.sum()),monthly_min_kwh=float(monthly.min()),monthly_max_kwh=float(monthly.max()),ev_annual_ac_kwh=float(e.energia_entregue_kwh.sum()),sessions=len(s),mean_ev_occupancy_pct=float(e.ocupacao_media_pct.mean()),unmet_session_energy_kwh=float(s.unmet_ac_kwh.sum()),termination_reasons=s.reason.value_counts().to_dict())
    report=dict(success=result.wasSuccessful() and all(preserved.values()),tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),energyplus_deterministic_replay=replay,original_files_checked=len(preserved),original_changed=[k for k,v in preserved.items() if not v],frozen_manifest_entries=len(frozen),preexisting_frozen_mismatches=frozen_mismatch,summary=summary)
    save_json(DATA/'validation_report.json',report);print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['success'] else 1)

if __name__=='__main__':main()
