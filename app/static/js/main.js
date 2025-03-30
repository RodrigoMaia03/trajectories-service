const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const form = document.getElementById('conversionForm');
const progressFill = document.querySelector('.progress-fill');
const progressBar = document.querySelector('.progress-bar');
const submitButton = form.querySelector('button');

// Handlers para Drag and Drop
dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
});

// Handler para seleção de arquivo
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
    }
});

// Manipulação do arquivo selecionado
function handleFile(file) {
    if (file.type !== 'text/plain') {
        alert('Por favor, selecione um arquivo TXT válido.');
        return;
    }

    // Atualiza interface
    document.getElementById('filePreview').innerHTML = `
        <div class="alert alert-info">
            Arquivo selecionado: <strong>${file.name}</strong><br>
            Tamanho: ${(file.size / 1024).toFixed(2)} KB
        </div>
    `;

    // Adiciona ao histórico
    const historyItem = document.createElement('div');
    historyItem.className = 'alert alert-light mb-2';
    historyItem.textContent = `✉️ ${file.name} - ${new Date().toLocaleTimeString()}`;
    document.getElementById('conversionHistory').prepend(historyItem);
}

// Envio do formulário
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const file = fileInput.files[0];
    const camera = document.getElementById('cameraInput').value;
    const endpoint = document.getElementById('conversionType').value;

    if (!file || !camera) {
        alert('Por favor, selecione um arquivo e insira o nome da câmera.');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('camera', camera);

    try {
        // Mostra loading
        submitButton.disabled = true;
        submitButton.querySelector('.upload-text').style.display = 'none';
        submitButton.querySelector('.spinner-border').style.display = 'inline-block';
        progressBar.style.display = 'block';

        // Envia arquivo
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(await response.text());
        }

        // Download automático do JSON
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = file.name.replace('.txt', '_converted.json');
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);

        // Atualiza interface
        document.getElementById('filePreview').innerHTML += `
            <div class="alert alert-success mt-3">
                Conversão concluída com sucesso!
            </div>
        `;

    } catch (error) {
        console.error('Erro na conversão:', error);
        document.getElementById('filePreview').innerHTML += `
            <div class="alert alert-danger mt-3">
                Erro na conversão: ${error.message}
            </div>
        `;
    } finally {
        // Reseta interface
        submitButton.disabled = false;
        submitButton.querySelector('.upload-text').style.display = 'inline';
        submitButton.querySelector('.spinner-border').style.display = 'none';
        progressBar.style.display = 'none';
        progressFill.style.width = '0%';
        form.reset();
    }
});

// Atualiza controles visuais
function updatePlotControls() {
    const plotType = document.getElementById('plotType').value;
    document.getElementById('categoryField').style.display = 
        (plotType === '/plot_trajectories_one_category') ? 'block' : 'none';
}

// Converte timepicker para float
function timeToFloat(timeString) {
    const [hours, minutes] = timeString.split(':');
    return parseFloat(hours) + (parseFloat(minutes)/60);
}

// Gera a plotagem
async function generatePlot() {
    // 1. Capturar elementos do botão
    const button = document.querySelector('button[onclick="generatePlot()"]');
    const spinner = button.querySelector('.spinner-border');
    const buttonText = button.querySelector('.upload-text');

    try {
        // 2. Estado de loading
        button.disabled = true;
        spinner.style.display = 'inline-block';
        buttonText.textContent = ' Processando...';

        // Parâmetros existentes
        const params = new URLSearchParams({
            camera: document.getElementById('plotCamera').value,
            selectedDate: document.getElementById('plotDate').value,
            startTime: timeToFloat(document.getElementById('plotStartTime').value),
            endTime: timeToFloat(document.getElementById('plotEndTime').value),
            xsize: document.getElementById('plotXsize').value,
            ysize: document.getElementById('plotYsize').value,
            xlim1: document.getElementById('plotXlim1').value,
            xlim2: document.getElementById('plotXlim2').value,
            ylim1: document.getElementById('plotYlim1').value,
            ylim2: document.getElementById('plotYlim2').value
        });

        // Adiciona categoria se necessário
        const plotType = document.getElementById('plotType').value;
        if(plotType === '/plot_trajectories_one_category') {
            params.append('category', document.getElementById('plotCategory').value);
        }

        const response = await fetch(`${plotType}?${params}`);
        
        if(!response.ok) {
            throw new Error(await response.text());
        }

        // Atualização da imagem
        const imageBlob = await response.blob();
        const imageUrl = URL.createObjectURL(imageBlob);
        const imgElement = document.getElementById('plotImage');
        imgElement.style.display = 'block';
        imgElement.src = imageUrl;

    } catch (error) {
        alert(`Erro na geração do plot: ${error.message}`);
    } finally {
        // 3. Restaura estado original
        button.disabled = false;
        spinner.style.display = 'none';
        buttonText.textContent = 'Gerar Plotagem';
    }
}        

// Atualiza preview em tempo real (opcional - pode ser ativado)
document.querySelectorAll('#plotPreview input, #plotPreview select').forEach(element => {
    element.addEventListener('change', () => {
        if(document.getElementById('plotImage').src) {
            generatePlot();
        }
    });
});

// Controles Dinâmicos
function updateBgPlotControls() {
    const plotType = document.getElementById('plotBackgroundType').value;
    const dynamicElements = {
        '/plot_one_category': ['bgCategoryField'],
        '/plot_with_limits': ['bgCategoryField', 'bgReferenceLineField'],
        '/plot_start_finish': ['bgCategoryField', 'bgStartFinishField', 'bgDepartureField'],
        '/plot_with_stopped': ['bgCategoryField']
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
            'bgXlim1', 'bgXlim2', 'bgYlim1', 'bgYlim2',
            'bgMinX', 'bgMaxX', 'bgMinY', 'bgMaxY'

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
            else if (id.match(/(Min|Max|lim|size)/i)) { // Captura campos numéricos
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
            '/plot_with_stopped': ['bgCategory']
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
                if (!formData.get('category')) {
                    throw new Error('Selecione uma categoria!');
                }
                break;
        }

        // Validação de limites numéricos
        const boundsFields = ['min_x', 'max_x', 'min_y', 'max_y'];
        boundsFields.forEach(field => {
            const value = formData.get(field);
            if (value && (isNaN(value) || value < 0)) {
                throw new Error(`Valor inválido para ${field.replace('_', ' ').toUpperCase()}`);
            }
        });

        // Processamento de arquivo de imagem
        const imageFile = document.getElementById('bgImageUpload').files[0];
        if (imageFile) {
            formData.append('background_image', imageFile);
        }

        // Envio da requisição
        fetch(plotType, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) throw response;
            return response.json();  // Assume que o back-end retorna JSON
        })
        .then(data => {
            if (data.image) {
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
                alert(`Erro ${error.status}: ${err.error}`);
            } else {
                alert(error.message);
            }
        })
        .finally(() => {
            spinner.style.display = 'none';
            buttonText.textContent = 'Gerar Plot com Background';
            button.disabled = false;
        });

    } catch (error) {
        alert(error.message);
        spinner.style.display = 'none';
        buttonText.textContent = 'Gerar Plot com Background';
        button.disabled = false;
    }
}