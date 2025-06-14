// Controles Dinâmicos
function updateBgPlotControls() {
    const plotType = document.getElementById('plotBackgroundType').value;
    const dynamicElements = {
        '/plot_one_category': ['bgCategoryField'],
        '/plot_with_limits': ['bgCategoryField', 'bgReferenceLineField'],
        '/plot_start_finish': ['bgCategoryField', 'bgStartFinishField', 'bgDepartureField'],
        '/plot_with_stopped': ['bgCategoryField', 'bgStopThresholdField', 'bgMinDurationField', 'bgNoiseToleranceField'],
        '/plot_with_stop_rec': ['bgCategoryField', 'bgStopThresholdField', 'bgMinDurationField', 'bgNoiseToleranceField',
                'bgRectMinXField', 'bgRectMaxXField', 'bgRectMinYField', 'bgRectMaxYField'],
        '/plot_monitored_area': ['bgCategoryField', 'bgRectMinXField', 'bgRectMaxXField', 'bgRectMinYField', 
                'bgRectMaxYField']
    };

    // Esconde todos os campos
    Object.values(dynamicElements).flat().forEach(id => {
        const el = document.getElementById(id);
        if(el) {
            el.style.display = 'none';
            el.querySelector('input').required = false;
        }
    });

    // Exibe campos do tipo selecionado
    if(dynamicElements[plotType]) {
        dynamicElements[plotType].forEach(id => {
            const el = document.getElementById(id);
            if(el) {
                el.style.display = 'block';
                // Aplica required apenas para campos específicos
                el.querySelector('input').required = id === 'bgCategoryField' ? false : true;
            }
        });
    }
}

// Converte campos de tempo para o padrão
function convertTimeToFloat(timeStr) {
    if (!timeStr) throw new Error("Horário vazio!");
    const [hours, minutes] = timeStr.split(':').map(Number);
    if (isNaN(hours) || hours < 0 || hours >= 24 || isNaN(minutes) || minutes < 0 || minutes >= 60) {
        throw new Error(`Horário inválido: ${timeStr}`);
    }
    return hours + (minutes / 60);
}

// Modifica o nome dos campos (Field)
function formatFieldName(id) {
    return id.replace('bg', '')
                .replace(/([a-z])([A-Z])/g, '$1_$2')
                .toLowerCase();
}

// Apresenta as métricas contida no payload do sumário
function buildMetricsHTML(summary) {
    let html = '<div class="metric-group"><h5>Resumo Geral</h5><ul class="list-unstyled">';

    if (summary) {
        for (const [key, value] of Object.entries(summary)) {
            let displayValue = value;
            
            if (typeof value === 'object') { 
                // Formatar categorias e suas contagens
                displayValue = '<ul>';
                for (const [cat, count] of Object.entries(value)) {
                    displayValue += `<li>Categoria ${parseInt(cat)}: ${count} trajetórias</li>`;
                }
                displayValue += '</ul>';
            } else if (typeof value === 'number') {
                displayValue = value.toFixed(2);
            }
            
            let label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            html += `<li><strong>${label}:</strong> ${displayValue}</li>`;
        }
    } else {
        html += '<li>Nenhuma métrica disponível.</li>';
    }
    html += '</ul></div>';

    return html;
}

/**
 * Exibe um alerta do Bootstrap dinâmico e autodestrutivo na interface.
 * @param {string} text - O texto da mensagem.
 * @param {'success'|'danger'|'info'|'warning'} type - O tipo de alerta do Bootstrap.
 * @param {number} duration - Duração em milissegundos para o alerta desaparecer. 0 para não desaparecer.
 */
