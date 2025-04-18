// Controles Dinâmicos
function updateBgPlotControls() {
    const plotType = document.getElementById('plotBackgroundType').value;
    const dynamicElements = {
        '/plot_one_category': ['bgCategoryField'],
        '/plot_with_limits': ['bgCategoryField', 'bgReferenceLineField'],
        '/plot_start_finish': ['bgCategoryField', 'bgStartFinishField', 'bgDepartureField'],
        '/plot_with_stopped': ['bgCategoryField', 'bgStopThresholdField', 'bgMinDurationField', 'bgNoiseToleranceField'],
        '/plot_with_stop_rec': ['bgCategoryField', 'bgStopThresholdField', 'bgMinDurationField', 'bgNoiseToleranceField',
                'bgRectMinXField', 'bgRectMaxXField', 'bgRectMinYField', 'bgRectMaxYField']
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

function convertTimeToFloat(timeStr) {
    if (!timeStr) throw new Error("Horário vazio!");
    const [hours, minutes] = timeStr.split(':').map(Number);
    if (isNaN(hours) || hours < 0 || hours >= 24 || isNaN(minutes) || minutes < 0 || minutes >= 60) {
        throw new Error(`Horário inválido: ${timeStr}`);
    }
    return hours + (minutes / 60);
}

function formatFieldName(id) {
    return id.replace('bg', '')
                .replace(/([a-z])([A-Z])/g, '$1_$2')
                .toLowerCase();
}

function generateBgPlot() {
    const button = document.querySelector('button[onclick="generateBgPlot()"]');
    const spinner = button.querySelector('.spinner-border');
    const buttonText = button.querySelector('.upload-text');
    const imgElement = document.getElementById('bgPlotImage');

    button.disabled = true;
    spinner.style.display = 'inline-block';
    buttonText.textContent = 'Processando...';
    imgElement.style.display = 'none';

    try {
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
                'bgRectMinX', 'bgRectMaxX', 'bgRectMinY', 'bgRectMaxY']
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
                else if (!formData.get('rect_min_x'||'rect_max_x'||'rect_min_y'||'rect_max_y')) {
                    throw new Error('Parâmetros de Área obrigatórios!');
                }
                else if (!formData.get('category')) {
                    throw new Error('Selecione uma categoria!');
                }
                break;
        }

        // Captura os valores dos inputs de tamanho da imagem
        const widthCm = parseFloat(document.getElementById('bgXsize').value);
        const heightCm = parseFloat(document.getElementById('bgYsize').value);

        if(widthCm < 1 || heightCm > 50){
            throw new Error('Valor de Altura ou Largura inválido (Mín: 1 e Máx: 50)');
        }

        // Envio da requisição
        fetch(plotType, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) throw response;
            return response.json();
        })
        .then(data => {
            if (data.image) {
                // Define as dimensões da imagem
                imgElement.style.width = `${widthCm * 37.8}px`;
                imgElement.style.height = `${heightCm * 37.8}px`;

                console.log('Parâmetros enviados:', Array.from(formData.entries()));
                imgElement.src = `data:image/png;base64,${data.image}`;
                imgElement.style.display = 'block';
            } else {
                throw new Error('Resposta inválida do servidor');
            }
        })
        .catch(async (error) => {
            if (error instanceof Response) {
                const err = await error.json();
                alert(`Erro ${error.status}: Erro no processamento dos parâmetros`);
            } else {
                alert(error.message);
            }
        })
        .finally(() => {
            spinner.style.display = 'none';
            buttonText.textContent = 'Gerar Plot';
            button.disabled = false;
        });

    } catch (error) {
        alert(error.message);
        spinner.style.display = 'none';
        buttonText.textContent = 'Gerar Plot';
        button.disabled = false;
    }
}