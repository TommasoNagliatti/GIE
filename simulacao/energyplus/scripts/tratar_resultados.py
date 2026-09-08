"""Valida resultados EnergyPlus e gera dataset, estatisticas e graficos.

Uso: python tratar_resultados.py [--resultados PASTA]
timestamp = inicio do intervalo [t,t+15min), hora local UTC-3.
Nao imputa, suaviza, recorta picos ou adiciona ruido ao consumo.
Dependencias: pandas, numpy, Pillow.
"""
from pathlib import Path
import argparse
import json
import re
import hashlib
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--resultados', type=Path, default=ROOT/'resultados'/'seis_meses')
args = parser.parse_args()
out = ROOT/'relatorios'
out.mkdir(exist_ok=True)
error = (args.resultados/'eplusout.err').read_text()
assert 'EnergyPlus Completed Successfully' in error
assert not re.search(r'\*\*\s+(Severe|Fatal)\s+\*\*', error), 'Corrigir erros do EnergyPlus primeiro'
a = pd.read_csv(args.resultados/'eplusout.csv')
b = pd.read_csv(args.resultados/'eplusmtr.csv')
assert a['Date/Time'].equals(b['Date/Time']), 'Timestamps dos medidores divergem'

def parse_end(value):
    match = re.fullmatch(r'\s*(\d+)/(\d+)\s+(\d+):(\d+):(\d+)\s*', value)
    assert match, value
    month, day, hour, minute, second = map(int, match.groups())
    return pd.Timestamp(2026,month,day)+pd.Timedelta(hours=hour,minutes=minute,seconds=second)

ts = pd.DatetimeIndex([parse_end(v)-pd.Timedelta(minutes=15) for v in a['Date/Time']])
expected = pd.date_range('2026-01-01','2026-07-01',freq='15min',inclusive='left')
assert ts.equals(expected), 'Lacunas, duplicatas ou periodo incorreto'
def col(fragment):
    found = [c for c in a if fragment in c]
    assert len(found)==1, found
    return a[found[0]]

df = pd.DataFrame({'timestamp':ts,
    'consumo_predio_kw': col('Facility Total Electricity Demand Rate [W]')/1000,
    'consumo_predio_kwh': b['Electricity:Facility [J](TimeStep)']/3_600_000,
    'temperatura_externa_c':col('Site Outdoor Air Drybulb Temperature [C]'),
    'umidade_relativa_pct':col('Site Outdoor Air Relative Humidity [%]')})
assert np.isfinite(df.select_dtypes('number')).all().all()
assert (df.consumo_predio_kw>=0).all()
assert df.umidade_relativa_pct.between(0,100).all()
assert df.temperatura_externa_c.between(-10,50).all()
assert np.allclose(df.consumo_predio_kwh,df.consumo_predio_kw*0.25,rtol=1e-7,atol=1e-7)
df['hora']=ts.hour
df['dia_semana']=ts.dayofweek
df['fim_de_semana']=(ts.dayofweek>=5).astype(int)
df['mes']=ts.month
enduse={c.split(' [')[0]:float(b[c].sum()/3_600_000) for c in b if c!='Date/Time'}
assert np.isclose(sum(v for k,v in enduse.items() if k!='Electricity:Facility'),enduse['Electricity:Facility'])
active=((df.dia_semana<5)&df.hora.between(8,21))|((df.dia_semana==5)&df.hora.between(9,15))
zt=a.filter(like='Zone Mean Air Temperature').to_numpy()
cool=a.filter(like='Zone Thermostat Cooling Setpoint Temperature').to_numpy()
heat=a.filter(like='Zone Thermostat Heating Setpoint Temperature').to_numpy()
comfort=((zt>cool+1)|(zt<heat-1))[active]
cool_kw=b['Cooling:Electricity [J](TimeStep)']/900_000
# Compare residuals after controlling calendar slot; this is diagnostic, not causal proof.
keys=[df.dia_semana,ts.hour,ts.minute]
temp_res=df.temperatura_externa_c-df.temperatura_externa_c.groupby(keys).transform('mean')
cool_res=cool_kw-cool_kw.groupby(keys).transform('mean')
stats={
 'registros':len(df),'inicio':str(ts.min()),'ultimo_inicio_intervalo':str(ts.max()),
 'fim_exclusivo':'2026-07-01 00:00:00','intervalo_minutos':15,'timezone':'UTC-03:00',
 'consumo_medio_kw':float(df.consumo_predio_kw.mean()),
 'consumo_maximo_kw':float(df.consumo_predio_kw.max()),
 'consumo_minimo_kw':float(df.consumo_predio_kw.min()),
 'energia_total_kwh':float(df.consumo_predio_kwh.sum()),
 'energia_semestral_kwh_m2':float(df.consumo_predio_kwh.sum()/8000),
 'media_dias_uteis_kw':float(df.loc[df.fim_de_semana==0,'consumo_predio_kw'].mean()),
 'media_fim_de_semana_kw':float(df.loc[df.fim_de_semana==1,'consumo_predio_kw'].mean()),
 'temperatura_min_c':float(df.temperatura_externa_c.min()),'temperatura_max_c':float(df.temperatura_externa_c.max()),
 'fracao_zona_intervalos_fora_setpoint_1c_apos_primeira_hora':float(comfort.mean()),
 'correlacao_temperatura_resfriamento_residual_calendario':float(temp_res[active].corr(cool_res[active])),
 'energia_por_uso_kwh':enduse,
 'energyplus_resumo':error.strip().splitlines()[-1].strip(),
 'epw_sha256':hashlib.sha256(next((ROOT/'clima').glob('*.epw')).read_bytes()).hexdigest(),
 'idf_sha256':hashlib.sha256((ROOT/'modelo'/'predio_sp.idf').read_bytes()).hexdigest(),
 'validacoes':'Sequencia completa, sem nulos/duplicatas, energia-potencia e soma de usos finais conferidas.'}
