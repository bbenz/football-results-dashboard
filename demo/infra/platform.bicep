targetScope = 'resourceGroup'

param location string = resourceGroup().location
param projectTag string
param eventDateTag string
param teardownDateTag string
param acrName string
param storageAccountName string
param foundryAccountName string
param appInsightsName string
param operatorPrincipalId string
param aksWebIdentityName string
param aksInsightsIdentityName string
param aksIngestIdentityName string
param acaWebIdentityName string
param acaInsightsIdentityName string
param acaIngestIdentityName string

var tags = {
  project: projectTag
  'event-date': eventDateTag
  'teardown-date': teardownDateTag
}

// Role IDs source: https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles
var foundryUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
var storageBlobDataReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')
var storageBlobDataContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var monitoringMetricsPublisherRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '3913510d-42f4-4e42-8a64-420c390055eb')

resource registry 'Microsoft.ContainerRegistry/registries@2025-05-01-preview' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
    publicNetworkAccess: 'Enabled'
    networkRuleBypassOptions: 'AzureServices'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-01-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource rawContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: 'raw'
  properties: {
    publicAccess: 'None'
  }
}

resource curatedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: 'curated'
  properties: {
    publicAccess: 'None'
  }
}

resource foundry 'Microsoft.CognitiveServices/accounts@2026-07-01' existing = {
  name: foundryAccountName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

var identityNames = [
  aksWebIdentityName
  aksInsightsIdentityName
  aksIngestIdentityName
  acaWebIdentityName
  acaInsightsIdentityName
  acaIngestIdentityName
]

resource identities 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = [for name in identityNames: {
  name: name
  location: location
  tags: tags
}]

var webIdentityIndexes = [0, 3]
var insightsIdentityIndexes = [1, 4]
var ingestIdentityIndexes = [2, 5]
var acaIdentityIndexes = [3, 4, 5]

resource webMetricsAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in webIdentityIndexes: {
  name: guid(appInsights.id, identityNames[i], monitoringMetricsPublisherRoleId)
  scope: appInsights
  properties: {
    roleDefinitionId: monitoringMetricsPublisherRoleId
    principalId: identities[i].properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource insightsFoundryAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in insightsIdentityIndexes: {
  name: guid(foundry.id, identityNames[i], foundryUserRoleId)
  scope: foundry
  properties: {
    roleDefinitionId: foundryUserRoleId
    principalId: identities[i].properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource insightsCuratedReadAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in insightsIdentityIndexes: {
  name: guid(curatedContainer.id, identityNames[i], storageBlobDataReaderRoleId)
  scope: curatedContainer
  properties: {
    roleDefinitionId: storageBlobDataReaderRoleId
    principalId: identities[i].properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource insightsMetricsAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in insightsIdentityIndexes: {
  name: guid(appInsights.id, identityNames[i], monitoringMetricsPublisherRoleId)
  scope: appInsights
  properties: {
    roleDefinitionId: monitoringMetricsPublisherRoleId
    principalId: identities[i].properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource ingestRawReadAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in ingestIdentityIndexes: {
  name: guid(rawContainer.id, identityNames[i], storageBlobDataReaderRoleId)
  scope: rawContainer
  properties: {
    roleDefinitionId: storageBlobDataReaderRoleId
    principalId: identities[i].properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource ingestCuratedWriteAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in ingestIdentityIndexes: {
  name: guid(curatedContainer.id, identityNames[i], storageBlobDataContributorRoleId)
  scope: curatedContainer
  properties: {
    roleDefinitionId: storageBlobDataContributorRoleId
    principalId: identities[i].properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource ingestMetricsAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in ingestIdentityIndexes: {
  name: guid(appInsights.id, identityNames[i], monitoringMetricsPublisherRoleId)
  scope: appInsights
  properties: {
    roleDefinitionId: monitoringMetricsPublisherRoleId
    principalId: identities[i].properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource acaAcrPullAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for i in acaIdentityIndexes: {
  name: guid(registry.id, identityNames[i], acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: identities[i].properties.principalId
    principalType: 'ServicePrincipal'
  }
}]

resource operatorRawContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(rawContainer.id, operatorPrincipalId, storageBlobDataContributorRoleId)
  scope: rawContainer
  properties: {
    roleDefinitionId: storageBlobDataContributorRoleId
    principalId: operatorPrincipalId
    principalType: 'User'
  }
}

output registryLoginServer string = registry.properties.loginServer
output storageBlobEndpoint string = storage.properties.primaryEndpoints.blob
output aksWebClientId string = identities[0].properties.clientId
output aksInsightsClientId string = identities[1].properties.clientId
output aksIngestClientId string = identities[2].properties.clientId
output acaWebClientId string = identities[3].properties.clientId
output acaInsightsClientId string = identities[4].properties.clientId
output acaIngestClientId string = identities[5].properties.clientId
output aksWebIdentityId string = identities[0].id
output aksInsightsIdentityId string = identities[1].id
output aksIngestIdentityId string = identities[2].id
output acaWebIdentityId string = identities[3].id
output acaInsightsIdentityId string = identities[4].id
output acaIngestIdentityId string = identities[5].id
output identityResourceIds array = [for i in range(0, 6): identities[i].id]
