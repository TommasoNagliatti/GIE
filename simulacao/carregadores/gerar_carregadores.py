"""Simulacao independente de carregadores AC; resolucao interna de 1 minuto.

Le SOMENTE timestamp do CSV do predio. Dependencias: numpy, pandas, Pillow.
python gerar_carregadores.py [--seed 20260905] [--verificar-reprodutibilidade]
"""
from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path
import hashlib
import json
import platform
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
CONFIG = {
    'carregadores': 4, 'potencia_nominal_kw': 22.0,
    'fila_maxima': 3, 'espera_maxima_min': 30,
    'seed': 20260905, 'resolucao_interna_min': 1,
    'chegadas_base_dia': 44.0,
    'max_chegadas_15min': 6,
    'distribuicao_chegadas': 'Binomial(6, 1-exp(-lambda_15min/6))',
    'fatores_seg_dom': [0.90, 1.06, 1.10, 1.04, 0.84, 0.20, 0.075],
    'fatores_mes': [0.94, 0.99, 1.04, 1.02, 0.98, 1.03],
    'prob_dia_movimentado': 0.055, 'prob_dia_vazio': 0.065,
    'sigma_variacao_diaria': 0.20,
    'prob_limite_veiculo_7_4_11_22_kw': [0.30, 0.50, 0.20],
}


def timeline(path):
    # Deliberately do not parse any consumption/weather column.
    source = pd.read_csv(path, usecols=['timestamp'])
    ts = pd.DatetimeIndex(pd.to_datetime(source.timestamp))
    assert len(ts) and ts.is_unique and ts.is_monotonic_increasing
    assert ts.equals(pd.date_range(ts[0], periods=len(ts), freq='15min'))
    assert ts[0] == ts[0].normalize()
    assert ts[-1] + pd.Timedelta(minutes=15) == (ts[-1] + pd.Timedelta(days=1)).normalize()
    assert set(ts.month) == set(range(1, 7)), 'Esta configuracao foi definida para janeiro-junho'
    return ts


def arrivals(ts, rng):
    records, daily = [], []
    # Smooth baseline: broad morning peak plus a smaller afternoon peak.
    h = np.arange(1440) / 60
    for day in pd.date_range(ts[0].normalize(), ts[-1].normalize(), freq='D'):
        dow = day.dayofweek
        month = day.month
        daily_shift = float(np.clip(rng.normal(0, 0.16), -0.4, 0.4))
        month_shift = [0.08, 0.03, -0.04, 0.0, 0.04, -0.03][month-1]
        morning_center = (8.25 if dow < 5 else 9.0) + daily_shift + month_shift
        afternoon_center = 15.1 + daily_shift + month_shift
        # Weights are relative intensity, normalized to expected daily arrivals.
        shape = (0.002 + 1.6*np.exp(-0.5*((h-morning_center)/0.72)**2)
                 + 0.28*np.exp(-0.5*((h-11.5)/1.55)**2)
                 + 0.78*np.exp(-0.5*((h-afternoon_center)/1.05)**2)
                 + 0.16*np.exp(-0.5*((h-18.0)/0.85)**2))
        shape[h < 6] *= 0.08
        shape[h >= 20] *= 0.25
        event_draw = rng.random()
        if event_draw < CONFIG['prob_dia_movimentado']:
            event, event_factor = 'movimentado', float(rng.uniform(1.55, 2.0))
        elif event_draw < CONFIG['prob_dia_movimentado'] + CONFIG['prob_dia_vazio']:
            event, event_factor = 'vazio', float(rng.uniform(0.25, 0.48))
        else:
            event, event_factor = 'normal', 1.0
        sigma = CONFIG['sigma_variacao_diaria']
        factor = float(rng.lognormal(-sigma*sigma/2, sigma))
        expected = (CONFIG['chegadas_base_dia']*CONFIG['fatores_seg_dom'][dow]
                    *CONFIG['fatores_mes'][month-1]*factor*event_factor)
        # Bounded arrival distribution at the source, not clipping generated counts.
        # Smoothly compress high intensities; preserve near-zero arrival intensity.
        intensity = expected*shape/shape.sum()
        limit = CONFIG['max_chegadas_15min']
        probabilities = -np.expm1(-intensity.reshape(-1,15).sum(axis=1)/limit)
        counts_15min = rng.binomial(limit, probabilities)
        counts = np.zeros(1440, dtype=int)
        for block, count in enumerate(counts_15min):
            weights = shape[block*15:(block+1)*15]
            counts[block*15:(block+1)*15] = rng.multinomial(int(count),weights/weights.sum())
        day_offset = int((day-ts[0]).total_seconds()/60)
        daily.append({'data': str(day.date()), 'dia_semana': dow, 'mes': month,
                      'tipo_dia': event, 'fator_diario': factor,
                      'fator_evento': event_factor, 'intensidade_diaria_referencia': expected,
                      'chegadas_esperadas': float((limit*probabilities).sum()),
                      'chegadas_observadas': int(counts.sum()),
                      'deslocamento_pico_min': (daily_shift+month_shift)*60})
        for minute in np.repeat(np.arange(1440), counts):
            hour = minute/60
            # Longer stays are more likely for morning workers.
            probs = [0.17, 0.48, 0.35] if dow < 5 and 7 <= hour < 10 else [0.30, 0.59, 0.11]
            kind = rng.choice(['curta', 'comum', 'longa'], p=probs)
            if kind == 'curta':
                dwell = int(rng.integers(30, 61))
            elif kind == 'comum':
                dwell = int(np.clip(rng.lognormal(np.log(115), 0.32), 61, 180))
            else:
                dwell = int(rng.integers(240, 481))
            battery = float(rng.choice([40, 50, 60, 75, 85], p=[.12, .22, .32, .24, .10]))
            initial_soc = float(rng.uniform(.18, .70))
            target_soc = float(rng.uniform(max(.72, initial_soc+.12), .96))
            requested = (target_soc-initial_soc)*battery
            limit = float(rng.choice([7.4, 11, 22], p=CONFIG['prob_limite_veiculo_7_4_11_22_kw']))
            effective = limit*float(rng.uniform(.95, 1.0))
            arrival = day_offset + int(minute)
            records.append({'arrival': arrival, 'planned_departure': arrival+dwell,
                            'kind': kind, 'dwell': dwell, 'battery': battery,
                            'initial_soc': initial_soc, 'target_soc': target_soc,
                            'requested': requested, 'limit': limit, 'effective': effective,
                            'start': None, 'departure': None, 'charger': None,
                            'energy': 0.0, 'charging_minutes': 0,
                            'status': 'pendente', 'charge_end': None})
    return records, pd.DataFrame(daily)