function displayMessage(text, type = 'info', duration = 5000) {
    const container = document.getElementById('message-display-container');
    if (!container) return;

    // Mapeia o tipo de mensagem para uma classe do Bootstrap e um ícone
    const alertConfig = {
        success: { class: 'alert-success', icon: '✔' },
        danger:  { class: 'alert-danger',  icon: '✖' },
        info:    { class: 'alert-info',    icon: 'ⓘ' },
        warning: { class: 'alert-warning', icon: '⚠' }
    };
    
    // Pega a configuração correta ou usa 'info' como padrão
    const config = alertConfig[type] || alertConfig.info;

    // Cria o elemento do alerta com as classes do Bootstrap
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert ${config.class} alert-dismissible fade show`;
    alertDiv.setAttribute('role', 'alert');

    // Monta o conteúdo do alerta (ícone + texto + botão de fechar)
    alertDiv.innerHTML = `
        <span class="alert-icon">${config.icon}</span>
        <div>${text}</div>
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    // Limpa mensagens anteriores e adiciona a nova
    container.innerHTML = ''; 
    container.appendChild(alertDiv);

    // Lógica para fazer o alerta desaparecer sozinho
    if (duration > 0) {
        setTimeout(() => {
            // Adiciona a classe para iniciar a animação de fade-out
            alertDiv.classList.add('fade-out');
            
            // Remove o elemento do DOM após a animação terminar
            alertDiv.addEventListener('transitionend', () => {
                alertDiv.remove();
            });
        }, duration);
    }
}

/**
 * Função principal que lida com a submissão do formulário, validação e chamada da API com timeout.
 * @param {boolean} isMetricsOnly - Se true, chama a rota de métricas; senão, chama a rota de plot.
 */

