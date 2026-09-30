targetScope = 'resourceGroup'

@description('Location for regional resources.')
param location string = resourceGroup().location

@description('Project tag value shared by every resource.')
param projectTag string

@description('Event date tag value.')
param eventDateTag string

@description('Teardown date tag value.')
param teardownDateTag string

@description('Microsoft Foundry account name and custom subdomain.')
param foundryAccountName string

@description('Microsoft Foundry project name.')
param foundryProjectName string

@description('Log Analytics workspace name.')
param logAnalyticsName string

@description('Application Insights component name.')
param appInsightsName string

@description('Operator Microsoft Entra object ID.')
param operatorPrincipalId string

@description('Monthly budget amount in USD.')
param budgetAmount int = 100

@description('Budget alert recipient email address.')
param budgetContactEmail string

@description('Budget start date in yyyy-MM-01 format.')
param budgetStartDate string

@description('gpt-6-astra deployment capacity.')
param gpt6AstraCapacity int = 100

@description('gpt-6-sol deployment capacity.')
param gpt6SolCapacity int = 100

var tags = {
  project: projectTag
  'event-date': eventDateTag
  'teardown-date': teardownDateTag
}

var foundryUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
// Role ID source: https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/monitor
var monitoringMetricsPublisherRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '3913510d-42f4-4e42-8a64-420c390055eb')

resource foundry 'Microsoft.CognitiveServices/accounts@2026-07-01' = {
  name: foundryAccountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: foundryAccountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2026-07-01' = {
  parent: foundry
  name: foundryProjectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

resource astraDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-07-01' = {
  parent: foundry
  name: 'gpt-6-astra'
  sku: {
    name: 'GlobalStandard'
    capacity: gpt6AstraCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-6-astra'
      version: '2026-09-03'
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource solDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-07-01' = {
  parent: foundry
  name: 'gpt-6-sol'
  sku: {
    name: 'GlobalStandard'
    capacity: gpt6SolCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-6-sol'
      version: '2026-09-22'
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
  dependsOn: [
    astraDeployment
  ]
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-02-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    DisableLocalAuth: true
  }
}

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: '${projectTag}-monthly'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
    }
    notifications: {
      Actual50: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        contactEmails: [ budgetContactEmail ]
        thresholdType: 'Actual'
      }
      Actual80: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        contactEmails: [ budgetContactEmail ]
        thresholdType: 'Actual'
      }
      Actual100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        contactEmails: [ budgetContactEmail ]
        thresholdType: 'Actual'
      }
      Forecast100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        contactEmails: [ budgetContactEmail ]
        thresholdType: 'Forecasted'
      }
    }
  }
}

resource operatorFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, operatorPrincipalId, foundryUserRoleId)
  scope: foundry
  properties: {
    roleDefinitionId: foundryUserRoleId
    principalId: operatorPrincipalId
    principalType: 'User'
  }
}

resource operatorMetricsPublisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appInsights.id, operatorPrincipalId, monitoringMetricsPublisherRoleId)
  scope: appInsights
  properties: {
    roleDefinitionId: monitoringMetricsPublisherRoleId
    principalId: operatorPrincipalId
    principalType: 'User'
  }
}

output foundryAccountId string = foundry.id
output foundryProjectId string = foundryProject.id
output foundryProjectEndpoint string = 'https://${foundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}'
output logAnalyticsWorkspaceId string = workspace.id
output applicationInsightsId string = appInsights.id
output applicationInsightsConnectionString string = appInsights.properties.ConnectionString
