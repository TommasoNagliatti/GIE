# Integração meteorológica e previsão solar V1

Módulo isolado; os Motores 1, 2, 3 e o Load Balancer permanecem inalterados. O mock solar do Motor 3 ainda existe. Nenhuma simulação integrada foi executada nesta etapa.

- Provedor: Forecast API oficial Open-Meteo, `https://api.open-meteo.com/v1/forecast`, sem API key.
- Local: latitude −23.5740619, longitude −46.6231674; America/Sao_Paulo.
- Painéis: inclinação 23°, azimute 180° (norte na convenção Open-Meteo). Configuráveis em WeatherSite.
- Potência instalada 150 kWp, inversor AC 125 kW, performance ratio 0,82. O PR é hipótese configurável do protótipo, não medição da instalação.
- Fórmula: `solar_previsto_kw = min(125, max(0, 150 * GTI / 1000 * 0.82))`. Sem ML ou correção adicional por temperatura nesta V1.

## Tempo e resolução

O provedor solicita `minutely_15` com GTI, shortwave radiation, DNI, temperatura, umidade e nuvens. A Open-Meteo oferece interpolação de dados horários para 15 minutos nesta região; o cliente não interpola novamente.

**A irradiância não instantânea é a média dos 15 minutos anteriores ao timestamp da API.** Assim, para o intervalo [08:00,08:15) do Motor 3, o adaptador meteorológico busca a irradiância da API identificada às 08:15 e a registra no início 08:00. Temperatura, umidade e nuvens usam os valores instantâneos identificados às 08:00. Isso é conversão explícita de fim para início de intervalo, não deslocamento arbitrário ou interpolação. Os testes usam valores distintos em cada horário para detectar erros de uma posição.

São requisitados 97 pontos, do início ao início+24h inclusive, permitindo normalizar 96 intervalos e manter margem para reutilização do cache nos ciclos seguintes. A saída pública é sempre **48 intervalos**, começando exatamente no decision_time recebido, até +11h45. Unix timestamps são convertidos de UTC para America/Sao_Paulo; timezone, offset, unidades, duplicatas, lacunas e campos nulos são validados. Uma falha de dados é tratada como falha do provedor.

Decision_time sem fuso é interpretado explicitamente como horário local de São Paulo. Valores com fuso são convertidos preservando o instante. O início deve cair em um quarto de hora exato; a função não arredonda. Somente o demonstrador escolhe o próximo quarto de hora após a chamada.

## Disponibilidade

Uma tentativa de rede, com timeout de 10 segundos, é seguida por cache se houver falha. O cache é uma resposta normalizada válida, persistida atomicamente, identificada por provedor/local/orientação e reutilizada somente se tiver no máximo **3 horas** desde a consulta e cobrir todos os 48 intervalos. O limite de idade é configurável e não representa garantia de idade da rodada meteorológica do servidor.

Sem cache elegível, a geração prevista é zero nos 48 intervalos. As variáveis meteorológicas ficam null/desconhecidas, em vez de irradiância fabricada. Respostas inválidas ou fallback nunca substituem o último cache válido. Falha na escrita de cache não descarta dados novos válidos.

Metadados: `source=open_meteo, stale=false` na resposta nova; `source=cache, stale=true` ao reutilizar após falha; `source=fallback, stale=true` quando não há previsão meteorológica utilizável. Os motivos ficam em diagnostics. O serviço preserva timestamps inclusive em fallback. Erros de configuração ou horizonte inválido são rejeitados explicitamente, pois não são falhas meteorológicas.

**A geração solar atual do passo zero continua vindo da telemetria real do inversor.** O módulo retorna previsões; não sobrescreve Measurements nem comandos atuais. O futuro chamador deverá passar a telemetria de execução normalmente ao Motor 3.

## Uso e substituição do provedor

```python
from integracoes.weather.open_meteo import OpenMeteoProvider
from integracoes.weather.cache import ForecastCache
from integracoes.solar.forecast import SolarForecaster
from integracoes.solar.adapter import to_motor3

servico = SolarForecaster(OpenMeteoProvider(), ForecastCache('outputs/integracoes/solar_v1/.cache/last_valid_weather.json'))
previsao = servico.forecast(timestamps_motor3[0])
solar = to_motor3(previsao, timestamps_motor3)
# solar: Series com 48 valores e índice idêntico ao horizonte do Motor 3.
# solar.to_numpy(): solar_previsto_kw[48].
```

O adaptador opcional valida igualdade integral dos timestamps e retorna índice local sem fuso, conforme o contrato existente do Motor 3. Não altera o relógio; remove apenas a informação de fuso após conferir São Paulo. Não aceita troca de horizonte silenciosa. O limite de 125 kW também é validado nesse adaptador para compatibilidade com o Motor 3 congelado.

Para trocar o provedor, implemente WeatherProvider.fetch e devolva WeatherBatch validado: seis colunas padronizadas, índice com fuso São Paulo e início do intervalo, irradiância média do intervalo e instante de consulta com fuso. Injete o novo provedor no SolarForecaster. O restante da conversão solar e o Motor 3 não conhecem o formato da Open-Meteo.

Dependências: pandas/numpy já presentes; rede, cache e testes usam biblioteca padrão. Matplotlib existente é usado apenas no demonstrador. Execute a partir da raiz GIE com `src` no PYTHONPATH para uso interativo.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/integracoes -v
.\.venv\Scripts\python.exe -B src/integracoes/solar/demo.py
```

O demonstrador grava tabela CSV de 48 registros, JSON completo normalizado, resposta bruta, URL/parâmetros, dois gráficos, exemplos de cache/fallback, testes e resumo em outputs/integracoes/solar_v1. As falhas dos exemplos são injetadas deliberadamente depois da consulta real; não são novos dados meteorológicos.

## Fonte e licença

Dados meteorológicos: Open-Meteo.com, CC BY 4.0. A API gratuita destina-se a uso **não comercial**. A condição de protótipo por si só não autoriza uso comercial; produção comercial deverá rever o plano/provedor.

- Documentação e semântica temporal: https://open-meteo.com/en/docs (seção 15-Minutely Parameter Definition).
- Condições de uso: https://open-meteo.com/en/terms.

Esta é uma estimativa meteorológica de geração potencial, não medição nem previsão validada contra um inversor físico.
