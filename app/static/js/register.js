document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('imageDropZone');
    const fileInput = document.getElementById('imageUpload');
    const preview = document.getElementById('imagePreview');
    const form = document.getElementById('cameraRegistrationForm');

    // Gerenciar drag and drop
    dropZone.addEventListener('click', () => fileInput.click());
    
    fileInput.addEventListener('change', handleFileSelect);
    dropZone.addEventListener('dragover', handleDragOver);
    dropZone.addEventListener('drop', handleFileDrop);

    // Envio do formulário
    form.addEventListener('submit', handleFormSubmit);

    function handleFileSelect(e) {
        const file = e.target.files[0];
        if (file && validateFile(file)) { 
            showPreview(file);
        }
    }
    
    function handleFileDrop(e) {
        e.preventDefault();
        const file = e.dataTransfer.files[0];
        if (file && validateFile(file)) {
            fileInput.files = e.dataTransfer.files;
            showPreview(file);
        }
        dropZone.classList.remove('drag-over');
    }
    
    function handleDragOver(e) {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    }
    
    function validateFile(file) {
        const validTypes = ['image/jpeg', 'image/png'];
        const maxSize = 5 * 1024 * 1024;

        if (!file) {
            alert('Nenhum arquivo selecionado');
            return false;
        }
    
        if (!validTypes.includes(file.type)) {
            alert('Formato de arquivo inválido! Use JPG ou PNG.');
            return false;
        }
    
        if (file.size > maxSize) {
            alert('Arquivo muito grande! Tamanho máximo: 5MB');
            return false;
        }
        
        return true;
    }

    function showPreview(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.innerHTML = `<img src="${e.target.result}" alt="Pré-visualização">`;
        }
        reader.readAsDataURL(file);
    }

    async function handleFormSubmit(e) {
        e.preventDefault();

        const cameraName = document.getElementById('cameraName').value.trim();
        const file = fileInput.files[0];

        if (!cameraName || !file) {
            alert('Por favor, insira o nome da câmera e selecione uma imagem.');
            return;
        }
    
        const formData = new FormData();
        formData.append('name', cameraName);
        formData.append('image', file);

        try {
            // Exemplo de envio para o Flask
            const response = await fetch('/register_camera', {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                alert('Câmera cadastrada com sucesso!');
                form.reset();
                preview.innerHTML = '';
            }
        } catch (error) {
            console.error('Erro:', error);
        }
    }
});
