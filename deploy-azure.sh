#!/bin/bash
# Deploy PodTranscode to Azure Container Apps (Consumption plan)
# Usage: ./deploy-azure.sh

set -e

# ============================================
# CONFIGURAÇÕES - ALTERE CONFORME NECESSÁRIO
# ============================================
RESOURCE_GROUP="podtranscode-rg"
LOCATION="eastus"  # Região mais barata geralmente
CONTAINER_APP_NAME="podtranscode"
CONTAINER_ENV_NAME="podtranscode-env"
ACR_NAME="podtranscodeacr$(date +%s | tail -c 5)"  # Nome único para o registry

echo "=========================================="
echo "  Deploy PodTranscode - Azure Container Apps"
echo "=========================================="

# Verificar se Azure CLI está instalado
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI não encontrado. Instale com: brew install azure-cli"
    exit 1
fi

# Login na Azure (se necessário)
echo ""
echo "📝 Verificando login na Azure..."
az account show &> /dev/null || az login

# Mostrar conta atual
echo ""
echo "📋 Conta Azure atual:"
az account show --query "{Nome:name, ID:id}" -o table

echo ""
read -p "Continuar com esta conta? (s/n): " confirm
if [[ $confirm != "s" && $confirm != "S" ]]; then
    echo "Abortando. Use 'az account set --subscription <ID>' para trocar de conta."
    exit 1
fi

# Criar Resource Group
echo ""
echo "📁 Criando Resource Group: $RESOURCE_GROUP..."
az group create --name $RESOURCE_GROUP --location $LOCATION -o none

# Criar Azure Container Registry
echo ""
echo "🐳 Criando Container Registry: $ACR_NAME..."
az acr create \
    --resource-group $RESOURCE_GROUP \
    --name $ACR_NAME \
    --sku Basic \
    --admin-enabled true \
    -o none

# Obter credenciais do ACR
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

# Build e Push da imagem Docker
echo ""
echo "🔨 Construindo e enviando imagem Docker..."
az acr build \
    --registry $ACR_NAME \
    --image podtranscode:latest \
    --file Dockerfile \
    .

# Criar Container Apps Environment
echo ""
echo "🌐 Criando Container Apps Environment..."
az containerapp env create \
    --name $CONTAINER_ENV_NAME \
    --resource-group $RESOURCE_GROUP \
    --location $LOCATION \
    -o none

# Verificar se OPENAI_API_KEY está definida
if [ -z "$OPENAI_API_KEY" ]; then
    echo ""
    echo "⚠️  OPENAI_API_KEY não está definida!"
    read -p "Digite sua OpenAI API Key: " OPENAI_API_KEY
fi

# Criar Container App
echo ""
echo "🚀 Criando Container App..."
az containerapp create \
    --name $CONTAINER_APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --environment $CONTAINER_ENV_NAME \
    --image "${ACR_LOGIN_SERVER}/podtranscode:latest" \
    --registry-server $ACR_LOGIN_SERVER \
    --registry-username $ACR_USERNAME \
    --registry-password $ACR_PASSWORD \
    --target-port 8080 \
    --ingress external \
    --cpu 1 \
    --memory 2.0Gi \
    --min-replicas 0 \
    --max-replicas 1 \
    --scale-rule-name http-scaling \
    --scale-rule-type http \
    --scale-rule-http-concurrency 10 \
    --env-vars "OPENAI_API_KEY=$OPENAI_API_KEY" \
    -o none

# Obter URL da aplicação
APP_URL=$(az containerapp show \
    --name $CONTAINER_APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --query properties.configuration.ingress.fqdn \
    -o tsv)

echo ""
echo "=========================================="
echo "  ✅ Deploy concluído com sucesso!"
echo "=========================================="
echo ""
echo "🌐 URL da aplicação: https://$APP_URL"
echo ""
echo "📊 Para ver os logs:"
echo "   az containerapp logs show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP --follow"
echo ""
echo "🗑️  Para remover tudo (se quiser):"
echo "   az group delete --name $RESOURCE_GROUP --yes --no-wait"
echo ""
echo "💰 Custo estimado:"
echo "   - Container Apps: ~\$0 quando ocioso (escala para 0)"
echo "   - Container Registry: ~\$5/mês (Basic tier)"
echo "   - Processamento: ~\$0.000012/vCPU-segundo quando ativo"
echo ""
