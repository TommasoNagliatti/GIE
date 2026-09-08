# Perfis de instalação
Cada instalação futura terá um manifesto versionado com site_id, localização/fuso, identificação dos equipamentos, limites de rede/exportação, solar (orientação/potência), bateria (capacidade/SOC/eficiência) e EVSEs (quantidade/capacidades/mínimos).
Referenciar separadamente modelos e seletores Motor 1 e Motor 2 próprios, hashes, período de treino e versão das features. Não reutilizar modelos de outro prédio sem avaliação.
Motor 3, Load Balancer, runtime e observabilidade devem permanecer reutilizáveis por contratos e configuração compatíveis.
Isto é uma especificação futura, não um carregador genérico de perfis implementado. V1 ainda pressupõe quatro EVSEs de 22 kW, convenções de São Paulo e caminhos/limites dos modelos existentes. Outra instalação exige validar essas restrições e adaptar carregamento de artefatos antes do comissionamento. Nenhum módulo congelado foi reconstruído.