def simulate(ts, seed):
    rng = np.random.default_rng(seed)
    sessions, daily = arrivals(ts, rng)
    n = len(ts)*15
    occ = np.zeros(n, dtype=np.int16)
    charging = np.zeros(n, dtype=np.int16)
    queue_n = np.zeros(n, dtype=np.int16)
    incoming = np.zeros(n, dtype=np.int16)
    departures = np.zeros(n, dtype=np.int16)
    requested_kw = np.zeros(n)
    delivered_kw = np.zeros(n)
    queue_kw = np.zeros(n)
    stations = [None]*CONFIG['carregadores']
    queue = deque()
    next_arrival = 0
    departures_by_minute = {}

    def connect(i, t):
        charger = stations.index(None)
        s = sessions[i]
        s.update(start=t, charger=charger+1, status='atendida',
                 departure=min(s['planned_departure'], n))
        stations[charger] = i
        departures_by_minute.setdefault(s['departure'], []).append(charger)

    for t in range(n):
        # Half-open intervals: departures free the charger before arrivals at t.
        for charger in departures_by_minute.pop(t, []):
            stations[charger] = None
            departures[t] += 1
        still_waiting = deque()
        while queue:
            i = queue.popleft()
            s = sessions[i]
            if t-s['arrival'] >= CONFIG['espera_maxima_min'] or t >= s['planned_departure']:
                s.update(status='abandono_espera', departure=t)
            else:
                still_waiting.append(i)
        queue = still_waiting
        while queue and None in stations:
            connect(queue.popleft(), t)
        while next_arrival < len(sessions) and sessions[next_arrival]['arrival'] == t:
            i = next_arrival
            next_arrival += 1
            incoming[t] += 1
            if None in stations:
                connect(i, t)
            elif len(queue) < CONFIG['fila_maxima']:
                queue.append(i)
            else:
                sessions[i].update(status='abandono_fila_cheia', departure=t)
        queue_n[t] = len(queue)
        queue_kw[t] = sum(sessions[i]['effective'] for i in queue)
        for i in stations:
            if i is None:
                continue
            s = sessions[i]
            occ[t] += 1
            remaining = max(0.0, s['requested']-s['energy'])
            if remaining <= 1e-9:
                continue
            soc = s['initial_soc'] + s['energy']/s['battery']
            # AC onboarding cap; gradual reduction only above 85% battery SOC.
            taper = float(np.clip(1-(soc-.85)/.15*.45, .55, 1.0))
            demand = s['effective']*taper
            energy = min(demand/60, remaining)
            requested_kw[t] += demand
            delivered_kw[t] += energy*60
            charging[t] += 1
            s['energy'] += energy
            s['charging_minutes'] += 1
            if s['requested']-s['energy'] <= 1e-9:
                s['charge_end'] = t+1
        assert occ[t] <= CONFIG['carregadores'] and len(queue) <= CONFIG['fila_maxima']
        assert delivered_kw[t] <= requested_kw[t]+1e-8 <= CONFIG['carregadores']*CONFIG['potencia_nominal_kw']+1e-8
    for s in sessions:
        if s['status'] == 'pendente':
            s.update(status='censurada_fila', departure=n)
        elif s['start'] is not None and s['planned_departure'] > n:
            s['status'] = 'atendida_censurada_fim_periodo'
        assert s['departure'] is not None

    def stamp(minute):
        return (ts[0]+pd.Timedelta(minutes=int(minute))).strftime('%Y-%m-%d %H:%M:%S') if minute is not None else None

    raw = []
    for i, s in enumerate(sessions, 1):
        raw.append({'session_id': f'EV_{i:06d}', 'data': stamp(s['arrival'])[:10],
                    'hora_chegada': stamp(s['arrival']), 'inicio_conexao': stamp(s['start']),
                    'hora_saida': stamp(s['departure']), 'saida_planejada': stamp(s['planned_departure']),
                    'duracao_min': s['departure']-s['start'] if s['start'] is not None else 0,
                    'permanencia_planejada_min': s['dwell'],
                    'espera_min': (s['start'] if s['start'] is not None else s['departure'])-s['arrival'],
                    'tempo_carregando_min': s['charging_minutes'],
                    'fim_carregamento': stamp(s['charge_end']),
                    'energia_solicitada_kwh': s['requested'], 'energia_entregue_kwh': s['energy'],
                    'energia_nao_atendida_kwh': max(0, s['requested']-s['energy']),
                    'potencia_carregador_kw': 22.0, 'limite_veiculo_kw': s['limit'],
                    'potencia_efetiva_nominal_kw': s['effective'],
                    'charger_id': f'AC_{s["charger"]:02d}' if s['charger'] else None,
                    'tipo_permanencia': s['kind'], 'status': s['status'],
                    'capacidade_bateria_kwh': s['battery'],
                    'soc_chegada_pct': s['initial_soc']*100, 'soc_alvo_pct': s['target_soc']*100})
    raw = pd.DataFrame(raw)
    def agg(v, op='mean'):
        return getattr(v.reshape(-1, 15), op)(axis=1)
    dataset = pd.DataFrame({'timestamp': ts,
        'carros_chegando': agg(incoming, 'sum'),
        'carros_conectados': agg(occ, 'max'),
        'carregadores_ocupados': agg(occ, 'max'),
        'ocupacao_pct': agg(occ, 'max')/CONFIG['carregadores']*100.0,
        'potencia_solicitada_kw': agg(requested_kw),
        'potencia_entregue_kw': agg(delivered_kw),
        'energia_entregue_kwh': agg(delivered_kw)*.25,
        'hora': ts.hour, 'dia_semana': ts.dayofweek,
        'fim_de_semana': (ts.dayofweek >= 5).astype(int), 'mes': ts.month,
        'carros_conectados_medios': agg(occ),
        'ocupacao_media_pct': agg(occ)/CONFIG['carregadores']*100.0,
        'carros_carregando_max': agg(charging, 'max'),
        'carros_carregando_medios': agg(charging),
        'carros_na_fila': agg(queue_n, 'max'),
        'carros_fila_max': agg(queue_n, 'max'),
        'carros_fila_medios': agg(queue_n),
        'potencia_fila_kw': agg(queue_kw),
        'potencia_entregue_max_kw': agg(delivered_kw, 'max'),
        'carros_saindo': agg(departures, 'sum')})
    audit = {'ocupacao_minuto': occ, 'carregando_minuto': charging,
             'potencia_minuto': delivered_kw, 'fila_minuto': queue_n}
    return raw, dataset, daily, audit