async function handleRequest(isMetricsOnly = false) {
    const buttonId = isMetricsOnly ? 'metricsOnlyButton' : 'plotButton';
    const button = document.getElementById(buttonId);
    const spinner = button.querySelector('.spinner-border');
    const buttonText = button.querySelector('.upload-text');
    const originalButtonText = buttonText.textContent;
    const imgElement = document.getElementById('bgPlotImage');
    const metricsContainer = document.getElementById('metricsContainer');
    
    // ATUALIZA A UI PARA O ESTADO DE CARREGAMENTO
    button.disabled = true;
    spinner.style.display = 'inline-block';
    buttonText.textContent = isMetricsOnly ? 'Processando...' : 'Processando...';
    imgElement.style.display = 'none';
    metricsContainer.style.display = 'none';
    displayMessage('Carregando, por favor aguarde...', 'info');

    // AbortController para o timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        controller.abort();
    }, 120000); // Timeout de 120 segundos

    try {
        // COLETA E VALIDAÇÃO DOS DADOS DO FORMULÁRIO
        const formData = new FormData();
        const plotType = document.getElementById('plotBackgroundType').value;

        // Campos principais
        const mainFields = [
            'bgCamera', 'bgSelectedDate',
            'bgStartTime', 'bgEndTime',
            'bgXsize', 'bgYsize',
            'bgXlim1', 'bgXlim2', 'bgYlim1', 'bgYlim2'
        ];

        mainFields.forEach(id => {
            const element = document.getElementById(id);
            if (!element) return;
            
            const fieldName = formatFieldName(id);
            let value = element.value;
        
            // Conversão de tipos específicos
            if (id.endsWith('Time')) {
                value = convertTimeToFloat(value);
            }
            else if (id.match(/(lim|size)/i)) {
                value = parseFloat(value);
                if (isNaN(value)) {
                    throw new Error(`Valor inválido para ${fieldName}`);
                } 
            }
        
            formData.append(fieldName, value);
        });

        // Campos dinâmicos condicionais
        const conditionalFields = {
            '/plot_one_category': ['bgCategory'],
            '/plot_with_limits': ['bgCategory', 'bgReferenceLine'],
            '/plot_start_finish': ['bgCategory','bgDepartureLine', 'bgFinishLine'],
            '/plot_with_stopped': ['bgCategory', 'bgStopThreshold', 'bgMinDuration', 'bgNoiseTolerance'],
            '/plot_with_stop_rec': ['bgCategory', 'bgStopThreshold', 'bgMinDuration', 'bgNoiseTolerance',
                'bgRectMinX', 'bgRectMaxX', 'bgRectMinY', 'bgRectMaxY'],
            '/plot_monitored_area': ['bgCategory', 'bgRectMinX', 'bgRectMaxX', 'bgRectMinY', 'bgRectMaxY']
        };

        (conditionalFields[plotType] || []).forEach(id => {
            const element = document.getElementById(id);
            if (!element) {
                console.error(`Elemento não encontrado: ${id}`);
                return;
            }
            else if (element && element.value) {
                formData.append(formatFieldName(id), element.value);
            }
        });

        // Validações específicas
        switch(plotType) {
            case '/plot_one_category':
                if (!formData.get('category')) {
                    throw new Error('Selecione uma categoria!');
                }
                break;

            case '/plot_with_limits':
                if (!formData.get('reference_line')) {
                    throw new Error('Linha de referência obrigatória!');
                }
                else if (!formData.get('category')) {
                    throw new Error('Selecione uma categoria!');
                }
                break;

            case '/plot_start_finish':
                if (!formData.get('departure_line') || !formData.get('finish_line')) {
                    throw new Error('Linhas de partida/chegada obrigatórias!');
                }
                else if (!formData.get('category')) {
                    throw new Error('Selecione uma categoria!');
                }
                break;
                
            case '/plot_with_stopped':
                if (!formData.get('stop_threshold')) {
                    throw new Error('Distância Limite obrigatória!');
                }
                else if (!formData.get('min_duration')) {
                    throw new Error('Tempo Limite obrigatório!');
                }
                else if (!formData.get('noise_tolerance')) {
                    throw new Error('Tolerância obrigatória!');
                }
                else if (!formData.get('category')) {
                    throw new Error('Selecione uma categoria!');
                }
                break;

            case '/plot_with_stop_rec':
                if (!formData.get('stop_threshold')) {
                    throw new Error('Distância Limite obrigatória!');
                }
                else if (!formData.get('min_duration')) {
                    throw new Error('Tempo Limite obrigatório!');
                }
                else if (!formData.get('noise_tolerance')) {
                    throw new Error('Tolerância obrigatória!');
                }
                else if (!formData.get('rect_min_x') || !formData.get('rect_max_x') || !formData.get('rect_min_y') || !formData.get('rect_max_y')) {
                    throw new Error('Parâmetros de Área obrigatórios!');
                }
                else if (!formData.get('category')) {
                    throw new Error('Selecione uma categoria!');
                }
                break;

            case '/plot_monitored_area':
                if (!formData.get('rect_min_x') || !formData.get('rect_max_x') || !formData.get('rect_min_y') || !formData.get('rect_max_y')) {
                    throw new Error('Parâmetros de Área obrigatórios!');
                }
                else if (!formData.get('category')) {
                    throw new Error('Selecione uma categoria!');
                }
                break;
        }

         // REQUISIÇÃO FETCH COM TIMEOUT
        const response = await fetch(plotType, {
            method: 'POST',
            body: formData,
            signal: controller.signal // Passa o sinal do AbortController
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            const errData = await response.json().catch(() => ({ message: 'Erro desconhecido no servidor.' }));
            throw new Error(`Erro ${response.status}: ${errData.message || response.statusText}`);
        }

        const data = await response.json();

        // PROCESSA A RESPOSTA E ATUALIZA A UI
        if (isMetricsOnly) {
            metricsContainer.innerHTML = `<div class="metric-section"><h4>Métricas Analíticas</h4>${buildMetricsHTML(data.metrics.summary)}</div>`;
            metricsContainer.style.display = 'block';
        } else if (data.image) {
            const widthCm = parseFloat(document.getElementById('bgXsize').value);
            const heightCm = parseFloat(document.getElementById('bgYsize').value);
            imgElement.style.width = `${widthCm * 37.8}px`;
            imgElement.style.height = `${heightCm * 37.8}px`;
            imgElement.src = `data:image/png;base64,${data.image}`;
            imgElement.style.display = 'block';
            metricsContainer.innerHTML = `<div class="metric-section"><h4>Métricas Analíticas</h4>${buildMetricsHTML(data.metrics.summary)}</div>`;
            metricsContainer.style.display = 'block';
        } else {
            throw new Error('Resposta inválida do servidor.');
        }

        displayMessage('Processado com sucesso!', 'success');

    } catch (error) {
        // TRATAMENTO DE ERROS
        clearTimeout(timeoutId); // Limpa o timeout em caso de erro também

        if (error.name === 'AbortError') {
            displayMessage('A requisição demorou muito para responder. Por favor, tente com um intervalo de tempo menor.', 'error');
        } else {
            displayMessage(error.message, 'error');
        }
    } finally {
        // RESTAURA A UI AO ESTADO INICIAL
        spinner.style.display = 'none';
        buttonText.textContent = originalButtonText;
        button.disabled = false;
    }
}

function generateBgPlot() {
    handleRequest(false); // Chama o handler para gerar o plot
}

function generateMetricsOnly() {
    handleRequest(true); // Chama o handler para gerar apenas as métricas
}