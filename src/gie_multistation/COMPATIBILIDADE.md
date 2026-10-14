# Compatibilidade energética e isolamento — Fases 3 e 4

Fase 5 adiciona estações dinâmicas BASELINE usando o mesmo Energy V3, sem CSV/modelo personalizado. Nenhum perfil existente é migrado. Sem current confiável, a nova estação fica degradada e não avança energia simulada. Contratos e limitações em `../gie_provisioning/README.md`.

| Perfil | Modelos | MPC / Load Balancer | Operação disponível |
|---|---|---|---|
| Commercial_HighAutonomy_V2 | Híbrido prédio + seletor EV V2 congelados, instâncias próprias | Política V2 e allocator originais; 4×22kW | Ciclo demonstrativo com modelos reais, NORMAL/SIMULATION, 16 cenas e MANUAL_DEMO |
| DEMO_POSTO_24H_001 | Fase 2: prédio LightGBM15, EV LightGBM, Q90 frequência | Energy V3 / allocator novos: 2×22kW e duas baterias individuais | Previsões + MPC simulado e SOC persistente |
| DEMO_CASA_001 | Fase 2: prédio LightGBM31; EV/Q90 somente diagnóstico | Energy V3 / allocator novos: 1×7kW e ausência de bateria inicial | Demanda atual independente + MPC simulado |

Não foram alteradas equações, objetivos, restrições, SOC ou capacidades do MPC comercial congelado. A Fase 4 cria matemática independente e versionada em gie_energy_v3. Não foram criados carregadores/baterias fictícios nem agregado o banco duplo do posto para contornar a incompatibilidade. Perfis originais e manifestos físicos novos são lidos e verificados por hash.

No comercial, building/EV vêm dos datasets sintéticos originais e a previsão é executada pelos motores congelados. Solar é uma previsão constante explicitamente demonstrativa, com zero na fixture padrão; SOC é entrada independente de 50%, não uma trajetória física contínua. A política e o Load Balancer executam de verdade, porém nenhuma saída chega a equipamento. As cenas permanecem byte a byte preservadas e os 16 resultados foram comparados integralmente.

Nos novos perfis, EnergyEngine utiliza MPC e allocator próprios. Estados individuais de bateria evoluem pelo primeiro passo e persistem entre reinícios. Nenhum setpoint é enviado a hardware. Detalhes, limites e reprodução em `../gie_energy_v3/README.md`; evidências em `reports/energy_v3/v1`. Registro mpc_compatible/load_balancer_compatible agora indica compatibilidade com Energy V3, jamais com o MPC comercial congelado.

## Residência e baixa qualidade EV
Recall da Fase 2 permanece **6,778%**, com apenas sete sessões no teste. Previsões aprendidas são mantidas sem recalibração ou métricas inventadas. A demanda atual simulada por EVSE é validada e somada separadamente, inclusive quando a previsão de chegada é baixa. Um envelope conservador diagnóstico usa max(demanda atual, limite alto previsto) em cada passo; ele é limitado implicitamente pelos dois termos ao teto de 7kW, não é Q90 calibrado, promessa de atendimento ou comando. Não se estima duração da conexão nem se declara que o carro ficará conectado 12h. O atendimento matemático simulado está disponível com Energy V3; atendimento físico continua indisponível.

## Isolamento operacional

Cada subprocesso tem um GIEControl, objetos LightGBM, DataFrames, último issue_time, histórico limitado a 100 ciclos, cache, BalancerState, mensagens e diretório próprios. Processos não herdam instâncias: usam spawn. A comunicação é Pipe privado e serializada por lock da estação; locks de estações diferentes não bloqueiam ciclos entre si. Não há estado de modelo operacional no FastAPI.

Timeout encerra somente o worker alvo e exige reinício. Perda/queda de processo retorna 503; nenhuma resposta em cache do processo morto é promovida a estado atual. Não há reinício automático ilimitado. Reinício gera UUID novo, NORMAL parado sem resultado/histórico operacional, presentation pausada. Eventos antigos continuam em journal por estação. Snapshot é escrito por substituição atômica para auditoria, nunca restaurado como comando. Arquivo parcial de journal após queda pode exigir inspeção, pois não é um banco transacional.

Trava exclusiva de diretório impede dois gerenciadores sobre os mesmos registros. Estados e modos independentes, concorrência simultânea entre três estações, serialização dentro da mesma estação, encerramento, queda externa, timeout e reinício completo foram testados. Processos compartilham o mesmo usuário do SO e filesystem: não é isolamento de segurança contra código hostil de tenants nem quota rígida de recursos.

## Auditoria lida

Referência: C:/goodwill_ai/EMPS_GITHUB/docs/GIE_V2_HANDOFF.md e gie/GIE/service/api.py, além do service/api.py local do ecossistema anterior. O contrato de serviço anterior é singleton com token/estação; esta extensão é nova e versionada, não substitui silenciosamente endpoints existentes. Consultados SITE_PROFILES, MAQUETTE_INTERFACE, REPRODUCIBILITY, GIEControl/runtime, MPC V1/V2, Load Balancer, perfis e datasets sintéticos e documentação/manifestos da Fase 2.

Diferença temporal: motores comerciais exigem timestamps locais ingênuos; conversão explícita America/Sao_Paulo -> local naive ocorre apenas no adaptador comercial. Novos motores mantêm offset, availability e schema da Fase 2. O serviço rejeita timestamps ingênuos e desalinhados. Nenhum dataset é alterado para simular compatibilidade.