def validate(raw, df, ts, audit):
    assert pd.DatetimeIndex(df.timestamp).equals(ts)
    assert len(df) == len(ts) and not df.isna().any().any()
    assert raw.session_id.is_unique
    served = raw[raw.charger_id.notna()].copy()
    abandoned = raw[raw.charger_id.isna()]
    assert np.isfinite(df.select_dtypes('number')).all().all()
    assert df.carros_chegando.sum() == len(raw)
    assert df.carros_chegando.between(0,CONFIG['max_chegadas_15min']).all()
    by_bin = pd.to_datetime(raw.hora_chegada).dt.floor('15min').value_counts().reindex(ts,fill_value=0)
    assert np.array_equal(by_bin.to_numpy(),df.carros_chegando.to_numpy())
    capacity = CONFIG['carregadores']
    power_cap = capacity*CONFIG['potencia_nominal_kw']
    assert df.carregadores_ocupados.between(0, capacity).all()
    assert df.carros_conectados.between(0, capacity).all()
    assert (df.carros_conectados == df.carregadores_ocupados).all()
    assert np.allclose(df.ocupacao_pct,df.carregadores_ocupados/capacity*100)
    assert np.allclose(df.ocupacao_media_pct,df.carros_conectados_medios/capacity*100)
    assert df.carros_na_fila.between(0, CONFIG['fila_maxima']).all()
    assert df.carros_na_fila.equals(df.carros_fila_max)
    assert np.all(audit['ocupacao_minuto'][audit['fila_minuto']>0] == capacity)
    assert df.ocupacao_pct.between(0, 100).all()
    assert df.ocupacao_media_pct.between(0, 100).all()
    assert (df.potencia_entregue_kw <= power_cap+1e-8).all()
    assert (df.potencia_entregue_max_kw <= power_cap+1e-8).all()
    assert (df.potencia_entregue_kw <= df.potencia_solicitada_kw+1e-8).all()
    assert np.allclose(df.energia_entregue_kwh, df.potencia_entregue_kw*.25)
    assert np.isclose(df.energia_entregue_kwh.sum(), raw.energia_entregue_kwh.sum(), atol=1e-6)
    assert (raw.energia_entregue_kwh >= 0).all()
    assert (raw.energia_entregue_kwh <= raw.energia_solicitada_kwh+1e-8).all()
    assert (abandoned.energia_entregue_kwh == 0).all()
    assert served.espera_min.between(0, 29).all()
    assert raw.espera_min.between(0, 30).all()
    assert (served.tempo_carregando_min <= served.duracao_min).all()
    assert (served.energia_entregue_kwh <= served.potencia_efetiva_nominal_kw*served.tempo_carregando_min/60+1e-8).all()
    # Independent reconstruction of occupancy from session endpoints, not interval maxima.
    delta = np.zeros(len(ts)*15+1, dtype=int)
    for _, group in served.groupby('charger_id'):
        group = group.sort_values('inicio_conexao')
        start = pd.to_datetime(group.inicio_conexao)
        end = pd.to_datetime(group.hora_saida)
        assert (start.to_numpy()[1:] >= end.to_numpy()[:-1]).all(), 'Sessoes sobrepostas no carregador'
        assert (end > start).all()
        for begin, finish in zip(start, end):
            delta[int((begin-ts[0]).total_seconds()/60)] += 1
            delta[int((finish-ts[0]).total_seconds()/60)] -= 1
    assert np.array_equal(np.cumsum(delta)[:-1], audit['ocupacao_minuto'])
    assert audit['carregando_minuto'].max() <= capacity
    assert np.all(audit['carregando_minuto'] <= audit['ocupacao_minuto'])
    assert np.isclose(served.duracao_min.sum(), audit['ocupacao_minuto'].sum())
    assert np.isclose(served.tempo_carregando_min.sum(), audit['carregando_minuto'].sum())
    return served


