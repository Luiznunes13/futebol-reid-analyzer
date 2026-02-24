#!/bin/bash

echo "🚀 Instalando dependências do projeto Terça Nobre..."
echo ""

# Verifica se está usando pyenv
if command -v pyenv &> /dev/null; then
    echo "✓ pyenv detectado"
    echo "Usando ambiente: $(pyenv version-name)"
else
    echo "⚠️  pyenv não detectado - usando Python do sistema"
fi

# Atualiza pip
echo ""
echo "📦 Atualizando pip..."
python -m pip install --upgrade pip

# Instala dependências
echo ""
echo "📦 Instalando dependências..."
pip install -r requirements.txt

# Verifica instalação
echo ""
echo "🔍 Verificando instalação..."
python -c "import cv2; import torch; from ultralytics import YOLO; import flask; print('✓ Todas as dependências principais instaladas!')"

echo ""
echo "✅ Instalação concluída!"
echo ""
echo "Para iniciar o sistema:"
echo "  python app_times.py"
echo ""
echo "Acesse: http://localhost:5001"