dest=ROOT.parents[1]/'data'/'consumo_predio_6_meses.csv'
dest.parent.mkdir(exist_ok=True)
df.to_csv(dest,index=False,float_format='%.6f',date_format='%Y-%m-%d %H:%M:%S')
(out/'estatisticas.json').write_text(json.dumps(stats,indent=2,ensure_ascii=False),encoding='utf-8')
df.groupby('mes').agg(energia_kwh=('consumo_predio_kwh','sum'),media_kw=('consumo_predio_kw','mean'),pico_kw=('consumo_predio_kw','max')).to_csv(out/'resumo_mensal.csv')
profile=df.groupby(['fim_de_semana','hora']).consumo_predio_kw.mean().unstack(0)
profile.to_csv(out/'perfil_horario.csv')

def font(size):
    return ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
def plot(filename,title,subtitle,series,xticks,xmax):
    im=Image.new('RGB',(1400,680),'#f5f7fa'); d=ImageDraw.Draw(im)
    left,top,right,bottom=100,150,1350,555
    d.text((70,30),title,font=font(30),fill='#182b45')
    d.text((70,80),subtitle,font=font(19),fill='#526174')
    ymax=np.ceil(max(max(y) for _,_,y,_ in series)/50)*50
    for y in np.linspace(0,ymax,6):
        py=bottom-y/ymax*(bottom-top)
        d.line((left,py,right,py),fill='#d9e0e9',width=1)
        d.text((left-15,py),f'{y:.0f}',font=font(17),fill='#526174',anchor='rm')
    d.text((left,top-30),'Potência média no intervalo (kW)',font=font(17),fill='#526174')
    for x,label in xticks:
        px=left+x/xmax*(right-left)
        d.text((px,bottom+15),label,font=font(17),fill='#526174',anchor='mt')
    for i,(name,x,y,color) in enumerate(series):
        pts=[(left+float(xx)/xmax*(right-left),bottom-float(yy)/ymax*(bottom-top)) for xx,yy in zip(x,y)]
        d.line(pts,fill=color,width=3)
        lx=100+i*440
        d.line((lx,635,lx+35,635),fill=color,width=4)
        d.text((lx+45,623),name,font=font(18),fill='#182b45')
    im.save(out/filename)

first=df.iloc[:7*96]
plot('primeiros_dias.png','Consumo do prédio | primeiros sete dias','São Paulo · 8.000 m² · janeiro de 2026 · clima típico · sem carregadores VE',
 [('Consumo total do prédio',np.arange(len(first))/96,first.consumo_predio_kw,'#176cc1')],
 [(i,f'{i+1:02d}/01') for i in range(8)],7)
plot('perfil_medio_hora.png','Perfil médio de consumo por hora','Janeiro a junho de 2026 · hora local UTC−3 · média dos intervalos em cada hora',
 [('Dias úteis',profile.index,profile[0],'#176cc1'),('Finais de semana',profile.index,profile[1],'#db7331')],
 [(i,f'{i:02d}h') for i in range(0,24,2)],23)
print(json.dumps(stats,indent=2,ensure_ascii=False))
print(f'CSV: {dest}')