def reports(raw, df, daily, audit, ts):
    served = raw[raw.charger_id.notna()]
    histogram = df.carros_chegando.value_counts().reindex(range(CONFIG['max_chegadas_15min']+1),fill_value=0).sort_index()
    distribution = pd.DataFrame({'intervalos':histogram,'percentual':histogram/len(df)*100})
    distribution.index.name='carros_chegando'
    distribution.to_csv(ROOT/'relatorios'/'distribuicao_chegadas.csv',float_format='%.6f')
    h = df.groupby('hora').agg(chegadas=('carros_chegando','sum'), potencia_media_kw=('potencia_entregue_kw','mean'), ocupacao_media_pct=('ocupacao_media_pct','mean'))
    h['chegadas_medias_por_hora_dia'] = h.chegadas / len(daily)
    h.to_csv(ROOT/'relatorios'/'perfil_horario.csv', float_format='%.6f')
    queue_hourly = df.assign(com_fila=(df.carros_na_fila>0)*100.0).groupby('hora').agg(
        fila_media_temporal=('carros_fila_medios','mean'), fila_maxima=('carros_na_fila','max'),
        intervalos_com_fila_pct=('com_fila','mean'))
    queue_hourly.to_csv(ROOT/'relatorios'/'fila_por_hora.csv',float_format='%.6f')
    daily = daily.merge(raw.groupby('data').size().rename('tentativas'),on='data',how='left')
    daily = daily.merge(served.groupby('data').size().rename('sessoes_atendidas'),on='data',how='left').fillna({'tentativas':0,'sessoes_atendidas':0})
    daily.to_csv(ROOT/'relatorios'/'dias_simulados.csv',index=False,float_format='%.6f')
    groups = []
    for name, weekdays in [('dias_uteis',list(range(5))),('finais_de_semana',[5,6])]:
        sub = df[df.dia_semana.isin(weekdays)]
        ds = daily[daily.dia_semana.isin(weekdays)]
        groups.append({'tipo':name,'dias':len(ds),'chegadas_por_dia':float(ds.tentativas.mean()),
                       'sessoes_atendidas_por_dia':float(ds.sessoes_atendidas.mean()),
                       'ocupacao_media_pct':float(sub.ocupacao_media_pct.mean()),
                       'potencia_media_kw':float(sub.potencia_entregue_kw.mean()),
                       'energia_total_kwh':float(sub.energia_entregue_kwh.sum())})
    pd.DataFrame(groups).to_csv(ROOT/'relatorios'/'comparacao_semanal.csv',index=False,float_format='%.6f')
    df.groupby(['dia_semana','hora']).agg(chegadas=('carros_chegando','sum'),potencia_media_kw=('potencia_entregue_kw','mean'),ocupacao_media_pct=('ocupacao_media_pct','mean')).to_csv(ROOT/'relatorios'/'perfil_segunda_domingo.csv',float_format='%.6f')
    df.groupby('mes').agg(chegadas=('carros_chegando','sum'),energia_kwh=('energia_entregue_kwh','sum'),potencia_media_kw=('potencia_entregue_kw','mean'),ocupacao_media_pct=('ocupacao_media_pct','mean')).to_csv(ROOT/'relatorios'/'resumo_mensal.csv',float_format='%.6f')
    durations = pd.cut(served.duracao_min, bins=[0,29,60,180,239,10000],labels=['1-29 min (espera/corte)','30-60 min','61-180 min','181-239 min','240 min ou mais']).value_counts(sort=False)
    durations.rename('sessoes').to_csv(ROOT/'relatorios'/'distribuicao_duracao.csv')
    weekdays = df[df.fim_de_semana==0].groupby('hora').carros_chegando.sum()/len(daily[daily.dia_semana<5])
    morning = int(weekdays.loc[7:9].idxmax())
    afternoon = int(weekdays.loc[14:16].idxmax())
    stats = {'seed':CONFIG['seed'],'registros_agregados':len(df),'dias':len(daily),
        'max_carros_chegando':int(df.carros_chegando.max()),
        'max_ocupacao_pct':float(df.ocupacao_pct.max()),
        'distribuicao_carros_chegando':distribution.reset_index().to_dict(orient='records'),
        'intervalos_5_ou_6_chegadas_pct':float(df.carros_chegando.isin([5,6]).mean()*100),
        'primeiro_timestamp':str(ts[0]),'ultimo_timestamp':str(ts[-1]),
        'total_tentativas_sessoes':len(raw),'sessoes_atendidas':len(served),
        'sessoes_nao_conectadas':len(raw)-len(served),
        'media_chegadas_por_dia':len(raw)/len(daily),'media_sessoes_atendidas_por_dia':len(served)/len(daily),
        'max_carros_conectados_simultaneos':int(audit['ocupacao_minuto'].max()),
        'max_carros_carregando_simultaneos':int(audit['carregando_minuto'].max()),
        'numero_carregadores':CONFIG['carregadores'],
        'potencia_maxima_fisica_kw':CONFIG['carregadores']*CONFIG['potencia_nominal_kw'],
        'max_carregadores_ocupados':int(df.carregadores_ocupados.max()),
        'ocupacao_media_temporal_pct':float(audit['ocupacao_minuto'].mean()/CONFIG['carregadores']*100),
        'fila_media_temporal_carros':float(audit['fila_minuto'].mean()),
        'fila_maxima_carros':int(audit['fila_minuto'].max()),
        'media_coluna_carros_na_fila':float(df.carros_na_fila.mean()),
        'intervalos_com_fila_pct':float((df.carros_na_fila>0).mean()*100),
        'intervalos_todos_carregadores_ocupados_em_algum_minuto_pct':float((df.carregadores_ocupados==CONFIG['carregadores']).mean()*100),
        'intervalos_todos_carregadores_ocupados_15min_inteiros_pct':float((audit['ocupacao_minuto'].reshape(-1,15).min(axis=1)==CONFIG['carregadores']).mean()*100),
        'fila_por_hora':queue_hourly.reset_index().to_dict(orient='records'),
        'potencia_media_kw':float(df.potencia_entregue_kw.mean()),
        'potencia_max_media_15min_kw':float(df.potencia_entregue_kw.max()),
        'potencia_max_1min_kw':float(audit['potencia_minuto'].max()),
        'energia_total_entregue_kwh':float(raw.energia_entregue_kwh.sum()),
        'energia_total_solicitada_todas_tentativas_kwh':float(raw.energia_solicitada_kwh.sum()),
        'energia_nao_atendida_kwh':float(raw.energia_nao_atendida_kwh.sum()),
        'sessoes_atendidas_com_meta_energia_cumprida':int(np.isclose(served.energia_entregue_kwh,served.energia_solicitada_kwh).sum()),
        'sessoes_que_esperaram_e_conectaram':int((served.espera_min>0).sum()),
        'espera_media_atendidas_min':float(served.espera_min.mean()),
        'status_sessoes':{str(k):int(v) for k,v in raw.status.value_counts().items()},
        'tipos_dia':{str(k):int(v) for k,v in daily.tipo_dia.value_counts().items()},
        'duracao_conexao_min':{k:float(v) for k,v in served.duracao_min.describe(percentiles=[.1,.25,.5,.75,.9,.95]).items()},
        'distribuicao_duracao':{str(k):int(v) for k,v in durations.items()},
        'comparacao_semanal':groups,'chegadas_medias_por_hora_por_dia':{str(k):float(v) for k,v in h.chegadas_medias_por_hora_dia.items()},
        'pico_manha_dias_uteis_hora':morning,'pico_tarde_dias_uteis_hora':afternoon,
        'chegadas_pico_manha_por_dia_util':float(weekdays[morning]),
        'chegadas_pico_tarde_por_dia_util':float(weekdays[afternoon]),
        'timestamps_sha256':hashlib.sha256('\n'.join(ts.strftime('%Y-%m-%d %H:%M:%S')).encode()).hexdigest(),
        'validacoes':'Capacidade, fila, nao sobreposicao, conservacao energia, ocupacao reconstruida, timestamps e ausencia de nulos no agregado: OK',
        'configuracao':CONFIG,'ambiente':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__}}
    assert weekdays[morning] > weekdays.loc[11:13].mean()
    assert weekdays[afternoon] > weekdays.loc[11:13].mean()
    return stats


