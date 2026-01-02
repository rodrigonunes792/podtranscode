#!/bin/bash
# Deploy PodTranscode to Azure Web App for Containers with persistent storage
# Usage: OPENAI_API_KEY=sk-xxx ./deploy-webapp.sh

set -e

# Configuracoes
RESOURCE_GROUP="podtranscode-rg"
LOCATION="eastus"
APP_NAME="listenup-app"
ACR_NAME="podtranscodeacr3415"
APP_SERVICE_PLAN="listenup-plan"
STORAGE_ACCOUNT="listenupdata$(date +%s | tail -c 5)"

echo "=========================================="
echo "  Deploy ListenUp - Azure Web App"
echo "  (com armazenamento persistente)"
echo "=========================================="

# Verificar OPENAI_API_KEY
if [ -z "$OPENAI_API_KEY" ]; then
    echo ""
    echo "OPENAI_API_KEY nao definida!"
    read -p "Digite sua OpenAI API Key: " OPENAI_API_KEY
fi

# Login check
echo ""
echo "Verificando login Azure..."
az account show &> /dev/null || az login

# Build da imagem no ACR
echo ""
echo "Construindo imagem Docker..."
az acr build --registry $ACR_NAME --image listenup:latest --file Dockerfile .

# Obter credenciais do ACR
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

# Criar Storage Account para persistencia
echo ""
echo "Criando Storage Account para dados..."
az storage account create \
    --name $STORAGE_ACCOUNT \
    --resource-group $RESOURCE_GROUP \
    --location $LOCATION \
    --sku Standard_LRS \
    -o none 2>/dev/null || echo "Storage ja existe"

# Obter connection string
STORAGE_CONNECTION=$(az storage account show-connection-string \
    --name $STORAGE_ACCOUNT \
    --resource-group $RESOURCE_GROUP \
    --query connectionString -o tsv)

# Criar File Share para cache
echo ""
echo "Criando File Share..."
az storage share create \
    --name listenup-data \
    --connection-string "$STORAGE_CONNECTION" \
    -o none 2>/dev/null || echo "Share ja existe"

# Obter Storage Key
STORAGE_KEY=$(az storage account keys list \
    --account-name $STORAGE_ACCOUNT \
    --resource-group $RESOURCE_GROUP \
    --query "[0].value" -o tsv)

# Criar App Service Plan (Linux)
echo ""
echo "Criando App Service Plan..."
az appservice plan create \
    --name $APP_SERVICE_PLAN \
    --resource-group $RESOURCE_GROUP \
    --is-linux \
    --sku B1 \
    -o none 2>/dev/null || echo "Plan ja existe"

# Criar Web App
echo ""
echo "Criando Web App..."
az webapp create \
    --name $APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --plan $APP_SERVICE_PLAN \
    --container-image-name "${ACR_LOGIN_SERVER}/listenup:latest" \
    --container-registry-url "https://${ACR_LOGIN_SERVER}" \
    --container-registry-user $ACR_USERNAME \
    --container-registry-password $ACR_PASSWORD \
    -o none 2>/dev/null || echo "App ja existe, atualizando..."

# Configurar variaveis de ambiente
echo ""
echo "Configurando variaveis de ambiente..."
az webapp config appsettings set \
    --name $APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --settings \
        OPENAI_API_KEY="$OPENAI_API_KEY" \
        WEBSITES_PORT=8080 \
    -o none

# Configurar montagem de storage (cache persistente)
echo ""
echo "Configurando armazenamento persistente..."
az webapp config storage-account add \
    --name $APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --custom-id listenupdata \
    --storage-type AzureFiles \
    --share-name listenup-data \
    --account-name $STORAGE_ACCOUNT \
    --access-key "$STORAGE_KEY" \
    --mount-path /app/cache \
    -o none 2>/dev/null || echo "Storage mount ja existe"

# Atualizar container
echo ""
echo "Atualizando container..."
az webapp config container set \
    --name $APP_NAME \
    --resource-group $RESOURCE_GROUP \
    --container-image-name "${ACR_LOGIN_SERVER}/listenup:latest" \
    --container-registry-url "https://${ACR_LOGIN_SERVER}" \
    --container-registry-user $ACR_USERNAME \
    --container-registry-password $ACR_PASSWORD \
    -o none

# Reiniciar
echo ""
echo "Reiniciando app..."
az webapp restart --name $APP_NAME --resource-group $RESOURCE_GROUP

# URL
APP_URL="https://${APP_NAME}.azurewebsites.net"

echo ""
echo "=========================================="
echo "  Deploy concluido!"
echo "=========================================="
echo ""
echo "URL: $APP_URL"
echo ""
echo "Dados persistentes em: Azure Files (listenup-data)"
echo ""
echo "Para ver logs:"
echo "  az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "Para remover tudo:"
echo "  az group delete --name $RESOURCE_GROUP --yes"
echo ""
