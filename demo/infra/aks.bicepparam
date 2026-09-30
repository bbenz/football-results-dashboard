using './aks.bicep'

param location = readEnvironmentVariable('AZURE_LOCATION')
param projectTag = readEnvironmentVariable('PROJECT_TAG')
param eventDateTag = readEnvironmentVariable('EVENT_DATE')
param teardownDateTag = readEnvironmentVariable('TEARDOWN_DATE')
param aksClusterName = readEnvironmentVariable('AKS_CLUSTER_NAME')
param kubernetesVersion = readEnvironmentVariable('AKS_KUBERNETES_VERSION')
param acrName = readEnvironmentVariable('ACR_NAME')
param aksWebIdentityName = readEnvironmentVariable('AKS_WEB_IDENTITY_NAME')
param aksInsightsIdentityName = readEnvironmentVariable('AKS_INSIGHTS_IDENTITY_NAME')
param aksIngestIdentityName = readEnvironmentVariable('AKS_INGEST_IDENTITY_NAME')
param operatorPrincipalId = readEnvironmentVariable('OPERATOR_PRINCIPAL_ID')