def chart(path, title, subtitle, series, xticks, xmax, ylabel, ylim=None, panels=None):
    im=Image.new('RGB',(1440,760),'#f5f7fa'); d=ImageDraw.Draw(im)
    def font(size): return ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    d.text((65,30),title,font=font(29),fill='#182b45')
    d.text((65,80),subtitle,font=font(18),fill='#526174')
    left,top,right,bottom=100,160,1370,580
    ymax=ylim or max(1, np.ceil(max(max(y) for _,_,y,_ in series)*1.12))
    if panels:
        for x0,x1 in panels:
            d.rectangle((left+x0/xmax*(right-left),top,left+x1/xmax*(right-left),bottom),fill='#e5eaf1')
    for y in np.linspace(0,ymax,6):
        py=bottom-y/ymax*(bottom-top)
        d.line((left,py,right,py),fill='#d4dce6')
        d.text((left-12,py),f'{y:.1f}',font=font(16),fill='#526174',anchor='rm')
    d.text((left,top-30),ylabel,font=font(17),fill='#526174')
    for x,label in xticks:
        px=left+x/xmax*(right-left)
        d.text((px,bottom+15),label,font=font(16),fill='#526174',anchor='mt')
    for i,(name,x,y,color) in enumerate(series):
        pts=[(left+float(xx)/xmax*(right-left),bottom-float(yy)/ymax*(bottom-top)) for xx,yy in zip(x,y)]
        d.line(pts,fill=color,width=3)
        col,row=i%4,i//4
        lx,ly=90+col*330,650+row*40
        d.line((lx,ly,lx+30,ly),fill=color,width=4)
        d.text((lx+40,ly-11),name,font=font(17),fill='#182b45')
    im.save(path)


