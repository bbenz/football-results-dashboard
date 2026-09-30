targetScope = 'resourceGroup'

param location string = resourceGroup().location
param projectTag string
param eventDateTag string
param teardownDateTag string
param aksClusterName string
param kubernetesVersion string = '1.36'
param acrName string
param aksWebIdentityName string
param aksInsightsIdentityName string
param aksIngestIdentityName string
param operatorPrincipalId string

var tags = {
  project: projectTag
  'event-date': eventDateTag
  'teardown-date': teardownDateTag
}

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var aksRbacClusterAdminRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b1ff04bb-8a4e-4dc4-8eb5-8693973ce19b')

// AKS Automatic upgrades the cluster (stable channel) and node images automatically. Planned maintenance keeps
// both upgrades out of the days around the event: https://learn.microsoft.com/en-us/azure/aks/planned-maintenance
var upgradeFreeze = {
  start: dateTimeAdd('${eventDateTag}T00:00:00Z', '-P3D', 'yyyy-MM-dd')
  end: dateTimeAdd('${eventDateTag}T00:00:00Z', 'P1D', 'yyyy-MM-dd')
}
var maintenanceWindow = {
  schedule: {
    weekly: {
      intervalWeeks: 1
      dayOfWeek: 'Sunday'
    }
  }
  durationHours: 4
  startTime: '02:00'
  utcOffset: '+00:00'
  notAllowedDates: [ upgradeFreeze ]
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-05-01-preview' existing = {
  name: acrName
}

resource aksWeb 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = { name: aksWebIdentityName }
resource aksInsights 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = { name: aksInsightsIdentityName }
resource aksIngest 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = { name: aksIngestIdentityName }

// AKS Automatic Bicep shape follows the Automatic quickstart: https://learn.microsoft.com/en-us/azure/aks/automatic/quick-automatic-managed-network
// New Automatic clusters on 1.36+ already use the application routing Gateway API implementation; the ingress
// profile states it explicitly so the approuting-istio GatewayClass never depends on a default:
// https://learn.microsoft.com/en-us/azure/aks/app-routing-gateway-api
resource cluster 'Microsoft.ContainerService/managedClusters@2026-05-01' = {
  name: aksClusterName
  location: location
  tags: tags
  sku: {
    name: 'Automatic'
    tier: 'Standard'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    dnsPrefix: aksClusterName
    kubernetesVersion: kubernetesVersion
    enableRBAC: true
    oidcIssuerProfile: {
      enabled: true
    }
    securityProfile: {
      workloadIdentity: {
        enabled: true
      }
    }
    networkProfile: {
      networkPlugin: 'azure'
      networkPluginMode: 'overlay'
      networkPolicy: 'cilium'
      networkDataplane: 'cilium'
      outboundType: 'managedNATGateway'
    }
    ingressProfile: {
      gatewayAPI: {
        installation: 'Standard'
      }
      webAppRouting: {
        enabled: true
        gatewayAPIImplementations: {
          appRoutingIstio: {
            mode: 'Enabled'
          }
        }
      }
    }
  }
}

resource kubeletAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, aksClusterName, 'kubelet', acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: cluster.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
  }
}

// AKS Automatic uses Microsoft Entra ID with Azure RBAC for Kubernetes. The CLI grants the creator this role
// automatically; a Bicep deployment does not, so the operator gets it explicitly to run kubectl.
resource operatorClusterAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cluster.id, operatorPrincipalId, aksRbacClusterAdminRoleId)
  scope: cluster
  properties: {
    roleDefinitionId: aksRbacClusterAdminRoleId
    principalId: operatorPrincipalId
    principalType: 'User'
  }
}

resource webFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  name: 'football-web'
  parent: aksWeb
  properties: {
    audiences: [ 'api://AzureADTokenExchange' ]
    issuer: cluster.properties.oidcIssuerProfile.issuerURL
    subject: 'system:serviceaccount:football:web'
  }
}

resource insightsFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  name: 'football-insights'
  parent: aksInsights
  properties: {
    audiences: [ 'api://AzureADTokenExchange' ]
    issuer: cluster.properties.oidcIssuerProfile.issuerURL
    subject: 'system:serviceaccount:football:insights'
  }
}

resource ingestFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  name: 'football-ingest'
  parent: aksIngest
  properties: {
    audiences: [ 'api://AzureADTokenExchange' ]
    issuer: cluster.properties.oidcIssuerProfile.issuerURL
    subject: 'system:serviceaccount:football:ingest'
  }
}

resource autoUpgradeSchedule 'Microsoft.ContainerService/managedClusters/maintenanceConfigurations@2026-05-01' = {
  parent: cluster
  name: 'aksManagedAutoUpgradeSchedule'
  properties: {
    maintenanceWindow: maintenanceWindow
  }
}

resource nodeOsUpgradeSchedule 'Microsoft.ContainerService/managedClusters/maintenanceConfigurations@2026-05-01' = {
  parent: cluster
  name: 'aksManagedNodeOSUpgradeSchedule'
  properties: {
    maintenanceWindow: maintenanceWindow
  }
}

output clusterName string = cluster.name
output oidcIssuer string = cluster.properties.oidcIssuerProfile.issuerURL
