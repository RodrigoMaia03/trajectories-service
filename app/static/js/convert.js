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
        // Estado de carregamento
        submitButton.disabled = true;
        submitButton.querySelector('.upload-text').style.display = 'none';
        submitButton.querySelector('.spinner-border').style.display = 'inline-block';
        progressBar.style.display = 'block';
        
        // Envio da requisição
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });
        
        // Tratamento de erros do backend
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message);
        }
        
        // Processamento do sucesso
        const resposeJson = await response.json();

        document.getElementById('filePreview').innerHTML = `
            <div class="alert alert-success mt-3">
                ${resposeJson.message}
            </div>
        `;
    } catch (error) {
        console.error('Erro na conversão:', error);
        
        const errorMessage = error.message.includes('não cadastrada') ? 
            `${error.message}<br><a href="/cam" class="alert-link">Cadastrar câmera</a>` : 
            error.message;

        document.getElementById('filePreview').innerHTML = `
            <div class="alert alert-danger mt-3">
                ${errorMessage}
            </div>
        `;
    } finally {
        // Restaura estado normal
        submitButton.disabled = false;
        submitButton.querySelector('.upload-text').style.display = 'inline';
        submitButton.querySelector('.spinner-border').style.display = 'none';
        progressBar.style.display = 'none';
        progressFill.style.width = '0%';
        form.reset();

        // Adiciona ao histórico
        const historyItem = document.createElement('div');
        historyItem.className = 'alert alert-light mb-2';
        historyItem.textContent = `✉️ ${file.name} - ${new Date().toLocaleTimeString()}`;
        document.getElementById('conversionHistory').prepend(historyItem);
    }
});