def graphs(df):
    folder=ROOT/'graficos'
    ndays=df.groupby('fim_de_semana').timestamp.apply(lambda x:x.dt.normalize().nunique())
    arr=df.groupby(['hora','fim_de_semana']).carros_chegando.sum().unstack()/ndays
    power=df.groupby(['hora','fim_de_semana']).potencia_entregue_kw.mean().unstack()
    ticks=[(i,f'{i:02d}h') for i in range(0,24,2)]
    colors=['#176cc1','#d46a25']
    for filename, table, title, label in [
        ('01_chegadas_por_hora.png',arr,'Chegadas médias por hora','Veículos / hora / dia'),
        ('02_potencia_por_hora.png',power,'Potência média por hora','Potência média (kW)')]:
        chart(folder/filename,title,f'{CONFIG["carregadores"]} carregadores AC de 22 kW · janeiro a junho de 2026 · simulação independente',
              [(name,table.index,table[i],colors[i]) for i,name in enumerate(['Dias úteis','Finais de semana'])],ticks,23,label)
    # First complete Monday-to-Sunday week, selected by calendar, not load.
    start=df.loc[df.dia_semana==0,'timestamp'].iloc[0].normalize()
    week=df[(df.timestamp>=start)&(df.timestamp<start+pd.Timedelta(days=7))]
    x=(week.timestamp-start).dt.total_seconds()/86400
    chart(folder/'03_ocupacao_semana.png','Ocupação dos carregadores | primeira semana completa',
          'Máximo simultâneo em cada intervalo de 15 min · faixa cinza: final de semana',
          [('Conectados',x,week.carros_conectados,'#176cc1'),('Carregando',x,week.carros_carregando_max,'#d46a25'),('Na fila',x,week.carros_na_fila,'#329a69')],
          [(i,(start+pd.Timedelta(days=i)).strftime('%d/%m')) for i in range(8)],7,'Veículos simultâneos',max(CONFIG['carregadores'],CONFIG['fila_maxima']),[(5,7)])
    queue_profile=df.groupby(['hora','fim_de_semana']).carros_fila_medios.mean().unstack()
    chart(folder/'05_fila_por_hora.png','Fila média por hora | cenário oficial de 4 carregadores',
          'Média temporal · fila FIFO de até 3 veículos · espera máxima de 30 minutos',
          [(name,queue_profile.index,queue_profile[i],colors[i]) for i,name in enumerate(['Dias úteis','Finais de semana'])],
          ticks,23,'Veículos na fila (média)')
    profile=df.groupby(['hora','dia_semana']).potencia_entregue_kw.mean().unstack()
    palette=['#176cc1','#329a69','#aa539b','#c99a16','#ce573e','#5664b2','#657a84']
    chart(folder/'04_perfil_segunda_domingo.png','Perfil médio de segunda a domingo',
          'Potência entregue · médias por hora e dia da semana · 181 dias simulados',
          [(name,profile.index,profile[i],palette[i]) for i,name in enumerate(['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo'])],
          ticks,23,'Potência média (kW)')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=CONFIG['seed'])
    parser.add_argument('--timestamps',type=Path,default=PROJECT/'data'/'consumo_predio_6_meses.csv')
    parser.add_argument('--verificar-reprodutibilidade',action='store_true')
    args=parser.parse_args()
    CONFIG['seed']=args.seed
    for name in ['relatorios','graficos']:
        (ROOT/name).mkdir(parents=True,exist_ok=True)
    ts=timeline(args.timestamps)
    raw,df,daily,audit=simulate(ts,args.seed)
    validate(raw,df,ts,audit)
    if args.verificar_reprodutibilidade:
        r2,d2,day2,a2=simulate(ts,args.seed)
        pd.testing.assert_frame_equal(raw,r2)
        pd.testing.assert_frame_equal(df,d2)
        pd.testing.assert_frame_equal(daily,day2)
        for key in audit:
            assert np.array_equal(audit[key],a2[key])
    stats=reports(raw,df,daily,audit,ts)
    stats['reprodutibilidade_duas_execucoes_identicas']=args.verificar_reprodutibilidade
    for name,frame in [('sessoes_carregadores_6_meses.csv',raw),('demanda_carregadores_6_meses.csv',df)]:
        path=PROJECT/'data'/name
        frame.to_csv(path,index=False,float_format='%.8f',date_format='%Y-%m-%d %H:%M:%S')
        stats[name+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    # Read back serialized files and check conservation after decimal rounding.
    saved=pd.read_csv(PROJECT/'data'/'demanda_carregadores_6_meses.csv')
    saved_raw=pd.read_csv(PROJECT/'data'/'sessoes_carregadores_6_meses.csv')
    assert pd.DatetimeIndex(pd.to_datetime(saved.timestamp)).equals(ts)
    assert np.allclose(saved.energia_entregue_kwh,saved.potencia_entregue_kw*.25,atol=1e-8)
    assert abs(saved.energia_entregue_kwh.sum()-saved_raw.energia_entregue_kwh.sum())<1e-5
    graphs(df)
    (ROOT/'relatorios'/'estatisticas.json').write_text(json.dumps(stats,indent=2,ensure_ascii=False),encoding='utf-8')
    lines=['# Estatísticas — carregadores AC', '',
           f'Seed: {args.seed}. Período: {ts[0]} a {ts[-1]}, inícios de intervalos de 15 minutos (UTC−3).', '',
           '| Indicador | Valor |','|---|---:|']
    for label,key in [('Registros agregados','registros_agregados'),('Tentativas de uso','total_tentativas_sessoes'),
                      ('Sessões conectadas','sessoes_atendidas'),('Não conectadas','sessoes_nao_conectadas'),
                      ('Sessões conectadas por dia','media_sessoes_atendidas_por_dia'),
                      ('Máximo simultâneo carregando','max_carros_carregando_simultaneos'),
                      ('Ocupação média temporal (%)','ocupacao_media_temporal_pct'),
                      ('Fila média temporal (veículos)','fila_media_temporal_carros'),
                      ('Fila máxima (veículos)','fila_maxima_carros'),
                      ('Intervalos com fila (%)','intervalos_com_fila_pct'),
                      ('Intervalos com todos ocupados em algum minuto (%)','intervalos_todos_carregadores_ocupados_em_algum_minuto_pct'),
                      ('Intervalos com todos ocupados durante os 15 min (%)','intervalos_todos_carregadores_ocupados_15min_inteiros_pct'),
                      ('Potência média (kW)','potencia_media_kw'),('Máximo médio de 15 min (kW)','potencia_max_media_15min_kw'),
                      ('Máximo de 1 min (kW)','potencia_max_1min_kw'),('Energia entregue (kWh)','energia_total_entregue_kwh')]:
        lines.append(f'| {label} | {stats[key]:.2f} |')
    lines += ['', '## Distribuição de chegadas por intervalo', '', '| Chegadas | Intervalos | Percentual |', '|---|---:|---:|']
    for row in stats['distribuicao_carros_chegando']:
        lines.append(f'| {row["carros_chegando"]} | {row["intervalos"]} | {row["percentual"]:.3f}% |')
    lines += ['', '## Duração de conexão das sessões atendidas', '', '| Faixa | Sessões | Percentual |','|---|---:|---:|']
    for label,count in stats['distribuicao_duracao'].items():
        lines.append(f'| {label} | {count} | {100*count/stats["sessoes_atendidas"]:.2f}% |')
    lines += ['', '## Dias úteis e finais de semana', '', '| Tipo | Chegadas/dia | Conectadas/dia | Ocupação média | Potência média |', '|---|---:|---:|---:|---:|']
    for item in stats['comparacao_semanal']:
        lines.append(f'| {item["tipo"]} | {item["chegadas_por_dia"]:.2f} | {item["sessoes_atendidas_por_dia"]:.2f} | {item["ocupacao_media_pct"]:.2f}% | {item["potencia_media_kw"]:.2f} kW |')
    lines += ['', '## Chegadas por hora', '', '| Hora | Média de chegadas por hora por dia, incluindo dias com zero |', '|---|---:|']
    for hour,value in stats['chegadas_medias_por_hora_por_dia'].items():
        lines.append(f'| {int(hour):02d}h | {value:.3f} |')
    lines += ['', '## Fila por hora', '', '| Hora | Fila média temporal | Fila máxima | Intervalos com fila (%) |', '|---|---:|---:|---:|']
    for row in stats['fila_por_hora']:
        lines.append(f'| {int(row["hora"]):02d}h | {row["fila_media_temporal"]:.3f} | {row["fila_maxima"]} | {row["intervalos_com_fila_pct"]:.2f} |')
    lines += ['', '## Verificações', '', stats['validacoes'], '',
              f'Reprodutibilidade verificada em duas execuções: {args.verificar_reprodutibilidade}.', '',
              'Potências são médias temporais; a ocupação média utiliza minutos conectados, não a média dos máximos de cada intervalo.',
              'Dados sintéticos, sem calibração em sessões reais. Feriados não modelados. Detalhes e dicionário no README.', '']
    (ROOT/'relatorios'/'estatisticas.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(stats,indent=2,ensure_ascii=False))


if __name__ == '__main__':
    main()
